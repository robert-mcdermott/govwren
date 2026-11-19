#!/usr/bin/env python3
"""Ask GovWren whether a reference is approved, before another process goes ahead.

A purchasing form, an ethics application, or a data access request asks for a GovWren
reference. The system that receives it runs this check and proceeds only on a yes.

    export GOVWREN_URL=https://ai.example.org
    export GOVWREN_TOKEN=gw_...          # a token with the checkpoint scope is enough
    python3 checkpoint.py UC-0042 protected

It prints one line saying yes or no and why, and exits with 0 for yes, 1 for no, and 2 if
GovWren could not be asked. Treat 2 as "not yet": never as a yes.

Standard library only. Copy `ask` and `decide` into your own system if that is easier.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def ask(base: str, token: str, ref: str, data_class: str | None = None) -> dict[str, Any] | None:
    """The checkpoint's answer for a reference, or None if there is no such record."""
    address = f"{base.rstrip('/')}/api/v1/checkpoint/{urllib.parse.quote(ref.strip().upper())}"
    if data_class:
        address += "?" + urllib.parse.urlencode({"data_class": data_class})
    request = urllib.request.Request(address, headers={"Authorization": f"Bearer {token}"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:  # noqa: S310
            return json.load(answer)["data"]  # type: ignore[no-any-return]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def decide(answer: dict[str, Any] | None, ref: str) -> tuple[bool, str]:
    """Whether to go ahead, and a sentence to show the person who gave the reference."""
    if answer is None:
        return False, f"There is no record {ref}. Check the reference."
    if "allowed" in answer:
        if answer["allowed"]:
            until = f" until {answer['approved_until']}" if answer.get("approved_until") else ""
            return True, f"{ref} is approved for {answer['asked_data_class']} data{until}."
        if answer.get("approved"):
            covers = answer.get("data_class_label") or "less sensitive"
            return False, f"{ref} is approved, but only for data up to {covers}."
    elif answer.get("approved"):
        until = f" until {answer['approved_until']}" if answer.get("approved_until") else ""
        return True, f"{ref} is approved{until}."
    standing = str(answer.get("status") or "not approved").replace("_", " ")
    return False, f"{ref} is not approved. Its standing is: {standing}."


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2
    base, token = os.environ.get("GOVWREN_URL"), os.environ.get("GOVWREN_TOKEN")
    if not base or not token:
        print("Set GOVWREN_URL and GOVWREN_TOKEN.", file=sys.stderr)
        return 2
    ref = sys.argv[1]
    try:
        answer = ask(base, token, ref, sys.argv[2] if len(sys.argv) == 3 else None)
    except (OSError, ValueError, KeyError) as error:
        print(f"GovWren could not be asked: {error}", file=sys.stderr)
        return 2
    go, why = decide(answer, ref)
    print(("Yes. " if go else "No. ") + why)
    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
