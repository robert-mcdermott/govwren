// The evidence list: for those who read everything, all of it; for everyone else, what they
// own or added.

import { button, h } from "../core/dom.js";
import { date, plural } from "../core/format.js";
import { label, options, vocabularies } from "../core/lookups.js";
import { query, setQuery } from "../core/router.js";
import { can } from "../core/session.js";
import { allEvidence, size, statePill } from "../components/evidence.js";
import { hrefOf } from "../components/record.js";
import { card, emptyState, pageHeader } from "../components/ui.js";
import { savedViews, viewsBar } from "../components/views.js";
import { show } from "./page.js";

const STATES = [["", "Any state"], ["current", "Current"], ["expiring", "Expires within 60 days"], ["expired", "Expired"], ["withdrawn", "Withdrawn"]];

function supported(item) {
  return item.supports.map((s, index) => [index ? ", " : "",
    s.type === "condition" || s.type === "review_task" ? h("a", { href: s.type === "condition" ? `/use-cases/${s.ref}` : `/reviews?open=${s.ref}` }, s.type === "condition" ? `A condition on ${s.ref}` : `${s.name}, ${s.ref}`)
      : s.type === "agreement" ? h("a", { href: hrefOf(s.ref) }, s.name) : h("a", { href: hrefOf(s.ref) }, `${s.name} (${s.ref})`)]);
}

export function evidencePage(main) {
  return show(main, {
    title: "Evidence",
    load: async () => {
      const [page, vocab, views] = await Promise.all([
        allEvidence(Object.fromEntries(query())), vocabularies(), savedViews("evidence")]);
      return { page, vocab, views };
    },
    view: (data, reload) => {
      const rows = data.page.data;
      const { total, offset, next_cursor: next, prev_cursor: prev } = data.page.meta;
      const filter = (name, choices, text) => {
        const node = h("select", { class: "select", "aria-label": text, onchange: () => setQuery({ [name]: node.value, cursor: null }) },
          choices.map(([key, shown]) => h("option", { value: key, selected: key === (query().get(name) ?? "") }, shown)));
        return node;
      };
      const search = h("input", { class: "input", type: "search", value: query().get("q") ?? "", placeholder: "Search evidence", "aria-label": "Search" });
      let timer = null;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => setQuery({ q: search.value, cursor: null }), 250);
      });
      const filtering = ["q", "kind", "state"].some((key) => query().get(key));
      const body = rows.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, ["Evidence", "Supports", "Looked after by", "Good until"].map((text) => h("th", { scope: "col" }, text)))),
        h("tbody", {}, rows.map((item) => h("tr", {},
          h("td", {}, item.file ? h("a", { class: "cell-main", href: item.file.href, download: item.file.name }, item.title)
            : item.url ? h("a", { class: "cell-main", href: item.url, target: "_blank", rel: "noopener noreferrer" }, item.title)
              : h("span", { class: "cell-main" }, item.title),
          h("div", { class: "cell-sub" }, [item.ref, label(data.vocab, "evidence_kinds", item.kind), item.file ? size(item.file.size) : null].filter(Boolean).join(" · "))),
          h("td", {}, supported(item)),
          h("td", {}, item.owner?.name ?? ""),
          h("td", { class: "nowrap" }, item.expires_on ? date(item.expires_on) : h("span", { class: "subtle" }, "No end date"), " ", statePill(item)))))))
        : emptyState(filtering ? { iconName: "search", title: "Nothing matches", text: "Try fewer words, or clear a filter." }
          : { iconName: "file", title: "No evidence yet", text: "Evidence is attached from the record, condition, or review it supports." });
      const footer = total > rows.length ? h("div", { class: "row" },
        h("span", { class: "muted numeric" }, `${offset + 1}–${offset + rows.length} of ${total}`),
        h("div", { class: "spacer row-sm" },
          button("Previous", { kind: "btn-sm", disabled: !prev, onclick: () => setQuery({ cursor: prev }, { replace: false }) }),
          button("Next", { kind: "btn-sm", disabled: !next, onclick: () => setQuery({ cursor: next }, { replace: false }) }))) : null;
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Inventory", title: "Evidence",
          lede: can("read_all") ? "The documents, links, and notes that decisions rest on, soonest to expire first."
            : "The evidence you look after or attached. Evidence on a record is shown on that record." }),
        h("div", { class: "filters" }, h("div", { class: "filter-search" }, search),
          filter("state", STATES, "State"), filter("kind", options(data.vocab, "evidence_kinds", { blank: "Any kind" }), "Kind")),
        card({ title: plural(total, "piece of evidence", "pieces of evidence"), flush: true, footer,
          actions: viewsBar("evidence", data.views, reload) }, body));
    },
  });
}
