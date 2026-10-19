; ModuleID = 'tests/fixtures/clang21/nested_fnv.ll'
source_filename = "benchmarks/nested_fnv.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

; Function Attrs: nofree norecurse nosync nounwind memory(none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp eq i32 %0, 0
  br i1 %2, label %34, label %.preheader

.preheader:                                       ; preds = %1
  %3 = add i32 %0, -1
  %xtraiter = and i32 %0, 3
  %4 = icmp ult i32 %3, 3
  br i1 %4, label %.loopexit.unr-lcssa, label %.preheader.new

.preheader.new:                                   ; preds = %.preheader
  %unroll_iter = sub i32 %0, %xtraiter
  br label %5

5:                                                ; preds = %102, %.preheader.new
  %6 = phi i32 [ 0, %.preheader.new ], [ %103, %102 ]
  %7 = phi i32 [ -2128831035, %.preheader.new ], [ %.lcssa.3, %102 ]
  %niter = phi i32 [ 0, %.preheader.new ], [ %niter.next.3, %102 ]
  br label %104

.loopexit.unr-lcssa.loopexit:                     ; preds = %102
  %.lcssa.lcssa.ph.ph = phi i32 [ %.lcssa.3, %102 ]
  %.unr.ph = phi i32 [ %103, %102 ]
  %.unr1.ph = phi i32 [ %.lcssa.3, %102 ]
  br label %.loopexit.unr-lcssa

.loopexit.unr-lcssa:                              ; preds = %.loopexit.unr-lcssa.loopexit, %.preheader
  %.lcssa.lcssa.ph = phi i32 [ poison, %.preheader ], [ %.lcssa.lcssa.ph.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr = phi i32 [ 0, %.preheader ], [ %.unr.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr1 = phi i32 [ -2128831035, %.preheader ], [ %.unr1.ph, %.loopexit.unr-lcssa.loopexit ]
  %lcmp.mod = icmp ne i32 %xtraiter, 0
  br i1 %lcmp.mod, label %.epil.preheader, label %.loopexit

.epil.preheader:                                  ; preds = %.loopexit.unr-lcssa
  br label %8

8:                                                ; preds = %31, %.epil.preheader
  %9 = phi i32 [ %32, %31 ], [ %.unr, %.epil.preheader ]
  %10 = phi i32 [ %.lcssa.epil, %31 ], [ %.unr1, %.epil.preheader ]
  %epil.iter = phi i32 [ 0, %.epil.preheader ], [ %epil.iter.next, %31 ]
  br label %11

11:                                               ; preds = %11, %8
  %12 = phi i32 [ 0, %8 ], [ %29, %11 ]
  %13 = phi i32 [ %10, %8 ], [ %28, %11 ]
  %14 = add i32 %12, %9
  %15 = xor i32 %14, %13
  %16 = mul i32 %15, 16777619
  %17 = add nuw nsw i32 %12, 1
  %18 = add i32 %17, %9
  %19 = xor i32 %18, %16
  %20 = mul i32 %19, 16777619
  %21 = add nuw nsw i32 %12, 2
  %22 = add i32 %21, %9
  %23 = xor i32 %22, %20
  %24 = mul i32 %23, 16777619
  %25 = add nuw nsw i32 %12, 3
  %26 = add i32 %25, %9
  %27 = xor i32 %26, %24
  %28 = mul i32 %27, 16777619
  %29 = add nuw nsw i32 %12, 4
  %30 = icmp eq i32 %29, 16
  br i1 %30, label %31, label %11, !llvm.loop !6

31:                                               ; preds = %11
  %.lcssa.epil = phi i32 [ %28, %11 ]
  %32 = add nuw i32 %9, 1
  %33 = icmp eq i32 %32, %0
  %epil.iter.next = add i32 %epil.iter, 1
  %epil.iter.cmp = icmp ne i32 %epil.iter.next, %xtraiter
  br i1 %epil.iter.cmp, label %8, label %.loopexit.epilog-lcssa, !llvm.loop !10

.loopexit.epilog-lcssa:                           ; preds = %31
  %.lcssa.lcssa.ph2 = phi i32 [ %.lcssa.epil, %31 ]
  br label %.loopexit

.loopexit:                                        ; preds = %.loopexit.unr-lcssa, %.loopexit.epilog-lcssa
  %.lcssa.lcssa = phi i32 [ %.lcssa.lcssa.ph, %.loopexit.unr-lcssa ], [ %.lcssa.lcssa.ph2, %.loopexit.epilog-lcssa ]
  br label %34

34:                                               ; preds = %.loopexit, %1
  %35 = phi i32 [ -2128831035, %1 ], [ %.lcssa.lcssa, %.loopexit ]
  ret i32 %35

36:                                               ; preds = %104
  %.lcssa = phi i32 [ %121, %104 ]
  %37 = add nuw nsw i32 %6, 1
  br label %38

38:                                               ; preds = %38, %36
  %39 = phi i32 [ 0, %36 ], [ %56, %38 ]
  %40 = phi i32 [ %.lcssa, %36 ], [ %55, %38 ]
  %41 = add i32 %39, %37
  %42 = xor i32 %41, %40
  %43 = mul i32 %42, 16777619
  %44 = add nuw nsw i32 %39, 1
  %45 = add i32 %44, %37
  %46 = xor i32 %45, %43
  %47 = mul i32 %46, 16777619
  %48 = add nuw nsw i32 %39, 2
  %49 = add i32 %48, %37
  %50 = xor i32 %49, %47
  %51 = mul i32 %50, 16777619
  %52 = add nuw nsw i32 %39, 3
  %53 = add i32 %52, %37
  %54 = xor i32 %53, %51
  %55 = mul i32 %54, 16777619
  %56 = add nuw nsw i32 %39, 4
  %57 = icmp eq i32 %56, 16
  br i1 %57, label %58, label %38, !llvm.loop !6

58:                                               ; preds = %38
  %.lcssa.1 = phi i32 [ %55, %38 ]
  %59 = add nuw nsw i32 %6, 2
  br label %60

60:                                               ; preds = %60, %58
  %61 = phi i32 [ 0, %58 ], [ %78, %60 ]
  %62 = phi i32 [ %.lcssa.1, %58 ], [ %77, %60 ]
  %63 = add i32 %61, %59
  %64 = xor i32 %63, %62
  %65 = mul i32 %64, 16777619
  %66 = add nuw nsw i32 %61, 1
  %67 = add i32 %66, %59
  %68 = xor i32 %67, %65
  %69 = mul i32 %68, 16777619
  %70 = add nuw nsw i32 %61, 2
  %71 = add i32 %70, %59
  %72 = xor i32 %71, %69
  %73 = mul i32 %72, 16777619
  %74 = add nuw nsw i32 %61, 3
  %75 = add i32 %74, %59
  %76 = xor i32 %75, %73
  %77 = mul i32 %76, 16777619
  %78 = add nuw nsw i32 %61, 4
  %79 = icmp eq i32 %78, 16
  br i1 %79, label %80, label %60, !llvm.loop !6

80:                                               ; preds = %60
  %.lcssa.2 = phi i32 [ %77, %60 ]
  %81 = add nuw nsw i32 %6, 3
  br label %82

82:                                               ; preds = %82, %80
  %83 = phi i32 [ 0, %80 ], [ %100, %82 ]
  %84 = phi i32 [ %.lcssa.2, %80 ], [ %99, %82 ]
  %85 = add i32 %83, %81
  %86 = xor i32 %85, %84
  %87 = mul i32 %86, 16777619
  %88 = add nuw nsw i32 %83, 1
  %89 = add i32 %88, %81
  %90 = xor i32 %89, %87
  %91 = mul i32 %90, 16777619
  %92 = add nuw nsw i32 %83, 2
  %93 = add i32 %92, %81
  %94 = xor i32 %93, %91
  %95 = mul i32 %94, 16777619
  %96 = add nuw nsw i32 %83, 3
  %97 = add i32 %96, %81
  %98 = xor i32 %97, %95
  %99 = mul i32 %98, 16777619
  %100 = add nuw nsw i32 %83, 4
  %101 = icmp eq i32 %100, 16
  br i1 %101, label %102, label %82, !llvm.loop !6

102:                                              ; preds = %82
  %.lcssa.3 = phi i32 [ %99, %82 ]
  %103 = add nuw i32 %6, 4
  %niter.next.3 = add i32 %niter, 4
  %niter.ncmp.3 = icmp eq i32 %niter.next.3, %unroll_iter
  br i1 %niter.ncmp.3, label %.loopexit.unr-lcssa.loopexit, label %5, !llvm.loop !11

104:                                              ; preds = %104, %5
  %105 = phi i32 [ 0, %5 ], [ %122, %104 ]
  %106 = phi i32 [ %7, %5 ], [ %121, %104 ]
  %107 = add i32 %105, %6
  %108 = xor i32 %107, %106
  %109 = mul i32 %108, 16777619
  %110 = add nuw nsw i32 %105, 1
  %111 = add i32 %110, %6
  %112 = xor i32 %111, %109
  %113 = mul i32 %112, 16777619
  %114 = add nuw nsw i32 %105, 2
  %115 = add i32 %114, %6
  %116 = xor i32 %115, %113
  %117 = mul i32 %116, 16777619
  %118 = add nuw nsw i32 %105, 3
  %119 = add i32 %118, %6
  %120 = xor i32 %119, %117
  %121 = mul i32 %120, 16777619
  %122 = add nuw nsw i32 %105, 4
  %123 = icmp eq i32 %122, 16
  br i1 %123, label %36, label %104, !llvm.loop !6
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
!10 = distinct !{!10, !9}
!11 = distinct !{!11, !7, !8, !9}
