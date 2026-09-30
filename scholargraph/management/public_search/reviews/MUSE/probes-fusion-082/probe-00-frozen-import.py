"""Independent probe 00: frozen pins + target clean + actual import path.
Uses absolute runtime D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe
with PYTHONPATH=D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/src.
Read-only: no writes to target, no network, no secrets.
"""
import hashlib
import json
import subprocess
from pathlib import Path

MUSE_ROOT = Path("D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph")
TARGET_ROOT = Path("D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph")
TARGET_HEAD = "791bb8c43faa96c0b2161080ab89fe93e1a6b6e1"

def main():
    w0 = json.loads((MUSE_ROOT / "management/public_search/W0-FREEZE-081.json").read_text(encoding="utf-8"))
    w1 = json.loads((MUSE_ROOT / "management/public_search/W1-FREEZE-081.json").read_text(encoding="utf-8"))
    print(f"W0 pins={len(w0['sha256'])} W1 pins={len(w1['sha256'])}")
    overlap = [k for k in w0["sha256"] if k in w1["sha256"]]
    print(f"OVERLAP={overlap}")
    combined = {}
    combined.update(w0["sha256"])
    combined.update(w1["sha256"])
    print(f"UNION={len(combined)} (expect 45)")
    assert len(combined) == 45, f"union {len(combined)} != 45"
    bad = []
    for key in sorted(combined):
        expected = combined[key]
        actual = hashlib.sha256((TARGET_ROOT / key).read_bytes()).hexdigest()
        ok = (actual == expected)
        print(f"{'OK ' if ok else 'BAD'} {key}")
        if not ok:
            print(f"  expected={expected}")
            print(f"  actual  ={actual}")
            bad.append(key)
    print(f"frozen_match={len(combined)-len(bad)}/{len(combined)}")
    assert not bad, f"frozen mismatch: {bad}"
    # target HEAD + clean (read-only git query)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(TARGET_ROOT.parent),
                          capture_output=True, text=True, timeout=20)
    print(f"target_HEAD={head.stdout.strip()} exit={head.returncode}")
    assert head.stdout.strip() == TARGET_HEAD, "HEAD drift"
    status = subprocess.run(["git", "status", "--short"], cwd=str(TARGET_ROOT.parent),
                            capture_output=True, text=True, timeout=20)
    print(f"target_status={status.stdout!r} exit={status.returncode}")
    assert status.stdout.strip() == "", f"target dirty: {status.stdout!r}"
    diffcheck = subprocess.run(["git", "diff", "5c41e37da38577a16dbedec18afd94b149647575..HEAD", "--check"],
                               cwd=str(TARGET_ROOT.parent), capture_output=True, text=True, timeout=20)
    print(f"diff_check_exit={diffcheck.returncode} out={diffcheck.stdout!r} err={diffcheck.stderr!r}")
    # owned-only scope: only these 6 paths changed vs W1 base
    names = subprocess.run(["git", "diff", "--name-only", "5c41e37da38577a16dbedec18afd94b149647575..HEAD"],
                           cwd=str(TARGET_ROOT.parent), capture_output=True, text=True, timeout=20)
    print("changed_paths:")
    print(names.stdout)
    # import path proof (PYTHONPATH must be target/src externally)
    import scholargraph.public_search.fusion as f
    print(f"fusion_file={f.__file__}")
    print(f"FUSION_VERSION={f.FUSION_VERSION} RRF_K={f.RRF_K}")
    assert "public-sol" in f.__file__.replace("\\", "/"), "wrong import path"
    assert f.FUSION_VERSION == "fusion-1.0.0" and f.RRF_K == 60
    print("PROBE00 PASS")

if __name__ == "__main__":
    main()
