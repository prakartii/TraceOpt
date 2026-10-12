// Phase 0 probe guest: a minimal loop whose cycle count we can measure.
use risc0_zkvm::guest::env;

fn main() {
    let n: u32 = env::read();

    let mut acc: u32 = 0;
    for i in 0..n {
        acc = acc.wrapping_add(i.wrapping_mul(i));
    }

    env::commit(&acc);
}
