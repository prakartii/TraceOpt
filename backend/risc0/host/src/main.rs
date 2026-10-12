//! Phase 0 host: runs a guest in the RISC Zero executor (or prover) and prints
//! one JSON object with the measurements RISC Zero exposes.
//!
//! Usage: host <execute|prove> <probe|kernel> [n]
//!
//! - `probe`:  Rust-only guest; journal is the u32 result.
//! - `kernel`: Rust guest calling a C kernel via FFI; journal is
//!             (u32 result, u64 cycles spent inside the kernel).
//!
//! `TRACEOPT_SEGMENT_PO2=<k>` caps segments at 2^k cycles. Smaller segments
//! lower prover memory but add per-segment paging, so keep it fixed when
//! comparing variants.

use std::time::Instant;

use anyhow::{bail, Context, Result};
use methods::{KERNEL_ELF, KERNEL_ID, PROBE_ELF, PROBE_ID};
use risc0_zkvm::{default_prover, ExecutorEnv, ExecutorImpl, Journal, SessionStats};
use serde_json::{json, Value};

fn decode_output(guest: &str, journal: &Journal) -> Result<Value> {
    Ok(match guest {
        "probe" => {
            let output: u32 = journal.decode()?;
            json!({ "output": output })
        }
        _ => {
            let (output, kernel_cycles): (u32, u64) = journal.decode()?;
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

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("execute");
    let guest = args.get(2).map(String::as_str).unwrap_or("probe");
    let n: u32 = match args.get(3) {
        Some(s) => s.parse().context("n must be a u32")?,
        None => 1000,
    };
    let (elf, id) = match guest {
        "probe" => (PROBE_ELF, PROBE_ID),
        "kernel" => (KERNEL_ELF, KERNEL_ID),
        other => bail!("unknown guest {other:?}; expected probe or kernel"),
    };

    let segment_po2: Option<u32> = match std::env::var("TRACEOPT_SEGMENT_PO2") {
        Ok(s) => Some(s.parse().context("TRACEOPT_SEGMENT_PO2 must be a u32")?),
        Err(_) => None,
    };

    let mut builder = ExecutorEnv::builder();
    builder.write(&n)?;
    if let Some(po2) = segment_po2 {
        builder.segment_limit_po2(po2);
    }
    let env = builder.build()?;

    let mut report = json!({
        "mode": mode,
        "guest": guest,
        "n": n,
        "segment_limit_po2": segment_po2,
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
            let info = default_prover().prove(env, elf)?;
            report["prove_seconds"] = json!(start.elapsed().as_secs_f64());
            info.receipt.verify(id)?;
            report["result"] = decode_output(guest, &info.receipt.journal)?;
            report["stats"] = stats_json(&info.stats);
            report["dev_mode"] = json!(std::env::var("RISC0_DEV_MODE").unwrap_or_default());
        }
        other => bail!("unknown mode {other:?}; expected execute or prove"),
    }

    println!("{report}");
    Ok(())
}
