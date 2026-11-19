"""The documentation site builds from the guides with no broken link, anchor, or image."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _node() -> str | None:
    node = shutil.which("node")
    if node is None:
        return None
    major = (
        subprocess.run([node, "--version"], capture_output=True, text=True)
        .stdout.lstrip("v")
        .split(".")[0]
    )
    return node if major.isdigit() and int(major) >= 22 else None


def test_the_site_builds() -> None:
    node = _node()
    if node is None:
        pytest.skip("Node 22 or newer is not installed")
    built = subprocess.run(
        [node, str(REPO / "scripts" / "site" / "build.mjs")],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert built.returncode == 0, built.stderr or built.stdout
    site = REPO / "site"
    assert (site / "index.html").exists()
    assert (site / "api-reference.html").exists()
    assert "GovWren" in (site / "getting-started.html").read_text(encoding="utf-8")
