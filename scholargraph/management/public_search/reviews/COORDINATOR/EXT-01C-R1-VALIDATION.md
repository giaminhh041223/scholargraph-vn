# Kiểm chứng coordinator — EXT-01C R1

- Không phải review độc lập của MUSE. Đây là kiểm chứng đầu ra native-file GEMINI
  trong đợt hiện tại, để checkpoint trước khi tạm dừng theo user.
- Contract SOL 1.0.0, implementation pin93f8c75; commit reviewer f6582d9 sau đó chỉ
  thêm hai report/log SOL, không đổi source contract đã import.
- Gemini đã ghi sáu owned outputs. CLI lượt cuối ERROR vì output token limit;
  controller FAIL exit1, không coi partial final response là task PASS. Artifacts
  đã tồn tại được giữ lại; không gọi thêm lượt sửa sau yêu cầu pause.

## Kết quả thực tế

- Lệnh `.venv/Scripts/python.exe tests/fixtures/public_search/gemini/validate_fixtures.py`
  tại project GEMINI: **exit1**, 10 datetime_type errors ngay envelope đầu.
- Root recursive typed JSON validation theo các node `envelope`, `library_entry`,
  `invalid_request_payload`: **12 positive objects PASS + 1 expected invalid request**;
  0 unexpected errors. Dùng model_validate_json trên JSON serialized theo contract,
  không sửa schema hoặc fixture để vượt lỗi.
- Evidence local:
  `data/public_search/control/verification/20260930-R1-GEMINI/verification.json`,
  `validator.stdout`, `validator.stderr`; run agent
  `data/public_search/control/runs/fe80edf0-d827-41b9-9279-640d8a40dcea/summary.json`.

## Việc chưa đạt trong validator/packet

1. `validate_fixtures.py` dùng model_validate(dict) cho timestamp JSON strings
   trong strict models. Contract yêu cầu model_validate_json cho wire/persisted
   data; đây là nguyên nhân CLI positive thất bại. Title-only constructor cũng
   truyền retrieved_at string vào Python validation path và chưa tới được vì
   positive validation đã fail. **Phải sửa trước acceptance.**
2. Leakage case chỉ kiểm chuỗi sentinel rồi `pass`, không gọi validator trên
   bad_file, không có nhánh fail nếu không phát hiện, không subprocess exit1.
   Không dùng nó làm bằng chứng chống leakage hoặc negative gate đã pass.
3. Missing-file/field/score/count negatives hiện là catches trong cùng process,
   chưa có subprocess cases exit1 như yêu cầu dispatch; chúng NOT_REACHED trong
   lệnh hiện tại vì positive validation fail. Packet phải giữ chúng NOT_RUN.
4. Validator ghi “100% examples” nhưng enumerate các tên cố định, không chứng minh
   không bỏ qua example/subcase mới; cần reconciled inventory hoặc traversal typed
   đầy đủ. Đây là nhận xét static, chưa sửa code và chưa chạy regression cho case
   thêm mới trong lượt này.
5. Packet nói “user denied permission”: nguyên nhân thực là headless CLI soft-deny
   command theo runtime policy, không có human denial. Các claim “không còn mismatch”
   phải gắn scope typed fixture JSON ở trên; chưa được suy thành CLI/negative PASS.

EXT-01C vẫn REVIEW, review độc lập chưa thực hiện. Sau user resume, GEMINI sửa
validator/packet và chạy positive/adversarial subprocess; MUSE review snapshot mới.
Không freeze contract hoặc mở W1 ở checkpoint này.
