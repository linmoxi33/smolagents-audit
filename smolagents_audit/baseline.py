"""Baseline of known findings.

The audit is *supposed* to find problems — that is its job. A CI gate that goes
red because the known findings still exist tells you nothing and trains people
to ignore red. So the gate compares against this file: it fails only when a
finding appears that is not listed here.

Refreshing the baseline is a deliberate act, and it should come with a note in
the commit message explaining why the finding is now acceptable.
"""

from __future__ import annotations

import json
import pathlib

BASELINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "baseline.json"

# Case ids whose MISMATCH status is a known, documented property of the audited
# version — not a regression. Each one is explained in README.md.
KNOWN_MISMATCHES = {
    # README advertises video input; `video` has zero hits in the package source.
    "C8",
    # Deny-list is 9 names; subprocess family and Windows' nt.system are absent.
    "C11",
    # Documented CLI example (`--imports pandas numpy`) grants file I/O.
    "B1",
    "B2",
    "B3",
    # Granting os/subprocess yields command execution.
    "E1",
    "E2",
}


def load() -> dict:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {"smolagents": None, "known_mismatches": sorted(KNOWN_MISMATCHES)}


def save(version: str) -> None:
    data = {"smolagents": version, "known_mismatches": sorted(KNOWN_MISMATCHES)}
    BASELINE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
