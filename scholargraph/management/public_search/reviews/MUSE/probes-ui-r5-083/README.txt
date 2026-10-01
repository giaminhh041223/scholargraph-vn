R5-083 probes (reviewer-owned, target read-only, HEAD 93f0c2d254da3182f51a7ee58cbba028686aa433)
- probe01-r5-source-calendar.js : 51 checks (Finding-1 9-key presence + nullable types, Finding-2 calendar/offset, safe-URL spot)
- probe02-r5-save-race-xss-export.js : 18 checks (Finding-3 idempotent original-snapshot + mismatch loud, race/XSS/pagination/stale/detail/export)
- probe03-r5-python-strict.py : 61 checks (Python SourceResult strict, JSON calendar, LibraryEntry, malformed 25, safe_url, fixture, no-skip, Node/CLI exit-1 in temp paths)
Run from reviewer checkout D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph :
  node management/public_search/reviews/MUSE/probes-ui-r5-083/probe01-r5-source-calendar.js
  node management/public_search/reviews/MUSE/probes-ui-r5-083/probe02-r5-save-race-xss-export.js
  $env:PYTHONPATH="D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/src"; python management/public_search/reviews/MUSE/probes-ui-r5-083/probe03-r5-python-strict.py
No target writes. Destructive JSON in tempfile.TemporaryDirectory only.
Native (target workdir):
  pytest tests/unit/test_public_ui.py -v : 16 passed in 5.32s
  node harness : TOTAL 111 PASSED 111 FAILED 0 exit 0
