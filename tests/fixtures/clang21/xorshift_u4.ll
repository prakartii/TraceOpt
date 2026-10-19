; ModuleID = 'tests/fixtures/clang21/xorshift.ll'
source_filename = "benchmarks/xorshift.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

; Function Attrs: nofree norecurse nosync nounwind memory(none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp eq i32 %0, 0
  br i1 %2, label %16, label %.preheader

.preheader:                                       ; preds = %1
  %3 = add i32 %0, -1
  %xtraiter = and i32 %0, 3
  %4 = icmp ult i32 %3, 3
  br i1 %4, label %.loopexit.unr-lcssa, label %.preheader.new

.preheader.new:                                   ; preds = %.preheader
  %unroll_iter = sub i32 %0, %xtraiter
  br label %18

.loopexit.unr-lcssa.loopexit:                     ; preds = %18
  %.lcssa.ph.ph = phi i32 [ %44, %18 ]
  %.unr.ph = phi i32 [ %45, %18 ]
  %.unr1.ph = phi i32 [ %44, %18 ]
  br label %.loopexit.unr-lcssa

.loopexit.unr-lcssa:                              ; preds = %.loopexit.unr-lcssa.loopexit, %.preheader
  %.lcssa.ph = phi i32 [ poison, %.preheader ], [ %.lcssa.ph.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr = phi i32 [ 0, %.preheader ], [ %.unr.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr1 = phi i32 [ -1831433054, %.preheader ], [ %.unr1.ph, %.loopexit.unr-lcssa.loopexit ]
  %lcmp.mod = icmp ne i32 %xtraiter, 0
  br i1 %lcmp.mod, label %.epil.preheader, label %.loopexit

.epil.preheader:                                  ; preds = %.loopexit.unr-lcssa
  br label %5

5:                                                ; preds = %5, %.epil.preheader
  %6 = phi i32 [ %14, %5 ], [ %.unr, %.epil.preheader ]
  %7 = phi i32 [ %13, %5 ], [ %.unr1, %.epil.preheader ]
  %epil.iter = phi i32 [ 0, %.epil.preheader ], [ %epil.iter.next, %5 ]
  %8 = shl i32 %7, 13
  %9 = xor i32 %8, %7
  %10 = lshr i32 %9, 17
  %11 = xor i32 %10, %9
  %12 = shl i32 %11, 5
  %13 = xor i32 %12, %11
  %14 = add nuw i32 %6, 1
  %15 = icmp eq i32 %14, %0
  %epil.iter.next = add i32 %epil.iter, 1
  %epil.iter.cmp = icmp ne i32 %epil.iter.next, %xtraiter
  br i1 %epil.iter.cmp, label %5, label %.loopexit.epilog-lcssa, !llvm.loop !6

.loopexit.epilog-lcssa:                           ; preds = %5
  %.lcssa.ph2 = phi i32 [ %13, %5 ]
  br label %.loopexit

.loopexit:                                        ; preds = %.loopexit.unr-lcssa, %.loopexit.epilog-lcssa
  %.lcssa = phi i32 [ %.lcssa.ph, %.loopexit.unr-lcssa ], [ %.lcssa.ph2, %.loopexit.epilog-lcssa ]
  br label %16

16:                                               ; preds = %.loopexit, %1
  %17 = phi i32 [ -1831433054, %1 ], [ %.lcssa, %.loopexit ]
  ret i32 %17

18:                                               ; preds = %18, %.preheader.new
  %19 = phi i32 [ 0, %.preheader.new ], [ %45, %18 ]
  %20 = phi i32 [ -1831433054, %.preheader.new ], [ %44, %18 ]
  %niter = phi i32 [ 0, %.preheader.new ], [ %niter.next.3, %18 ]
  %21 = shl i32 %20, 13
  %22 = xor i32 %21, %20
  %23 = lshr i32 %22, 17
  %24 = xor i32 %23, %22
  %25 = shl i32 %24, 5
  %26 = xor i32 %25, %24
  %27 = shl i32 %26, 13
  %28 = xor i32 %27, %26
  %29 = lshr i32 %28, 17
  %30 = xor i32 %29, %28
  %31 = shl i32 %30, 5
  %32 = xor i32 %31, %30
  %33 = shl i32 %32, 13
  %34 = xor i32 %33, %32
  %35 = lshr i32 %34, 17
  %36 = xor i32 %35, %34
  %37 = shl i32 %36, 5
  %38 = xor i32 %37, %36
  %39 = shl i32 %38, 13
  %40 = xor i32 %39, %38
  %41 = lshr i32 %40, 17
  %42 = xor i32 %41, %40
  %43 = shl i32 %42, 5
  %44 = xor i32 %43, %42
  %45 = add nuw i32 %19, 4
  %niter.next.3 = add i32 %niter, 4
  %niter.ncmp.3 = icmp eq i32 %niter.next.3, %unroll_iter
  br i1 %niter.ncmp.3, label %.loopexit.unr-lcssa.loopexit, label %18, !llvm.loop !8
}

attributes #0 = { nofree norecurse nosync nounwind memory(none) "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="generic-rv32" "target-features"="+32bit,+m,+relax,+zmmul,-a,-b,-c,-d,-e,-experimental-p,-experimental-smctr,-experimental-ssctr,-experimental-svukte,-experimental-xqccmp,-experimental-xqcia,-experimental-xqciac,-experimental-xqcibi,-experimental-xqcibm,-experimental-xqcicli,-experimental-xqcicm,-experimental-xqcics,-experimental-xqcicsr,-experimental-xqciint,-experimental-xqciio,-experimental-xqcilb,-experimental-xqcili,-experimental-xqcilia,-experimental-xqcilo,-experimental-xqcilsm,-experimental-xqcisim,-experimental-xqcisls,-experimental-xqcisync,-experimental-xrivosvisni,-experimental-xrivosvizip,-experimental-xsfmclic,-experimental-xsfsclic,-experimental-zalasr,-experimental-zicfilp,-experimental-zicfiss,-experimental-zvbc32e,-experimental-zvkgs,-experimental-zvqdotq,-f,-h,-q,-sdext,-sdtrig,-sha,-shcounterenw,-shgatpa,-shlcofideleg,-shtvala,-shvsatpa,-shvstvala,-shvstvecd,-smaia,-smcdeleg,-smcntrpmf,-smcsrind,-smdbltrp,-smepmp,-smmpm,-smnpm,-smrnmi,-smstateen,-ssaia,-ssccfg,-ssccptr,-sscofpmf,-sscounterenw,-sscsrind,-ssdbltrp,-ssnpm,-sspm,-ssqosid,-ssstateen,-ssstrict,-sstc,-sstvala,-sstvecd,-ssu64xl,-supm,-svade,-svadu,-svbare,-svinval,-svnapot,-svpbmt,-svvptc,-v,-xandesbfhcvt,-xandesperf,-xandesvbfhcvt,-xandesvdot,-xandesvpackfph,-xandesvsintload,-xcvalu,-xcvbi,-xcvbitmanip,-xcvelw,-xcvmac,-xcvmem,-xcvsimd,-xmipscbop,-xmipscmov,-xmipslsp,-xsfcease,-xsfmm128t,-xsfmm16t,-xsfmm32a16f,-xsfmm32a32f,-xsfmm32a8f,-xsfmm32a8i,-xsfmm32t,-xsfmm64a64f,-xsfmm64t,-xsfmmbase,-xsfvcp,-xsfvfnrclipxfqf,-xsfvfwmaccqqq,-xsfvqmaccdod,-xsfvqmaccqoq,-xsifivecdiscarddlone,-xsifivecflushdlone,-xtheadba,-xtheadbb,-xtheadbs,-xtheadcmo,-xtheadcondmov,-xtheadfmemidx,-xtheadmac,-xtheadmemidx,-xtheadmempair,-xtheadsync,-xtheadvdot,-xventanacondops,-xwchc,-za128rs,-za64rs,-zaamo,-zabha,-zacas,-zalrsc,-zama16b,-zawrs,-zba,-zbb,-zbc,-zbkb,-zbkc,-zbkx,-zbs,-zca,-zcb,-zcd,-zce,-zcf,-zclsd,-zcmop,-zcmp,-zcmt,-zdinx,-zfa,-zfbfmin,-zfh,-zfhmin,-zfinx,-zhinx,-zhinxmin,-zic64b,-zicbom,-zicbop,-zicboz,-ziccamoa,-ziccamoc,-ziccif,-zicclsm,-ziccrse,-zicntr,-zicond,-zicsr,-zifencei,-zihintntl,-zihintpause,-zihpm,-zilsd,-zimop,-zk,-zkn,-zknd,-zkne,-zknh,-zkr,-zks,-zksed,-zksh,-zkt,-ztso,-zvbb,-zvbc,-zve32f,-zve32x,-zve64d,-zve64f,-zve64x,-zvfbfmin,-zvfbfwma,-zvfh,-zvfhmin,-zvkb,-zvkg,-zvkn,-zvknc,-zvkned,-zvkng,-zvknha,-zvknhb,-zvks,-zvksc,-zvksed,-zvksg,-zvksh,-zvkt,-zvl1024b,-zvl128b,-zvl16384b,-zvl2048b,-zvl256b,-zvl32768b,-zvl32b,-zvl4096b,-zvl512b,-zvl64b,-zvl65536b,-zvl8192b" }

!llvm.module.flags = !{!0, !1, !2, !4}
!llvm.ident = !{!5}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 1, !"target-abi", !"ilp32"}
!2 = !{i32 6, !"riscv-isa", !3}
!3 = !{!"rv32i2p1_m2p0_zmmul1p0"}
!4 = !{i32 8, !"SmallDataLimit", i32 0}
!5 = !{!"Ubuntu clang version 21.1.8 (6ubuntu1)"}
!6 = distinct !{!6, !7}
!7 = !{!"llvm.loop.unroll.disable"}
!8 = distinct !{!8, !9, !10, !7}
!9 = !{!"llvm.loop.mustprogress"}
!10 = !{!"traceopt.unroll.cleared"}
