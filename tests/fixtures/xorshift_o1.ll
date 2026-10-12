; Hand-written fixture modeled on Clang -O1 output for benchmarks/xorshift.c
; (riscv32). To be cross-checked against real Clang output (issue #2).
source_filename = "xorshift.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

; Function Attrs: nofree norecurse nosync nounwind memory(none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp eq i32 %0, 0
  br i1 %2, label %3, label %5

3:                                                ; preds = %5, %1
  %4 = phi i32 [ -1831433054, %1 ], [ %13, %5 ]
  ret i32 %4

5:                                                ; preds = %1, %5
  %6 = phi i32 [ %14, %5 ], [ 0, %1 ]
  %7 = phi i32 [ %13, %5 ], [ -1831433054, %1 ]
  %8 = shl i32 %7, 13
  %9 = xor i32 %8, %7
  %10 = lshr i32 %9, 17
  %11 = xor i32 %10, %9
  %12 = shl i32 %11, 5
  %13 = xor i32 %12, %11
  %14 = add nuw i32 %6, 1
  %15 = icmp eq i32 %14, %0
  br i1 %15, label %3, label %5, !llvm.loop !6
}

attributes #0 = { nofree norecurse nosync nounwind memory(none) }

!6 = distinct !{!6, !7}
!7 = !{!"llvm.loop.mustprogress"}
