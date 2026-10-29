# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""The CI checker must reject absent, late, or truncated licence identifiers."""
import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_spdx", Path(__file__).resolve().parents[1] / "scripts" / "check_spdx.py",
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize("line", range(1, 6))
def test_header_is_accepted_in_first_five_lines(tmp_path, line):
    path = tmp_path / "source.py"
    path.write_text("# preamble\n" * (line - 1) + f"# {checker.IDENTIFIER}\n")
    assert checker.has_header(path)


@pytest.mark.parametrize("text", [
    "", "print('no header')\n",
    "# preamble\n" * 5 + f"# {checker.IDENTIFIER}\n",
    f"# {checker.IDENTIFIER[:-1]}",
])
def test_missing_late_or_truncated_identifier_is_rejected(tmp_path, text):
    path = tmp_path / "source.py"
    path.write_text(text)
    assert not checker.has_header(path)


def test_source_discovery_checks_tests_and_skips_generated_files(tmp_path, monkeypatch):
    included = ["src/pkg/core.py", "tests/test_core.py", "scripts/check.py"]
    skipped = ["src/cache/generated.py", "tests/__pycache__/generated.py", "other.py"]
    for name in included + skipped:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    assert checker.source_files() == sorted(tmp_path / name for name in included)


def test_gate_status_follows_header_validity_and_fix_preserves_content(tmp_path, monkeypatch, capsys):
    path = tmp_path / "tests" / "sample.py"
    path.parent.mkdir()
    body = "print('fixture')\n"
    path.write_text(f"# {checker.IDENTIFIER}\n" + body)
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_spdx.py"])
    assert checker.main() == 0
    assert "all 1 source files" in capsys.readouterr().out
    path.write_text(body)
    assert checker.main() == 1
    assert str(Path("tests", "sample.py")) in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["check_spdx.py", "--fix"])
    assert checker.main() == 0
    assert path.read_text() == f"# {checker.IDENTIFIER}\n" + body
    assert checker.has_header(path)
