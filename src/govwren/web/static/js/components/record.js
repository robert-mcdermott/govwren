// How records, their standing, and their tier are shown everywhere.

import { h, icon } from "../core/dom.js";
import { titleCase } from "../core/format.js";
import { pill } from "./ui.js";

export const TYPES = {
  use_case: { path: "use-cases", label: "Use case", plural: "Use cases", noun: "use case", nouns: "use cases", iconName: "use_case" },
  system: { path: "systems", label: "AI system", plural: "AI systems", noun: "AI system", nouns: "AI systems", iconName: "system" },
  vendor: { path: "vendors", label: "Vendor", plural: "Vendors", noun: "vendor", nouns: "vendors", iconName: "vendor" },
};

export function typeOfRef(ref) {
  const prefix = String(ref).split("-")[0];
  return { UC: "use_case", SYS: "system", VND: "vendor" }[prefix];
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
