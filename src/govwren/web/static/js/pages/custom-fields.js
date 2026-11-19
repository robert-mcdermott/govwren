// Program → Fields: what an organization adds to each kind of record.

import { get, put } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { banner, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { TYPES } from "../components/record.js";
import { toast } from "../components/toast.js";
import { card, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

function editField(kinds, current, save) {
  const label = field("Label", { value: current?.label ?? "", maxlength: 80, hint: "What people see beside the answer." });
  const kind = select("Kind of answer", Object.entries(kinds), { value: current?.kind ?? "text" });
  const choices = field("Choices", { type: "textarea", rows: 4, value: (current?.options ?? []).join("\n"), hint: "One to a line. At least two." });
  const help = field("Help", { value: current?.help ?? "", maxlength: 300, hint: "Optional. A line shown under the field when it is edited." });
  const sync = () => {
    choices.node.hidden = kind.input.value !== "choice";
  };
  kind.input.addEventListener("change", sync);
  sync();
  openOverlay({
    title: current ? "Change a field" : "Add a field", kind: "dialog",
    render: (body, footer, shut) => {
      const problem = banner();
      const go = button(current ? "Save" : "Add it", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const next = { ...(current?.key ? { key: current.key } : {}), label: label.input.value, kind: kind.input.value, help: help.input.value,
          ...(kind.input.value === "choice" ? { options: choices.input.value.split("\n").map((line) => line.trim()).filter(Boolean) } : {}) };
        if (await submit({ button: go, banner: problem, run: () => save(next) })) shut();
      });
      body.append(h("div", { class: "stack" }, problem, label.node, kind.node, choices.node, help.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function customFieldsPage(main) {
  return show(main, {
    title: "Fields",
    load: async () => (await get("/api/v1/record-types", null, { fresh: true })).data,
    view: (data, reload) => {
      const store = async (type, fields, message) => {
        const saved = await put(`/api/v1/record-types/${type}/custom-fields`, { fields });
        toast(message);
        reload();
        return saved;
      };
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Program", title: "Fields",
          lede: "Add your own fields to a kind of record: a cost center, a contract number, a go-live date. They are shown on each record under More details, kept in its history, and included in its dossier." }),
        Object.entries(TYPES).map(([type, meta]) => {
          const fields = data.custom[type] ?? [];
          return card({ title: meta.plural, flush: fields.length > 0,
            actions: button("Add a field", { kind: "btn-sm", iconName: "plus", "aria-label": `Add a field to ${meta.nouns}`,
              onclick: () => editField(data.custom_kinds, null, (next) => store(type, [...fields, next], "The field was added.")) }) },
          fields.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, ["Label", "Kind of answer", "Help", ""].map((heading) => h("th", { scope: "col" }, heading || h("span", { class: "sr-only" }, "Actions"))))),
            h("tbody", {}, fields.map((item, index) => h("tr", {},
              h("td", {}, h("span", { class: "cell-main" }, item.label), h("div", { class: "cell-sub" }, item.key)),
              h("td", {}, pill(data.custom_kinds[item.kind]), item.options ? h("div", { class: "cell-sub" }, item.options.join(" · ")) : null),
              h("td", { class: "muted" }, item.help ?? ""),
              h("td", {}, h("div", { class: "row-sm" },
                button("Change", { kind: "btn-sm", "aria-label": `Change ${item.label}`,
                  onclick: () => editField(data.custom_kinds, item, (next) => store(type, fields.map((each, at) => at === index ? next : each), "The field was changed.")) }),
                button("Remove", { kind: "btn-sm btn-ghost", "aria-label": `Remove ${item.label}`,
                  onclick: () => store(type, fields.filter((_, at) => at !== index), "The field was removed. Answers already given are kept on the records.") }))))))))
            : h("p", { class: "muted" }, `Nothing has been added to ${meta.nouns}.`));
        }));
    },
  });
}
