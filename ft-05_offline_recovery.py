#!/usr/bin/env python3
"""Deprecated: use `python3 ft-03.py` (Scenario 1 is included in the master suite)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_ft03():
    path = Path(__file__).resolve().parent / "ft-03.py"
    spec = importlib.util.spec_from_file_location("ft_03", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ft-03.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ft03 = _load_ft03()
    ft03._heading("FT-05 (legacy wrapper) — running FT-03 Scenario 1 only")
    ft03.preflight_backend_health()
    ft03.scenario_01_offline_edge_recovery()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
