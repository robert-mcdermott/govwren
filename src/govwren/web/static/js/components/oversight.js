// Keeping watch, on a record's page: what to know before relying on it, and what a change
// review shows of the change.

import { button, h, icon } from "../core/dom.js";
import { dateTime } from "../core/format.js";
import { TYPES } from "./record.js";
import { alert, card, pill } from "./ui.js";

/** A record's own findings, then those inherited from what it relies on. */
export function findingsAlerts(findings) {
  if (!findings) return null;
  const inherited = findings.inherited.map((finding) => alert(finding.tone, icon("link"), h("div", {},
    h("strong", {}, "Inherited from "), h("a", { href: `/${TYPES[finding.from.type].path}/${finding.from.ref}` }, finding.from.name),
    `. ${finding.text}. `, h("span", { class: "subtle" }, finding.distance > 1 ? "This record relies on it through another." : "This record relies on it directly."))));
  const incidents = findings.own.filter((finding) => finding.kind === "incident").map((finding) => alert(finding.tone, icon("alert"), h("div", {},
    h("strong", {}, "An incident is open. "), h("a", { href: `/incidents/${finding.ref}` }, finding.ref),
    " involves this record. Anything that relies on it shows the same.")));
  const risks = findings.own.filter((finding) => finding.kind === "risk").map((finding) => alert(finding.tone, icon("shield"), h("div", {},
    `${finding.text}. `, h("a", { href: `/risks/${finding.ref}` }, "See the risk"))));
  const own = findings.own.filter((finding) => finding.kind === "exception").map((finding) => alert("warn", icon("alert"), h("div", {},
    h("strong", {}, "Under an exception. "), `${finding.text}. `, h("a", { href: `/exceptions/${finding.ref}` }, "See the exception"))));
  return incidents.length + risks.length + own.length + inherited.length ? h("div", { class: "stack-sm" }, incidents, risks, own, inherited) : null;
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

/** Where the rules require a named person to accept the risk: who was asked, what they said. */
export function acceptanceCard(packet, reload) {
  const acceptance = packet.acceptance;
  if (!acceptance) return null;
  const tone = { accepted: "ok", declined: "danger", requested: "warn", needed: "warn" }[acceptance.status];
  const words = { accepted: "Accepted", declined: "Not accepted", requested: "Waiting for an answer", needed: "Nobody asked yet" }[acceptance.status];
  const open = async (name) => (await import("./oversight-forms.js"))[name](packet, reload);
  return card({ title: "Risk acceptance", actions: pill(words, tone) }, h("div", { class: "stack-sm" },
    h("p", { class: "muted" }, "The rules require a named person to accept the risk of this use before it can be approved."),
    acceptance.name ? h("div", {}, h("span", { class: "cell-main" }, acceptance.name),
      acceptance.answered_at ? h("span", { class: "subtle" }, ` · ${dateTime(acceptance.answered_at)}`) : null) : null,
    acceptance.statement ? h("p", { class: "prose" }, acceptance.statement) : null,
    acceptance.can_answer || acceptance.can_ask ? h("div", { class: "row-sm wrap" },
      acceptance.can_answer ? button("Accept the risk…", { kind: "btn-primary btn-sm", onclick: () => open("acceptRisk") }) : null,
      acceptance.can_answer ? button("Decline…", { kind: "btn-sm", onclick: () => open("declineRisk") }) : null,
      acceptance.can_ask ? button(acceptance.name ? "Ask someone else…" : "Ask someone to accept it…", { kind: "btn-sm", onclick: () => open("askAcceptance") }) : null) : null));
}
