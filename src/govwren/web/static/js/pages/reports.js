// Leadership reports: made once for a period, frozen, and reopened as they were.

import { get, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime } from "../core/format.js";
import { navigate } from "../core/router.js";
import { banner, field, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { alert, card, emptyState, pageHeader, pill, stat } from "../components/ui.js";
import { counted, shown } from "./measures.js";
import { show } from "./page.js";

const iso = (value) => value.toISOString().slice(0, 10);
const words = (key) => String(key).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const LEVEL_TONE = { critical: "danger", high: "warn", moderate: "", low: "" };

/** The quarter that ended most recently: the usual period for a report. */
function lastQuarter(now = new Date()) {
  const quarter = Math.floor(now.getUTCMonth() / 3);
  const start = new Date(Date.UTC(now.getUTCFullYear(), quarter * 3 - 3, 1));
  const end = new Date(Date.UTC(now.getUTCFullYear(), quarter * 3, 0));
  return { from: iso(start), to: iso(end), title: `Q${Math.floor(start.getUTCMonth() / 3) + 1} ${start.getUTCFullYear()} report to leadership` };
}

function make() {
  const usual = lastQuarter();
  const title = field("Title", { value: usual.title, maxlength: 200 });
  const from = field("From", { type: "date", value: usual.from });
  const to = field("To", { type: "date", value: usual.to });
  const commentary = field("Commentary", { type: "textarea", rows: 5, hint: "Optional. A few sentences in your own words, shown at the top of the report." });
  const fields = { title, from, to, commentary };
  openOverlay({
    title: "Make a report", subtitle: "It is worked out now and never changes afterwards.", kind: "dialog",
    render: (body, footer, shut) => {
      const problem = banner();
      const go = button("Make and freeze it", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const made = await submit({ button: go, banner: problem, fields, run: () => post("/api/v1/reports",
          { title: title.input.value, from: from.input.value, to: to.input.value, commentary: commentary.input.value }) });
        if (made) {
          shut();
          navigate(`/reports/${made.data.ref}`);
        }
      });
      body.append(h("div", { class: "stack" }, problem, title.node, h("div", { class: "grid-2" }, from.node, to.node), commentary.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function reportList(main) {
  return show(main, {
    title: "Reports",
    load: async () => (await get("/api/v1/reports", null, { fresh: true })).data,
    view: (data) => h("div", { class: "stack-lg" },
      pageHeader({ title: "Reports", lede: "Reports to leadership, each frozen on the day it was made. Opening one shows what it said then.",
        actions: data.can_create ? button("Make a report", { kind: "btn-primary", iconName: "plus", onclick: make }) : null }),
      data.reports.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ["Report", "Period", "Made", "By"].map((heading) => h("th", { scope: "col" }, heading)))),
        h("tbody", {}, data.reports.map((report) => h("tr", {},
          h("td", {}, h("a", { class: "cell-main", href: `/reports/${report.ref}` }, report.title), h("div", { class: "cell-sub" }, report.ref)),
          h("td", { class: "nowrap" }, `${date(report.from)} to ${date(report.to)}`),
          h("td", { class: "nowrap" }, date(report.created_at)), h("td", {}, report.created_by ?? "")))))))
        : emptyState({ iconName: "note", title: "No report has been made yet", text: "A report sets down the program's figures for a period so that they can be shown later exactly as they stood." })),
  });
}

const table = (headings, rows) => h("div", { class: "table-wrap" }, h("table", { class: "table" },
  h("thead", {}, h("tr", {}, headings.map((heading) => h("th", { scope: "col" }, heading)))),
  h("tbody", {}, rows.map((row) => h("tr", {}, row.map((cell, index) => h("td", { class: index ? "numeric" : "" }, cell?.nodeType ? cell : String(cell ?? ""))))))));

const groupRows = (groups) => groups.map((group) => [h("span", { class: "cell-main" }, group.label), group.in_use, group.approved, group.in_review,
  group.lapsed + group.suspended, group.high_tier, group.decided]);
const GROUP_HEADINGS = ["In use", "Approved", "In review", "Lapsed or suspended", "High or critical", "Decided in the period"];

export function reportPage(main, params) {
  return show(main, {
    title: params.ref,
    load: async () => (await get(`/api/v1/reports/${params.ref}`, null, { fresh: true })).data,
    view: (report) => {
      const c = report.content;
      document.title = `${report.title} · ${report.ref}`;
      const a = c.attention;
      const needs = [
        a.lapsed ? `${a.lapsed} ${a.lapsed === 1 ? "approval has" : "approvals have"} lapsed` : null,
        a.suspended ? `${a.suspended} ${a.suspended === 1 ? "approval is" : "approvals are"} suspended` : null,
        a.conditions_overdue ? `${a.conditions_overdue} ${a.conditions_overdue === 1 ? "condition is" : "conditions are"} overdue` : null,
        a.ending_soon ? `${a.ending_soon} ${a.ending_soon === 1 ? "approval ends" : "approvals end"} within sixty days` : null,
      ].filter(Boolean);
      const severities = Object.entries(c.incidents.by_severity).map(([key, count]) => `${count} ${words(key).toLowerCase()}`).join(", ");
      return h("div", { class: "stack-lg dossier" },
        h("a", { class: "back-link no-print", href: "/reports" }, icon("chevron-left", "icon icon-sm"), "Reports"),
        pageHeader({ eyebrow: `${c.organization || c.product} · ${report.ref}`, title: report.title,
          lede: `${date(c.from)} to ${date(c.to)}. Frozen ${dateTime(report.created_at)}${report.created_by ? ` by ${report.created_by}` : ""}.`,
          actions: h("div", { class: "no-print" }, button("Print", { onclick: () => window.print() })) }),
        report.intact ? null : alert("danger", icon("alert"), h("div", {}, h("strong", {}, "This report has been altered. "),
          "What is stored no longer matches the hash it was frozen under.")),
        report.commentary ? card({ title: "Commentary" }, report.commentary.split(/\n{2,}/).map((paragraph) => h("p", {}, paragraph))) : null,
        h("div", { class: "grid-3" }, stat(String(c.totals.in_use), "Uses in the inventory"),
          stat(String(c.totals.decided), `Decisions in the period: ${c.totals.approved_in_period} approved, ${c.totals.declined_in_period} declined`),
          stat(String(c.totals.in_review), "In review when this was made")),
        needs.length ? alert("warn", icon("alert"), h("div", {}, h("strong", {}, "Needed attention. "), h("ul", {}, needs.map((line) => h("li", {}, line)))))
          : alert("ok", icon("check"), h("div", {}, "Nothing was lapsed, suspended, overdue, or about to end.")),
        card({ title: "Measures" }, h("div", { class: "stack" }, c.measures.map((measure) => h("div", { class: "report-measure" },
          h("div", {}, h("div", { class: "measure-value" }, shown(measure)), h("div", { class: "muted" }, counted(measure))),
          h("div", {}, h("h3", {}, measure.title), h("p", { class: "muted" }, measure.definition)))))),
        card({ title: "By tier", flush: true }, table(["Tier", ...GROUP_HEADINGS], groupRows(c.by_tier))),
        card({ title: c.units > c.by_unit.length ? `The ${c.by_unit.length} units with the most uses, of ${c.units}` : "By unit", flush: true },
          table(["Unit", ...GROUP_HEADINGS], groupRows(c.by_unit))),
        card({ title: "Risks" }, h("div", { class: "row-sm wrap" }, Object.entries(c.risks.by_level).map(([level, count]) => pill(`${count} ${level}`, count ? LEVEL_TONE[level] : ""))),
          c.risks.serious.length ? table(["Risk", "Level", "Standing", "Owner"], c.risks.serious.map((risk) =>
            [h("span", {}, h("span", { class: "cell-main" }, risk.title), h("div", { class: "cell-sub" }, risk.ref)), words(risk.level), words(risk.status), risk.owner]))
            : h("p", { class: "muted" }, "No risk stood at high or critical.")),
        card({ title: "Incidents, exceptions, and controls" }, h("dl", { class: "dl" },
          h("dt", {}, "Incidents reported in the period"), h("dd", {}, c.incidents.reported ? `${c.incidents.reported}: ${severities}. ${c.incidents.still_open} still open.` : "None"),
          h("dt", {}, "Exceptions in force"), h("dd", {}, `${c.exceptions.in_force}, of which ${c.exceptions.granted} were granted in the period`),
          h("dt", {}, "Program controls"), h("dd", {}, Object.keys(c.controls).length
            ? Object.entries(c.controls).map(([key, count]) => `${count} ${key === "implemented" ? "in place" : words(key).toLowerCase()}`).join(", ") : "None has a standing yet"))),
        h("p", { class: "subtle" }, "This report was worked out once and stored. It reads the same whatever has changed since. SHA-256 of what was stored: ",
          h("code", { class: "hash" }, report.sha256)));
    },
  });
}
