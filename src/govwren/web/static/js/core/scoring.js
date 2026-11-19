// Which questions are showing, and the likely tier, worked out in the browser as someone
// answers. These are twins of govwren/intake/forms.py (showing) and scoring.py (assess), and
// must agree with them on tests/parity/scoring.json. The server's result is the one recorded.

import { evaluate } from "./conditions.js";

function answered(value) {
  return !(value == null || value === "" || (Array.isArray(value) && value.length === 0));
}

/** { keys: the questions showing, in order; kept: the answers to them }. */
export function showing(schema, answers) {
  const kept = {};
  const keys = [];
  for (const section of schema.sections) {
    if (!evaluate(section.show_when, { answers: kept })) continue;
    for (const question of section.questions) {
      if (!evaluate(question.show_when, { answers: kept })) continue;
      keys.push(question.key);
      if (answered(answers[question.key])) kept[question.key] = answers[question.key];
    }
  }
  return { keys, kept };
}

export function tierFor(definition, total) {
  let level = definition.tiers[0].level;
  for (const tier of definition.tiers) {
    if (total >= tier.min) level = tier.level;
  }
  return level;
}

/** The tier for these answers, with the reason for every part of it. */
export function assess(definition, answers) {
  const context = { answers };
  const factors = {};
  for (const factor of definition.factors) factors[factor.key] = { level: 0, reason: null };
  for (const contribution of definition.contributions) {
    const current = factors[contribution.factor];
    if (contribution.level > current.level && evaluate(contribution.when, context)) {
      current.level = contribution.level;
      current.reason = contribution.reason;
    }
  }
  const total = Object.values(factors).reduce((sum, factor) => sum + factor.level, 0);
  const computed = tierFor(definition, total);
  const floors = (definition.floors ?? [])
    .filter((floor) => floor.tier > computed && evaluate(floor.when, context))
    .map((floor) => ({ tier: floor.tier, reason: floor.reason }));
  const stops = (definition.stops ?? [])
    .filter((stop) => evaluate(stop.when, context))
    .map((stop) => ({ key: stop.key, reason: stop.reason }));
  return {
    factors,
    total,
    computed_tier: computed,
    floors,
    final_tier: Math.max(computed, ...floors.map((floor) => floor.tier)),
    stops,
  };
}

const AUTHORITIES = ["governance", "committee", "committee_with_acceptance"];

/** What happens next: who must review, who decides, by when. The twin of review/routing.py. */
export function route(definition, tier, answers, stops = []) {
  const context = { tier, answers };
  const require = [];
  const conditions = [];
  const rules = [];
  let authority = AUTHORITIES[0];
  let dueDays = null;
  let cadence = null;
  let auto = null;
  for (const rule of definition.rules ?? []) {
    if (!evaluate(rule.when, context)) continue;
    const then = rule.then ?? {};
    rules.push({ key: rule.key, name: rule.name });
    for (const name of then.require ?? []) {
      if (!require.some((entry) => entry.function === name)) require.push({ function: name, rule: rule.name });
    }
    if (AUTHORITIES.indexOf(then.authority ?? authority) > AUTHORITIES.indexOf(authority)) authority = then.authority;
    if ("due_days" in then) dueDays = then.due_days;
    if ("cadence_months" in then) cadence = then.cadence_months;
    for (const key of then.conditions ?? []) {
      if (!conditions.includes(key)) conditions.push(key);
    }
    if (then.auto_approve && auto === null) auto = rule.name;
  }
  if (require.length || stops.length) auto = null;
  return { require, authority, due_days: dueDays, cadence_months: cadence, conditions, auto_approve: auto, rules };
}
