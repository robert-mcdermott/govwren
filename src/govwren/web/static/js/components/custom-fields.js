// The fields an organization has added to a kind of record: shown on the record, and edited there.

import { patch } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { date } from "../core/format.js";
import { banner, checkbox, field, select, submit } from "./form.js";
import { openOverlay } from "./overlay.js";
import { TYPES } from "./record.js";
import { toast } from "./toast.js";
import { card } from "./ui.js";

function shown(definition, value) {
  if (value == null || value === "") return h("span", { class: "subtle" }, "Not answered");
  if (definition.kind === "yes_no") return value ? "Yes" : "No";
  if (definition.kind === "date") return date(value);
  return String(value);
}

function edit(record, definitions, reload) {
  const inputs = definitions.map((definition) => {
    const value = record.custom?.[definition.key];
    const hint = definition.help ?? null;
    if (definition.kind === "yes_no") {
      const box = checkbox(definition.label, { checked: value === true, hint });
      return { definition, node: box.node, read: () => box.input.checked, setError: () => {}, input: box.input };
    }
    const made = definition.kind === "choice"
      ? select(definition.label, [["", "Not answered"], ...definition.options.map((option) => [option, option])], { value: value ?? "", hint })
      : field(definition.label, { hint, value: value ?? "", type: { long: "textarea", date: "date", number: "number" }[definition.kind] ?? "text",
        ...(definition.kind === "long" ? { rows: 4 } : {}), ...(definition.kind === "number" ? { step: "any" } : {}) });
    return { definition, node: made.node, input: made.input, setError: made.setError,
      read: () => definition.kind === "number" ? (made.input.value === "" ? null : Number(made.input.value)) : made.input.value };
  });
  openOverlay({
    title: "More details", subtitle: `${record.ref} · ${record.name}`, kind: "drawer",
    render: (body, footer, shut) => {
      const problem = banner();
      const go = button("Save", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem,
          fields: Object.fromEntries(inputs.map((input) => [`custom.${input.definition.key}`, input])),
          run: () => patch(`/api/v1/${TYPES[record.type].path}/${record.ref}`,
            { version: record.version, custom: Object.fromEntries(inputs.map((input) => [input.definition.key, input.read()])) }) });
        if (done) {
          shut();
          toast("Saved.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, inputs.map((input) => input.node)));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

/** The card on a record's page, or nothing if no fields have been added for its kind. */
export function customCard(record, definitions, reload) {
  if (!definitions?.length || record.sight !== "full") return null;
  return card({ title: "More details",
    actions: record.can?.edit ? button("Edit", { kind: "btn-sm", "aria-label": "Edit more details", onclick: () => edit(record, definitions, reload) }) : null },
  h("dl", { class: "dl" }, definitions.flatMap((definition) => [h("dt", {}, definition.label), h("dd", {}, shown(definition, record.custom?.[definition.key]))])));
}
