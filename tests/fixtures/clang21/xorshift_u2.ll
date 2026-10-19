; ModuleID = 'tests/fixtures/clang21/xorshift.ll'
source_filename = "benchmarks/xorshift.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

; Function Attrs: nofree norecurse nosync nounwind memory(none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp eq i32 %0, 0
  br i1 %2, label %11, label %.preheader

.preheader:                                       ; preds = %1
  %3 = add i32 %0, -1
  %xtraiter = and i32 %0, 1
  %4 = icmp ult i32 %3, 1
  br i1 %4, label %.loopexit.unr-lcssa, label %.preheader.new

.preheader.new:                                   ; preds = %.preheader
  %unroll_iter = sub i32 %0, %xtraiter
  br label %13

.loopexit.unr-lcssa.loopexit:                     ; preds = %13
  %.lcssa.ph.ph = phi i32 [ %27, %13 ]
  %.unr1.ph = phi i32 [ %27, %13 ]
  br label %.loopexit.unr-lcssa

.loopexit.unr-lcssa:                              ; preds = %.loopexit.unr-lcssa.loopexit, %.preheader
  %.lcssa.ph = phi i32 [ poison, %.preheader ], [ %.lcssa.ph.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr1 = phi i32 [ -1831433054, %.preheader ], [ %.unr1.ph, %.loopexit.unr-lcssa.loopexit ]
  %lcmp.mod = icmp ne i32 %xtraiter, 0
  br i1 %lcmp.mod, label %.epil.preheader, label %.loopexit

.epil.preheader:                                  ; preds = %.loopexit.unr-lcssa
  br label %.loopexit.epilog-lcssa

.loopexit.epilog-lcssa:                           ; preds = %.epil.preheader
  %5 = shl i32 %.unr1, 13
  %6 = xor i32 %5, %.unr1
  %7 = lshr i32 %6, 17
  %8 = xor i32 %7, %6
  %9 = shl i32 %8, 5
  %10 = xor i32 %9, %8
  br label %.loopexit

.loopexit:                                        ; preds = %.loopexit.unr-lcssa, %.loopexit.epilog-lcssa
  %.lcssa = phi i32 [ %.lcssa.ph, %.loopexit.unr-lcssa ], [ %10, %.loopexit.epilog-lcssa ]
  br label %11

11:                                               ; preds = %.loopexit, %1
  %12 = phi i32 [ -1831433054, %1 ], [ %.lcssa, %.loopexit ]
  ret i32 %12

13:                                               ; preds = %13, %.preheader.new
  %14 = phi i32 [ 0, %.preheader.new ], [ %28, %13 ]
  %15 = phi i32 [ -1831433054, %.preheader.new ], [ %27, %13 ]
  %niter = phi i32 [ 0, %.preheader.new ], [ %niter.next.1, %13 ]
  %16 = shl i32 %15, 13
  %17 = xor i32 %16, %15
  %18 = lshr i32 %17, 17
  %19 = xor i32 %18, %17
  %20 = shl i32 %19, 5
  %21 = xor i32 %20, %19
  %22 = shl i32 %21, 13
  %23 = xor i32 %22, %21
  %24 = lshr i32 %23, 17
  %25 = xor i32 %24, %23
  %26 = shl i32 %25, 5
  %27 = xor i32 %26, %25
  %28 = add nuw i32 %14, 2
  %niter.next.1 = add i32 %niter, 2
  %niter.ncmp.1 = icmp eq i32 %niter.next.1, %unroll_iter
  br i1 %niter.ncmp.1, label %.loopexit.unr-lcssa.loopexit, label %13, !llvm.loop !6
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
!6 = distinct !{!6, !7, !8, !9}
!7 = !{!"llvm.loop.mustprogress"}
!8 = !{!"traceopt.unroll.cleared"}
!9 = !{!"llvm.loop.unroll.disable"}
