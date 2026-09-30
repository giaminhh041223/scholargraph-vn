# EXT-01A R2 — SOL response

- Finding scope: two accepted findings only.
- Checkout: `D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/`
- Branch: `codex/public-search-sol`
- Parent review snapshot: `f6582d985e0be2555d8368716d82a0766d16ffc9`
- Fix commit: `774aeef0bfc42c636779f739c3fb4fbb8e9e37c4`
- Contract remains `1.0.0`; actual model/effort remains unknown.

## Changes

1. `SourceResult` now rejects `not_requested` with `server` or `bounded_pool`; `none` is required and tested.
2. `CONTRACT.md` states arXiv 3-second politeness via process-local `RateState` only, with no distributed lock/cross-machine guarantee and an explicit operational gap before multi-worker/machine scale.

## Verification

`python -m pytest tests/unit/test_public_contracts.py tests/unit/test_public_transport.py -q` → **111 passed**, exit 0.
`git diff --check` → exit 0.

No live source, qrels, labels, env or other checkout was read/written. No rejected findings were processed. Request MUSE re-review of commit `774aeef`.
