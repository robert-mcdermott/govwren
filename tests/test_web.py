"""Rules the web app is held to (ADR-0004). More arrive with the design system."""

from __future__ import annotations

import re

from govwren.api.static import WEB_ROOT


def test_no_inline_script_or_style() -> None:
    for page in WEB_ROOT.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f"inline script in {page.name}"
        assert "<style" not in html, f"inline style in {page.name}"
        assert not re.search(r"\sstyle\s*=", html), f"style attribute in {page.name}"
        assert not re.search(r"\son[a-z]+\s*=", html), f"inline handler in {page.name}"


def test_nothing_is_loaded_from_another_origin() -> None:
    for file in WEB_ROOT.rglob("*"):
        if file.suffix in {".html", ".css", ".js"}:
            text = file.read_text(encoding="utf-8")
            assert not re.search(r"""(src|href)\s*=\s*["'](https?:)?//""", text), file.name
            assert not re.search(r"""(import|from)\s+["']https?://""", text), file.name
            assert "url(http" not in text, file.name


def test_scripts_never_parse_data_as_html() -> None:
    forbidden = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(")
    for script in WEB_ROOT.rglob("*.js"):
        text = script.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{word} in {script.name}"
