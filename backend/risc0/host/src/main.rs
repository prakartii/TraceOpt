//! Phase 0 host: runs a guest in the RISC Zero executor (or prover) and prints
//! one JSON object with the measurements RISC Zero exposes.
//!
//! Usage: host <execute|prove> <probe|kernel> [word ...]
//!        host verify <probe|kernel> <receipt file> <image ID>   (see `verify`)
//!
//! - `probe`:  Rust-only guest; input is one u32 n (the first word); journal
//!             is the u32 result.
//! - `kernel`: Rust guest calling a C kernel via FFI; input is the kernel's
//!             arguments as u32 words, at most 16 (traceopt/signature.py); journal is
//!             (u64 result bits, u64 cycles spent inside the kernel).
//!
//! `TRACEOPT_SEGMENT_PO2=<k>` caps segments at 2^k cycles. Smaller segments
//! lower prover memory but add per-segment paging, so keep it fixed when
//! comparing variants.
//!
//! `prove` also reports `seal_bytes`, the size of the proof itself (the
//! receipt's seals, without the journal), and `peak_memory_kib`, the host's
//! peak resident memory. `TRACEOPT_RECEIPT=succinct` compresses the
//! per-segment proofs into one constant-size proof (default: `composite`,
//! one proof per segment).
//!
//! `TRACEOPT_RECEIPT_OUT=<path>` saves the receipt (proof plus journal) to
//! that file, for `verify`.
//!
//! `TRACEOPT_KERNEL_ELF=<path>` runs the kernel guest from that program
//! binary (the `kernel.bin` risc0-build writes) instead of the one embedded
//! at build time, so a new kernel variant only needs the guest rebuilt.

use std::time::Instant;

use anyhow::{bail, Context, Result};
use methods::{KERNEL_ELF, KERNEL_ID, PROBE_ELF, PROBE_ID};
use risc0_zkvm::{
    compute_image_id, default_prover, sha::Digest, ExecutorEnv, ExecutorImpl, Journal,
    ProverOpts, SessionStats,
};
use serde_json::{json, Value};

/// Input words the kernel guest reads (its `WORDS`).
const KERNEL_WORDS: usize = 16;

fn decode_output(guest: &str, journal: &Journal) -> Result<Value> {
    Ok(match guest {
        "probe" => {
            let output: u32 = journal.decode()?;
            json!({ "output": output })
        }
        _ => {
            let (output, kernel_cycles): (u64, u64) = journal.decode()?;
            json!({ "output": output, "kernel_cycles": kernel_cycles })
        }
    })
}

fn stats_json(stats: &SessionStats) -> Value {
    json!({
        "segments": stats.segments,
        "total_cycles": stats.total_cycles,
        "user_cycles": stats.user_cycles,
        "paging_cycles": stats.paging_cycles,
        "reserved_cycles": stats.reserved_cycles,
    })
}

/// Peak resident memory of this process in KiB (VmHWM), on Linux.
fn peak_memory_kib() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with("VmHWM:"))?;
    line.split_whitespace().nth(1)?.parse().ok()
}

/// `verify <guest> <receipt file> <image ID>`: what a blockchain's verifier
/// does. It never runs the program: it checks the proof against the image ID
/// of the program that should have run, then reads the answer from the
/// journal. Prints `"valid": false` and exits with 1 if the check fails.
fn verify(args: &[String]) -> Result<()> {
    let [_, _, guest, path, image] = args else {
        bail!("usage: host verify <probe|kernel> <receipt file> <image ID in hex>");
    };
    let image_id = <Digest as hex::FromHex>::from_hex(image)
        .map_err(|e| anyhow::anyhow!("image ID must be 64 hex digits: {e}"))?;
    let bytes = std::fs::read(path).with_context(|| format!("reading {path}"))?;
    let mut report = json!({
        "mode": "verify", "guest": guest, "receipt_file": path,
        "receipt_file_bytes": bytes.len(), "image_id": image,
    });
    let start = Instant::now();
    let checked = bincode::deserialize::<risc0_zkvm::Receipt>(&bytes)
        .map_err(|e| anyhow::anyhow!("not a readable receipt: {e}"))
        .and_then(|receipt| {
            receipt.verify(image_id).map_err(|e| anyhow::anyhow!("{e}"))?;
            Ok(receipt)
        });
    report["verify_seconds"] = json!(start.elapsed().as_secs_f64());
    match checked {
        Ok(receipt) => {
            report["valid"] = json!(true);
            report["seal_bytes"] = json!(receipt.seal_size());
            report["result"] = decode_output(guest, &receipt.journal)?;
            println!("{report}");
            Ok(())
        }
        Err(e) => {
            report["valid"] = json!(false);
            report["error"] = json!(e.to_string());
            println!("{report}");
            std::process::exit(1);
        }
    }
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("execute");
    if mode == "verify" {
        return verify(&args);
    }
    let guest = args.get(2).map(String::as_str).unwrap_or("probe");
    let mut words: Vec<u32> = args[3.min(args.len())..]
        .iter()
        .map(|s| s.parse().context("inputs must be u32 words"))
        .collect::<Result<_>>()?;
    if words.is_empty() {
        words.push(1000); // a kernel without parameters ignores it
    }
    if words.len() > KERNEL_WORDS {
        bail!("at most {KERNEL_WORDS} input words");
    }
    let n = words[0];
    let kernel_path = std::env::var("TRACEOPT_KERNEL_ELF").ok();
    let loaded: Vec<u8>;
    let (elf, id): (&[u8], Digest) = match guest {
        "probe" => (PROBE_ELF, Digest::from(PROBE_ID)),
        "kernel" => match &kernel_path {
            Some(path) => {
                loaded = std::fs::read(path).with_context(|| format!("reading {path}"))?;
                let id = compute_image_id(&loaded).context("computing the image ID")?;
                (&loaded, id)
            }
            None => (KERNEL_ELF, Digest::from(KERNEL_ID)),
        },
        other => bail!("unknown guest {other:?}; expected probe or kernel"),
    };

    let segment_po2: Option<u32> = match std::env::var("TRACEOPT_SEGMENT_PO2") {
        Ok(s) => Some(s.parse().context("TRACEOPT_SEGMENT_PO2 must be a u32")?),
        Err(_) => None,
    };

    let receipt_kind =
        std::env::var("TRACEOPT_RECEIPT").unwrap_or_else(|_| "composite".to_string());

    let mut builder = ExecutorEnv::builder();
    if guest == "probe" {
        builder.write(&n)?;
    } else {
        let mut padded = [0u32; KERNEL_WORDS];
        padded[..words.len()].copy_from_slice(&words);
        builder.write_slice(&padded);
    }
    if let Some(po2) = segment_po2 {
        builder.segment_limit_po2(po2);
    }
    let env = builder.build()?;

    let mut report = json!({
        "mode": mode,
        "guest": guest,
        "n": n,
        "words": words,
        "segment_limit_po2": segment_po2,
        "kernel_elf": if guest == "kernel" { kernel_path.clone() } else { None },
    });
    match mode {
        "execute" => {
            let start = Instant::now();
            let session = ExecutorImpl::from_elf(env, elf)?.run()?;
            report["execute_seconds"] = json!(start.elapsed().as_secs_f64());
            let journal = session.journal.as_ref().context("session produced no journal")?;
            report["result"] = decode_output(guest, journal)?;
            report["stats"] = stats_json(&session.stats());
        }
        "prove" => {
            let start = Instant::now();
            let opts = match receipt_kind.as_str() {
                "composite" => ProverOpts::composite(),
                "succinct" => ProverOpts::succinct(),
                other => bail!("unknown TRACEOPT_RECEIPT {other:?}; expected composite or succinct"),
            };
            let info = default_prover().prove_with_opts(env, elf, &opts)?;
            report["prove_seconds"] = json!(start.elapsed().as_secs_f64());
            info.receipt.verify(id)?;
            report["image_id"] = json!(id.to_string());
            if let Ok(path) = std::env::var("TRACEOPT_RECEIPT_OUT") {
                let bytes = bincode::serialize(&info.receipt).context("encoding the receipt")?;
                std::fs::write(&path, &bytes).with_context(|| format!("writing {path}"))?;
                report["receipt_file"] = json!(path);
                report["receipt_file_bytes"] = json!(bytes.len());
            }
            report["seal_bytes"] = json!(info.receipt.seal_size());
            report["peak_memory_kib"] = json!(peak_memory_kib());
            report["result"] = decode_output(guest, &info.receipt.journal)?;
            report["stats"] = stats_json(&info.stats);
            report["receipt"] = json!(receipt_kind);
            report["dev_mode"] = json!(std::env::var("RISC0_DEV_MODE").unwrap_or_default());
        }
        other => bail!("unknown mode {other:?}; expected execute or prove"),
    }

    println!("{report}");
    Ok(())
}
