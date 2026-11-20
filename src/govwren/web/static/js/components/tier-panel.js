// A tier and the reasons for it: each factor's level and what set it, floors, and stops.
// Used live beside the request form, and on a record for the tier that was recorded.

import { h, icon } from "../core/dom.js";
import { alert, tierBadge } from "./ui.js";

function pips(level, max) {
  return h("span", { class: "pips", role: "img", "aria-label": `Level ${level} of ${max}` },
    Array.from({ length: max }, (_, index) => h("i", { class: index < level ? "on" : "" })));
}

/**
 * view: { factors: [{label, level, max, reason}], total, max_total, final_tier, tier_label,
 *         computed_tier, computed_label, floors, stops, override, tiers }
 */
export function tierReasons(view, { preview = false } = {}) {
  const raised = view.final_tier !== view.computed_tier && !view.override;
  return h("div", { class: "stack" },
    h("div", { class: "row" }, tierBadge(view.final_tier, view.tier_label),
      h("span", { class: "muted numeric" }, `${view.total} of ${view.max_total} points`)),
    view.stops.length ? alert("danger", icon("alert"), h("div", {},
      h("strong", {}, preview ? "This would be a prohibited use. " : "A prohibited use. "),
      view.stops.map((stop) => stop.reason).join(" "),
      preview ? " You can still submit it, but it cannot be approved." : "")) : null,
    view.override ? alert("info", icon("info"), h("div", {},
      h("strong", {}, `Changed from ${view.computed_label} by ${view.override.by ?? "a reviewer"}. `), view.override.reason)) : null,
    raised ? alert("warn", icon("info"), h("div", {},
      h("strong", {}, `The points alone would make it ${view.computed_label}. `), view.floors.map((floor) => floor.reason).join(" "))) : null,
    preview && view.factors.some((factor) => factor.unanswered)
      ? h("p", { class: "subtle" }, "Factors marked “Not answered yet” count as nothing so far. The tier can rise as you answer them.")
      : null,
    h("ul", { class: "factors" }, view.factors.map((factor) => h("li", {},
      h("div", { class: "row" }, h("span", { class: "cell-main grow" }, factor.label), pips(factor.level, factor.max)),
      h("div", { class: factor.unanswered ? "cell-sub subtle" : "cell-sub" }, factor.unanswered ? "Not answered yet" : factor.reason)))),
    h("details", { class: "examples" }, h("summary", {}, "How points become a tier"),
      h("dl", {}, view.tiers.map((tier, index) => {
        const next = view.tiers[index + 1];
        return [h("dt", {}, tier.label), h("dd", {}, `${tier.min}${next ? `–${next.min - 1}` : " and above"} points. ${tier.description ?? ""}`)];
      }))));
}

/** The answers a condition reads, by question key. */
function fieldsOf(condition, out = new Set()) {
  if (!condition || typeof condition !== "object") return out;
  if (typeof condition.field === "string" && condition.field.startsWith("answers.")) out.add(condition.field.slice("answers.".length));
  for (const part of [...(condition.all ?? []), ...(condition.any ?? []), condition.not].filter(Boolean)) fieldsOf(part, out);
  return out;
}

const empty = (value) => value == null || value === "" || (Array.isArray(value) && !value.length);

/** Shape a live assessment (from core/scoring.js) like the server's view of a recorded one.
 *  Given the answers, a factor none of whose questions has an answer yet is marked as such,
 *  so that a level of nothing is not read as an answer of "nothing". */
export function previewView(definition, result, answers = null) {
  const labels = new Map(definition.tiers.map((tier) => [tier.level, tier.label]));
  const reads = new Map(definition.factors.map((factor) => [factor.key, new Set()]));
  for (const contribution of definition.contributions ?? []) fieldsOf(contribution.when, reads.get(contribution.factor));
  return {
    factors: definition.factors.map((factor) => ({
      label: factor.label,
      level: result.factors[factor.key].level,
      max: factor.levels.length - 1,
      reason: result.factors[factor.key].reason ?? factor.levels[0],
      unanswered: Boolean(answers) && result.factors[factor.key].level === 0
        && reads.get(factor.key).size > 0 && [...reads.get(factor.key)].every((key) => empty(answers[key])),
    })),
    total: result.total,
    max_total: definition.factors.reduce((sum, factor) => sum + factor.levels.length - 1, 0),
    computed_tier: result.computed_tier,
    computed_label: labels.get(result.computed_tier),
    final_tier: result.final_tier,
    tier_label: labels.get(result.final_tier),
    floors: result.floors,
    stops: result.stops,
    override: null,
    tiers: definition.tiers,
  };
}
