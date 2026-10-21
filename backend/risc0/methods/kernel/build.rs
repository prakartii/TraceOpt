//! Links a C kernel and the entry function that calls it into the guest.
//!
//! - `TRACEOPT_KERNEL_OBJ=<path.o>`: link a prebuilt RISC-V object (e.g. produced
//!   from optimized LLVM IR by `llc`).
//! - otherwise: compile `TRACEOPT_KERNEL_SRC` (default: benchmarks/xorshift.c)
//!   with the C compiler configured by risc0-build. The default kernel is a
//!   loop LLVM cannot fold into a closed form.
//! - `TRACEOPT_ENTRY_OBJ=<path.o>`: the entry function `traceopt_entry`
//!   (traceopt/signature.py); without it, default_entry.c, which calls
//!   `uint32_t traceopt_kernel(uint32_t)`.

use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-env-changed=TRACEOPT_KERNEL_OBJ");
    println!("cargo:rerun-if-env-changed=TRACEOPT_KERNEL_SRC");
    println!("cargo:rerun-if-env-changed=TRACEOPT_ENTRY_OBJ");

    let manifest = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let mut build = cc::Build::new();
    build.opt_level(2);
    match std::env::var("TRACEOPT_ENTRY_OBJ") {
        Ok(entry) => {
            println!("cargo:rerun-if-changed={entry}");
            build.object(&entry);
        }
        Err(_) => {
            let entry = manifest.join("default_entry.c");
            println!("cargo:rerun-if-changed={}", entry.display());
            build.file(&entry);
        }
    }

    if let Ok(obj) = std::env::var("TRACEOPT_KERNEL_OBJ") {
        println!("cargo:rerun-if-changed={obj}");
        build.object(&obj).compile("traceopt_kernel");
        return;
    }

    let src = std::env::var("TRACEOPT_KERNEL_SRC").map(PathBuf::from).unwrap_or_else(|_| {
        manifest.join("../../../../benchmarks/xorshift.c")
    });
    println!("cargo:rerun-if-changed={}", src.display());
    build.file(&src).compile("traceopt_kernel");
}
