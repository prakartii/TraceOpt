; ModuleID = 'tests/fixtures/clang21/branchy.ll'
source_filename = "benchmarks/branchy.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

; Function Attrs: nofree norecurse nosync nounwind memory(none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp eq i32 %0, 0
  br i1 %2, label %32, label %.preheader

.preheader:                                       ; preds = %1
  %3 = add i32 %0, -1
  %xtraiter = and i32 %0, 3
  %4 = icmp ult i32 %3, 3
  br i1 %4, label %.loopexit.unr-lcssa, label %.preheader.new

.preheader.new:                                   ; preds = %.preheader
  %unroll_iter = sub i32 %0, %xtraiter
  br label %34

.loopexit.unr-lcssa.loopexit:                     ; preds = %123
  %.lcssa.ph.ph = phi i32 [ %124, %123 ]
  %.unr.ph = phi i32 [ %125, %123 ]
  %.unr1.ph = phi i32 [ %124, %123 ]
  %.unr2.ph = phi i32 [ %109, %123 ]
  br label %.loopexit.unr-lcssa

.loopexit.unr-lcssa:                              ; preds = %.loopexit.unr-lcssa.loopexit, %.preheader
  %.lcssa.ph = phi i32 [ poison, %.preheader ], [ %.lcssa.ph.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr = phi i32 [ 0, %.preheader ], [ %.unr.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr1 = phi i32 [ 0, %.preheader ], [ %.unr1.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr2 = phi i32 [ -1831433054, %.preheader ], [ %.unr2.ph, %.loopexit.unr-lcssa.loopexit ]
  %lcmp.mod = icmp ne i32 %xtraiter, 0
  br i1 %lcmp.mod, label %.epil.preheader, label %.loopexit

.epil.preheader:                                  ; preds = %.loopexit.unr-lcssa
  br label %5

5:                                                ; preds = %28, %.epil.preheader
  %6 = phi i32 [ %30, %28 ], [ %.unr, %.epil.preheader ]
  %7 = phi i32 [ %29, %28 ], [ %.unr1, %.epil.preheader ]
  %8 = phi i32 [ %14, %28 ], [ %.unr2, %.epil.preheader ]
  %epil.iter = phi i32 [ 0, %.epil.preheader ], [ %epil.iter.next, %28 ]
  %9 = shl i32 %8, 13
  %10 = xor i32 %9, %8
  %11 = lshr i32 %10, 17
  %12 = xor i32 %11, %10
  %13 = shl i32 %12, 5
  %14 = xor i32 %13, %12
  %15 = and i32 %12, 1
  %16 = icmp eq i32 %15, 0
  br i1 %16, label %20, label %17

17:                                               ; preds = %5
  %18 = lshr i32 %14, 3
  %19 = add i32 %18, %7
  br label %28

20:                                               ; preds = %5
  %21 = and i32 %12, 2
  %22 = icmp eq i32 %21, 0
  br i1 %22, label %26, label %23

23:                                               ; preds = %20
  %24 = mul i32 %14, 3
  %25 = xor i32 %24, %7
  br label %28

26:                                               ; preds = %20
  %27 = sub i32 %7, %6
  br label %28

28:                                               ; preds = %26, %23, %17
  %29 = phi i32 [ %19, %17 ], [ %25, %23 ], [ %27, %26 ]
  %30 = add nuw i32 %6, 1
  %31 = icmp eq i32 %30, %0
  %epil.iter.next = add i32 %epil.iter, 1
  %epil.iter.cmp = icmp ne i32 %epil.iter.next, %xtraiter
  br i1 %epil.iter.cmp, label %5, label %.loopexit.epilog-lcssa, !llvm.loop !6

.loopexit.epilog-lcssa:                           ; preds = %28
  %.lcssa.ph3 = phi i32 [ %29, %28 ]
  br label %.loopexit

.loopexit:                                        ; preds = %.loopexit.unr-lcssa, %.loopexit.epilog-lcssa
  %.lcssa = phi i32 [ %.lcssa.ph, %.loopexit.unr-lcssa ], [ %.lcssa.ph3, %.loopexit.epilog-lcssa ]
  br label %32

32:                                               ; preds = %.loopexit, %1
  %33 = phi i32 [ 0, %1 ], [ %.lcssa, %.loopexit ]
  ret i32 %33

34:                                               ; preds = %123, %.preheader.new
  %35 = phi i32 [ 0, %.preheader.new ], [ %125, %123 ]
  %36 = phi i32 [ 0, %.preheader.new ], [ %124, %123 ]
  %37 = phi i32 [ -1831433054, %.preheader.new ], [ %109, %123 ]
  %niter = phi i32 [ 0, %.preheader.new ], [ %niter.next.3, %123 ]
  %38 = shl i32 %37, 13
  %39 = xor i32 %38, %37
  %40 = lshr i32 %39, 17
  %41 = xor i32 %40, %39
  %42 = shl i32 %41, 5
  %43 = xor i32 %42, %41
  %44 = and i32 %41, 1
  %45 = icmp eq i32 %44, 0
  br i1 %45, label %49, label %46

46:                                               ; preds = %34
  %47 = lshr i32 %43, 3
  %48 = add i32 %47, %36
  br label %57

49:                                               ; preds = %34
  %50 = and i32 %41, 2
  %51 = icmp eq i32 %50, 0
  br i1 %51, label %55, label %52

52:                                               ; preds = %49
  %53 = mul i32 %43, 3
  %54 = xor i32 %53, %36
  br label %57

55:                                               ; preds = %49
  %56 = sub i32 %36, %35
  br label %57

57:                                               ; preds = %55, %52, %46
  %58 = phi i32 [ %48, %46 ], [ %54, %52 ], [ %56, %55 ]
  %59 = add nuw nsw i32 %35, 1
  %60 = shl i32 %43, 13
  %61 = xor i32 %60, %43
  %62 = lshr i32 %61, 17
  %63 = xor i32 %62, %61
  %64 = shl i32 %63, 5
  %65 = xor i32 %64, %63
  %66 = and i32 %63, 1
  %67 = icmp eq i32 %66, 0
  br i1 %67, label %71, label %68

68:                                               ; preds = %57
  %69 = lshr i32 %65, 3
  %70 = add i32 %69, %58
  br label %79

71:                                               ; preds = %57
  %72 = and i32 %63, 2
  %73 = icmp eq i32 %72, 0
  br i1 %73, label %77, label %74

74:                                               ; preds = %71
  %75 = mul i32 %65, 3
  %76 = xor i32 %75, %58
  br label %79

77:                                               ; preds = %71
  %78 = sub i32 %58, %59
  br label %79

79:                                               ; preds = %77, %74, %68
  %80 = phi i32 [ %70, %68 ], [ %76, %74 ], [ %78, %77 ]
  %81 = add nuw nsw i32 %35, 2
  %82 = shl i32 %65, 13
  %83 = xor i32 %82, %65
  %84 = lshr i32 %83, 17
  %85 = xor i32 %84, %83
  %86 = shl i32 %85, 5
  %87 = xor i32 %86, %85
  %88 = and i32 %85, 1
  %89 = icmp eq i32 %88, 0
  br i1 %89, label %93, label %90

90:                                               ; preds = %79
  %91 = lshr i32 %87, 3
  %92 = add i32 %91, %80
  br label %101

93:                                               ; preds = %79
  %94 = and i32 %85, 2
  %95 = icmp eq i32 %94, 0
  br i1 %95, label %99, label %96

96:                                               ; preds = %93
  %97 = mul i32 %87, 3
  %98 = xor i32 %97, %80
  br label %101

99:                                               ; preds = %93
  %100 = sub i32 %80, %81
  br label %101

101:                                              ; preds = %99, %96, %90
  %102 = phi i32 [ %92, %90 ], [ %98, %96 ], [ %100, %99 ]
  %103 = add nuw nsw i32 %35, 3
  %104 = shl i32 %87, 13
  %105 = xor i32 %104, %87
  %106 = lshr i32 %105, 17
  %107 = xor i32 %106, %105
  %108 = shl i32 %107, 5
  %109 = xor i32 %108, %107
  %110 = and i32 %107, 1
  %111 = icmp eq i32 %110, 0
  br i1 %111, label %115, label %112

112:                                              ; preds = %101
  %113 = lshr i32 %109, 3
  %114 = add i32 %113, %102
  br label %123

115:                                              ; preds = %101
  %116 = and i32 %107, 2
  %117 = icmp eq i32 %116, 0
  br i1 %117, label %121, label %118

118:                                              ; preds = %115
  %119 = mul i32 %109, 3
  %120 = xor i32 %119, %102
  br label %123

121:                                              ; preds = %115
  %122 = sub i32 %102, %103
  br label %123

123:                                              ; preds = %121, %118, %112
  %124 = phi i32 [ %114, %112 ], [ %120, %118 ], [ %122, %121 ]
  %125 = add nuw i32 %35, 4
  %niter.next.3 = add i32 %niter, 4
  %niter.ncmp.3 = icmp eq i32 %niter.next.3, %unroll_iter
  br i1 %niter.ncmp.3, label %.loopexit.unr-lcssa.loopexit, label %34, !llvm.loop !8
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
