//! Phase 0 probe host: runs the probe guest in the RISC Zero executor (or prover)
//! and prints one JSON object with the measurements RISC Zero exposes.
//!
//! Usage: host <execute|prove> [n]

use std::time::Instant;

use anyhow::{bail, Context, Result};
use methods::{PROBE_ELF, PROBE_ID};
use risc0_zkvm::{default_prover, ExecutorEnv, ExecutorImpl};
use serde_json::json;

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("execute");
    let n: u32 = match args.get(2) {
        Some(s) => s.parse().context("n must be a u32")?,
        None => 1000,
    };

    let env = ExecutorEnv::builder().write(&n)?.build()?;

    let report = match mode {
        "execute" => {
            let start = Instant::now();
            let session = ExecutorImpl::from_elf(env, PROBE_ELF)?.run()?;
            let elapsed = start.elapsed();
            let stats = session.stats();
            let output: u32 = session
                .journal
                .context("session produced no journal")?
                .decode()?;
            json!({
                "mode": "execute",
                "n": n,
                "output": output,
                "segments": stats.segments,
                "total_cycles": stats.total_cycles,
                "user_cycles": stats.user_cycles,
                "paging_cycles": stats.paging_cycles,
                "reserved_cycles": stats.reserved_cycles,
                "execute_seconds": elapsed.as_secs_f64(),
            })
        }
        "prove" => {
            let start = Instant::now();
            let info = default_prover().prove(env, PROBE_ELF)?;
            let elapsed = start.elapsed();
            info.receipt.verify(PROBE_ID)?;
            let output: u32 = info.receipt.journal.decode()?;
            json!({
                "mode": "prove",
                "n": n,
                "output": output,
                "segments": info.stats.segments,
                "total_cycles": info.stats.total_cycles,
                "user_cycles": info.stats.user_cycles,
                "paging_cycles": info.stats.paging_cycles,
                "reserved_cycles": info.stats.reserved_cycles,
                "prove_seconds": elapsed.as_secs_f64(),
                "dev_mode": std::env::var("RISC0_DEV_MODE").unwrap_or_default(),
            })
        }
        other => bail!("unknown mode {other:?}; expected execute or prove"),
    };

    println!("{report}");
    Ok(())
}
