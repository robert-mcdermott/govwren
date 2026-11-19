// The questions a form can ask, one renderer per type. Each returns
// { node, get(), setError(message), focus() } and calls onChange when its answer changes.

import { get as apiGet } from "../core/api.js";
import { h, icon, uid } from "../core/dom.js";
import { unitOptions } from "../core/lookups.js";
import { can, session } from "../core/session.js";
import { standingPill } from "./record.js";

function shell(question, control, { group = false } = {}) {
  const id = uid("q");
  const error = h("div", { class: "error", id: `${id}-error`, role: "alert", hidden: true });
  const help = question.help ? h("p", { class: "hint", id: `${id}-help` }, question.help) : null;
  const mark = question.required ? null : h("span", { class: "optional" }, " optional");
  const node = group
    ? h("fieldset", { class: "question", "data-question": question.key, "aria-describedby": help ? `${id}-help` : null },
      h("legend", {}, question.label, mark), help, control, error)
    : h("div", { class: "question field", "data-question": question.key },
      h("label", { for: id }, question.label, mark), help, control, error);
  if (!group) {
    control.id = id;
    if (help) control.setAttribute("aria-describedby", `${id}-help`);
  }
  return {
    node,
    setError: (message) => {
      error.hidden = !message;
      error.textContent = message ?? "";
      node.classList.toggle("has-error", Boolean(message));
    },
    focus: () => (group ? node.querySelector("input, select, textarea, button") : control)?.focus(),
  };
}

function optionsOf(question, vocab) {
  if (question.vocabulary) {
    return (vocab[question.vocabulary] ?? []).filter((item) => !item.retired)
      .map((item) => ({ key: item.key, label: item.label, help: item.description, examples: item.examples }));
  }
  return question.options ?? [];
}

function text(question, value, onChange) {
  const long = question.type === "long_text";
  const control = long
    ? h("textarea", { class: "textarea", rows: 4 }, value ?? "")
    : h("input", { class: "input", type: question.type === "number" ? "number" : question.type === "date" ? "date" : "text", value: value ?? "" });
  control.addEventListener("input", onChange);
  return { ...shell(question, control), get: () => {
    const raw = control.value.trim();
    if (raw === "") return null;
    return question.type === "number" ? Number(raw) : raw;
  } };
}

function choice(question, value, onChange, vocab) {
  const name = uid("choice");
  let current = value ?? null;
  const cards = optionsOf(question, vocab).map((option) => {
    const examples = Object.entries(option.examples ?? {});
    return h("label", { class: "choice" },
      h("input", { type: "radio", name, value: option.key, checked: option.key === current, onchange: () => {
        current = option.key;
        onChange();
      } }),
      h("div", { class: "grow" }, h("div", { class: "cell-main" }, option.label),
        option.help ? h("div", { class: "cell-sub" }, option.help) : null,
        examples.length ? h("details", { class: "examples" }, h("summary", {}, "Examples"),
          h("dl", {}, examples.map(([group, list]) => [h("dt", {}, group), h("dd", {}, list.join(" · "))]))) : null));
  });
  return { ...shell(question, h("div", { class: "stack-sm" }, cards), { group: true }), get: () => current };
}

function choices(question, value, onChange, vocab) {
  const chosen = new Set(value ?? []);
  const boxes = optionsOf(question, vocab).map((option) => {
    const id = uid("check");
    return h("div", { class: "check" },
      h("input", { type: "checkbox", id, checked: chosen.has(option.key), onchange: (event) => {
        if (event.target.checked) chosen.add(option.key);
        else chosen.delete(option.key);
        onChange();
      } }),
      h("label", { for: id }, option.label, option.help ? h("span", { class: "subtle" }, ` ${option.help}`) : null));
  });
  const all = optionsOf(question, vocab).map((option) => option.key);
  return { ...shell(question, h("div", { class: "grid-2" }, boxes), { group: true }),
    get: () => (chosen.size ? all.filter((key) => chosen.has(key)) : null) };
}

function yesNo(question, value, onChange) {
  const name = uid("yn");
  let current = typeof value === "boolean" ? value : null;
  const radio = (label, answer) => h("label", { class: "choice choice-inline" },
    h("input", { type: "radio", name, checked: current === answer, onchange: () => {
      current = answer;
      onChange();
    } }), h("span", { class: "cell-main" }, label));
  return { ...shell(question, h("div", { class: "row" }, radio("Yes", true), radio("No", false)), { group: true }), get: () => current };
}

function unit(question, value, onChange, vocab, ctx) {
  const me = session();
  const own = new Set([...(me.member_units ?? []), ...(me.steward_units ?? [])]);
  const offered = can("edit_all") || !own.size ? null : own;
  const choicesList = unitOptions(ctx.units.tree, { only: offered, blank: "Choose a unit" });
  const control = h("select", { class: "select", onchange: onChange },
    choicesList.map(([key, label]) => h("option", { value: key, selected: String(key) === String(value ?? "") }, label)));
  return { ...shell(question, control), get: () => (control.value ? Number(control.value) : null) };
}

function systems(question, value, onChange) {
  const chosen = new Map();
  let all = [];
  const list = h("div", { class: "stack-sm" });
  const search = h("input", { class: "input", type: "search", placeholder: "Find a tool by name", "aria-label": "Find a tool by name" });
  const results = h("div", { class: "pick-results" });
  const draw = () => {
    list.replaceChildren(...[...chosen.values()].map((system) => h("div", { class: "owner-row" },
      icon("system"), h("div", { class: "grow" }, h("span", { class: "cell-main" }, system.name),
        h("span", { class: "cell-sub" }, ` ${[system.ref, system.edition].filter(Boolean).join(" · ")}`)),
      standingPill(system.catalog_status),
      h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => {
        chosen.delete(system.ref);
        draw();
        onChange();
      } }, "Remove"))));
    const words = search.value.toLowerCase().trim();
    const offered = words.length || all.length <= 8
      ? all.filter((s) => !chosen.has(s.ref) && `${s.name} ${s.ref} ${s.edition ?? ""}`.toLowerCase().includes(words)).slice(0, 8)
      : [];
    results.replaceChildren(...offered.map((system) => h("button", { type: "button", class: "pick-item", onclick: () => {
      chosen.set(system.ref, system);
      search.value = "";
      draw();
      onChange();
    } }, icon("system"), h("span", {}, h("span", { class: "cell-main" }, system.name),
      h("span", { class: "cell-sub" }, ` ${[system.ref, system.edition].filter(Boolean).join(" · ")}`)),
    h("span", { class: "spacer" }, standingPill(system.catalog_status)))));
  };
  search.addEventListener("input", draw);
  apiGet("/api/v1/systems", { sort: "name", limit: 200 }).then((answer) => {
    all = answer.data.filter((system) => system.status !== "retired");
    for (const ref of value ?? []) {
      const found = all.find((system) => system.ref === ref);
      if (found) chosen.set(ref, found);
    }
    draw();
  }).catch(() => {});
  const frame = shell(question, h("div", { class: "stack-sm" }, list, search, results), { group: true });
  return { ...frame, get: () => (chosen.size ? [...chosen.keys()] : (value?.length && !all.length ? value : null)) };
}

const RENDERERS = { text, long_text: text, number: text, date: text, choice, data_class: choice, choices, yes_no: yesNo, unit, systems };

export function renderQuestion(question, value, onChange, vocab, ctx) {
  return (RENDERERS[question.type] ?? text)(question, value, onChange, vocab, ctx);
}

/** An answer as words, for showing a submitted request. */
export function answerText(question, value, vocab, ctx) {
  if (value == null || value === "" || (Array.isArray(value) && !value.length)) return null;
  const labels = new Map(optionsOf(question, vocab).map((option) => [option.key, option.label]));
  if (["choice", "data_class"].includes(question.type)) return labels.get(value) ?? String(value);
  if (question.type === "choices") return value.map((key) => labels.get(key) ?? key).join(", ");
  if (question.type === "yes_no") return value ? "Yes" : "No";
  if (question.type === "unit") return ctx.units.byId.get(value)?.name ?? String(value);
  if (question.type === "systems") return value.map((ref) => ctx.systems?.get(ref) ?? ref).join(", ");
  return String(value);
}
