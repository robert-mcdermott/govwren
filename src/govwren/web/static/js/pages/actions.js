// Actions: everything someone must do, in one list. Corrective actions from incidents, and
// the conditions of decisions that have a date or must be met before use.

import { get, post } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { date } from "../core/format.js";
import { query, setQuery } from "../core/router.js";
import { can } from "../core/session.js";
import { banner, field, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

function closeDialog(row, status, reload) {
  const done = status === "done";
  openOverlay({
    title: done ? "Mark as done" : row.kind === "condition" ? "Waive this condition" : "Cancel this action", subtitle: row.title, kind: "dialog",
    render: (body, footer, shut) => {
      const note = field(done ? "What was done?" : "Why is it not needed?", { type: "textarea", hint: "Kept with it on the record." });
      const problem = banner();
      const go = button(done ? "Mark as done" : "Confirm", { kind: done ? "btn-primary" : "btn-danger" });
      go.addEventListener("click", async () => {
        const result = await submit({ button: go, banner: problem, fields: { note },
          run: () => (row.kind === "condition"
            ? post(`/api/v1/conditions/${row.id}/close`, { status: done ? "met" : "waived", note: note.input.value })
            : post(`/api/v1/actions/${row.id}/close`, { status, note: note.input.value })) });
        if (result) {
          shut();
          toast(done ? "Done." : "Closed.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, note.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function actionList(main) {
  const all = can("read_all");
  const scope = all && query().get("scope") === "all" ? "all" : "mine";
  const status = query().get("show") === "all" ? "all" : "open";
  return show(main, {
    title: "Actions",
    load: async () => (await get("/api/v1/actions", { scope, status }, { fresh: true })).data,
    view: (rows, reload) => {
      const toggle = (name, current, pairs, label) => h("div", { class: "segmented", role: "group", "aria-label": label },
        pairs.map(([key, text, value]) => h("button", { type: "button", "aria-pressed": String(current === key),
          onclick: () => setQuery({ [name]: value }, { replace: false }) }, text)));
      const late = rows.filter((row) => row.overdue).length;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Actions", lede: "What must be done, by whom, and by when: actions set after incidents, and the conditions that came with a decision.",
          actions: [all ? toggle("scope", scope, [["mine", "Mine", null], ["all", "Everyone's", "all"]], "Whose actions") : null,
            toggle("show", status, [["open", "Open", null], ["all", "All", "all"]], "Which actions")] }),
        late ? h("p", { class: "due-late" }, `${late} ${late === 1 ? "is" : "are"} overdue.`) : null,
        rows.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "What"), h("th", { scope: "col" }, "About"), h("th", { scope: "col" }, "Owner"),
            h("th", { scope: "col" }, "Due"), h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Close")))),
          h("tbody", {}, rows.map((row) => h("tr", {},
            h("td", {}, h("div", { class: "cell-main" }, row.title),
              h("div", { class: "cell-sub" }, row.source ? h("a", { href: row.source.href }, row.source.label) : "An action", row.detail ? ` · ${row.detail}` : "",
                row.note ? ` · ${row.note}` : "")),
            h("td", {}, row.about ? h("a", { href: row.about.href }, row.about.name) : ""),
            h("td", {}, row.owner ?? h("span", { class: "subtle" }, "Nobody")),
            h("td", { class: "nowrap" }, row.status !== "open" ? pill(row.status === "done" ? "Done" : "Not needed", row.status === "done" ? "ok" : "")
              : row.due_on ? (row.overdue ? pill(`Was due ${date(row.due_on)}`, "danger") : date(row.due_on)) : h("span", { class: "subtle" }, "Before use")),
            h("td", {}, h("div", { class: "row-sm" },
              row.can_close ? button("Done…", { kind: "btn-sm", "aria-label": `Mark as done: ${row.title}`, onclick: () => closeDialog(row, "done", reload) }) : null,
              row.can_cancel ? button(row.kind === "condition" ? "Waive…" : "Cancel…", { kind: "btn-sm btn-ghost", "aria-label": `Not needed: ${row.title}`, onclick: () => closeDialog(row, "cancelled", reload) }) : null))))))))
          : emptyState({ iconName: "check", title: status === "open" ? "Nothing is waiting" : "No actions yet",
            text: scope === "mine" ? "When an action or a condition is yours to meet, it is listed here." : "Actions set after incidents and conditions of approval are listed here." }));
    },
  });
}
