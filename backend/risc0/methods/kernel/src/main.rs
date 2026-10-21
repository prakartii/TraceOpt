// Kernel guest: calls a C kernel through a generated entry function and
// measures the cycles spent in the kernel call.
//
// The input is the kernel's arguments as 32-bit words, padded to 16. The
// entry function (traceopt/signature.py, or default_entry.c for
// `traceopt_kernel(n)`) loads them, calls the kernel between two `traceopt_cycle_count` calls, and
// writes the result (raw bits, zero-extended) and the cycles.
use risc0_zkvm::guest::env;

extern "C" {
    fn traceopt_entry(words: *const u32, out: *mut u64);
}

#[no_mangle]
pub extern "C" fn traceopt_cycle_count() -> u64 {
    env::cycle_count()
}

/// Input words the guest always reads, so its own cost does not depend on
/// the kernel's signature.
const WORDS: usize = 16;

fn main() {
    let mut words = [0u32; WORDS];
    env::read_slice(&mut words); // raw words: much cheaper than serde
    let mut out = [0u64; 2];
    unsafe { traceopt_entry(words.as_ptr(), out.as_mut_ptr()) };
    env::commit(&(out[0], out[1]));
}
