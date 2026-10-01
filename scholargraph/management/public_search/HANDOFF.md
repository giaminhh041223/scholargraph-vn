# Giai đoạn B đã được giao — 2026-10-01T23:30:30.299120+07:00

EXT09/10 IN_PROGRESS trên codex/public-search-phase-b. SOL Crossref; Gemini crawler HTML JOSS; coordinator config/policy/tests/live; Muse review sau snapshot. [Log107](logs/SESSION-20261002-107-CODEX.md). Chưa có code/test phaseB, không suy DONE từ phaseA. Next: nhận implementation → kiểm adversarial/CLI → live → review. Main SG030/033 human gates còn chờ.

## Lịch sử phaseA

# Tích hợp hoàn tất — 2026-10-01T23:13:32.489133+07:00

**Master local đã nhận public search; human gate PASS_USER_CONFIRMED;14task phaseA DONE.**

- Merge fast-forward83358a9→3b61cfc. [Gate106](reviews/COORDINATOR/INTEGRATION-FINAL-GATE-106.md), [approval](HUMAN_APPROVAL-106.json), [kiểm sau merge](../../artifacts/reports/public_search/sol/integration-106.json).
-96testPASS;155requiredhashesPASS;33corefreeze giữ nguyên. Regression630 đã có, code không đổi; fullrerunNOT_RUN. Cảnhbáo2dependencydeprecated giữ nhưlog, không thêmdependency.
- [Hướng dẫn](../../docs/public_search/USER_GUIDE.md), [gói bàn giao](../../docs/public_search/RELEASE_PACKET.md), [demo](../../docs/public_search/DEMO.md). Download do user xácnhận, không bịa captureagent.
- Không còn bước phaseA; chỉ xử lý bug nếu được báo. EXT09/10DEFERRED; mainSG030/033 chưa hoàn thànhhuman researchgates. Không push/publication. Branchworkers được giữ nguyên, không xóa checkout/data.
- Bằng chứngFINAL_PACKET_INDEX105 được giữ nhưsnapshot cũ; dùng FINAL_PACKET_INDEX106 để đối chiếu tài liệu đã cậpnhật humanapproval.

## Lịch sử trước tích hợp

# Human gate106 — 2026-10-01T23:10:58.246939+07:00

Người dùng xác nhận demo/download và chấp thuận tích hợp; [approval](HUMAN_APPROVAL-106.json). Coordinator đang fast-forward master, sau đó kiểm continuity và ghi closeout. PhaseBDEFERRED; SG030/033 giữ nguyên.

## Lịch sử trước xác nhận

# Bàn giao cuối phần agent — 2026-10-01T15:10:53.260921+07:00

**14 task EXT01..08 DONE; EXT09/10 DEFERRED. Không còn worker đang chạy. Human demo, tải tệp thật và merge master PENDING.**

- [Gói bàn giao](../../docs/public_search/RELEASE_PACKET.md), [hướng dẫn](../../docs/public_search/USER_GUIDE.md), [demo/checklist](../../docs/public_search/DEMO.md), [gate cuối](reviews/COORDINATOR/EXT-08-FINAL-GATE-105.md).
- Regression 630 PASS, verifier 7 PASS/CLI0, core freeze33 giữ nguyên. Code được kiểm66264a7; UI fix6a5d4e1, tài liệu sửae3a2730. W5checkpoint62f4b4f gồm manifest/evidence.
- Gemini author; Muse R1 chỉ ra lỗi tài liệu nhưng controller timeout, R2 timeout không report hoàn chỉnh. Coordinator sửa; SOL review thay thế PASS. Giữ lịch sử/attribution đầy đủ.
- Recovery102=10success (5refresh+5cache hai nguồn), old6partialFAIL giữ nguyên, history26=20success6partial. Live provenanceca0344d; không gọi pilot chạy trên bảncode cuối. CacheP95.5674156s vượt đề xuất500ms, n5; không đo relevance/availability dài hạn.
- Preview [localhost8011](http://127.0.0.1:8011/public/ui) còn chạy, exec15061, parent14492/child15220. Store pilot riêng6entries; không phải store mặc định. Tệp browserdownload NOT_VERIFIED, API bytes và Node mock đã kiểm.
- **Bước tiếp duy nhất:** người dùng thử 5 query, lưu bài, mở JSON/BibTeX đã tải thực tế theo DEMO, báo lỗi hoặc xác nhận tích hợp. Sau xác nhận thật, coordinator cập nhật human gate rồi mới xử lý merge. Không chạy lại pilot/test dài nếu code/evidence chưa thay đổi. Không tự mở phaseB hoặc đổi main SG030/033.

## Lịch sử checkpoint

# Checkpoint105 — tài liệu đã sửa, chờ Muse R2

EXT08 REVIEW, target e3a2730. Gemini draft1023cb9; fresh MuseR1 report CHANGES_REQUIRED đã ghi nhưng controller timeout600s (7906d4bd), giữ limitation. Coordinator sửa3docs,6commands khớp exit kỳ vọng gồm thiếu config/overwrite refusal; checker555linksPASS. MuseR2 exec17160 đang chạy file-only concise. Bước tiếp: thu report/log→gateEXT08→checkpoint cuối→human demo/download thật. Preview8011 còn mở. Không merge master/phaseB.

# Checkpoint104 — W5 DONE, EXT08 đang làm

630 regression PASS; verifier7PASS,33 core hashes giữ nguyên. Ba audit và third-check đóng; xem [gate104](reviews/COORDINATOR/EXT-07-W5-GATE-104.md). EXT08 Gemini file-only author→Muse narrative review→coordinator đóng packet. Preview localhost8011 đã restart code66264a7. Human demo/download file PENDING; cacheP95 0.567s vượt proposal;6 historical failures giữ nguyên. Không merge master, không mở EXT09/10.

# W5 checkpoint103 — fixes/re-review

UI6a5d4e1fixed3SOLfindings,25testsPASS; backendSOLfix103activeforMUSEelapsedNone/CLIexit2findings. Gemini125tests+corruptDBPASSexecutedbycoordinator, R3nativependingthirdcheck. NativeMUSEfileonlyreportfollowup. Nextcollect/pinbackendfix→MUSErerun/crossreports→3auditDONE→EXT08docs. HumanPENDING; cacheP95.567sproposalnotmet; historicalfailuresretained. Localdemo127.0.0.1:8011keptforhuman, browserdownloadfileproofNOT_RUN.

# Checkpoint W5 — UI fix + recovery102

Targeted routes/UI24PASS. Gemini file-only delivery nhập và coordinator sửa serializer sources/error/harness/UTF8. Recovery102 verifierPASS,10successful two-source runs; cacheP950.567s chưa đạt500ms. History6FAIL giữ nguyên. Bước kế tiếp: pin commit và giao 3 audit EXT07 trên cùng snapshot; browser export download timeout cần kiểm. Human demoPENDING. Server127.0.0.1:8011 PID11128, pilotstore riêng.

# W4 100 — Evidence DONE; sửa UI entry trước audit W5

- Fresh SOL R3 PASS_EVIDENCE trên5f16994; gate EXT-06-W4-GATE-100. Operational two-source FAIL, release/human demo PENDING.
- Helper /root/public_ui_route_fix đang sửa additive page/link/tests riêng; chưa audit mutable snapshot.
- Gemini/MUSE smoke channels đang chạy; kết quả phải kiểm thực.
- Next executable: thu UI delta/test và pin; dispatch3audit trên cùng snapshot; sửa/re-review findings; EXT-08 docs/checklist. Không merge master trước operational+human demo gate.

# W4 098 — EXT-06 REVIEW; operational hai nguồn FAIL

- User đã xác nhận bộ 5 query và giao tiếp tục đến hết.
- Target immutable `9a20cdf`; packet MUSE/EXT-06-W4-096, manifest W4-REVIEW-098, verifier validation-098.
- 523 regression PASS; 77 focused PASS; 33 primary freeze hashes khớp. 16 canonical runs: 10 explicit OpenAlex success/cache, 6 two-source partial_failure/CLI1, arXiv 4 timeout+2 quota.
- Fresh reviewer `/root/review_ext06_gate` đang re-review. Không author nào sửa implementation.
- Evidence completeness có thể PASS độc lập operational FAIL theo decision096; final release/merge PENDING và human demo PENDING. Không giảm scope một nguồn.
- Next executable: nhận report SOL, sửa findings nếu có; gate evidence rồi dispatch 3 audit W5. EXT-08 sau audit; không merge master trước demo/two-source operational gate.

# W4 090 — EXT-06 coordinator takeover (2026-10-01T10:17:30+07:00)

- MUSE runner `EXT06-W4-MUSE-090` failed exit 1 before producing artifacts; failure evidence `data/public_search/control/runs/437d74cb-7ecf-4f1e-9d26-c7f526737bdd/summary.json`.
- Coordinator owns only adversarial test/verification/report namespace for continuity; production code remains frozen at `b304bf4`.
- EXT-06 is IN_PROGRESS; live pilot will be marked PASS/FAIL/NOT_RUN from actual run, never inferred.

# W3 084 — EXT-05B DONE sau fallback review (2026-10-01T10:09:30+07:00)

- Parent `b304bf4` đã tích hợp delivery SOL `66aad9b`; 485 regression tests pass sau tích hợp.
- Fresh fallback review report PASS không findings tại `reviews/GEMINI/EXT-05B-W3-R1-084.md`; deviation: reviewer là Codex fallback vì Gemini/MUSE channel fail, runtime metadata unavailable.
- Gate: [EXT-05B-W3-FINAL-GATE-084](reviews/COORDINATOR/EXT-05B-W3-FINAL-GATE-084.md). EXT-05B DONE.
- EXT-06 là bước kế tiếp nhưng chưa dispatch trong checkpoint này; chưa có live/pilot claim.

# W3 084 — EXT-05B gate INSUFFICIENT_EVIDENCE (2026-10-01T10:04:30+07:00)

- Implementation SOL đã nhập parent `b304bf4`; 451 regression tests và 21 focused tests pass.
- Không có independent review artifact: Gemini bị Antigravity từ chối, MUSE worker exit 1, fallback SOL không ghi report. Gate coordinator: [EXT-05B-W3-GATE-084](reviews/COORDINATOR/EXT-05B-W3-GATE-084.md).
- EXT-05B giữ REVIEW/INSUFFICIENT_EVIDENCE; EXT-06 chưa mở. Bước tiếp theo duy nhất là chạy fresh reviewer khi kênh worker hoạt động, rồi mới quyết định DONE hoặc sửa findings.

# W3 084 — short fresh review fallback đang chạy (2026-10-01T09:57:30+07:00)

- Lượt Gemini Antigravity bị từ chối; fallback trước không tạo artifact nên đã dừng.
- Fresh short reviewer `/root/review_ext05b_short` đang rà target immutable `b304bf4`; chỉ ghi report/log theo namespace GEMINI, không sửa code.
- EXT-05B vẫn REVIEW, EXT-06 chưa mở.

# W3 084 — fallback fresh review đang chạy (2026-10-01T09:47:30+07:00)

- Gemini Antigravity runner exec 24435 bị `required action denied` trước khi tạo report; run summary đã lưu, không có PASS.
- Để không tự review, đã giao fresh fallback reviewer `/root/review_ext05b_fresh` bằng gpt-6.1-sol/high; target immutable `b304bf4`; chỉ ghi review/log/probes trong namespace GEMINI và phải ghi rõ model fallback.
- EXT-05B vẫn REVIEW; EXT-06 chưa mở.

# W3 084 — EXT-05B chuyển REVIEW, GEMINI đang review fresh (2026-10-01T09:42:40+07:00)

- SOL delivery `66aad9b0751bad10ef7222685977f6c03d0ab5a3` đã nhập parent tại `b304bf4`; packet/log và 451-test evidence tồn tại.
- SOL app thread dừng do usage limit sau implementation trước closeout; coordinator đã hoàn thiện boundary fixes/test/packet trong checkout cô lập và ghi rõ limitation, không coi runtime model là đã xác minh.
- Gemini fresh review đang chạy qua runner exec `24435`, target immutable `b304bf4`, requested `gemini-3.8-flash-high/high`; dispatch `management/public_search/dispatch/GEMINI-W3-EXT05B-R1-084.txt`. Chỉ report/log/probes được ghi.
- Chưa mở EXT-06 và chưa đổi DONE. Bước kế tiếp: nhận verdict Gemini, kiểm report/probes, chạy gate coordinator; nếu PASS mới chuyển DONE.

# W3 084 — EXT-05B đang được SOL triển khai (2026-10-01T09:14:20+07:00)

- User đã giao tiếp tục sau W2 freeze; coordinator mở EXT-05B, chưa mở EXT-06.
- SOL thread `01a0efcc-2062-7d01-b687-10d249b56cbe` đang chạy với requested `gpt-6.1-sol/high` trong checkout `.worktrees/public-sol/scholargraph`; actual model runtime chưa quan sát.
- Dispatch: [SOL-W3-EXT05B-084](dispatch/SOL-W3-EXT05B-084.txt); coordinator log: [DISPATCH-W3-084-SOL](logs/COORDINATOR/DISPATCH-W3-084-SOL.md).
- Owned implementation: service, public routes, additive app router, CLI, config và tests/packet/log đã liệt kê trong dispatch. Worker không sửa board/state/HANDOFF.
- Input checkpoint: parent `749baf1`; EXT-04A/EXT-04B/EXT-05A đã DONE và freeze W2.
- Bước kế tiếp: nhận commit+packet immutable của SOL, chạy kiểm chứng coordinator; chỉ khi đủ evidence mới chuyển REVIEW và giao GEMINI fresh review.

# W2 083 — freeze hoàn tất EXT-04B + EXT-05A

- W2 đã freeze tại [manifest](W2-FREEZE-083.json) sau khi nhập exact UI Gemini R4 `93f0c2d254da3182f51a7ee58cbba028686aa433` và fusion SOL `791bb8c43faa96c0b2161080ab89fe93e1a6b6e1`.
- EXT-05A Gate PASS: [gate](reviews/COORDINATOR/EXT-05A-W2-R5-GATE-083.md). MUSE fresh R5 PASS trên đúng target; 16 pytest + 111 Node + 130 probe độc lập; parent combined 446 PASS. SOL R3 findings đã có adversarial evidence đóng.
- Fixture UI đã pin SHA `21838284af5c7ae7fc3e0bb9443f21108a34bdd6e9aef5408cd50c8eb5cdbd8e`; không còn `NOTMEASURED` trong sidecar.
- Controller MUSE trả exit 1 vì denied final bookkeeping action; report/log/probes đã ghi đủ và được coordinator kiểm tra. Giữ failure điều khiển trong lịch sử, không suy diễn thành product failure.
- Không mở EXT-05B/W3 tự động. Bước tiếp theo chờ user giao rõ.

# W2 082 — fusion đã nhập; UI còn sửa R3

- EXT-04B source/review artifact accepted tại791bb8c,6tệp nhập exact. Childindependent99PASS; parentfirst97PASS2CLI20sTIMEOUT, loggiữriêng và retryđúng2cases; chưaW2combinedgatePASS. Musecontroller TIMEOUTs giữFAIL dùreportartifact đầyđủ verdictPASS; gate giải thích tại reviews/COORDINATOR/EXT-04B-W2-GATE-082.md.
- EXT-05A IN_PROGRESS: GempartialR2TIMEOUT, shortclosefixCLI0PASS, R3sửa4validationgaps/calendar/error evidence/requirednull/URLraw + exportsilentfailure. Next executable: đợiauthorfinish, actualpytest/Node/browser, pinnewtarget freshMUSEreview, fixesrequired, import+fullW2gate+freeze. KhôngW3dispatch.
- Unknownuntracked artifacts/vn_labeling_kit_SG033 (2).zip từngoàiworkflow này: khôngsửa/stage; humanSGgatesgiữnguyên.

# W2 082 — UI R1 cần sửa, fusion regression qua

- EXT-05A REVIEW tại head68b24163: authorGemini native PASS nhưng actualpytest11pass1fail/exit1; Nodeharnesslocator sai. Coordinator8probes JSON dị dạng đều UIaccept/Pydanticreject; paginationcontrols chưa có và quota partial không incompletebanner/old snapshot action. Report coordinator management/public_search/reviews/COORDINATOR/EXT-05A-W2-R1-082.md.
- Fresh Muse UIreview đang chạy controller569bbe8f, chỉ report/probes owned; chưa sửa immutabletarget. SOLfusion428regressionPASS reported, đang closeout packet; đợi finish trước freshMUSEfusionreview.
- Next executable: nhận2delivery/review, gomfindingsUIR2 choGemini nativefix, chạyactualJS/browser; fusion handcalc/adversarialreview. KhôngW3dispatch.

# W2 082 — đăng ký author fusion và UI

- User yêu cầu tiếp bước. EXT-04B SOL và EXT-05A Gemini IN_PROGRESS; chưa dispatch W3.
- Input45pins W0/W1 identical parent+3checkout, worker clean; Gemini freshsmokePASS. Dispatch chi tiết trong dispatch/SOL-W2-082.txt và dispatch/GEMINI-W2-082.txt.
- Coordinator giữ board; worker riêng module; Muse review context mới sau mỗi immutable delivery.
- Next executable: gửi SOL existingthread + freshGemini workCLI, ghi runtimeevidence, chạy actualtests, review/fix/integrate và checkpoint W2.

# W1 081 — hoàn tất sau review và tích hợp

- EXT-02 OpenAlex, EXT-03 arXiv, EXT-04A storage/cache/library/export DONE. W0 đãfreeze14pins. GateW1 mới [manifest](W1-FREEZE-081.json), [gate](reviews/COORDINATOR/W1-FINISH-081.md).
- Parent actual362testsPASS/exit0/36.52s:111contract+transport,106OpenAlex,70arxiv,44store+export,31controller. Loglocal data/public_search/control/w1-081/parent-w1-final-r4.log. FirstcombinedR3fatal -1073741819 giữnguyên riêng, đãsửa metadata/close race và SOL event/proxyreviewPASS.
- Review độc lập: MuseOpenAlexPASS; SOLarxivR5PASS; Gemini storageR2PASS, finalstorageR4SOLPASS sauGemR3eligibilityhostTCPtimeout. Model requests SOL6.1/high, GeminiHigh/high, Musefree/xhigh; Museactualmetadataobserved, SOLactualmetadataunknown.
- Khôngauthor/reviewerCLIactive; SOLappchatidle. Worktreeshash cuối đồng bộ saufreeze, không xóa targetreview/history. MainSGhumangatesunchanged. Usertiếp tục, không đặtpause mới.
- Chưa cóluồng tìmkiếm sảnphẩm hoànchỉnh: nextcards EXT-04B dedup/filter/RRF (SOL) và EXT-05A UI (Gemini) làW2; EXT-05Bservice/routes/CLI saufusion. W2 chưa đượcdispatch trongW1turn. Next executable: đọccard/board, kiểmGemconnection, đăngkýownedpaths/dispatchW2 khi tiếp tụcvòngtiếp.

# W1 081 — storage R4 review đã pin

- Muse R4 nativeauthorCLI0/44focusedtestsPASS, immutableHEAD5b1bd1d. RLock bao quanh toàn bộpublicoperations để metadata/query/close không overlap.
- SOL reviewercontext /root/review_storage_r3_081 re-reviewdelta; chỉ ghi report/log R4 mới. Repo test mới là barrier/subprocess bounded, không gọi đó là deterministic metadata pause; reviewer thiết kế probe event/proxy cho race cụ thể.
- Parent vẫn R3failingcopy ởcheckpoint417ab73; sauSOLPASS importexactR4 rồicombinedretrylogmới, khôngghiđè firstfatal. Bước tiếp này chưahoànthành. NoW2dispatch.

# W1 081 — sửa race SQLite phát hiện lúc tích hợp

- EXT-02/03 DONE. EXT-04A IN_PROGRESS R4: parent combinedsuite crash accessviolation -1073741819 khi close và metadata verification cùng connection; chưa tổng kết361tests, khôngPASS.
- Bằng chứng parent-w1-final.log (control/w1-081) và gate COORDINATOR/EXT-04A-R3-CONCURRENCY-GATE-081.md. MuseR4 runner36193/session ses_f0ea2fb52ffeXlJNnX5Xk3iiHT đang sửa; khôngreviewtargetđangviết.
- Next: thuR4, focusedtests+deterministicconcurrencycase, pin; SOL originalstoragefreshreviewcontext re-reviewdelta; sauPASS mớiretrycombinedsuite/freeze. NoW2dispatch.

# W1 081 — SOL review storage cuối

- EXT-02/03 DONE; EXT-04A REVIEW: MuseR3 6b33c8f/43testsPASS + faultCLI1. Không writer nào đang sửa target.
- Gemini R3 hai attemptsFAIL do eligibilitycheck cần Google profilehost nhưng TCPtimeout; không có R3output, không tựPASS. FreshSOL6.1/high child /root/review_storage_r3_081 được giao finalstorage review, ghi report/log riêng.
- Bước tiếp: SOLPASS -> importexactstorage, combinedsuite và freezeW1; nếu findings trảMusefix. NoW2dispatch.

# W1 081 — storage R3 theo gate chống nuốt lỗi

- EXT-02/03 DONE; parentadapters287testsPASS. EXT-04A IN_PROGRESS: Gemini R2PASS choF1-F3, nhưng coordinatorfaultinjection thấy closefailureCLI0 và evidenceenumerationfallbackFalse.
- MuseR3 đang sửa trong originalsuccessfulretry session ses_f0ea2fb52ffeXlJNnX5Xk3iiHT, runner63883/runbe38c554-50cd-4190-82cc-9609dcf37f50. Không dispatchreview khi author còn viết target.
- Bước executable: thu authorR3, chạy focused/faultsubprocess, pinHEAD; Gemini originalindependentreviewcontextreviewdeltaR3. SauPASS importstorage và combinedsuite, freezeW1. W2 chưadispatch.

# W1 081 — chỉ còn review storage R2

- EXT-02 DONE (MUSE reviewPASS, parent217tests). EXT-03 DONE (SOL R5reviewPASS, parentadapters287tests). Arxiv head049a2b8/source7524a8f đã nhập exactbytes.
- EXT-04A REVIEW: MUSE R2 head e6ba94f/40testsPASS; Gemini independent originalreviewcontext đang re-review runner24299/session0cb3bca2. TargetMUSEcode/tests immutable.
- OpenCode scoped relativepermissions corrected;31controller testsPASS incl denialCLIexit1. Earlier timeout/blockedwrite records retained as failures.
- Next executable: thu review rồi import storage, combinedW1suite và checkpoint. W2 chưa dispatch, main human gates giữ nguyên.

# W1 081 — corrections after independent review

- EXT-02 DONE: OpenAlex exact bytes imported; fresh MUSE review PASS; parent217tests PASS.
- EXT-03 IN_PROGRESS: R4 oldF1-F7 resolved/67testsPASS; SOL re-review finds2P2 wrong request diagnosis and malformed URL ports. Gemini R5 author fix next.
- EXT-04A IN_PROGRESS: author TIMEOUT preserved,34testsPASS; freshGemini review finds cache integrity/timezone/close lock. Coordinator executed temp reviewer probe: both functional defects reproduced. Muse R2 author fix next.
- SupplementalMusecloseout runnerPASS but file writes blocked, no closure artifacts; not completed author acceptance.
- W0 freeze57b6598 unchanged; no W2 dispatch. Next executable: run author corrections, focused suites, pin heads and re-review.

# W1 checkpoint 081 — review và storage author

- EXT-02 REVIEW: SOL author ended HEADfea4992, coordinator106 tests PASS; fresh MUSE review running99663/session ses_f0ed8e478ffePAh4Pr2C06KuSh xhigh.
- EXT-03 REVIEW: GEMINI R1 23fail/15pass -> R2 3fail/40pass -> R3 53pass; head74df8db pinned. Fresh SOL6.1/high reviewer /root/review_w1_arxiv_081 đang xác nhận thêm findings (không tự DONE từ tests). Gemini idle, nhận sửa sau report cuối.
- EXT-04A IN_PROGRESS: MUSE original author56754/session ses_f0ef27bcfffekQkB6r6eCHL40x xhigh đang viết storage/export/tests. Permissions captured at dispatch remain distinct from fresh review scopes.
- W0 freeze57b6598, W1 chưa tích hợp; main SG human gates nguyên trạng. Next: thu review reports, trả author fixes, kiểm storage và giao Gemini fresh review.

# W1 081 — ba author được giao song song

W0 freeze commit 57b6598; 14 hash input khớp cả ba checkout. EXT-02 SOL, EXT-03 GEMINI, EXT-04A MUSE IN_PROGRESS, phạm vi riêng đăng ký trong tasks.json. Gemini chỉ native file tools; coordinator chạy tests/commit. Muse xhigh, Gemini high (max runtime), Sol high. Bước tiếp: thu packet và kiểm tests; reviewer khác author trước DONE.

# W0 freeze 081 — chuẩn bị W1

EXT-01A/B/C DONE sau review độc lập; config policy delta MUSE PASS. Input khóa tại [manifest](W0-FREEZE-081.json), [gate](reviews/COORDINATOR/W0-FREEZE-081.md). Bước tiếp: đồng bộ input/commit checkout rồi dispatch EXT-02 SOL, EXT-03 GEMINI, EXT-04A MUSE song song. User đã tiếp tục, pause cũ không còn hiệu lực.

# Resume 081 — W0 parent policy review

User requested continue. Prior pause revoked. EXT-01A remains REVIEW; MUSE fresh CLI review registered for parent policy/config/test delta. Inputs pinned by policy-review-input-081.json; targets remain immutable during review. W1 depends on this PASS and W0 freeze.

# Checkpoint 080 — tạm dừng theo yêu cầu mới (2026-09-30T12:50:33.836835+07:00)

- Tất cả worker author/reviewer đã kết thúc. Không dispatch thêm.
- EXT-01B và EXT-01C DONE sau sửa và review độc lập PASS.
- EXT-01A REVIEW: author fixes PASS; parent policy config/test delta chưa được MUSE review. W0 chưa freeze.
- Parent code/tests/audit/UX và packets đã nhập; kiểm tra 111 contract/transport, 24 controller, source audit và UX validator PASS. Project checker exit0, 458 links.
- Raw pilot local-only ở data/public_search/muse/source_pilot; không sửa bytes, không live request mới.
- Bước executable sau khi user tiếp tục: review độc lập config policy và hai test adaptations trong parent, rồi freeze W0. Chưa mở W1.
- [Gate checkpoint](reviews/COORDINATOR/W0-R2-GATE.md) · [Log 080](logs/SESSION-20260930-080-CODEX.md)

## Lịch sử checkpoint (được thay thế bởi trạng thái ở trên)

# Bàn giao điều phối phần mở rộng public search

Ngày chuẩn bị: 2026-09-30. Nhánh điều phối: `codex/public-paper-search`.

## Phiên 080 — đóng W0 R2 và tạm dừng theo user (2026-09-30T11:32:14.507259+07:00)

- Ba author fixes R2 đã được nhập parent: SOL contract, MUSE source audit/validator/raw snapshot, GEMINI UX/validator.
- Re-review độc lập PASS: MUSE cho EXT-01A và EXT-01C; SOL fresh-context cho EXT-01B sau F5/F6.
- Coordinator checks: SOL 111 tests exit0; Muse positive exit0 + 7 negatives exit1 và hai temp reproducers F5/F6 exit1; Gemini 13 typed + 16 negative exit1 + title-only/benign positive.
- Policy delta đã nhập config với evidence hash `a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923`. OpenAlex vẫn CONDITIONAL; quota/runtime sustained chưa đo.
- EXT-01A/B/C chuyển DONE với review PASS. W1 chưa dispatch. User yêu cầu tạm dừng sau đợt song song này; `pause_after_current_round=true`.
- Gate: [W0-R2-GATE](reviews/COORDINATOR/W0-R2-GATE.md). Log: [SESSION-080](logs/SESSION-20260930-080-CODEX.md).

## Trạng thái thật

### Phiên 080 — đang tiếp tục W0 R2 (2026-09-30T10:09:24.368313+07:00)

- User “Hãy tiếp tục nhé” đã bỏ pause trước; ba worker được dispatch author fixes R2.
- SOL chat turn01a0f03c-af42-7bc2-94fa-ec586bf28782 hoàn tất: code774aeef,
  packet/logcb64c59, báo111 tests exit0. Task01A REVIEW; chưa re-review/freeze.
- GEMINI sessione3622839-d0fe-425d-87f7-dbf06e7771ac runnerPASS; coordinator chạy
  validator13 typed objects +6 negative CLIexit1. Ba mutation coverage/type vẫn
  exit0 sai, đã dispatch followup file-only; chưa commit/finalacceptance.
- MUSE author audit runner đang chạy, có file đang sửa; không dispatch reviewer
  vào cùng checkout khi author chưa kết thúc.
- Bước executable: thu Muse/Gemini completion, xác minh validators và files;
  pin commits rồi reviewer độc lập. Không mở W1 trước W0 gate.
- Root log: [080](logs/SESSION-20260930-080-CODEX.md); quyền ghi/dispatch tại board.

### Phiên 079 — ĐÃ TẠM DỪNG sau đợt song song theo người dùng

- User yêu cầu làm bước tiếp theo với ba agents, Sol high, Gemini/Muse mức cao nhất.
  Gemini Flash High từ chối max, đã dùng high (cao nhất của đúng model); MUSE free xhigh.
- SOL fresh agent đã review EXT-01B: CHANGES_REQUIRED, report/log commit f6582d9
  trong checkout SOL; 1P1 hash arXiv và 3P2 auth/timing/DOI narrative. Chưa sửa audit.
- MUSE đã giao report/log review01A tại commit 9f70669; còn hai P2 được gate giữ.
  Hai P1 của reviewer bị bác: OpenAlex hỗ trợ Bearer; store factories được spec
  đặt trong store.py chưa triển khai, không phải contracts.py.
- GEMINI ghi sáu UX/fixture outputs, coordinator checkpoint commit cc51ef8. Agent
  terminal ERROR/output token limit; validator CLI1. Typed JSON checks 12PASS +1
  expected invalid không thay validator/negative acceptance.
- **pause_after_current_round=true**: chỉ thu ba outputs đã giao rồi checkpoint/dừng.
  Cả ba agents đã kết thúc lượt, không process điều phối dài còn chạy. Không dispatch
  fixes, UX review/re-review hoặc W1 trước khi người dùng tiếp tục.
- Kết luận [gate W0 R1](reviews/COORDINATOR/W0-R1-GATE.md) và
  [UX validation](reviews/COORDINATOR/EXT-01C-R1-VALIDATION.md). Cả ba task REVIEW,
  chưa DONE/freeze. Implementation chưa nhập parent branch.
- Runtime IDs/owned paths/verdicts tại current_round_assignments trong board;
  [log 079](../logs/SESSION-20260930-079-CODEX.md). Main human gates giữ nguyên.

### Checkpoint mới nhất — thiết lập kênh trực tiếp, phiên 078

- SOL/GEMINI/MUSE đã có packet và commit W0 trong ba checkout sạch; board ghi
  EXT-01A/01B/01C REVIEW. Chưa review độc lập, chưa DONE/freeze/W1.
- [Kênh trực tiếp](CONTROL.md) và [cấu hình](channels.json) đã chuẩn bị; probe thật
  trả nonce đúng từ SOL, Gemini High và Muse miễn phí. Runtime của implementation
  W0 trước probe còn unknown theo packet, không lấy model probe làm bằng chứng cũ.
- OpenCode1.17.7 lỗi SQLite; `meta` lỗi401; free tier yêu cầu CLI>=1.18.0.
  Đã cài CLI1.18.0 riêng trong data/control và dùng kho phiên riêng; free PASS.
- Người dùng xác nhận model miễn phí; ID catalog `opencode/muse-spark-1.3-contributor-free`.
- Bước executable tiếp: coordinator tạo prompt review với head pin trong board,
  gửi SOL review EXT-01B qua chat đã có; gửi MUSE review EXT-01A rồi EXT-01C qua
  runner. Chưa gửi các review này. Không dùng session probe thay quyền ghi review.
- Không scheduler nền. Xem [log 078](../logs/SESSION-20260930-078-CODEX.md).

### Lịch sử setup trước phiên 078

- Người dùng cung cấp ba worker: gpt 6.1 sol, gemini 3.8 flash high, muse spark 1.3; yêu cầu thiết kế task chi tiết có thể chạy song song, review và sửa.
- Đã soạn [task cards và lịch chạy](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md), [board extension](tasks.json) và prompt từng worker.
- Đã tạo ba checkout/branches, xác minh Git/runtime import, cấp quyền W0. Chưa xác nhận ba worker chạy implementation hoặc kết quả online. Reviewer tài liệu [report](reviews/PLANNING-20260930-SOL.md) PASS là review thiết kế.
- Owner/dispatch/session cấp quyền có thật được đăng ký; worker execution session/model runtime chưa xác minh vẫn null. SOL có chat thật, Gemini/Muse chưa xác minh thread.
- Board extension thuộc phạm vi nhánh này; không thay SG-030/033, không chuyển next_task SG-034 hoặc ghi vào routing main đang dùng catalog cũ.

## Nguồn sự thật của extension

- Phạm vi chức năng: [PUBLIC_PAPER_SEARCH_PLAN.md](../../docs/PUBLIC_PAPER_SEARCH_PLAN.md).
- Task, quyền ghi, gate và review: [PUBLIC_PAPER_SEARCH_TASKS.md](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md).
- Status/session/evidence khi chạy: `tasks.json` trong thư mục này, một coordinator extension ghi.
- Con trỏ startup/progress: [state extension](state.json); `session_id` W0 là session cấp quyền coordinator có log thật, `session_kind=coordinator_issued_dispatch`; `worker_execution_session_id` vẫn null trước ACK. Không nhầm dispatch session với worker đã chạy.
- Prompts: [SOL](../../docs/agent_packets/public_search/SOL.md), [GEMINI](../../docs/agent_packets/public_search/GEMINI.md), [MUSE](../../docs/agent_packets/public_search/MUSE.md).

Các EXT là task extension trong board riêng, không phải SG đã đăng ký ở board main. Khi tích hợp vào lịch core, coordinator main ánh xạ sang SG IDs và routing được hỗ trợ bằng quyết định có thật. Không tạo SG IDs giả hoặc ép tên model ngoại vào schema main để vượt checker.

## Bước khởi động W0 trước phiên 079 (lịch sử; không chạy lại khi đang pause)

**Setup đã hoàn tất:** worker đọc [dispatch SOL](dispatch/SOL-W0.md), [GEMINI](dispatch/GEMINI-W0.md), [MUSE](dispatch/MUSE-W0.md), ACK/log rồi bắt đầu card W0 được cấp. Không chờ bước tạo worktree nữa. Python W0 dùng runtime root read-only với PYTHONPATH source riêng, đã kiểm cả ba.

`active_assignments` của extension ghi quyền ghi đã cấp với state authorized_awaiting_ack; status task chưa chuyển IN_PROGRESS khi chưa có ACK. Đây không phải nhận xét worker đang chạy; dispatch cho phép worker bắt đầu và coordinator cập nhật khi nhận ACK. Bản board trong checkout worker là snapshot; luôn đọc root board authoritative.

1. Kiểm tra Git/worktree/process và scope coordinator main trước sửa phần dùng chung.
2. Ba checkout riêng đã có theo mục 3 của task cards, cùng commit dispatch. Không cho workers switch branch trên checkout dùng chung.
3. Dùng kênh trong CONTROL.md để gửi prompt trực tiếp. Kiểm tra checkout/session đang chạy trước gửi; tránh trùng lượt worker thủ công.
4. Coordinator ghi actual model nếu xác minh được, session/log thật, claimed_paths và owner; chỉ lúc worker thực sự nhận việc mới chuyển IN_PROGRESS.
5. Giao đồng thời EXT-01A cho SOL, EXT-01B cho MUSE, EXT-01C cho GEMINI: không có dependency, phạm vi ghi không giao nhau.
6. Review W0, pin contract commit và đồng bộ các checkout trước adapters/storage/UI.

Đầu vào chưa có: arXiv Terms cần kiểm chứng; site HTML B chưa chọn. B vẫn DEFERRED đến khi được giao cụ thể.

## Checkpoint mỗi phiên

Task / role / checkout / branch / base và head commit; model thực tế hoặc unknown; session/log thật; files đã sửa; commands/exit codes/pass-fail thật; evidence/hash; findings; process; việc dở và bước executable kế tiếp.

Không ghi fixture thành kết quả live. Không gửi message sang chat khác nếu chưa có quyền của người dùng; coordinator nhận packet qua file/đầu ra.
