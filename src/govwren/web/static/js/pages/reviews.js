// The review queue: the list on the left, the packet of the one that is open on the right.
// J and K (or the arrow keys) move through the list.

import { get } from "../core/api.js";
import { h } from "../core/dom.js";
import { units, vocabularies } from "../core/lookups.js";
import { query, setQuery } from "../core/router.js";
import { dueBadge, REVIEW_KINDS, reviewPacket, reviewStatusPill } from "../components/packet.js";
import { card, emptyState, errorState, pageHeader, skeletonPage, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

let stopKeys = null;

export function reviews(main) {
  stopKeys?.();
  return show(main, {
    title: "Reviews",
    load: async () => {
      const scope = query().get("scope") === "all" ? "all" : "open";
      const [queue, vocab, unitIndex] = await Promise.all([
        get("/api/v1/reviews", { scope }, { fresh: true }), vocabularies(), units()]);
      return { queue: queue.data, vocab, units: unitIndex, scope };
    },
    view: (data, reload) => {
      const open = query().get("open") ?? data.queue.find((item) => item.needs_me)?.ref ?? data.queue[0]?.ref ?? null;
      const pane = h("div", { class: "queue-pane" });
      const list = h("ul", { class: "queue-list", role: "listbox", "aria-label": "Reviews" });

      const drawPacket = async (ref) => {
        if (!ref) {
          pane.replaceChildren(card({}, emptyState({ iconName: "check", title: "Nothing is waiting",
            text: data.scope === "all" ? "No reviews yet." : "Every review you have a part in is finished." })));
          return;
        }
        pane.replaceChildren(card({}, skeletonPage()));
        try {
          const packet = (await get(`/api/v1/reviews/${ref}`, null, { fresh: true })).data;
          pane.replaceChildren(reviewPacket(packet, { vocab: data.vocab, units: data.units, reload }));
        } catch (error) {
          pane.replaceChildren(card({}, errorState(error, () => drawPacket(ref))));
        }
      };
      const select = (ref) => setQuery({ open: ref });
      list.replaceChildren(...data.queue.map((item) => h("li", { role: "option", "aria-selected": String(item.ref === open) },
        h("button", { type: "button", class: "queue-item", onclick: () => select(item.ref) },
          h("div", { class: "row-sm" }, h("span", { class: "cell-main grow truncate" }, item.subject.name),
            item.needs_me ? h("span", { class: "dot-me", title: "Waiting on you" }) : null),
          h("div", { class: "row-sm wrap" }, item.tier ? tierBadge(item.tier) : null, reviewStatusPill(item.status),
            item.kind !== "initial" ? h("span", { class: "pill" }, REVIEW_KINDS[item.kind]) : null),
          h("div", { class: "cell-sub" }, [item.ref, data.units.byId.get(item.subject.org_unit_id)?.name,
            item.tasks_total ? `${item.tasks_done} of ${item.tasks_total} reviews` : null].filter(Boolean).join(" · ")),
          item.my_tasks.length ? h("div", { class: "cell-sub me-text" }, `Yours: ${item.my_tasks.join(", ")}`) : null,
          ["decided", "cancelled"].includes(item.status) ? null : dueBadge(item.due_on, item.overdue)))));

      const onKey = (event) => {
        if (event.target.closest?.("input, textarea, select, [role=dialog]") || event.metaKey || event.ctrlKey) return;
        const step = { j: 1, ArrowDown: 1, k: -1, ArrowUp: -1 }[event.key];
        if (!step || !data.queue.length) return;
        const at = data.queue.findIndex((item) => item.ref === open);
        const next = data.queue[Math.max(0, Math.min(data.queue.length - 1, at + step))];
        if (next && next.ref !== open) {
          event.preventDefault();
          select(next.ref);
        }
      };
      document.addEventListener("keydown", onKey);
      stopKeys = () => document.removeEventListener("keydown", onKey);

      drawPacket(open);
      const scopeToggle = h("div", { class: "segmented", role: "group", "aria-label": "Which reviews" },
        [["open", "Open"], ["all", "All"]].map(([key, text]) => h("button", { type: "button", "aria-pressed": String(data.scope === key),
          onclick: () => setQuery({ scope: key === "open" ? null : key, open: null }) }, text)));
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Reviews", lede: "Requests you have a part in, soonest due first.", actions: scopeToggle }),
        data.queue.length
          ? h("div", { class: "queue" }, h("nav", { class: "queue-side", "aria-label": "Review queue" }, list,
            h("p", { class: "subtle keys-hint" }, h("kbd", {}, "J"), " and ", h("kbd", {}, "K"), " move through the list")), pane)
          : card({}, emptyState({ iconName: "check", title: "Nothing is waiting",
            text: "Requests that need triage, a review, or a decision from you will be listed here." })));
    },
  });
}
