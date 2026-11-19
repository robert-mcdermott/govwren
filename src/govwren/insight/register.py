"""The transparency register: chosen approved uses, published as static pages (RPT-09).

Governance chooses which uses appear and writes the words readers will see. The pages are
plain files with no script, made from those words and a few facts from the record, and can
be put on any web server. A use whose approval is not in force is held back until it is.
"""

from __future__ import annotations

import io
import zipfile
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Decision, OrgUnit, RegisterEntry, Review, UseCase
from govwren.events import audit
from govwren.inventory import records
from govwren.program import branding, vocab

IN_FORCE = ("approved", "approved_with_conditions")
_FIXED = (2000, 1, 1, 0, 0, 0)


def _entry_of(session: Session, use_case: UseCase) -> RegisterEntry | None:
    return session.scalars(
        select(RegisterEntry).where(RegisterEntry.use_case_id == use_case.id)
    ).first()


def put(
    session: Session, principal: Principal, use_case: UseCase, values: dict[str, Any]
) -> RegisterEntry:
    """Put a use on the register, or change the words shown for it."""
    if not principal.governs:
        raise PermissionDenied("Governance decides what is on the register.")
    title = str(values.get("title") or "").strip()
    description = str(values.get("description") or "").strip()
    errors: dict[str, str] = {}
    if not title:
        errors["title"] = "Give it a title readers will understand."
    elif len(title) > 200:
        errors["title"] = "Keep the title to 200 characters."
    if not description:
        errors["description"] = "Describe the use in plain words."
    elif len(description) > 4000:
        errors["description"] = "Keep the description to 4,000 characters."
    entry = _entry_of(session, use_case)
    if entry is None and use_case.status not in IN_FORCE:
        errors["ref"] = "Only a use with an approval in force can be put on the register."
    if errors:
        raise Invalid("The register was not changed.", errors)
    with audit.operation(session, "register.put"):
        if entry is None:
            entry = RegisterEntry(
                use_case_id=use_case.id, added_by=principal.account_id, added_at=utc_now()
            )
            session.add(entry)
        entry.title = title
        entry.description = description
        entry.show_unit = bool(values.get("show_unit", True))
        session.flush()
    return entry


def remove(session: Session, principal: Principal, use_case: UseCase) -> None:
    if not principal.governs:
        raise PermissionDenied("Governance decides what is on the register.")
    entry = _entry_of(session, use_case)
    if entry is None:
        raise NotFound(f"{use_case.ref} is not on the register.")
    with audit.operation(session, "register.remove"):
        session.delete(entry)
        session.flush()


def _facts(session: Session) -> list[dict[str, Any]]:
    """Each entry with the facts drawn from its record, newest first."""
    rows = session.execute(
        select(RegisterEntry, UseCase)
        .join(UseCase, UseCase.id == RegisterEntry.use_case_id)
        .order_by(RegisterEntry.id.desc())
    ).all()
    ids = [use.id for _entry, use in rows]
    systems = records.systems_of(session, ids)
    units = dict(session.execute(select(OrgUnit.id, OrgUnit.name)).all())  # type: ignore[arg-type]
    names = dict(session.execute(select(Account.id, Account.display_name)).all())  # type: ignore[arg-type]
    domains = vocab.labels(session, "domains")
    dates = {
        use_id: (first, last)
        for use_id, first, last in session.execute(
            select(Review.subject_id, func.min(Decision.decided_at), func.max(Decision.decided_at))
            .join(Decision, Decision.review_id == Review.id)
            .where(
                Review.subject_type == "use_case",
                Review.subject_id.in_(ids or [0]),
                Decision.outcome.in_(IN_FORCE),
            )
            .group_by(Review.subject_id)
        )
    }
    out = []
    for entry, use in rows:
        first, last = dates.get(use.id, (None, None))
        out.append(
            {
                "ref": use.ref,
                "title": entry.title,
                "description": entry.description,
                "show_unit": entry.show_unit,
                "unit": units.get(use.org_unit_id or 0),
                "area": domains.get(use.domain or "", None),
                "tools": [system.name for system in systems.get(use.id, [])],
                "human_oversight": use.human_oversight,
                "approved_on": first.date() if first else None,
                "last_reviewed_on": last.date() if last else None,
                "status": use.status,
                "published": use.status in IN_FORCE,
                "record_name": use.name,
                "added_by": names.get(entry.added_by or 0),
                "added_at": entry.added_at,
            }
        )
    return out


def listing(session: Session, principal: Principal) -> dict[str, Any]:
    entries = _facts(session)
    return {
        "entries": entries,
        "published": sum(1 for entry in entries if entry["published"]),
        "can_change": principal.governs,
    }


# --- The pages ---

_STYLE = """:root{color-scheme:light dark;--ink:#1b1f23;--muted:#55606b;--line:#d5dade;--bg:#fbfaf7;
--card:#fff;--accent:#0f5c4c}
@media (prefers-color-scheme:dark){:root{--ink:#eceae5;--muted:#b3b8be;--line:#3a4046;--bg:#17191c;
--card:#202327;--accent:#7fd1bd}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main,header,footer{max-width:46rem;margin:0 auto;padding:1.5rem 1.25rem}
header{padding-bottom:0}h1{font-size:1.9rem;line-height:1.2;margin:.3rem 0 .6rem}
h2{font-size:1.2rem;margin:0 0 .3rem}a{color:var(--accent)}.eyebrow{font-size:.8rem;
letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0}
.muted,footer{color:var(--muted)}ul.entries{list-style:none;padding:0;margin:1.5rem 0;
display:grid;gap:1rem}ul.entries li{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:1.1rem 1.25rem}ul.entries p{margin:.3rem 0 0}
dl{display:grid;grid-template-columns:max-content 1fr;gap:.5rem 1.5rem;margin:1.5rem 0;
padding:1.1rem 1.25rem;background:var(--card);border:1px solid var(--line);border-radius:10px}
dt{color:var(--muted)}dd{margin:0}footer{font-size:.9rem;border-top:1px solid var(--line)}
@media (max-width:32rem){dl{grid-template-columns:1fr;gap:.1rem}dd{margin-bottom:.6rem}}
"""


def _day(value: Any) -> str:
    return f"{value:%B} {value.day}, {value.year}" if value else ""


def _page(title: str, organization: str, body: str, product: str, home: bool = False) -> str:
    back = "" if home else '<p><a href="index.html">All uses on the register</a></p>'
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        '<link rel="stylesheet" href="style.css"></head><body>'
        f'<header><p class="eyebrow">{escape(organization)}</p></header>'
        f"<main>{body}{back}</main>"
        f"<footer>Published {_day(today())} with {escape(product)}.</footer></body></html>\n"
    )


def _paragraphs(text: str) -> str:
    return "".join(f"<p>{escape(part.strip())}</p>" for part in text.split("\n\n") if part.strip())


def pages(session: Session) -> dict[str, bytes]:
    """The register as files: an index, a page for each use in force, and a stylesheet."""
    brand = branding.load(session)
    organization = brand.organization_name or brand.product_name
    entries = [entry for entry in _facts(session) if entry["published"]]
    entries.sort(key=lambda entry: entry["title"].lower())
    files: dict[str, bytes] = {"style.css": _STYLE.encode()}
    items = []
    for entry in entries:
        name = f"{entry['ref'].lower()}.html"
        first = entry["description"].split("\n\n")[0].strip()
        where = " · ".join(
            filter(None, [entry["area"], entry["unit"] if entry["show_unit"] else None])
        )
        items.append(
            f'<li><h2><a href="{name}">{escape(entry["title"])}</a></h2>'
            f"<p>{escape(first)}</p>"
            + (f'<p class="muted">{escape(where)}</p>' if where else "")
            + "</li>"
        )
        facts = [
            ("Area of work", entry["area"]),
            ("Where", entry["unit"] if entry["show_unit"] else None),
            ("AI tools used", ", ".join(entry["tools"])),
            ("How people stay in charge", entry["human_oversight"]),
            ("First approved", _day(entry["approved_on"])),
            ("Last reviewed", _day(entry["last_reviewed_on"])),
            ("Reference", entry["ref"]),
        ]
        body = (
            f"<h1>{escape(entry['title'])}</h1>{_paragraphs(entry['description'])}<dl>"
            + "".join(
                f"<dt>{escape(label)}</dt><dd>{escape(str(value))}</dd>"
                for label, value in facts
                if value
            )
            + "</dl>"
        )
        files[name] = _page(
            f"{entry['title']} · {organization}", organization, body, brand.product_name
        ).encode()
    count = len(entries)
    intro = (
        f"<h1>How we use AI</h1><p>{escape(organization)} reviews each use of AI before it "
        "begins and again at set times afterwards. This register describes "
        + ("the one use" if count == 1 else f"{count} uses")
        + " we have approved and chosen to publish.</p>"
        if count
        else "<h1>How we use AI</h1><p>Nothing has been published on this register yet.</p>"
    )
    listing_html = f'<ul class="entries">{"".join(items)}</ul>' if items else ""
    files["index.html"] = _page(
        f"How we use AI · {organization}", organization, intro + listing_html,
        brand.product_name, home=True,
    ).encode()  # fmt: skip
    return files


def archive(session: Session) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, data in sorted(pages(session).items()):
            info = zipfile.ZipInfo(f"register/{path}", _FIXED)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, data)
    return out.getvalue()


def write(session: Session, directory: Path) -> int:
    """Write the pages into a directory, replacing the register pages already there."""
    files = pages(session)
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("uc-*.html"):
        old.unlink()
    for path, data in files.items():
        (directory / path).write_bytes(data)
    return len(files) - 2
