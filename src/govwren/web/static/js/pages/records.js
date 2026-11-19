// The inventory's list pages. Filters, sort, and page all live in the URL.

import { get } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { plural, relative } from "../core/format.js";
import { label, options, unitOptions, units, vocabularies } from "../core/lookups.js";
import { navigate, query, setQuery } from "../core/router.js";
import { can } from "../core/session.js";
import { hrefOf, standingPill, statusOptions, TYPES } from "../components/record.js";
import { EDITORS } from "../components/record-forms.js";
import { card, emptyState, pageHeader, tierBadge } from "../components/ui.js";
import { savedViews, viewsBar } from "../components/views.js";
import { show } from "./page.js";

const USE_CASE_STATUSES = ["draft", "submitted", "in_review", "returned", "approved", "approved_with_conditions",
  "declined", "withdrawn", "suspended", "lapsed", "retired"];
const CATALOG = ["approved", "approved_with_restrictions", "under_evaluation", "not_approved", "not_listed", "retired"];
const VENDOR_STATUSES = ["prospective", "active", "offboarding", "former"];
const TIERS = [["", "Any tier"], ["1", "Minimal"], ["2", "Moderate"], ["3", "High"], ["4", "Critical"]];

const LEDES = {
  use_case: "What AI is being used for, by whom, on what. Each one is requested, reviewed, and revisited.",
  system: "The tools, products, and services that use AI, and each one's standing in the catalog.",
  vendor: "The outside suppliers of AI systems and models.",
  model: "The models behind the tools: suppliers' models, open weights run here, and models trained or tuned in-house.",
  dataset: "The data AI is trained on, tuned with, or given. Descriptions only: the data stays where it is.",
};
const ADD = { use_case: "New request", system: "Add an AI system", vendor: "Add a vendor", model: "Add a model", dataset: "Add a dataset" };

/** Download the list as it is filtered now. */
export function exportMenu(path) {
  const menu = h("select", { class: "select export-menu", "aria-label": "Export this list", onchange: () => {
    if (!menu.value) return;
    const params = new URLSearchParams([...query()].filter(([key, value]) => key !== "cursor" && value !== ""));
    params.set("format", menu.value);
    menu.value = "";
    window.location.assign(`/api/v1/exports/${path}?${params}`);
  } }, h("option", { value: "" }, "Export…"), h("option", { value: "csv" }, "As CSV, for a spreadsheet"), h("option", { value: "json" }, "As JSON"));
  return menu;
}

function filterSelect(name, choices, labelText) {
  const node = h("select", { class: "select", "aria-label": labelText, onchange: () => setQuery({ [name]: node.value, cursor: null }) },
    choices.map(([key, text]) => h("option", { value: key, selected: String(key) === (query().get(name) ?? "") }, text)));
  return node;
}

function sortHeader(text, field) {
  const current = query().get("sort") ?? "-updated_at";
  const active = current.replace(/^-/, "") === field;
  const descending = active && current.startsWith("-");
  return h("th", { scope: "col", "aria-sort": active ? (descending ? "descending" : "ascending") : null },
    h("button", { type: "button", class: "sort-button", onclick: () => setQuery({ sort: active && !descending ? `-${field}` : field, cursor: null }) },
      text, active ? h("span", { "aria-hidden": "true" }, descending ? " ↓" : " ↑") : null));
}

const COLUMNS = {
  use_case: (ctx) => ({
    head: [sortHeader("Use case", "name"), h("th", { scope: "col" }, "Unit"), h("th", { scope: "col" }, "Owner"),
      sortHeader("Tier", "tier"), sortHeader("Standing", "status"), sortHeader("Updated", "updated_at")],
    row: (r) => [
      h("td", {}, h("a", { class: "cell-main", href: hrefOf(r.ref) }, r.name),
        h("div", { class: "cell-sub" }, r.ref, r.systems.length ? ` · ${r.systems.map((s) => s.name).join(", ")}` : "",
          r.sight === "summary" ? " · summary" : "")),
      h("td", {}, ctx.units.byId.get(r.org_unit_id)?.name ?? ""),
      h("td", {}, r.owners.map((o) => o.name).join(", "), r.orphaned ? h("div", { class: "cell-sub warn-text" }, "Owner has left") : null),
      h("td", {}, r.tier ? tierBadge(r.tier) : h("span", { class: "subtle" }, "Not set")),
      h("td", {}, standingPill(r.status)),
      h("td", { class: "nowrap muted" }, relative(r.updated_at)),
    ],
  }),
  system: (ctx) => ({
    head: [sortHeader("AI system", "name"), h("th", { scope: "col" }, "Vendor"), sortHeader("Catalog standing", "catalog_status"),
      h("th", { scope: "col" }, "May be used with"), sortHeader("Updated", "updated_at")],
    row: (r) => [
      h("td", {}, h("a", { class: "cell-main", href: hrefOf(r.ref) }, r.name),
        h("div", { class: "cell-sub" }, [r.ref, label(ctx.vocab, "system_kinds", r.kind), r.edition].filter(Boolean).join(" · "))),
      h("td", {}, r.vendor ? h("a", { href: hrefOf(r.vendor.ref) }, r.vendor.name) : ""),
      h("td", {}, standingPill(r.catalog_status)),
      h("td", {}, r.permitted_data_class ? `Up to ${label(ctx.vocab, "data_classes", r.permitted_data_class)}` : ""),
      h("td", { class: "nowrap muted" }, relative(r.updated_at)),
    ],
  }),
  model: (ctx) => ({
    head: [sortHeader("Model", "name"), sortHeader("Where it comes from", "origin"), h("th", { scope: "col" }, "Sensitivity"),
      sortHeader("Catalog standing", "catalog_status"), sortHeader("Updated", "updated_at")],
    row: (r) => [
      h("td", {}, h("a", { class: "cell-main", href: hrefOf(r.ref) }, r.name),
        h("div", { class: "cell-sub" }, [r.ref, label(ctx.vocab, "model_kinds", r.kind), r.provider, r.version_label].filter(Boolean).join(" · "))),
      h("td", {}, label(ctx.vocab, "model_origins", r.origin)),
      h("td", {}, r.data_class ? label(ctx.vocab, "data_classes", r.data_class) : ""),
      h("td", {}, standingPill(r.catalog_status)),
      h("td", { class: "nowrap muted" }, relative(r.updated_at)),
    ],
  }),
  dataset: (ctx) => ({
    head: [sortHeader("Dataset", "name"), h("th", { scope: "col" }, "Unit"), sortHeader("Data class", "data_class"),
      h("th", { scope: "col" }, "People identifiable?"), sortHeader("Updated", "updated_at")],
    row: (r) => [
      h("td", {}, h("a", { class: "cell-main", href: hrefOf(r.ref) }, r.name),
        h("div", { class: "cell-sub" }, [r.ref, ...(r.data_categories ?? []).map((key) => label(ctx.vocab, "data_categories", key))].join(" · "))),
      h("td", {}, ctx.units.byId.get(r.org_unit_id)?.name ?? ""),
      h("td", {}, r.data_class ? label(ctx.vocab, "data_classes", r.data_class) : ""),
      h("td", {}, label(ctx.vocab, "identifiability", r.identifiability)),
      h("td", { class: "nowrap muted" }, relative(r.updated_at)),
    ],
  }),
  vendor: () => ({
    head: [sortHeader("Vendor", "name"), sortHeader("Standing", "status"), h("th", { scope: "col" }, "Due diligence"),
      sortHeader("Updated", "updated_at")],
    row: (r) => [
      h("td", {}, h("a", { class: "cell-main", href: hrefOf(r.ref) }, r.name),
        h("div", { class: "cell-sub" }, [r.ref, r.website?.replace(/^https?:\/\//, "")].filter(Boolean).join(" · "))),
      h("td", {}, standingPill(r.status)),
      h("td", {}, standingPill(r.due_diligence_status)),
      h("td", { class: "nowrap muted" }, relative(r.updated_at)),
    ],
  }),
};

function filters(type, ctx) {
  const search = h("input", { class: "input", type: "search", value: query().get("q") ?? "",
    placeholder: `Search ${TYPES[type].nouns}`, "aria-label": "Search" });
  let timer = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => setQuery({ q: search.value, cursor: null }), 250);
  });
  const more = [];
  if (type === "use_case") {
    more.push(filterSelect("status", [...statusOptions(USE_CASE_STATUSES, "Any standing"), ["live", "Approved, with or without conditions"]], "Standing"),
      filterSelect("tier", TIERS, "Tier"),
      filterSelect("unit", unitOptions(ctx.units.tree, { blank: "Any unit" }), "Unit"));
  } else if (type === "system") {
    more.push(filterSelect("catalog_status", statusOptions(CATALOG, "Any catalog standing"), "Catalog standing"),
      filterSelect("kind", options(ctx.vocab, "system_kinds", { blank: "Any kind" }), "Kind"));
  } else if (type === "model") {
    more.push(filterSelect("origin", options(ctx.vocab, "model_origins", { blank: "From anywhere" }), "Where it comes from"),
      filterSelect("catalog_status", statusOptions(CATALOG, "Any catalog standing"), "Catalog standing"),
      filterSelect("data_class", options(ctx.vocab, "data_classes", { blank: "Any sensitivity" }), "Sensitivity"));
  } else if (type === "dataset") {
    more.push(filterSelect("data_class", options(ctx.vocab, "data_classes", { blank: "Any data class" }), "Data class"),
      filterSelect("identifiability", options(ctx.vocab, "identifiability", { blank: "Any identifiability" }), "Identifiability"),
      filterSelect("unit", unitOptions(ctx.units.tree, { blank: "Any unit" }), "Unit"));
  } else {
    more.push(filterSelect("status", statusOptions(VENDOR_STATUSES, "Any standing"), "Standing"));
  }
  if (type !== "vendor") {
    const mine = query().get("mine") === "true";
    more.push(h("button", { type: "button", class: `btn${mine ? " btn-primary" : ""}`, "aria-pressed": String(mine),
      onclick: () => setQuery({ mine: mine ? null : "true", cursor: null }) }, "Mine"));
  }
  return { node: h("div", { class: "filters" }, h("div", { class: "filter-search" }, search), more), search };
}

export function recordList(main, type) {
  const meta = TYPES[type];
  return show(main, {
    title: meta.plural,
    load: async () => {
      const params = Object.fromEntries(query());
      const [views, page, vocab, unitIndex, vendors] = await Promise.all([
        savedViews(type),
        get(`/api/v1/${meta.path}`, params, { fresh: true }), vocabularies(), units(),
        ["system", "model"].includes(type) ? get("/api/v1/vendors", { sort: "name", limit: 200 }) : null,
      ]);
      return { page, vocab, units: unitIndex, vendors: vendors?.data ?? [], views };
    },
    view: (data, reload) => {
      const ctx = { vocab: data.vocab, units: data.units };
      const columns = COLUMNS[type](ctx);
      const { total, offset, next_cursor: next, prev_cursor: prev } = data.page.meta;
      const rows = data.page.data;
      const filtering = [...query().keys()].some((key) => !["sort", "cursor"].includes(key));
      // A use case begins as a request; systems and vendors are added directly.
      const add = () => (type === "use_case" ? navigate("/requests/new")
        : EDITORS[type]({ vocab: data.vocab, units: data.units, vendors: data.vendors, onDone: reload }));
      const bar = filters(type, ctx);
      const restore = document.activeElement?.getAttribute?.("aria-label") === "Search";
      if (restore) queueMicrotask(() => {
        bar.search.focus();
        bar.search.setSelectionRange(bar.search.value.length, bar.search.value.length);
      });
      const body = rows.length
        ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, columns.head)),
          h("tbody", {}, rows.map((r) => h("tr", {}, columns.row(r))))))
        : emptyState(filtering
          ? { iconName: "search", title: "Nothing matches", text: "Try fewer words, or clear a filter.",
            action: button("Clear filters", { onclick: () => setQuery(Object.fromEntries([...query().keys()].map((k) => [k, null]))) }) }
          : { iconName: meta.iconName, title: `No ${meta.nouns} yet`, text: LEDES[type],
            action: button(ADD[type], { kind: "btn-primary", onclick: add }) });
      const footer = total > rows.length ? h("div", { class: "row" },
        h("span", { class: "muted numeric" }, `${offset + 1}–${offset + rows.length} of ${total}`),
        h("div", { class: "spacer row-sm" },
          button("Previous", { kind: "btn-sm", iconName: "chevron-left", disabled: !prev, onclick: () => setQuery({ cursor: prev }, { replace: false }) }),
          button("Next", { kind: "btn-sm", disabled: !next, onclick: () => setQuery({ cursor: next }, { replace: false }) }))) : null;
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Inventory", title: meta.plural, lede: LEDES[type],
          actions: [
            type === "model" ? h("a", { class: "btn", href: "/api/v1/bill-of-materials", download: "models.cdx.json" }, "Bill of materials") : null,
            exportMenu(meta.path),
            can("edit_all") && type !== "use_case" ? button("Import", { iconName: "upload", onclick: async () =>
              (await import("../components/record-import.js")).openRecordImport({ type, onDone: reload }) }) : null,
            button(ADD[type], { kind: "btn-primary", iconName: "plus", onclick: add })] }),
        bar.node,
        card({ title: plural(total, meta.noun, meta.nouns), flush: true, footer, actions: viewsBar(type, data.views, reload) }, body));
    },
  });
}

