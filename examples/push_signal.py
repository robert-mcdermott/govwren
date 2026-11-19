#!/usr/bin/env python3
"""Push a result onto a GovWren record, where it is kept as evidence.

For an evaluation harness, a monitoring job, or a scanner to hand in what it found.

    export GOVWREN_URL=https://ai.example.org
    export GOVWREN_TOKEN=gw_...          # a token with the signal scope
    python3 push_signal.py MDL-0007 fail "Nightly accuracy check" \\
        --source "Eval harness" --kind evaluation \\
        --summary "Accuracy fell from 0.94 to 0.81 on the held-out set." \\
        --url https://eval.example.org/runs/881

Send a summary, never data. The result is one of pass, warn, fail, or info. On warn or
fail, the record's owners are told.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def push(base: str, token: str, signal: dict[str, str]) -> dict[str, object]:
    request = urllib.request.Request(  # noqa: S310
        f"{base.rstrip('/')}/api/v1/signals",
        data=json.dumps(signal).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as answer:  # noqa: S310
        return json.load(answer)["data"]  # type: ignore[no-any-return]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("ref", help="the record, such as MDL-0007 or UC-0042")
    parser.add_argument("result", choices=["pass", "warn", "fail", "info"])
    parser.add_argument("title", help="what was checked")
    parser.add_argument("--source", required=True, help="the tool sending this")
    parser.add_argument(
        "--kind", default="other", choices=["evaluation", "monitoring", "scan", "other"]
    )
    parser.add_argument("--summary", default="")
    parser.add_argument("--url", default="", help="where the full result can be read")
    parser.add_argument("--good-until", default="", help="the day this result stops being current")
    args = parser.parse_args()
    base, token = os.environ.get("GOVWREN_URL"), os.environ.get("GOVWREN_TOKEN")
    if not base or not token:
        print("Set GOVWREN_URL and GOVWREN_TOKEN.", file=sys.stderr)
        return 2
    signal = {key: value for key, value in {
        "ref": args.ref, "result": args.result, "title": args.title, "source": args.source,
        "kind": args.kind, "summary": args.summary, "url": args.url, "good_until": args.good_until,
    }.items() if value}  # fmt: skip
    try:
        made = push(base, token, signal)
    except urllib.error.HTTPError as error:
        print(f"GovWren refused it ({error.code}): {error.read().decode()[:300]}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"GovWren could not be reached: {error}", file=sys.stderr)
        return 2
    print(f"Kept as {made['evidence']} on {made['record']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
