#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Regenerate golden files for the extractor tests.

Usage:
    python3 tests/regen_golden.py [fixture-name ...]

Without arguments, regenerates golden files for all fixtures listed in
tests/test_extract_commands.py::GOLDEN_CASES. Run this whenever a change to
extract_commands.py intentionally alters generated output, and review the
resulting diff carefully.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT = REPO_ROOT / "extract_commands.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = Path(__file__).resolve().parent / "golden"


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_commands", EXTRACT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    ec = _load_module()
    names = sys.argv[1:]
    if not names:
        spec = importlib.util.spec_from_file_location(
            "test_module", Path(__file__).resolve().parent / "test_extract_commands.py"
        )
        test_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_module)
        names = test_module.GOLDEN_CASES

    for name in names:
        fixture = FIXTURES / f"{name}.md"
        source = fixture.read_text(encoding="utf-8")
        script = ec.build_script(fixture, ec.extract_shell_blocks(source))
        GOLDEN.mkdir(parents=True, exist_ok=True)
        (GOLDEN / f"{name}.sh").write_text(script, encoding="utf-8")
        print(f"Regenerated {name}.sh")


if __name__ == "__main__":
    main()
