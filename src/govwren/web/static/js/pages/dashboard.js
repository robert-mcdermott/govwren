// The program dashboard: where things stand. Every figure leads to the records behind it.

import { get } from "../core/api.js";
import { h } from "../core/dom.js";
import { card, emptyState, pageHeader, pill, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

function bars(rows, { tier = false, empty = "Nothing to show yet." } = {}) {
  const most = Math.max(1, ...rows.map((row) => row.count));
  if (!rows.some((row) => row.count)) return h("p", { class: "muted bars-empty" }, empty);
  return h("ul", { class: "bars" }, rows.map((row) => {
    const fill = h("span", { class: "bar-fill", "data-level": tier ? row.key : null });
    fill.style.setProperty("--share", `${(row.count / most) * 100}%`);
    const name = tier ? tierBadge(row.key, row.label) : row.label;
    return h("li", {},
      row.href && row.count ? h("a", { class: "bar-label", href: row.href }, name) : h("span", { class: "bar-label" }, name),
      h("span", { class: "bar-track", "aria-hidden": "true" }, fill),
      h("span", { class: "bar-count" }, String(row.count)));
  }));
}

function tile(item) {
  const inner = [h("div", { class: "stat-value" }, String(item.count)), h("div", { class: "stat-label" }, item.label)];
  return item.href ? h("a", { class: "card stat stat-link", href: item.href }, inner) : h("div", { class: "card stat" }, inner);
}

export function dashboard(main) {
  return show(main, {
    title: "Dashboard",
    load: async () => (await get("/api/v1/dashboard", null, { fresh: true })).data,
    view: (data) => {
      const waiting = data.attention.filter((item) => item.count);
      const decisions = data.decisions;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Dashboard", lede: "Where the program stands today." }),
        h("div", { class: "stat-row" }, data.totals.map(tile)),
        h("div", { class: "grid-2" },
          card({ title: "Needs attention", flush: true, actions: waiting.length ? pill(String(waiting.length), "warn") : null },
            waiting.length ? h("ul", {}, waiting.map((item) => h("li", { class: "list-row" },
              h("div", { class: "grow cell-main" }, item.href ? h("a", { href: item.href }, item.label) : item.label),
              h("span", { class: "bar-count" }, String(item.count)))))
              : emptyState({ iconName: "check", title: "Nothing is overdue",
                text: "Late reviews, late conditions, and approvals about to end are listed here." })),
          card({ title: "Approved uses by tier" }, bars(data.by_tier, { tier: true, empty: "No approved uses yet." }))),
        h("div", { class: "grid-2" },
          card({ title: "Open reviews", actions: data.reviews.open ? h("a", { class: "btn btn-sm", href: "/reviews" }, "Open the queue") : null },
            h("div", { class: "stack" },
              h("div", {}, h("h3", { class: "bars-title" }, "Where they are"), bars(data.reviews.by_status, { empty: "No reviews are open." })),
              data.reviews.open ? h("div", {}, h("h3", { class: "bars-title" }, "How long they have been open"), bars(data.reviews.by_age)) : null)),
          card({ title: `Decisions in the last ${decisions.period_days} days` },
            h("div", { class: "stack" },
              h("div", { class: "figures" },
                h("div", {}, h("strong", {}, String(decisions.total)), "Decided"),
                h("div", {}, h("strong", {}, String(decisions.by_rule)), "By rule"),
                h("div", {}, h("strong", {}, String(decisions.by_people)), "By people"),
                h("div", {}, h("strong", {}, decisions.median_days == null ? "–" : String(decisions.median_days)), "Median days")),
              h("p", { class: "subtle" }, h("strong", {}, "Median days: "), decisions.definition)))),
        h("div", { class: "grid-2" },
          card({ title: "Approved uses by unit" }, bars(data.by_unit, { empty: "No approved uses yet." })),
          card({ title: "Approved uses by area" }, bars(data.by_domain, { empty: "No approved uses yet." }))),
        h("div", { class: "grid-2" },
          card({ title: "Every use case by status" }, bars(data.by_status, { empty: "Nothing has been submitted yet." })),
          card({ title: "Approved uses by stage" }, bars(data.by_stage, { empty: "No approved uses yet." }))));
    },
  });
}
