; ModuleID = 'benchmarks/strided_rw.c'
source_filename = "benchmarks/strided_rw.c"
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

@buf = internal unnamed_addr global [16384 x i32] zeroinitializer, align 4

; Function Attrs: nofree norecurse nosync nounwind memory(readwrite, argmem: none, inaccessiblemem: none)
define dso_local i32 @traceopt_kernel(i32 noundef %0) local_unnamed_addr #0 {
  br label %4

2:                                                ; preds = %4
  %3 = icmp eq i32 %0, 0
  br i1 %3, label %13, label %10

4:                                                ; preds = %1, %4
  %5 = phi i32 [ 0, %1 ], [ %8, %4 ]
  %6 = mul i32 %5, -1640531535
  %7 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %5
  store i32 %6, ptr %7, align 4, !tbaa !6
  %8 = add nuw nsw i32 %5, 1
  %9 = icmp eq i32 %8, 16384
  br i1 %9, label %2, label %4, !llvm.loop !10

10:                                               ; preds = %2, %15
  %11 = phi i32 [ %16, %15 ], [ 0, %2 ]
  %12 = phi i32 [ %26, %15 ], [ 0, %2 ]
  br label %18

13:                                               ; preds = %15, %2
  %14 = phi i32 [ 0, %2 ], [ %26, %15 ]
  ret i32 %14

15:                                               ; preds = %18
  %16 = add nuw i32 %11, 1
  %17 = icmp eq i32 %16, %0
  br i1 %17, label %13, label %10, !llvm.loop !13

18:                                               ; preds = %10, %18
  %19 = phi i32 [ 0, %10 ], [ %27, %18 ]
  %20 = phi i32 [ %12, %10 ], [ %26, %18 ]
  %21 = add i32 %19, %11
  %22 = and i32 %21, 16383
  %23 = getelementptr inbounds nuw [16384 x i32], ptr @buf, i32 0, i32 %22
  %24 = load i32, ptr %23, align 4, !tbaa !6
  %25 = xor i32 %24, %20
  %26 = add i32 %25, %11
  store i32 %26, ptr %23, align 4, !tbaa !6
  %27 = add nuw nsw i32 %19, 256
  %28 = icmp samesign ult i32 %19, 16128
  br i1 %28, label %18, label %15, !llvm.loop !14
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
!10 = distinct !{!10, !11, !12}
!11 = !{!"llvm.loop.mustprogress"}
!12 = !{!"traceopt.unroll.cleared"}
!13 = distinct !{!13, !11, !12}
!14 = distinct !{!14, !11, !12}
