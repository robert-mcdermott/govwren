// A record, and the inventory, as they stood at the end of a chosen day.

import { get } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { query, setQuery } from "../core/router.js";
import { hrefOf, standingPill } from "../components/record.js";
import { alert, card, emptyState, pageHeader, pill, stat } from "../components/ui.js";
import { show } from "./page.js";

const iso = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
const chosen = () => /^\d{4}-\d\d-\d\d$/.test(query().get("on") ?? "") ? query().get("on") : iso(new Date(Date.now() - 90 * 86400000));

/** A date and a button: the day to look back to. */
function picker(on) {
  const input = h("input", { class: "input", type: "date", value: on, max: iso(new Date()), "aria-label": "As it stood on" });
  return h("form", { class: "row-sm no-print", onsubmit: (event) => {
    event.preventDefault();
    if (input.value) setQuery({ on: input.value }, { replace: false });
  } }, input, button("Show", { type: "submit" }));
}

export function recordAsOf(main, params) {
  const on = chosen();
  return show(main, {
    title: `${params.ref} as it stood`,
    load: async () => (await get(`/api/v1/records/${params.ref}/as-of`, { on }, { fresh: true })).data,
    view: (data) => {
      document.title = `${data.name_now} · ${data.ref} on ${date(data.on)}`;
      const changed = data.fields.filter((field) => field.changed).length;
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: `${hrefOf(data.ref)}?tab=history` }, icon("chevron-left", "icon icon-sm"), `${data.ref} today`),
        pageHeader({ eyebrow: `${data.ref} · As it stood`, title: data.name, lede: `At the end of ${date(data.on)}, worked out from the history.`, actions: picker(on) }),
        !data.existed ? emptyState({ iconName: "history", title: "It was not on the record yet", text: data.created_on ? `It was added on ${date(data.created_on)}.` : null })
          : [changed ? alert("warn", icon("alert"), h("div", {}, `${changed} ${changed === 1 ? "field has" : "fields have"} changed since, and ${data.changes_since} ${data.changes_since === 1 ? "thing has" : "things have"} been recorded about it.`))
            : alert("ok", icon("check"), h("div", {}, data.changes_since ? `No field shown here has changed since, though ${data.changes_since} ${data.changes_since === 1 ? "thing has" : "things have"} been recorded about it.` : "Nothing has changed since.")),
          card({ title: "The record", flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Field"), h("th", { scope: "col" }, `On ${date(data.on)}`), h("th", { scope: "col" }, "Now"))),
            h("tbody", {}, data.fields.map((field) => h("tr", {},
              h("th", { scope: "row", class: "subtle" }, field.label),
              h("td", {}, field.then == null ? h("span", { class: "subtle" }, "Not set") : String(field.then)),
              h("td", {}, field.changed ? h("div", { class: "row-sm wrap" }, field.now == null ? h("span", { class: "subtle" }, "Not set") : String(field.now), pill("Changed", "warn"))
                : h("span", { class: "subtle" }, "The same")))))))),
          h("div", { class: "grid-3" },
            card({ title: "Owners" }, data.owners.length ? h("ul", { class: "rows" }, data.owners.map((owner) => h("li", { class: "row" }, h("span", { class: "grow" }, owner.name), h("span", { class: "subtle" }, owner.kind))))
              : h("p", { class: "muted" }, "Nobody was named.")),
            card({ title: "Relied on" }, data.relies_on.length ? h("ul", { class: "rows" }, data.relies_on.map((item) => h("li", { class: "row" }, h("span", { class: "grow" }, item.name), h("span", { class: "subtle" }, item.relation))))
              : h("p", { class: "muted" }, "Nothing was linked.")),
            card({ title: "Conditions" }, data.conditions.length ? h("ul", { class: "rows" }, data.conditions.map((item) => h("li", { class: "row" }, h("span", { class: "grow" }, item.text), h("span", { class: "subtle" }, item.status))))
              : h("p", { class: "muted" }, "None had been set.")))]);
    },
  });
}

export function inventoryAsOf(main) {
  const on = chosen();
  return show(main, {
    title: "The inventory as it stood",
    load: async () => (await get("/api/v1/inventory/as-of", { on }, { fresh: true })).data,
    view: (data) => h("div", { class: "stack-lg" },
      h("a", { class: "back-link", href: "/portfolio" }, icon("chevron-left", "icon icon-sm"), "Portfolio"),
      pageHeader({ title: "The inventory as it stood", lede: `Every use that had been submitted by the end of ${date(data.on)}, with its standing then. Worked out from the history.`, actions: picker(on) }),
      h("div", { class: "grid-3" }, stat(String(data.in_use), "Uses in the inventory then"), stat(String(data.uses.length), "On the record, counting requests and those declined"),
        stat(String(data.changed_since), "Have a different standing now")),
      Object.keys(data.by_tier).length ? h("div", { class: "row-sm wrap" }, h("span", { class: "subtle" }, "In use, by tier:"), Object.entries(data.by_tier).map(([tier, count]) => pill(`${count} ${tier}`))) : null,
      data.uses.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ["Use", "Unit", "Tier", "Standing then", "Now"].map((heading) => h("th", { scope: "col" }, heading)))),
        h("tbody", {}, data.uses.map((use) => h("tr", {},
          h("td", {}, h("a", { class: "cell-main", href: `/as-of/${use.ref}?on=${data.on}` }, use.name), h("div", { class: "cell-sub" }, use.ref)),
          h("td", {}, use.unit ?? ""), h("td", {}, use.tier_label ?? ""), h("td", {}, standingPill(use.status)),
          h("td", {}, use.status === use.status_now ? h("span", { class: "subtle" }, "The same") : standingPill(use.status_now))))))))
        : emptyState({ iconName: "history", title: "Nothing was on the record yet" })),
  });
}
