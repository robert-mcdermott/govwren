// Measures: five figures about the program, each with the sentence that defines it, the
// cohort it counts, and its trend.

import { get } from "../core/api.js";
import { h } from "../core/dom.js";
import { date } from "../core/format.js";
import { query, setQuery } from "../core/router.js";
import { card, pageHeader } from "../components/ui.js";
import { show } from "./page.js";

const PERIODS = [["90", "90 days"], ["180", "6 months"], ["365", "A year"]];

export function shown(measure) {
  if (measure.value == null) return "—";
  if (measure.unit === "percent") return `${measure.value}%`;
  if (measure.unit === "days") return `${measure.value} ${measure.value === 1 ? "day" : "days"}`;
  return String(Math.round(measure.value));
}

export function counted(measure) {
  if (measure.key === "throughput") return measure.denominator ? `${measure.numerator} of them by rule` : "None in the period";
  if (measure.numerator != null) return `${measure.numerator} of ${measure.denominator}`;
  return measure.denominator ? `Across ${measure.denominator}` : "Nothing to count yet";
}

/** A small bar chart of the stored values, oldest first, with a table for those who cannot see it. */
function trend(measure) {
  const points = measure.trend.filter((point) => point.value != null);
  if (points.length < 2) return h("p", { class: "subtle" }, "A trend appears once a few days have been stored.");
  const top = Math.max(...points.map((point) => point.value)) || 1;
  const first = points[0];
  const last = points[points.length - 1];
  const bars = h("div", { class: "trend", role: "img", "aria-label": `${measure.title} from ${date(first.on)} to ${date(last.on)}: ${first.value} to ${last.value}` },
    points.map((point) => {
      const bar = h("span", { title: `${date(point.on)}: ${point.value}` });
      bar.style.setProperty("--share", `${Math.max(4, (point.value / top) * 100)}%`);
      return bar;
    }));
  return h("div", { class: "stack-sm" }, bars,
    h("div", { class: "row subtle" }, h("span", { class: "grow" }, date(first.on)), h("span", {}, date(last.on))));
}

export function measuresPage(main) {
  const days = PERIODS.some(([key]) => key === query().get("days")) ? query().get("days") : "90";
  return show(main, {
    title: "Measures",
    load: async () => {
      const end = new Date();
      const start = new Date(end.getTime() - Number(days) * 86400000);
      const iso = (value) => value.toISOString().slice(0, 10);
      return (await get("/api/v1/measures", { from: iso(start), to: iso(end) }, { fresh: true })).data;
    },
    view: (data) => h("div", { class: "stack-lg" },
      pageHeader({ title: "Measures", lede: `How the program is doing, from ${date(data.from)} to ${date(data.to)}. Each figure says what it counts.`,
        actions: h("div", { class: "segmented", role: "group", "aria-label": "Period" }, PERIODS.map(([key, text]) =>
          h("button", { type: "button", "aria-pressed": String(days === key), onclick: () => setQuery({ days: key === "90" ? null : key }, { replace: false }) }, text))) }),
      h("div", { class: "measures" }, data.measures.map((measure) => card({ title: measure.title },
        h("div", { class: "stack" },
          h("div", {}, h("div", { class: "measure-value" }, shown(measure)), h("div", { class: "muted" }, counted(measure))),
          h("p", {}, measure.definition),
          h("p", { class: "subtle" }, h("strong", {}, "Counts: "), measure.cohort),
          trend(measure),
          h("p", { class: "subtle" }, `The trend is the figure for the ninety days before each date, as it was stored that day. ${measure.better === "lower" ? "Lower is better." : "Higher is better."}`)))))),
  });
}
