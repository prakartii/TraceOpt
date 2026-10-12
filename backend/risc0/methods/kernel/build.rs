//! Links a C kernel exporting `uint32_t traceopt_kernel(uint32_t)` into the guest.
//!
//! - `TRACEOPT_KERNEL_OBJ=<path.o>`: link a prebuilt RISC-V object (e.g. produced
//!   from optimized LLVM IR by `llc`).
//! - otherwise: compile `TRACEOPT_KERNEL_SRC` (default: benchmarks/xorshift.c)
//!   with the C compiler configured by risc0-build. The default kernel is a
//!   loop LLVM cannot fold into a closed form.

use std::path::PathBuf;

fn main() {
    println!("cargo:rerun-if-env-changed=TRACEOPT_KERNEL_OBJ");
    println!("cargo:rerun-if-env-changed=TRACEOPT_KERNEL_SRC");

    if let Ok(obj) = std::env::var("TRACEOPT_KERNEL_OBJ") {
        println!("cargo:rerun-if-changed={obj}");
        cc::Build::new().object(&obj).compile("traceopt_kernel");
        return;
    }

    let manifest = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let src = std::env::var("TRACEOPT_KERNEL_SRC").map(PathBuf::from).unwrap_or_else(|_| {
        manifest.join("../../../../benchmarks/xorshift.c")
    });
    println!("cargo:rerun-if-changed={}", src.display());
    cc::Build::new().file(&src).opt_level(2).compile("traceopt_kernel");
}
