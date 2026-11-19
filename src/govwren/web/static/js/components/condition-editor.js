// A condition, edited as a sentence: "when all of these are true: …". Used wherever the
// program asks "when?": a question that appears, points for a factor, a rule that fires.
// Anything more intricate than a list of tests is edited as JSON, which the server checks.

import { button, h, iconButton } from "../core/dom.js";

const OPS = [
  ["eq", "is"], ["ne", "is not"], ["in", "is one of"], ["not_in", "is not one of"],
  ["contains", "includes"], ["contains_any", "includes any of"], ["contains_all", "includes all of"],
  ["gte", "is at least"], ["gt", "is more than"], ["lte", "is at most"], ["lt", "is less than"],
  ["answered", "is answered"], ["empty", "is not answered"],
];
const MANY = new Set(["in", "not_in", "contains_any", "contains_all"]);
const NONE = new Set(["answered", "empty"]);
const NUMERIC = new Set(["gte", "gt", "lte", "lt"]);

const isTest = (node) => node && typeof node === "object" && "field" in node;

/** How a condition can be shown: as a list of tests joined one way, or only as JSON. */
function read(condition) {
  if (!condition || !Object.keys(condition).length) return { mode: "always", tests: [] };
  if (isTest(condition)) return { mode: "all", tests: [{ ...condition }] };
  for (const mode of ["all", "any"]) {
    if (Array.isArray(condition[mode]) && Object.keys(condition).length === 1 && condition[mode].every(isTest)) {
      return { mode, tests: condition[mode].map((test) => ({ ...test })) };
    }
  }
  return { mode: "json", tests: [] };
}

function write(mode, tests) {
  if (mode === "always" || !tests.length) return {};
  const clean = tests.map((test) => (NONE.has(test.op) ? { field: test.field, op: test.op } : { field: test.field, op: test.op, value: test.value }));
  return clean.length === 1 ? clean[0] : { [mode]: clean };
}

function valueControl(test, field, onChange) {
  if (NONE.has(test.op)) return h("span");
  const options = field?.options;
  if (MANY.has(test.op)) {
    const chosen = Array.isArray(test.value) ? test.value : test.value == null || test.value === "" ? [] : [test.value];
    test.value = chosen;
    if (options) {
      return h("div", { class: "condition-many" }, options.map((option) => h("label", { class: "check" },
        h("input", { type: "checkbox", checked: chosen.includes(option.key), onchange: (event) => {
          test.value = event.target.checked ? [...test.value, option.key] : test.value.filter((key) => key !== option.key);
          onChange();
        } }), h("span", {}, option.label))));
    }
    return h("input", { class: "input", value: chosen.join(", "), placeholder: "Values, separated by commas", "aria-label": "Values",
      oninput: (event) => {
        test.value = event.target.value.split(",").map((part) => part.trim()).filter(Boolean);
        onChange();
      } });
  }
  if (Array.isArray(test.value)) test.value = test.value[0] ?? "";
  if (field?.type === "yes_no") {
    return h("select", { class: "select", "aria-label": "Value", onchange: (event) => {
      test.value = event.target.value === "true";
      onChange();
    } }, h("option", { value: "true", selected: test.value === true }, "Yes"), h("option", { value: "false", selected: test.value !== true }, "No"));
  }
  if (options && !NUMERIC.has(test.op)) {
    if (!options.some((option) => option.key === test.value)) test.value = options[0]?.key ?? "";
    return h("select", { class: "select", "aria-label": "Value", onchange: (event) => {
      test.value = event.target.value;
      onChange();
    } }, options.map((option) => h("option", { value: option.key, selected: option.key === test.value }, option.label)));
  }
  const numeric = NUMERIC.has(test.op) || field?.type === "number";
  return h("input", { class: "input", type: numeric ? "number" : "text", value: test.value ?? "", "aria-label": "Value",
    oninput: (event) => {
      test.value = numeric && event.target.value !== "" ? Number(event.target.value) : event.target.value;
      onChange();
    } });
}

/**
 * condition: the condition as stored. fields: [{ key, label, type, options }] that a test
 * may be about. onChange(condition) is called with the new condition whenever it changes.
 */
export function conditionEditor(condition, { fields, onChange, always = "Always" }) {
  let { mode, tests } = read(condition);
  const root = h("div", { class: "condition-editor" });
  const emit = () => onChange(write(mode, tests));
  const draw = () => {
    if (mode === "json") {
      const area = h("textarea", { class: "textarea mono", rows: 6, "aria-label": "Condition, as JSON" }, JSON.stringify(condition ?? {}, null, 2));
      const note = h("div", { class: "hint subtle" }, "This condition is more intricate than the editor shows, so it is edited as JSON.");
      area.addEventListener("input", () => {
        try {
          onChange(JSON.parse(area.value || "{}"));
          note.textContent = "This condition is edited as JSON.";
        } catch {
          note.textContent = "Not valid JSON yet.";
        }
      });
      root.replaceChildren(area, note);
      return;
    }
    const how = h("select", { class: "select", "aria-label": "When", onchange: () => {
      mode = how.value;
      if (mode !== "always" && !tests.length) tests.push({ field: fields[0]?.key ?? "", op: "eq", value: "" });
      emit();
      draw();
    } }, h("option", { value: "always", selected: mode === "always" }, always),
    h("option", { value: "all", selected: mode === "all" }, tests.length > 1 ? "When all of these are true" : "When this is true"),
    h("option", { value: "any", selected: mode === "any" }, "When any of these is true"));
    const rows = mode === "always" ? [] : tests.map((test, index) => {
      const field = fields.find((item) => item.key === test.field);
      const slot = h("div", { class: "condition-value" });
      const redrawValue = () => slot.replaceChildren(valueControl(test, fields.find((item) => item.key === test.field), emit));
      redrawValue();
      return h("div", { class: "condition-test" },
        h("select", { class: "select", "aria-label": "What", onchange: (event) => {
          test.field = event.target.value;
          test.value = "";
          redrawValue();
          emit();
        } }, field ? null : h("option", { value: test.field, selected: true }, test.field || "Choose"),
        fields.map((item) => h("option", { value: item.key, selected: item.key === test.field }, item.label))),
        h("select", { class: "select", "aria-label": "How it compares", onchange: (event) => {
          test.op = event.target.value;
          redrawValue();
          emit();
        } }, OPS.map(([key, text]) => h("option", { value: key, selected: key === test.op }, text))),
        slot,
        iconButton("close", "Remove this test", { onclick: () => {
          tests.splice(index, 1);
          if (!tests.length) mode = "always";
          emit();
          draw();
        } }));
    });
    root.replaceChildren(how, ...rows,
      mode === "always" ? "" : h("div", {}, button("Add a test", { kind: "btn-ghost btn-sm", iconName: "plus", onclick: () => {
        tests.push({ field: fields[0]?.key ?? "", op: "eq", value: "" });
        emit();
        draw();
      } })));
  };
  draw();
  return root;
}

/** A condition in words, for lists. */
export function conditionText(condition, fields) {
  const { mode, tests } = read(condition);
  if (mode === "always") return "Always";
  if (mode === "json") return "A custom condition";
  const say = (test) => {
    const field = fields.find((item) => item.key === test.field);
    const name = field?.label ?? test.field;
    const word = OPS.find(([key]) => key === test.op)?.[1] ?? test.op;
    if (NONE.has(test.op)) return `${name} ${word}`;
    const show = (value) => (value === true ? "Yes" : value === false ? "No" : field?.options?.find((option) => option.key === value)?.label ?? String(value));
    return `${name} ${word} ${Array.isArray(test.value) ? test.value.map(show).join(", ") : show(test.value)}`;
  };
  return tests.map(say).join(mode === "any" ? " or " : " and ");
}
