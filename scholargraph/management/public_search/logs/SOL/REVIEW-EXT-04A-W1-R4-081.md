# Log SOL re-review storage R4 081

- Thời điểm 2026-09-30T16:19:13.032179+07:00; reviewer context ban đầu được dùng lại, requested SOL6.1/high, actual runtime metadata unknown. Target immutable HEAD `5b1bd1db235a4c4f7865f36bc5c9e621c07d31dc`, base R3 `6b33c8fe1f5817d38960ac6db29ac62af899da3b`.
- Đã đọc gate fatal R3/log stack thật, parent checkpoint, summary R4 tác giả, toàn SQLiteStore class/diff/new test. AST inventory: __init__1/load_cache3/save_snapshot9/read_snapshot2/save_paper8/list_library2/close1 = 26 references; 25 shared-handle uses được đối chiếu scope RLock.
- Before/after HEAD/status sạch, 8 scope hashes bất biến/14 W0 matches. R3 report/log unchanged; [report R4](../../reviews/SOL/EXT-04A-W1-R4-081.md) có bảng đầy đủ.

## Lệnh và kết quả thật

Cwd targeted pytest: target nested scholargraph. Cwd probe: parent. Environment cho cả hai:
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph/src`. Runtime `D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe`.

```powershell
& 'D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe' -m pytest -p no:cacheprovider tests/unit/test_public_store.py -k 'concurrent_read_write or close_concurrent_bounded or metadata_close_interleaving_controlled or close_fault_structured_failure_and_retry or check_storage_close_fault_cli_exit1 or has_evidence_enumeration_fault_fails_loud or close_handles' -q
```

Chunk 55367d exit0: `7 passed, 28 deselected in 1.76s`. 3 R3 resource-error regressions PASS (CLI error subprocess1); new repo concurrency case chỉ bounded barrier, không metadata pause deterministic.

Probe dưới đây được chạy bằng PowerShell single-quoted here-string đưa vào absolute runtime `python.exe -` (chunk 2e7f9a). Temp only, từng child timeout20s. R3 lấy đúng code bằng read-only git show, không checkout/sửa Git. Proxy suppress real concurrent close khi overlap ở R3; R4 close connection thật sau release. Source tái lập đầy đủ:

```python
import json,os,subprocess,sys
child = r"""import json,subprocess,sys,tempfile,threading,types
from pathlib import Path
from scholargraph.public_search import store as current
mode=sys.argv[1]; repo=Path('D:/Web_mining_20261/scholargraph/.worktrees/public-muse')
if mode=='R3':
 code=subprocess.check_output(['git','show','6b33c8fe1f5817d38960ac6db29ac62af899da3b:scholargraph/src/scholargraph/public_search/store.py'],cwd=repo)
 s=types.ModuleType('scholargraph.public_search.probe_r3');s.__package__='scholargraph.public_search'
 exec(compile(code,'immutable_R3_store','exec'),s.__dict__)
else: s=current
entered=threading.Event();release=threading.Event();closing=threading.Event();close_call=threading.Event()
timeline=[];errors=[];guard=threading.Lock()
def mark(name):
 with guard:timeline.append(name)
class ObservedLock:
 def __init__(self,real):self.real=real
 def __enter__(self):
  if threading.current_thread().name=='closer':closing.set()
  self.real.acquire();return self
 def __exit__(self,*args):self.real.release()
class Cursor:
 def __init__(self,real):self.real=real
 def __iter__(self):
  mark('metadata_inflight');entered.set()
  assert release.wait(5),'metadata release timed out'
  mark('metadata_released');return iter(self.real)
class Proxy:
 def __init__(self,real):self.real=real;self.overlap=False
 def execute(self,sql,*args):
  cursor=self.real.execute(sql,*args)
  return Cursor(cursor) if sql=='SELECT key, value FROM metadata' else cursor
 def close(self):
  self.overlap=entered.is_set() and not release.is_set()
  mark('close_called');close_call.set()
  if self.overlap:return
  self.real.close()
def worker(action):
 try:action()
 except BaseException as exc:
  with guard:errors.append(type(exc).__name__+':'+str(exc))
with tempfile.TemporaryDirectory(prefix='sg-sol-r4-child-') as tmp:
 root=Path(tmp);cfg=s.load_config(Path('D:/Web_mining_20261/scholargraph/configs/public_search.json'))
 obj=s.initialize_store(root,cfg);real=obj._conn;proxy=Proxy(real)
 obj._conn=proxy;obj._lock=ObservedLock(obj._lock)
 reader=threading.Thread(name='reader',target=worker,args=(lambda:obj.list_library(offset=0,limit=1),),daemon=True)
 closer=threading.Thread(name='closer',target=worker,args=(obj.close,),daemon=True)
 reader.start()
 try:
  assert entered.wait(5),'reader did not reach metadata'
  closer.start();assert closing.wait(5),'closer did not attempt lock'
  early=close_call.wait(0.3)
 finally:release.set()
 reader.join(5);closer.join(5)
 assert not reader.is_alive() and not closer.is_alive(),'thread hung'
 assert not errors,errors
 assert early==(mode=='R3'),(mode,early,timeline)
 assert proxy.overlap==(mode=='R3'),(mode,proxy.overlap,timeline)
 assert obj._closed is True
 try:obj.list_library(offset=0,limit=1)
 except s.StoreError as exc:assert exc.error.kind=='storage'
 else:raise AssertionError('post-close operation succeeded')
 real.close()
 print(json.dumps({'mode':mode,'close_before_metadata_release':early,'overlap_close_safely_suppressed':proxy.overlap,'timeline':timeline,'errors':errors,'closed':obj._closed}))
"""
results=[]
for mode in ['R3','R4']:
 proc=subprocess.run([sys.executable,'-c',child,mode],env=dict(os.environ),capture_output=True,text=True,timeout=20)
 assert proc.returncode==0,(mode,proc.returncode,proc.stdout,proc.stderr)
 assert proc.stderr=='',proc.stderr
 results.append(json.loads(proc.stdout))
print(json.dumps({'controlled_metadata_close_subprocesses':results}))
```

Output thực:
```json
{"controlled_metadata_close_subprocesses":[{"mode":"R3","close_before_metadata_release":true,"overlap_close_safely_suppressed":true,"timeline":["metadata_inflight","close_called","metadata_released"],"errors":[],"closed":true},{"mode":"R4","close_before_metadata_release":false,"overlap_close_safely_suppressed":false,"timeline":["metadata_inflight","metadata_released","close_called"],"errors":[],"closed":true}]}
```

Python collector exit0; 2/2 subprocess assertions PASS/exit0, stderr rỗng. Không crash native được gây ra ở R3; đây là safe reproduction of close attempt và fixed ordering ở R4. Không chứng minh mọi interleaving.

Verdict PASS cho P1 scope; coordinator nhập exact bytes R4 và chạy combined parent suite/log mới. Chưa có parent integration PASS; fatal R3/original review histories giữ nguyên. Reviewer không sửa source/tests/config/fixture/board/Git hoặc dispatch.

Closeout `scripts/check_project.ps1` thực chạy từ parent (chunk e6d5df): exit0, 53 tasks/489 local Markdown links/53 routes/7 lanes/79 sessions; WARN SG-034 awaits SG-033 giữ nguyên human dependency.
