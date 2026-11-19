// The portfolio grouped one way at a time, and one unit on a page.

import { get } from "../core/api.js";
import { h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { navigate, query, setQuery } from "../core/router.js";
import { session } from "../core/session.js";
import { standingPill } from "../components/record.js";
import { alert, card, emptyState, pageHeader, pill, stat, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

const BY = [["unit", "Unit"], ["tier", "Tier"], ["domain", "Area"], ["data_class", "Data class"], ["vendor", "Supplier"]];
const PERIODS = [["90", "90 days"], ["180", "6 months"], ["365", "A year"]];

function bar(part, whole, label) {
  const node = h("div", { class: "meter", role: "img", "aria-label": label }, h("span"));
  node.style.setProperty("--share", `${whole ? Math.max(2, (part / whole) * 100) : 0}%`);
  return node;
}

export function portfolioPage(main) {
  const params = query();
  const by = BY.some(([key]) => key === params.get("by")) ? params.get("by") : "unit";
  const days = PERIODS.some(([key]) => key === params.get("days")) ? params.get("days") : "90";
  return show(main, {
    title: "Portfolio",
    load: async () => {
      const end = new Date();
      const iso = (value) => value.toISOString().slice(0, 10);
      return (await get("/api/v1/portfolio", { by, from: iso(new Date(end.getTime() - Number(days) * 86400000)), to: iso(end) }, { fresh: true })).data;
    },
    view: (data) => {
      const toggle = (name, current, pairs, fallback, label) => h("div", { class: "segmented", role: "group", "aria-label": label },
        pairs.map(([key, text]) => h("button", { type: "button", "aria-pressed": String(current === key),
          onclick: () => setQuery({ [name]: key === fallback ? null : key }, { replace: false }) }, text)));
      const heading = BY.find(([key]) => key === by)[1];
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Portfolio", lede: `${data.total_in_use} uses are in the inventory. Decisions are counted from ${date(data.from)} to ${date(data.to)}.`,
          actions: [toggle("by", by, BY, "unit", "Group by"), toggle("days", days, PERIODS, "90", "Period"), h("a", { class: "btn", href: "/as-of" }, "As it stood on a date")] }),
        data.groups.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, heading), h("th", { scope: "col" }, "In use"), h("th", { scope: "col" }, "Standing now"),
            h("th", { scope: "col" }, "Needs a look"), h("th", { scope: "col" }, "Decided in the period"))),
          h("tbody", {}, data.groups.map((group) => h("tr", {},
            h("td", {}, group.href ? h("a", { class: "cell-main", href: group.href }, group.label) : h("span", { class: "cell-main" }, group.label)),
            h("td", {}, h("div", { class: "portfolio-bar" }, h("span", { class: "numeric cell-main" }, String(group.in_use)), bar(group.in_use, data.largest, `${group.in_use} in use`))),
            h("td", {}, h("div", { class: "row-sm wrap" }, group.approved ? pill(`${group.approved} approved`, "ok") : null,
              group.lapsed ? pill(`${group.lapsed} lapsed`, "danger") : null, group.suspended ? pill(`${group.suspended} suspended`, "danger") : null,
              group.in_review ? pill(`${group.in_review} in review`, "accent") : null)),
            h("td", {}, h("div", { class: "row-sm wrap" }, group.high_tier ? pill(`${group.high_tier} high or critical`, "warn") : null,
              group.serious_risks ? pill(`${group.serious_risks} serious ${group.serious_risks === 1 ? "risk" : "risks"}`, "warn") : null,
              !group.high_tier && !group.serious_risks ? h("span", { class: "subtle" }, "Nothing") : null)),
            h("td", {}, group.decided ? `${group.decided}: ${group.approved_in_period} approved${group.declined_in_period ? `, ${group.declined_in_period} declined` : ""}` : h("span", { class: "subtle" }, "None"))))))))
          : emptyState({ iconName: "units", title: "Nothing is in the inventory yet" }),
        h("p", { class: "subtle" }, by === "vendor" ? "A use that relies on tools from two suppliers is counted under both." : "Each name opens the list of uses it counts."));
    },
  });
}

export function unitReportPage(main, params) {
  return show(main, {
    title: "Unit report",
    load: async () => (await get(`/api/v1/units/${params.id}/report`, null, { fresh: true })).data,
    view: (data) => {
      document.title = `${data.unit.name} · Unit report`;
      const a = data.attention;
      const needs = [
        a.to_confirm ? `${a.to_confirm} ${a.to_confirm === 1 ? "use is" : "uses are"} waiting for an owner to confirm` : null,
        a.conditions_overdue ? `${a.conditions_overdue} ${a.conditions_overdue === 1 ? "condition is" : "conditions are"} overdue` : null,
        a.ending_soon ? `${a.ending_soon} ${a.ending_soon === 1 ? "approval ends" : "approvals end"} within sixty days` : null,
        data.counts.lapsed ? `${data.counts.lapsed} ${data.counts.lapsed === 1 ? "approval has" : "approvals have"} lapsed` : null,
        a.incidents ? `${a.incidents} open ${a.incidents === 1 ? "incident involves" : "incidents involve"} a use here` : null,
      ].filter(Boolean);
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Unit report", title: data.unit.name,
          lede: data.unit.units > 1 ? `With the ${data.unit.units - 1} ${data.unit.units === 2 ? "unit" : "units"} beneath it.` : null,
          actions: h("a", { class: "btn", href: `/use-cases?unit=${data.unit.id}` }, "Open the list of uses") }),
        h("div", { class: "grid-3" }, stat(String(data.counts.in_use), "Uses in the inventory"), stat(String(data.counts.approved), "With an approval in force"),
          stat(String(data.counts.in_review), "In review")),
        needs.length ? alert("warn", icon("alert"), h("div", {}, h("strong", {}, "Needs attention. "), h("ul", {}, needs.map((line) => h("li", {}, line)))))
          : alert("ok", icon("check"), h("div", {}, "Nothing here is overdue or about to end.")),
        card({ title: "Uses", flush: true }, data.uses.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Use"), h("th", { scope: "col" }, "Unit"), h("th", { scope: "col" }, "Tier"), h("th", { scope: "col" }, "Standing"), h("th", { scope: "col" }, "Approved until"))),
          h("tbody", {}, data.uses.map((use) => h("tr", {},
            h("td", {}, h("a", { class: "cell-main", href: `/use-cases/${use.ref}` }, use.name), h("div", { class: "cell-sub" }, use.ref)),
            h("td", {}, use.unit ?? ""), h("td", {}, use.tier ? tierBadge(use.tier) : ""),
            h("td", {}, h("div", { class: "row-sm wrap" }, standingPill(use.status), use.to_confirm ? pill("To confirm", "warn") : null)),
            h("td", { class: "nowrap" }, use.approved_until ? h("span", { class: use.ending_soon ? "due-late" : "" }, date(use.approved_until)) : ""))))))
          : h("p", { class: "muted card-pad" }, "No use is recorded for this unit.")),
        data.exceptions.length ? card({ title: "Exceptions" }, h("ul", { class: "rows" }, data.exceptions.map((item) => h("li", { class: "row wrap" },
          h("a", { class: "grow", href: `/exceptions/${item.ref}` }, item.title), h("span", { class: "subtle" }, `${item.status === "approved" ? "In force until" : "Asked for, to"} ${date(item.ends_on)}`))))) : null,
        data.incidents.length ? card({ title: "Open incidents" }, h("ul", { class: "rows" }, data.incidents.map((item) => h("li", { class: "row wrap" },
          h("a", { class: "grow", href: `/incidents/${item.ref}` }, item.title), item.severity ? pill(`${item.severity} severity`, item.severity === "low" ? "" : "warn") : pill("Not triaged"))))) : null);
    },
  });
}

/** A steward's own unit: the first one they steward. */
export function myUnit(main) {
  const mine = session()?.steward_units ?? [];
  if (mine.length) {
    queueMicrotask(() => navigate(`/units/${mine[0]}/report`, { replace: true }));
    return null;
  }
  return show(main, { title: "My unit", view: () => emptyState({ iconName: "units", title: "You are not a steward of a unit" }) });
}
