// Kernel guest: calls a C kernel through FFI and measures the cycles spent in it.
use risc0_zkvm::guest::env;

extern "C" {
    fn traceopt_kernel(n: u32) -> u32;
}

fn main() {
    let n: u32 = env::read();

    let start = env::cycle_count();
    let result = unsafe { traceopt_kernel(n) };
    let kernel_cycles = env::cycle_count() - start;

    env::commit(&(result, kernel_cycles));
}
