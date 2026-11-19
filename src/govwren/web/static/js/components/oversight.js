// Keeping watch, on a record's page: what to know before relying on it, and what a change
// review shows of the change.

import { h, icon } from "../core/dom.js";
import { TYPES } from "./record.js";
import { alert, card, pill } from "./ui.js";

/** A record's own findings, then those inherited from what it relies on. */
export function findingsAlerts(findings) {
  if (!findings) return null;
  const inherited = findings.inherited.map((finding) => alert(finding.tone, icon("link"), h("div", {},
    h("strong", {}, "Inherited from "), h("a", { href: `/${TYPES[finding.from.type].path}/${finding.from.ref}` }, finding.from.name),
    `. ${finding.text}. `, h("span", { class: "subtle" }, finding.distance > 1 ? "This record relies on it through another." : "This record relies on it directly."))));
  return inherited.length ? h("div", { class: "stack-sm" }, inherited) : null;
}

/** What a change review is about: the answers that differ, and what the rules made of them. */
export function changeCard(change) {
  if (!change) return null;
  const changed = change.changed ?? [];
  return card({ title: "What changed", actions: change.material == null ? pill("Not submitted yet")
    : change.material ? pill("Material", "warn") : pill("Not material", "ok") },
  h("div", { class: "stack" },
    change.summary ? h("p", { class: "prose" }, change.summary) : null,
    change.reasons?.length ? h("ul", {}, change.reasons.map((reason) => h("li", {}, reason))) : null,
    changed.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Question"), h("th", { scope: "col" }, "Before"), h("th", { scope: "col" }, "Now"))),
      h("tbody", {}, changed.map((item) => h("tr", {},
        h("td", {}, item.label), h("td", { class: "muted" }, item.before ?? "Not answered"), h("td", { class: "cell-main" }, item.after ?? "Not answered"))))))
      : change.material == null ? h("p", { class: "muted" }, "The owner has yet to submit the corrected answers.") : h("p", { class: "muted" }, "No answer changed.")));
}
