// The dossier: everything about one record on a page to read, print, or take away.

import { get } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { date, dateTime } from "../core/format.js";
import { hrefOf, standingLabel } from "../components/record.js";
import { card, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const STAMP = /^\d{4}-\d\d-\d\dT/;
const DAY = /^\d{4}-\d\d-\d\d$/;
const KEY = /^[a-z]+(_[a-z0-9]+)+$/;
const SKIP = new Set(["type", "ref", "name", "sight", "evidence", "links", "references", "completeness", "version", "org_unit_id", "orphaned",
  "merged_into", "used_by_hidden", "agent_profile", "agreements", "systems", "summary", "status"]);

const words = (key) => String(key).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function text(value) {
  if (value == null || value === "") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join(", ");
  if (typeof value === "object") {
    const named = value.name ?? value.label ?? value.title ?? value.ref;
    return named ? String(named) : Object.entries(value).filter(([, v]) => text(v)).map(([k, v]) => `${words(k)}: ${text(v)}`).join("; ");
  }
  const s = String(value);
  return STAMP.test(s) ? dateTime(s) : DAY.test(s) ? date(s) : KEY.test(s) ? words(s) : s;
}

const plain = (value) => Array.isArray(value) ? value.map(plain) : typeof value === "string" && /^[a-z_]+$/.test(value) ? words(value) : value;

const facts = (pairs) => {
  const shown = pairs.filter(([, value]) => text(value));
  return shown.length ? h("dl", { class: "dl" }, shown.flatMap(([label, value]) => [h("dt", {}, label), h("dd", {}, text(value))])) : null;
};

const table = (headings, rows) => h("div", { class: "table-wrap" }, h("table", { class: "table" },
  h("thead", {}, h("tr", {}, headings.map((heading) => h("th", { scope: "col" }, heading)))),
  h("tbody", {}, rows.map((row) => h("tr", {}, row.map((cell) => h("td", {}, cell?.nodeType ? cell : text(cell))))))));

const link = (ref, path) => h("a", { href: path ? `/${path}/${ref}` : hrefOf(ref) }, ref);
const part = (title, count, ...children) => children.some(Boolean) ? card({ title: count == null ? title : `${title} (${count})` }, ...children) : null;
const asked = (sections) => sections.filter((section) => section.questions.length).map((section) => h("div", { class: "stack-sm" },
  h("h3", {}, section.title), facts(section.questions.map((question) => [question.label, question.answer]))));

export function dossierPage(main, params) {
  return show(main, {
    title: `${params.ref} dossier`,
    load: async () => (await get(`/api/v1/records/${params.ref}/dossier`, null, { fresh: true })).data,
    view: (d) => {
      const record = d.record;
      document.title = `${record.name} · ${record.ref} · Dossier`;
      const connections = [...(record.systems ?? []).map((system) => ["Uses", link(system.ref), system.name]),
        ...(record.links?.outgoing ?? []).map((item) => [item.label, link(item.record.ref), item.record.name]),
        ...(record.links?.incoming ?? []).map((item) => [`${item.label} (from)`, link(item.record.ref), item.record.name])];
      const findings = [...d.findings.own, ...d.findings.inherited];
      return h("div", { class: "stack-lg dossier" },
        h("a", { class: "back-link no-print", href: hrefOf(record.ref) }, `Back to ${record.ref}`),
        pageHeader({ eyebrow: `Dossier · ${record.ref}`, title: record.name,
          lede: `Made ${dateTime(d.generated_at)} by ${d.generated_by}. It shows what you may see of this record.`,
          actions: h("div", { class: "row-sm wrap no-print" }, button("Print", { onclick: () => window.print() }),
            h("a", { class: "btn btn-primary", href: `/api/v1/records/${record.ref}/dossier/package`, download: `${record.ref}-dossier.zip` }, "Download the package")) }),
        part("The record", null, h("div", { class: "row-sm wrap" }, pill(standingLabel(record.catalog_status ?? record.status)), record.summary ? h("span", { class: "muted" }, record.summary) : null),
          facts(Object.entries(record).filter(([key]) => !SKIP.has(key)).map(([key, value]) => [words(key), plain(value)]))),
        d.answers ? part(`Answers on the request form, version ${d.answers.form_version}`, null, ...asked(d.answers.sections)) : null,
        d.reviews.length ? part("Reviews and decisions", d.reviews.length, ...d.reviews.map((review) => h("div", { class: "stack-sm" },
          h("h3", {}, `${review.ref}: ${words(review.kind)} review`),
          facts([["Status", review.status], ["Opened", review.opened_at], ["Closed", review.closed_at], ["Decided by", review.authority]]),
          review.tasks.length ? table(["Review function", "Status", "Finding", "By", "Notes"],
            review.tasks.map((task) => [task.function, task.status, task.finding, task.completed_by, task.notes])) : null,
          ...review.decisions.map((decision) => facts([["Decision", decision.outcome], ["Reason", decision.rationale],
            ["By", decision.by_rule || decision.decided_by], ["On", decision.decided_at], ["Approved until", decision.approved_until]]))))) : null,
        d.conditions.length ? part("Conditions", d.conditions.length, table(["Condition", "Owner", "Due", "Status", "Evidence"],
          d.conditions.map((c) => [c.text, c.owner, c.due_on, c.status, c.evidence.map((item) => item.ref)]))) : null,
        findings.length ? part("Findings, its own and inherited", findings.length, table(["Finding", "From"],
          findings.map((finding) => [finding.text, finding.from ? `${finding.from.name} (${finding.from.ref})` : "This record"]))) : null,
        d.risks.length ? part("Risks", d.risks.length, table(["Risk", "What could go wrong", "Level", "Status", "Owner"],
          d.risks.map((risk) => [link(risk.ref, "risks"), risk.title, risk.level, risk.status, risk.owner]))) : null,
        d.controls.length ? part("Controls that apply", d.controls.length, table(["Control", "Standing", "Owner", "Next check"],
          d.controls.map((control) => [control.title, control.status_label, control.owner, control.next_check_on]))) : null,
        d.exceptions.length ? part("Exceptions", d.exceptions.length, table(["Exception", "Title", "Status", "Ends"],
          d.exceptions.map((item) => [link(item.ref, "exceptions"), item.title, item.status, item.ends_on]))) : null,
        d.incidents.length ? part("Incidents", d.incidents.length, table(["Incident", "Title", "Severity", "Status", "Reported"],
          d.incidents.map((item) => [link(item.ref, "incidents"), item.title, item.severity, item.status, item.reported_at]))) : null,
        ...d.assessments.map((assessment) => part(`${assessment.title} (${words(assessment.status).toLowerCase()})`, null,
          facts([["Submitted by", assessment.submitted_by], ["Reviewed by", assessment.reviewed_by], ["Note", assessment.review_note]]), ...asked(assessment.sections))),
        connections.length ? part("Connections", connections.length, table(["Relation", "Record", "Name"], connections)) : null,
        d.evidence.length ? part("Evidence", d.evidence.length, table(["Evidence", "Title", "Dated", "Good until", "File and SHA-256"],
          d.evidence.map((item) => [item.ref, item.title, item.dated_on, item.expires_on,
            item.file ? h("span", {}, item.file.name, h("code", { class: "hash" }, item.file.sha256)) : item.url]))) : null,
        part("History, oldest first", d.history.length, table(["When", "Who", "What"],
          d.history.map((entry) => [entry.at, entry.actor, [entry.title, ...entry.lines.map((line) => line.label ? `${line.label}: ${text(line.after)}` : text(line))].join(". ")]))),
        h("p", { class: "subtle" }, `When this was made the history stood at event ${d.history_head.events}, `, h("code", { class: "hash" }, d.history_head.hash),
          ". The package carries a manifest that lists every file with its SHA-256."));
    },
  });
}
