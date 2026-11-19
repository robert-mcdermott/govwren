// How records, their standing, and their tier are shown everywhere.

import { h, icon } from "../core/dom.js";
import { titleCase } from "../core/format.js";
import { pill } from "./ui.js";

export const TYPES = {
  use_case: { path: "use-cases", label: "Use case", plural: "Use cases", noun: "use case", nouns: "use cases", iconName: "use_case" },
  system: { path: "systems", label: "AI system", plural: "AI systems", noun: "AI system", nouns: "AI systems", iconName: "system" },
  model: { path: "models", label: "Model", plural: "Models", noun: "model", nouns: "models", iconName: "model",
    blurb: "A specific model: a supplier's, open weights you run, or one you trained or tuned." },
  dataset: { path: "datasets", label: "Dataset", plural: "Datasets", noun: "dataset", nouns: "datasets", iconName: "dataset",
    blurb: "Data that AI is trained on, tuned with, or given. A description only: the data stays where it is." },
  vendor: { path: "vendors", label: "Vendor", plural: "Vendors", noun: "vendor", nouns: "vendors", iconName: "vendor" },
};

/** What the organization calls a unit, when it has its own word. */
export const UNIT = { label: "Unit", plural: "Units" };

/** Use the organization's own words for the kinds of record and for units. */
export function applyTerms(terms = {}) {
  const lower = (word) => /^[A-Z][a-z]/.test(word) ? word[0].toLowerCase() + word.slice(1) : word;
  for (const [key, words] of Object.entries(terms)) {
    if (key === "unit") Object.assign(UNIT, { label: words.one, plural: words.many });
    else if (TYPES[key]) Object.assign(TYPES[key], { label: words.one, plural: words.many, noun: lower(words.one), nouns: lower(words.many) });
  }
}

export function typeOfRef(ref) {
  const prefix = String(ref).split("-")[0];
  return { UC: "use_case", SYS: "system", MDL: "model", DS: "dataset", VND: "vendor" }[prefix];
}

export function hrefOf(ref) {
  return `/${TYPES[typeOfRef(ref)].path}/${ref}`;
}

/** A record as a link: its type's icon, its name, and its reference. */
export function recordChip(record, { link = true } = {}) {
  const type = typeOfRef(record.ref);
  const inner = [icon(TYPES[type].iconName), h("span", { class: "truncate" }, record.name), h("span", { class: "ref" }, record.ref)];
  return link
    ? h("a", { class: "chip", "data-record": type, href: hrefOf(record.ref) }, inner)
    : h("span", { class: "chip", "data-record": type }, inner);
}

// Standing: a word, a mark, and a tone. Never a color alone.
const STANDING = {
  draft: ["Draft", "", "○"],
  submitted: ["Submitted", "info", "◔"],
  in_review: ["In review", "info", "◔"],
  returned: ["With requester", "warn", "↩"],
  approved: ["Approved", "ok", "●"],
  approved_with_conditions: ["Approved with conditions", "ok", "◐"],
  declined: ["Declined", "danger", "✕"],
  withdrawn: ["Withdrawn", "", "○"],
  suspended: ["Suspended", "danger", "!"],
  lapsed: ["Lapsed", "danger", "!"],
  retired: ["Retired", "", "○"],
  // AI systems in the catalog
  not_listed: ["Not in the catalog", "", "○"],
  under_evaluation: ["Under evaluation", "info", "◔"],
  approved_with_restrictions: ["Approved with restrictions", "ok", "◐"],
  not_approved: ["Not approved", "danger", "✕"],
  // Vendors
  prospective: ["Prospective", "", "○"],
  active: ["Active", "ok", "●"],
  offboarding: ["Offboarding", "warn", "↩"],
  former: ["Former", "", "○"],
  // Due diligence
  not_started: ["Not started", "", "○"],
  in_progress: ["In progress", "info", "◔"],
  complete: ["Complete", "ok", "●"],
};

export function standingLabel(status) {
  return STANDING[status]?.[0] ?? titleCase(status);
}

export function standingPill(status) {
  const [label, tone, mark] = STANDING[status] ?? [titleCase(status), "", "○"];
  const node = pill("", tone);
  node.append(h("span", { "aria-hidden": "true" }, mark), label);
  return node;
}

export function statusOptions(keys, blank) {
  return [["", blank], ...keys.map((key) => [key, standingLabel(key)])];
}
