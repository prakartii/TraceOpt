; ModuleID = 'tests/fixtures/clang21/strided_rw.ll'
source_filename = "benchmarks/strided_rw.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

@buf = internal unnamed_addr global [16384 x i32] zeroinitializer, align 4

; Function Attrs: nofree norecurse nosync nounwind memory(readwrite, argmem: none, inaccessiblemem: none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  br label %6

2:                                                ; preds = %6
  %3 = icmp eq i32 %0, 0
  br i1 %3, label %62, label %.preheader

.preheader:                                       ; preds = %2
  %4 = add i32 %0, -1
  %xtraiter = and i32 %0, 3
  %5 = icmp ult i32 %4, 3
  br i1 %5, label %.loopexit.unr-lcssa, label %.preheader.new

.preheader.new:                                   ; preds = %.preheader
  %unroll_iter = sub i32 %0, %xtraiter
  br label %21

6:                                                ; preds = %6, %1
  %7 = phi i32 [ 0, %1 ], [ %19, %6 ]
  %8 = mul i32 %7, -1640531535
  %9 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %7
  store i32 %8, ptr %9, align 4, !tbaa !6
  %10 = add nuw nsw i32 %7, 1
  %11 = mul i32 %10, -1640531535
  %12 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %10
  store i32 %11, ptr %12, align 4, !tbaa !6
  %13 = add nuw nsw i32 %7, 2
  %14 = mul i32 %13, -1640531535
  %15 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %13
  store i32 %14, ptr %15, align 4, !tbaa !6
  %16 = add nuw nsw i32 %7, 3
  %17 = mul i32 %16, -1640531535
  %18 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %16
  store i32 %17, ptr %18, align 4, !tbaa !6
  %19 = add nuw nsw i32 %7, 4
  %20 = icmp eq i32 %19, 16384
  br i1 %20, label %2, label %6, !llvm.loop !10

21:                                               ; preds = %166, %.preheader.new
  %22 = phi i32 [ 0, %.preheader.new ], [ %167, %166 ]
  %23 = phi i32 [ 0, %.preheader.new ], [ %.lcssa.3, %166 ]
  %niter = phi i32 [ 0, %.preheader.new ], [ %niter.next.3, %166 ]
  br label %168

.loopexit.unr-lcssa.loopexit:                     ; preds = %166
  %.lcssa.lcssa.ph.ph = phi i32 [ %.lcssa.3, %166 ]
  %.unr.ph = phi i32 [ %167, %166 ]
  %.unr1.ph = phi i32 [ %.lcssa.3, %166 ]
  br label %.loopexit.unr-lcssa

.loopexit.unr-lcssa:                              ; preds = %.loopexit.unr-lcssa.loopexit, %.preheader
  %.lcssa.lcssa.ph = phi i32 [ poison, %.preheader ], [ %.lcssa.lcssa.ph.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr = phi i32 [ 0, %.preheader ], [ %.unr.ph, %.loopexit.unr-lcssa.loopexit ]
  %.unr1 = phi i32 [ 0, %.preheader ], [ %.unr1.ph, %.loopexit.unr-lcssa.loopexit ]
  %lcmp.mod = icmp ne i32 %xtraiter, 0
  br i1 %lcmp.mod, label %.epil.preheader, label %.loopexit

.epil.preheader:                                  ; preds = %.loopexit.unr-lcssa
  br label %24

24:                                               ; preds = %59, %.epil.preheader
  %25 = phi i32 [ %60, %59 ], [ %.unr, %.epil.preheader ]
  %26 = phi i32 [ %.lcssa.epil, %59 ], [ %.unr1, %.epil.preheader ]
  %epil.iter = phi i32 [ 0, %.epil.preheader ], [ %epil.iter.next, %59 ]
  br label %27

27:                                               ; preds = %27, %24
  %28 = phi i32 [ 0, %24 ], [ %57, %27 ]
  %29 = phi i32 [ %26, %24 ], [ %56, %27 ]
  %30 = add i32 %28, %25
  %31 = and i32 %30, 16383
  %32 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %31
  %33 = load i32, ptr %32, align 4, !tbaa !6
  %34 = xor i32 %33, %29
  %35 = add i32 %34, %25
  store i32 %35, ptr %32, align 4, !tbaa !6
  %36 = add nuw nsw i32 %28, 256
  %37 = add i32 %36, %25
  %38 = and i32 %37, 16383
  %39 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %38
  %40 = load i32, ptr %39, align 4, !tbaa !6
  %41 = xor i32 %40, %35
  %42 = add i32 %41, %25
  store i32 %42, ptr %39, align 4, !tbaa !6
  %43 = add nuw nsw i32 %28, 512
  %44 = add i32 %43, %25
  %45 = and i32 %44, 16383
  %46 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %45
  %47 = load i32, ptr %46, align 4, !tbaa !6
  %48 = xor i32 %47, %42
  %49 = add i32 %48, %25
  store i32 %49, ptr %46, align 4, !tbaa !6
  %50 = add nuw nsw i32 %28, 768
  %51 = add i32 %50, %25
  %52 = and i32 %51, 16383
  %53 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %52
  %54 = load i32, ptr %53, align 4, !tbaa !6
  %55 = xor i32 %54, %49
  %56 = add i32 %55, %25
  store i32 %56, ptr %53, align 4, !tbaa !6
  %57 = add nuw nsw i32 %28, 1024
  %58 = icmp samesign ult i32 %50, 16128
  br i1 %58, label %27, label %59, !llvm.loop !14

59:                                               ; preds = %27
  %.lcssa.epil = phi i32 [ %56, %27 ]
  %60 = add nuw i32 %25, 1
  %61 = icmp eq i32 %60, %0
  %epil.iter.next = add i32 %epil.iter, 1
  %epil.iter.cmp = icmp ne i32 %epil.iter.next, %xtraiter
  br i1 %epil.iter.cmp, label %24, label %.loopexit.epilog-lcssa, !llvm.loop !15

.loopexit.epilog-lcssa:                           ; preds = %59
  %.lcssa.lcssa.ph2 = phi i32 [ %.lcssa.epil, %59 ]
  br label %.loopexit

.loopexit:                                        ; preds = %.loopexit.unr-lcssa, %.loopexit.epilog-lcssa
  %.lcssa.lcssa = phi i32 [ %.lcssa.lcssa.ph, %.loopexit.unr-lcssa ], [ %.lcssa.lcssa.ph2, %.loopexit.epilog-lcssa ]
  br label %62

62:                                               ; preds = %.loopexit, %2
  %63 = phi i32 [ 0, %2 ], [ %.lcssa.lcssa, %.loopexit ]
  ret i32 %63

64:                                               ; preds = %168
  %.lcssa = phi i32 [ %197, %168 ]
  %65 = add nuw nsw i32 %22, 1
  br label %66

66:                                               ; preds = %66, %64
  %67 = phi i32 [ 0, %64 ], [ %96, %66 ]
  %68 = phi i32 [ %.lcssa, %64 ], [ %95, %66 ]
  %69 = add i32 %67, %65
  %70 = and i32 %69, 16383
  %71 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %70
  %72 = load i32, ptr %71, align 4, !tbaa !6
  %73 = xor i32 %72, %68
  %74 = add i32 %73, %65
  store i32 %74, ptr %71, align 4, !tbaa !6
  %75 = add nuw nsw i32 %67, 256
  %76 = add i32 %75, %65
  %77 = and i32 %76, 16383
  %78 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %77
  %79 = load i32, ptr %78, align 4, !tbaa !6
  %80 = xor i32 %79, %74
  %81 = add i32 %80, %65
  store i32 %81, ptr %78, align 4, !tbaa !6
  %82 = add nuw nsw i32 %67, 512
  %83 = add i32 %82, %65
  %84 = and i32 %83, 16383
  %85 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %84
  %86 = load i32, ptr %85, align 4, !tbaa !6
  %87 = xor i32 %86, %81
  %88 = add i32 %87, %65
  store i32 %88, ptr %85, align 4, !tbaa !6
  %89 = add nuw nsw i32 %67, 768
  %90 = add i32 %89, %65
  %91 = and i32 %90, 16383
  %92 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %91
  %93 = load i32, ptr %92, align 4, !tbaa !6
  %94 = xor i32 %93, %88
  %95 = add i32 %94, %65
  store i32 %95, ptr %92, align 4, !tbaa !6
  %96 = add nuw nsw i32 %67, 1024
  %97 = icmp samesign ult i32 %89, 16128
  br i1 %97, label %66, label %98, !llvm.loop !14

98:                                               ; preds = %66
  %.lcssa.1 = phi i32 [ %95, %66 ]
  %99 = add nuw nsw i32 %22, 2
  br label %100

100:                                              ; preds = %100, %98
  %101 = phi i32 [ 0, %98 ], [ %130, %100 ]
  %102 = phi i32 [ %.lcssa.1, %98 ], [ %129, %100 ]
  %103 = add i32 %101, %99
  %104 = and i32 %103, 16383
  %105 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %104
  %106 = load i32, ptr %105, align 4, !tbaa !6
  %107 = xor i32 %106, %102
  %108 = add i32 %107, %99
  store i32 %108, ptr %105, align 4, !tbaa !6
  %109 = add nuw nsw i32 %101, 256
  %110 = add i32 %109, %99
  %111 = and i32 %110, 16383
  %112 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %111
  %113 = load i32, ptr %112, align 4, !tbaa !6
  %114 = xor i32 %113, %108
  %115 = add i32 %114, %99
  store i32 %115, ptr %112, align 4, !tbaa !6
  %116 = add nuw nsw i32 %101, 512
  %117 = add i32 %116, %99
  %118 = and i32 %117, 16383
  %119 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %118
  %120 = load i32, ptr %119, align 4, !tbaa !6
  %121 = xor i32 %120, %115
  %122 = add i32 %121, %99
  store i32 %122, ptr %119, align 4, !tbaa !6
  %123 = add nuw nsw i32 %101, 768
  %124 = add i32 %123, %99
  %125 = and i32 %124, 16383
  %126 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %125
  %127 = load i32, ptr %126, align 4, !tbaa !6
  %128 = xor i32 %127, %122
  %129 = add i32 %128, %99
  store i32 %129, ptr %126, align 4, !tbaa !6
  %130 = add nuw nsw i32 %101, 1024
  %131 = icmp samesign ult i32 %123, 16128
  br i1 %131, label %100, label %132, !llvm.loop !14

132:                                              ; preds = %100
  %.lcssa.2 = phi i32 [ %129, %100 ]
  %133 = add nuw nsw i32 %22, 3
  br label %134

134:                                              ; preds = %134, %132
  %135 = phi i32 [ 0, %132 ], [ %164, %134 ]
  %136 = phi i32 [ %.lcssa.2, %132 ], [ %163, %134 ]
  %137 = add i32 %135, %133
  %138 = and i32 %137, 16383
  %139 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %138
  %140 = load i32, ptr %139, align 4, !tbaa !6
  %141 = xor i32 %140, %136
  %142 = add i32 %141, %133
  store i32 %142, ptr %139, align 4, !tbaa !6
  %143 = add nuw nsw i32 %135, 256
  %144 = add i32 %143, %133
  %145 = and i32 %144, 16383
  %146 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %145
  %147 = load i32, ptr %146, align 4, !tbaa !6
  %148 = xor i32 %147, %142
  %149 = add i32 %148, %133
  store i32 %149, ptr %146, align 4, !tbaa !6
  %150 = add nuw nsw i32 %135, 512
  %151 = add i32 %150, %133
  %152 = and i32 %151, 16383
  %153 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %152
  %154 = load i32, ptr %153, align 4, !tbaa !6
  %155 = xor i32 %154, %149
  %156 = add i32 %155, %133
  store i32 %156, ptr %153, align 4, !tbaa !6
  %157 = add nuw nsw i32 %135, 768
  %158 = add i32 %157, %133
  %159 = and i32 %158, 16383
  %160 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %159
  %161 = load i32, ptr %160, align 4, !tbaa !6
  %162 = xor i32 %161, %156
  %163 = add i32 %162, %133
  store i32 %163, ptr %160, align 4, !tbaa !6
  %164 = add nuw nsw i32 %135, 1024
  %165 = icmp samesign ult i32 %157, 16128
  br i1 %165, label %134, label %166, !llvm.loop !14

166:                                              ; preds = %134
  %.lcssa.3 = phi i32 [ %163, %134 ]
  %167 = add nuw i32 %22, 4
  %niter.next.3 = add i32 %niter, 4
  %niter.ncmp.3 = icmp eq i32 %niter.next.3, %unroll_iter
  br i1 %niter.ncmp.3, label %.loopexit.unr-lcssa.loopexit, label %21, !llvm.loop !16

168:                                              ; preds = %168, %21
  %169 = phi i32 [ 0, %21 ], [ %198, %168 ]
  %170 = phi i32 [ %23, %21 ], [ %197, %168 ]
  %171 = add i32 %169, %22
  %172 = and i32 %171, 16383
  %173 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %172
  %174 = load i32, ptr %173, align 4, !tbaa !6
  %175 = xor i32 %174, %170
  %176 = add i32 %175, %22
  store i32 %176, ptr %173, align 4, !tbaa !6
  %177 = add nuw nsw i32 %169, 256
  %178 = add i32 %177, %22
  %179 = and i32 %178, 16383
  %180 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %179
  %181 = load i32, ptr %180, align 4, !tbaa !6
  %182 = xor i32 %181, %176
  %183 = add i32 %182, %22
  store i32 %183, ptr %180, align 4, !tbaa !6
  %184 = add nuw nsw i32 %169, 512
  %185 = add i32 %184, %22
  %186 = and i32 %185, 16383
  %187 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %186
  %188 = load i32, ptr %187, align 4, !tbaa !6
  %189 = xor i32 %188, %183
  %190 = add i32 %189, %22
  store i32 %190, ptr %187, align 4, !tbaa !6
  %191 = add nuw nsw i32 %169, 768
  %192 = add i32 %191, %22
  %193 = and i32 %192, 16383
  %194 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %193
  %195 = load i32, ptr %194, align 4, !tbaa !6
  %196 = xor i32 %195, %190
  %197 = add i32 %196, %22
  store i32 %197, ptr %194, align 4, !tbaa !6
  %198 = add nuw nsw i32 %169, 1024
  %199 = icmp samesign ult i32 %191, 16128
  br i1 %199, label %168, label %64, !llvm.loop !14
}

attributes #0 = { nofree norecurse nosync nounwind memory(readwrite, argmem: none, inaccessiblemem: none) "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="generic-rv32" "target-features"="+32bit,+m,+relax,+zmmul,-a,-b,-c,-d,-e,-experimental-p,-experimental-smctr,-experimental-ssctr,-experimental-svukte,-experimental-xqccmp,-experimental-xqcia,-experimental-xqciac,-experimental-xqcibi,-experimental-xqcibm,-experimental-xqcicli,-experimental-xqcicm,-experimental-xqcics,-experimental-xqcicsr,-experimental-xqciint,-experimental-xqciio,-experimental-xqcilb,-experimental-xqcili,-experimental-xqcilia,-experimental-xqcilo,-experimental-xqcilsm,-experimental-xqcisim,-experimental-xqcisls,-experimental-xqcisync,-experimental-xrivosvisni,-experimental-xrivosvizip,-experimental-xsfmclic,-experimental-xsfsclic,-experimental-zalasr,-experimental-zicfilp,-experimental-zicfiss,-experimental-zvbc32e,-experimental-zvkgs,-experimental-zvqdotq,-f,-h,-q,-sdext,-sdtrig,-sha,-shcounterenw,-shgatpa,-shlcofideleg,-shtvala,-shvsatpa,-shvstvala,-shvstvecd,-smaia,-smcdeleg,-smcntrpmf,-smcsrind,-smdbltrp,-smepmp,-smmpm,-smnpm,-smrnmi,-smstateen,-ssaia,-ssccfg,-ssccptr,-sscofpmf,-sscounterenw,-sscsrind,-ssdbltrp,-ssnpm,-sspm,-ssqosid,-ssstateen,-ssstrict,-sstc,-sstvala,-sstvecd,-ssu64xl,-supm,-svade,-svadu,-svbare,-svinval,-svnapot,-svpbmt,-svvptc,-v,-xandesbfhcvt,-xandesperf,-xandesvbfhcvt,-xandesvdot,-xandesvpackfph,-xandesvsintload,-xcvalu,-xcvbi,-xcvbitmanip,-xcvelw,-xcvmac,-xcvmem,-xcvsimd,-xmipscbop,-xmipscmov,-xmipslsp,-xsfcease,-xsfmm128t,-xsfmm16t,-xsfmm32a16f,-xsfmm32a32f,-xsfmm32a8f,-xsfmm32a8i,-xsfmm32t,-xsfmm64a64f,-xsfmm64t,-xsfmmbase,-xsfvcp,-xsfvfnrclipxfqf,-xsfvfwmaccqqq,-xsfvqmaccdod,-xsfvqmaccqoq,-xsifivecdiscarddlone,-xsifivecflushdlone,-xtheadba,-xtheadbb,-xtheadbs,-xtheadcmo,-xtheadcondmov,-xtheadfmemidx,-xtheadmac,-xtheadmemidx,-xtheadmempair,-xtheadsync,-xtheadvdot,-xventanacondops,-xwchc,-za128rs,-za64rs,-zaamo,-zabha,-zacas,-zalrsc,-zama16b,-zawrs,-zba,-zbb,-zbc,-zbkb,-zbkc,-zbkx,-zbs,-zca,-zcb,-zcd,-zce,-zcf,-zclsd,-zcmop,-zcmp,-zcmt,-zdinx,-zfa,-zfbfmin,-zfh,-zfhmin,-zfinx,-zhinx,-zhinxmin,-zic64b,-zicbom,-zicbop,-zicboz,-ziccamoa,-ziccamoc,-ziccif,-zicclsm,-ziccrse,-zicntr,-zicond,-zicsr,-zifencei,-zihintntl,-zihintpause,-zihpm,-zilsd,-zimop,-zk,-zkn,-zknd,-zkne,-zknh,-zkr,-zks,-zksed,-zksh,-zkt,-ztso,-zvbb,-zvbc,-zve32f,-zve32x,-zve64d,-zve64f,-zve64x,-zvfbfmin,-zvfbfwma,-zvfh,-zvfhmin,-zvkb,-zvkg,-zvkn,-zvknc,-zvkned,-zvkng,-zvknha,-zvknhb,-zvks,-zvksc,-zvksed,-zvksg,-zvksh,-zvkt,-zvl1024b,-zvl128b,-zvl16384b,-zvl2048b,-zvl256b,-zvl32768b,-zvl32b,-zvl4096b,-zvl512b,-zvl64b,-zvl65536b,-zvl8192b" }

!llvm.module.flags = !{!0, !1, !2, !4}
!llvm.ident = !{!5}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 1, !"target-abi", !"ilp32"}
!2 = !{i32 6, !"riscv-isa", !3}
!3 = !{!"rv32i2p1_m2p0_zmmul1p0"}
!4 = !{i32 8, !"SmallDataLimit", i32 0}
!5 = !{!"Ubuntu clang version 21.1.8 (6ubuntu1)"}
!6 = !{!7, !7, i64 0}
!7 = !{!"int", !8, i64 0}
!8 = !{!"omnipotent char", !9, i64 0}
!9 = !{!"Simple C/C++ TBAA"}
!10 = distinct !{!10, !11, !12, !13}
!11 = !{!"llvm.loop.mustprogress"}
!12 = !{!"traceopt.unroll.cleared"}
!13 = !{!"llvm.loop.unroll.disable"}
!14 = distinct !{!14, !11, !12, !13}
!15 = distinct !{!15, !13}
!16 = distinct !{!16, !11, !12, !13}
