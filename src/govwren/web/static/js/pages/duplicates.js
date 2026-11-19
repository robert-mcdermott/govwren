// Records that look like the same thing entered twice, and a way to fold one into the other.

import { get, post } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { plural } from "../core/format.js";
import { query, setQuery } from "../core/router.js";
import { can } from "../core/session.js";
import { confirmAction } from "../components/overlay.js";
import { hrefOf, standingPill, TYPES } from "../components/record.js";
import { toast } from "../components/toast.js";
import { card, emptyState, pageHeader } from "../components/ui.js";
import { show } from "./page.js";

const KINDS = ["system", "model", "dataset", "vendor"];

export function duplicatesPage(main) {
  const type = KINDS.includes(query().get("type")) ? query().get("type") : "system";
  return show(main, {
    title: "Duplicates",
    load: async () => (await get("/api/v1/duplicates", { type }, { fresh: true })).data,
    view: (pairs, reload) => {
      const merge = (from, into) => confirmAction({
        title: `Merge ${from.ref} into ${into.ref}?`,
        text: h("div", { class: "stack-sm" },
          h("p", {}, `Everything that points to ${from.name} (${from.ref}) will point to ${into.name} (${into.ref}): links, evidence, references, and helpers.`),
          h("p", {}, `${from.ref} is kept, marked as retired, and leads to ${into.ref}. This cannot be undone.`)),
        confirmLabel: "Merge", danger: true,
        run: async () => {
          await post(`/api/v1/records/${from.ref}/merge`, { into: into.ref });
          toast(`${from.ref} was merged into ${into.ref}.`);
          reload();
        } });
      const side = (record, other) => h("div", { class: "duplicate-side" },
        h("a", { class: "cell-main", href: hrefOf(record.ref) }, record.name),
        h("div", { class: "cell-sub" }, [record.ref, record.detail].filter(Boolean).join(" · ")),
        h("div", { class: "row-sm wrap" }, standingPill(record.status),
          can("edit_all") ? button("Keep this one", { kind: "btn-sm", "aria-label": `Keep ${record.name} ${record.ref}, and merge ${other.ref} into it`,
            onclick: () => merge(other, record) }) : null));
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Governance", title: "Duplicates",
          lede: "Records that look like the same thing entered twice. Two editions of a product, or two versions of a model, are different things and are not listed." }),
        h("div", { class: "tabs", role: "tablist" }, KINDS.map((key) => h("button", { type: "button", class: "tab", role: "tab",
          "aria-selected": String(key === type), onclick: () => setQuery({ type: key === "system" ? null : key }, { replace: false }) }, TYPES[key].plural))),
        card({ title: plural(pairs.length, "likely pair"), flush: pairs.length > 0 },
          pairs.length ? h("ul", {}, pairs.map((pair) => h("li", { class: "duplicate-pair" },
            side(pair.records[0], pair.records[1]),
            h("div", { class: "duplicate-score", title: "How alike their names are" }, `${Math.round(pair.score * 100)}%`),
            side(pair.records[1], pair.records[0]))))
            : emptyState({ iconName: "check", title: `No ${TYPES[type].nouns} look alike`, text: "Nothing to tidy here." })));
    },
  });
}
