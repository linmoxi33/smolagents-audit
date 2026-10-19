"""Verify every uploaded file matches the local bytes.

Blob-hash comparison is unreliable here: `.gitattributes` sets `eol=lf`, so the
locally computed git hash can differ from the raw bytes the API stored even when
the content is identical. Fetch the actual content and compare bytes instead.
"""

from __future__ import annotations

import base64
import json
import pathlib
import subprocess
import sys

REPO = "linmoxi33/smolagents-audit"
ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


def list_remote() -> list[str]:
    proc = subprocess.run(
        ["gh", "api", f"repos/{REPO}/git/trees/main?recursive=1", "--jq",
         '.tree[] | select(.type=="blob") | .path'],
        capture_output=True, text=True, encoding="utf-8",
    )
    return [x for x in proc.stdout.splitlines() if x.strip()]


def fetch(path: str) -> bytes:
    proc = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{path}?ref=main", "--jq", ".content"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return base64.b64decode(proc.stdout.strip())


remote = list_remote()
print(f"remote files: {len(remote)}")

mismatch = []
missing_local = []
for rel in remote:
    local = ROOT / rel
    if not local.exists():
        missing_local.append(rel)
        continue
    expect = local.read_bytes()
    actual = fetch(rel)
    if expect != actual:
        mismatch.append({"path": rel, "local": len(expect), "remote": len(actual)})

print(f"local missing : {len(missing_local)}")
print(f"byte mismatch : {len(mismatch)}")

if missing_local:
    for m in missing_local:
        print(f"  ! missing locally: {m}")
if mismatch:
    for m in mismatch:
        print(f"  ! differs: {m['path']} local={m['local']}B remote={m['remote']}B")

ok = not mismatch and not missing_local
print()
print("RESULT:", "ALL FILES BYTE-IDENTICAL" if ok else "MISMATCH FOUND")
raise SystemExit(0 if ok else 1)
