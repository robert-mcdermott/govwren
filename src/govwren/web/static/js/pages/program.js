// The program, edited in the app: the request form, the tiers, the routing rules, and the
// vocabularies. Changes are made to a working copy; nothing is in force until it is
// published, and before publishing you can see what the change would have done to the
// requests already submitted.

import { get, post, put } from "../core/api.js";
import { button, h, icon, iconButton } from "../core/dom.js";
import { dateTime, plural } from "../core/format.js";
import { label, units, vocabularies } from "../core/lookups.js";
import { assess, route, showing } from "../core/scoring.js";
import { conditionEditor, conditionText } from "../components/condition-editor.js";
import { checkbox, field, select } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { renderQuestion } from "../components/questions.js";
import { previewView, tierReasons } from "../components/tier-panel.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

const TABS = [["form", "Request form"], ["tiers", "Tiers"], ["rules", "Routing rules"], ["words", "Vocabularies"], ["versions", "Versions"]];
const TYPE_NAMES = { text: "A line of text", long_text: "A paragraph", number: "A number", date: "A date", choice: "One choice",
  choices: "Several choices", yes_no: "Yes or no", data_class: "A data class", unit: "A unit", systems: "AI tools from the inventory" };
const FIELD_NAMES = { name: "the use case's name", org_unit_id: "its unit", purpose: "its purpose", stage: "its stage", domain: "its domain",
  affected_groups: "who is affected", decision_role: "how outputs are used", human_oversight: "human oversight",
  outputs_used_for: "what outputs are used for", data_class: "its data class", data_categories: "its kinds of data", systems: "the tools it uses" };
const WORD_NAMES = { data_classes: "Data classes", data_categories: "Kinds of data", domains: "Domains", stages: "Stages",
  decision_roles: "How outputs are used", affected_groups: "Who is affected", outputs_used_for: "What outputs are used for",
  owner_kinds: "Kinds of owner", system_kinds: "Kinds of AI system", hosting: "Hosting", access_paths: "Ways a system is reached",
  review_functions: "Review functions", unit_kinds: "Kinds of unit", model_kinds: "Kinds of model", model_origins: "Where a model comes from",
  modalities: "What a model works with", weights_formats: "Formats of weights", tuning_methods: "How a model was tuned",
  sharing: "Who weights may go to", identifiability: "Identifiability", agreement_kinds: "Kinds of agreement",
  reference_kinds: "Kinds of reference", evidence_kinds: "Kinds of evidence", autonomy_levels: "How much an agent does by itself",
  reversibility: "Whether actions can be undone", agent_identities: "Whose identity an agent uses",
  agent_runtimes: "Where an agent runs", agent_delegation: "An agent and other agents", agent_inputs: "What an agent reads" };
const AUTHORITY = { governance: "Governance decides", committee: "The governance committee decides",
  committee_with_acceptance: "The committee decides, and an executive accepts the risk" };
const KINDS = { before_use: "Before use", by_date: "By a date", ongoing: "Ongoing" };

const slug = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
const clone = (value) => JSON.parse(JSON.stringify(value));

function unique(base, taken) {
  let key = base || "item";
  for (let n = 2; taken.has(key); n += 1) key = `${base}_${n}`;
  return key;
}

function move(list, index, by) {
  const to = index + by;
  if (to < 0 || to >= list.length) return false;
  [list[index], list[to]] = [list[to], list[index]];
  return true;
}

/** A labelled input bound to one property of an object. */
function bound(target, key, text, { type = "text", hint = null, onChange, numeric = false, ...attrs } = {}) {
  const made = field(text, { type, value: target[key] ?? "", hint, ...attrs });
  made.input.addEventListener("input", () => {
    const value = made.input.value;
    if (numeric) {
      if (value === "") delete target[key];
      else target[key] = Number(value);
    } else if (value === "" && type !== "text") delete target[key];
    else target[key] = value;
    onChange?.();
  });
  return made.node;
}

function arrows(list, index, redraw, what) {
  return [
    iconButton("chevron-up", `Move ${what} up`, { disabled: index === 0, onclick: () => move(list, index, -1) && redraw() }),
    iconButton("chevron-down", `Move ${what} down`, { disabled: index === list.length - 1, onclick: () => move(list, index, 1) && redraw() }),
  ];
}

/** Everything a condition may be about: each question in the form, and for rules the tier. */
function conditionFields(draft, vocab, { tier = false } = {}) {
  const form = draft.forms[0];
  const out = tier ? [{ key: "tier", label: "The tier", type: "number",
    options: draft.scoring_model.tiers.map((item) => ({ key: item.level, label: item.label })) }] : [];
  for (const section of form.sections) {
    for (const question of section.questions) {
      const options = question.options ?? (question.vocabulary ? (vocab[question.vocabulary] ?? []).map((item) => ({ key: item.key, label: item.label })) : null);
      out.push({ key: `answers.${question.key}`, label: question.label, type: question.type, options });
    }
  }
  return out;
}

// --- The request form ---

function formTab(state, touch) {
  const { draft, data } = state;
  const form = draft.forms[0];
  const original = new Set(data.program.forms[0].sections.flatMap((section) => section.questions.map((question) => question.key)));
  const keys = () => new Set(form.sections.flatMap((section) => section.questions.map((question) => question.key)));
  let pick = state.pick ?? { section: 0, question: null };
  const root = h("div", { class: "editor-split" });
  const draw = () => {
    state.pick = pick;
    const outline = h("div", { class: "outline" }, form.sections.map((section, s) => h("div", { class: "outline-section" },
      h("div", { class: "outline-row" },
        h("button", { type: "button", class: "pick", "aria-current": String(pick.section === s && pick.question == null),
          onclick: () => { pick = { section: s, question: null }; draw(); } }, section.title),
        arrows(form.sections, s, () => { pick = { section: Math.max(0, pick.section), question: null }; touch(); draw(); }, section.title)),
      h("div", { class: "outline-questions" }, section.questions.map((question, q) => h("div", { class: "outline-row" },
        h("button", { type: "button", class: "pick", "aria-current": String(pick.section === s && pick.question === q),
          onclick: () => { pick = { section: s, question: q }; draw(); } }, question.label || "(no label)"),
        arrows(section.questions, q, () => { touch(); draw(); }, question.label))),
      h("div", {}, button("Add a question", { kind: "btn-ghost btn-sm", iconName: "plus", onclick: () => {
        const key = unique("question", keys());
        section.questions.push({ key, type: "text", label: "New question" });
        pick = { section: s, question: section.questions.length - 1 };
        touch();
        draw();
      } }))))),
    h("div", {}, button("Add a section", { iconName: "plus", onclick: () => {
      const key = unique("section", new Set(form.sections.map((section) => section.key)));
      form.sections.push({ key, title: "New section", questions: [{ key: unique("question", keys()), type: "text", label: "New question" }] });
      pick = { section: form.sections.length - 1, question: null };
      touch();
      draw();
    } })));
    const section = form.sections[pick.section] ?? form.sections[0];
    const fields = conditionFields(draft, data.vocab);
    let editor;
    if (pick.question == null) {
      editor = card({ title: "Section", actions: form.sections.length > 1 ? button("Remove section", { kind: "btn-ghost btn-sm", onclick: () => {
        form.sections.splice(pick.section, 1);
        pick = { section: 0, question: null };
        touch();
        draw();
      } }) : null },
      h("div", { class: "stack" },
        bound(section, "title", "Title", { onChange: () => { touch(); } }),
        bound(section, "intro", "Introduction", { type: "textarea", hint: "A line under the title. Optional.", onChange: touch }),
        h("div", { class: "field" }, h("div", { class: "label" }, "Show this section"),
          conditionEditor(section.show_when, { fields, always: "Always", onChange: (value) => {
            if (Object.keys(value).length) section.show_when = value; else delete section.show_when;
            touch();
          } }))));
    } else {
      const question = section.questions[pick.question];
      const isNew = !original.has(question.key);
      const typeSelect = select("Kind of answer", data.question_types.map((key) => [key, TYPE_NAMES[key] ?? key]), { value: question.type });
      typeSelect.input.addEventListener("change", () => {
        question.type = typeSelect.input.value;
        if (["choice", "choices"].includes(question.type)) {
          if (!question.options && !question.vocabulary) question.options = [{ key: "first", label: "First choice" }];
        } else if (question.type === "data_class") {
          delete question.options;
          question.vocabulary = "data_classes";
        } else {
          delete question.options;
          delete question.vocabulary;
        }
        if (question.maps_to && !(data.fields[question.maps_to] ?? []).includes(question.type)) delete question.maps_to;
        touch();
        draw();
      });
      const required = checkbox("An answer is required", { checked: Boolean(question.required) });
      required.input.addEventListener("change", () => {
        if (required.input.checked) question.required = true; else delete question.required;
        touch();
      });
      const fills = Object.entries(data.fields).filter(([, kinds]) => kinds.includes(question.type));
      const mapsTo = fills.length ? select("Fills in", [["", "Nothing on the record: kept as an answer only"], ...fills.map(([key]) => [key, FIELD_NAMES[key] ?? key])],
        { value: question.maps_to ?? "", hint: "An answer can fill a field of the use case, so that it can be filtered and reported on." }) : null;
      mapsTo?.input.addEventListener("change", () => {
        if (mapsTo.input.value) {
          question.maps_to = mapsTo.input.value;
          const needed = data.field_vocabularies[question.maps_to];
          if (needed) {
            question.vocabulary = needed;
            delete question.options;
          }
        } else delete question.maps_to;
        touch();
        draw();
      });
      let choices = null;
      if (["choice", "choices"].includes(question.type)) {
        const source = select("Choices come from", [["own", "A list written here"], ...Object.keys(data.vocab).map((name) => [name, `The vocabulary: ${WORD_NAMES[name] ?? name}`])],
          { value: question.vocabulary ?? "own" });
        source.input.addEventListener("change", () => {
          if (source.input.value === "own") {
            delete question.vocabulary;
            question.options = [{ key: "first", label: "First choice" }];
          } else {
            question.vocabulary = source.input.value;
            delete question.options;
          }
          touch();
          draw();
        });
        const list = question.options ? h("div", { class: "stack-sm" }, question.options.map((option, index) => {
          const fresh = !original.has(question.key) || option.fresh;
          const input = h("input", { class: "input", value: option.label, "aria-label": `Choice ${index + 1}` });
          input.addEventListener("input", () => {
            option.label = input.value;
            if (fresh) option.key = unique(slug(input.value) || "choice", new Set(question.options.filter((o) => o !== option).map((o) => o.key)));
            touch();
          });
          return h("div", { class: "row-sm" }, input, arrows(question.options, index, () => { touch(); draw(); }, option.label),
            iconButton("close", `Remove ${option.label}`, { disabled: question.options.length < 2, onclick: () => {
              question.options.splice(index, 1);
              touch();
              draw();
            } }));
        }), h("div", {}, button("Add a choice", { kind: "btn-ghost btn-sm", iconName: "plus", onclick: () => {
          question.options.push({ key: unique("choice", new Set(question.options.map((o) => o.key))), label: "", fresh: true });
          touch();
          draw();
        } }))) : null;
        choices = h("div", { class: "stack-sm" }, source.node, list);
      }
      const labelInput = field("Question", { value: question.label ?? "" });
      labelInput.input.addEventListener("input", () => {
        question.label = labelInput.input.value;
        if (isNew) question.key = unique(slug(question.label) || "question", new Set([...keys()].filter((key) => key !== question.key)));
        touch();
      });
      labelInput.input.addEventListener("change", draw);
      editor = card({ title: "Question", actions: button("Remove question", { kind: "btn-ghost btn-sm", disabled: section.questions.length < 2, onclick: () => {
        section.questions.splice(pick.question, 1);
        pick = { section: pick.section, question: null };
        touch();
        draw();
      } }), footer: h("span", { class: "subtle" }, `Stored as “${question.key}”.`, isNew ? "" : " This name stays the same, so that rules and past answers keep working.") },
      h("div", { class: "stack" }, labelInput.node,
        bound(question, "help", "Help text", { type: "textarea", hint: "Shown under the question. Optional.", onChange: touch }),
        h("div", { class: "grid-2" }, typeSelect.node, mapsTo?.node), choices, required.node,
        h("div", { class: "field" }, h("div", { class: "label" }, "Ask this question"),
          conditionEditor(question.show_when, { fields: fields.filter((item) => item.key !== `answers.${question.key}`), always: "Always",
            onChange: (value) => {
              if (Object.keys(value).length) question.show_when = value; else delete question.show_when;
              touch();
            } }))));
    }
    root.replaceChildren(card({ title: "Sections and questions", actions: button("Preview", { kind: "btn-sm", onclick: () => preview(state) }) }, outline), editor);
  };
  draw();
  return root;
}

/** The working copy of the form, as a requester would meet it, with the tier it produces. */
function preview(state) {
  const { draft, data } = state;
  const schema = clone(draft.forms[0]);
  for (const section of schema.sections) for (const question of section.questions) for (const option of question.options ?? []) delete option.fresh;
  openOverlay({
    title: "Preview",
    subtitle: "The form as it stands in your working copy. Nothing you enter here is kept.",
    render: (body) => {
      const answers = {};
      const side = h("div", {});
      const main = h("div", { class: "stack-lg" });
      const controls = new Map();
      const draw = () => {
        const { keys, kept } = showing(schema, answers);
        const visible = new Set(keys);
        main.replaceChildren(...schema.sections
          .map((section) => ({ ...section, questions: section.questions.filter((question) => visible.has(question.key)) }))
          .filter((section) => section.questions.length)
          .map((section) => h("div", { class: "form-section stack" }, h("h3", {}, section.title),
            section.intro ? h("p", { class: "muted" }, section.intro) : null,
            section.questions.map((question) => {
              if (!controls.has(question.key)) {
                const made = renderQuestion(question, answers[question.key], () => {
                  answers[question.key] = made.get();
                  draw();
                }, data.vocab, { units: data.units });
                controls.set(question.key, made);
              }
              return controls.get(question.key).node;
            }))));
        const result = assess(draft.scoring_model, kept);
        const next = route(draft.review, result.final_tier, kept, result.stops);
        side.replaceChildren(card({ title: "Likely tier" }, tierReasons(previewView(draft.scoring_model, result), { preview: true }),
          h("p", { class: "subtle" }, next.auto_approve ? "Approved by rule on submission."
            : next.require.length ? `Reviewed by: ${next.require.map((entry) => label(data.vocab, "review_functions", entry.function)).join(", ")}.` : "No specialist review.")));
      };
      draw();
      body.append(h("div", { class: "stack-lg" }, side, main));
    },
  });
}

// --- Tiers ---

function tiersTab(state, touch) {
  const { draft, data } = state;
  const model = draft.scoring_model;
  const fields = conditionFields(draft, data.vocab);
  const root = h("div", { class: "stack-lg" });
  const draw = () => {
    const tiers = card({ title: "The tiers" }, h("div", { class: "stack" },
      h("p", { class: "muted" }, "Each factor scores from 0 to 3. The points are added up, and the total decides the tier. A tier begins at its lowest total."),
      model.tiers.map((tier, index) => h("div", { class: "grid-3" },
        bound(tier, "label", `Tier ${tier.level} is called`, { onChange: touch }),
        index === 0 ? h("div", { class: "field" }, h("div", { class: "label" }, "Begins at"), h("div", { class: "cell-main" }, "0 points"))
          : bound(tier, "min", "Begins at this many points", { type: "number", numeric: true, min: 1, onChange: touch }),
        bound(tier, "description", "In a sentence", { onChange: touch })))));
    const factors = model.factors.map((factor) => {
      const mine = model.contributions.filter((item) => item.factor === factor.key);
      return card({ title: factor.label, actions: button("Add a rule", { kind: "btn-sm", iconName: "plus", onclick: () => {
        model.contributions.push({ factor: factor.key, level: 1, when: {}, reason: "" });
        touch();
        draw();
      } }) }, h("div", { class: "stack" },
        h("p", { class: "muted" }, `Scores 0 (“${factor.levels[0]}”) unless one of these says otherwise. The highest that applies wins.`),
        mine.length ? mine.map((item) => contribution(item, factor, model, fields, touch, draw)) : h("p", { class: "subtle" }, "Nothing raises this factor yet.")));
    });
    root.replaceChildren(tiers, ...factors,
      listCard("Floors", "A floor sets the least a tier can be, whatever the points come to.", model.floors, touch, draw, {
        add: () => ({ tier: 3, when: {}, reason: "" }),
        row: (item) => [
          boundSelect(item, "tier", "At least", model.tiers.map((tier) => [tier.level, tier.label]), touch, true),
          whenField(item, fields, touch),
          bound(item, "reason", "Because", { type: "textarea", hint: "Shown with the tier.", onChange: touch })] }),
      listCard("Prohibited uses", "A request that matches one of these cannot be approved, and is told why.", model.stops, touch, draw, {
        add: () => ({ key: unique("stop", new Set(model.stops.map((stop) => stop.key))), when: {}, reason: "" }),
        row: (item) => [whenField(item, fields, touch),
          bound(item, "reason", "Because", { type: "textarea", hint: "Shown to the requester.", onChange: touch })] }));
  };
  draw();
  return root;
}

function boundSelect(target, key, text, choices, touch, numeric = false) {
  const made = select(text, choices, { value: target[key] ?? "" });
  made.input.addEventListener("change", () => {
    target[key] = numeric ? Number(made.input.value) : made.input.value;
    touch();
  });
  return made.node;
}

function whenField(item, fields, touch, text = "When") {
  return h("div", { class: "field" }, h("div", { class: "label" }, text),
    conditionEditor(item.when, { fields, always: "Always", onChange: (value) => {
      item.when = value;
      touch();
    } }));
}

function contribution(item, factor, model, fields, touch, draw) {
  return h("div", { class: "rule-card" },
    h("div", { class: "rule-head" },
      boundSelect(item, "level", "Scores", factor.levels.map((text, level) => [level, `${level}: ${text}`]).slice(1), touch, true),
      iconButton("close", "Remove this rule", { onclick: () => {
        model.contributions.splice(model.contributions.indexOf(item), 1);
        touch();
        draw();
      } })),
    whenField(item, fields, touch),
    bound(item, "reason", "Because", { hint: "Shown beside the factor, so that the tier explains itself.", onChange: touch }));
}

function listCard(title, lede, list, touch, draw, { add, row }) {
  return card({ title, actions: button("Add", { kind: "btn-sm", iconName: "plus", onclick: () => {
    list.push(add());
    touch();
    draw();
  } }) }, h("div", { class: "stack" }, h("p", { class: "muted" }, lede),
    list.length ? list.map((item, index) => h("div", { class: "rule-card" },
      h("div", { class: "rule-head" }, h("span", { class: "grow subtle" }, `${index + 1} of ${list.length}`),
        iconButton("close", "Remove", { onclick: () => {
          list.splice(index, 1);
          touch();
          draw();
        } })), row(item))) : h("p", { class: "subtle" }, "None.")));
}

// --- Routing rules ---

function rulesTab(state, touch) {
  const { draft, data } = state;
  const review = draft.review;
  const root = h("div", { class: "stack-lg" });
  const draw = () => {
    const fields = conditionFields(draft, data.vocab, { tier: true });
    const functions = (data.vocab.review_functions ?? []).filter((item) => !item.retired);
    const rules = review.rules.map((rule, index) => {
      const then = rule.then ?? (rule.then = {});
      const name = h("input", { class: "input", value: rule.name, "aria-label": "Name of the rule" });
      name.addEventListener("input", () => {
        rule.name = name.value;
        touch();
      });
      const tick = (list, key, text) => {
        const box = checkbox(text, { checked: (then[list] ?? []).includes(key) });
        box.input.addEventListener("change", () => {
          const have = new Set(then[list] ?? []);
          if (box.input.checked) have.add(key); else have.delete(key);
          if (have.size) then[list] = [...have]; else delete then[list];
          touch();
        });
        return box.node;
      };
      const auto = checkbox("Approve at once, with no review, if nothing else requires one", { checked: Boolean(then.auto_approve) });
      auto.input.addEventListener("change", () => {
        if (auto.input.checked) then.auto_approve = true; else delete then.auto_approve;
        touch();
      });
      const authority = select("Who decides", [["", "Leave as it is"], ...data.authorities.map((key) => [key, AUTHORITY[key] ?? key])], { value: then.authority ?? "" });
      authority.input.addEventListener("change", () => {
        if (authority.input.value) then.authority = authority.input.value; else delete then.authority;
        touch();
      });
      return h("div", { class: "rule-card" },
        h("div", { class: "rule-head" }, name, arrows(review.rules, index, () => { touch(); draw(); }, rule.name),
          iconButton("close", `Remove the rule ${rule.name}`, { onclick: () => {
            review.rules.splice(index, 1);
            touch();
            draw();
          } })),
        whenField(rule, fields, touch, "Applies"),
        h("fieldset", {}, h("legend", {}, "Requires a review by"), h("div", { class: "inline-list" }, functions.map((item) => tick("require", item.key, item.label)))),
        h("div", { class: "grid-3" }, authority.node,
          bound(then, "due_days", "Target, in working days", { type: "number", numeric: true, min: 1, onChange: touch }),
          bound(then, "cadence_months", "Look again every (months)", { type: "number", numeric: true, min: 1, onChange: touch })),
        h("fieldset", {}, h("legend", {}, "Adds these standard conditions"),
          h("div", { class: "stack-sm" }, review.condition_templates.map((template) => tick("conditions", template.key, template.text)))),
        auto.node);
    });
    const templates = review.condition_templates.map((template, index) => {
      const kind = select("Kind", Object.entries(KINDS), { value: template.kind });
      kind.input.addEventListener("change", () => {
        template.kind = kind.input.value;
        touch();
      });
      return h("div", { class: "rule-card" },
        bound(template, "text", "Condition", { type: "textarea", onChange: touch }),
        h("div", { class: "grid-3" }, kind.node,
          bound(template, "due_days", "Due after (working days)", { type: "number", numeric: true, min: 1, hint: "For a condition due by a date.", onChange: touch }),
          h("div", { class: "field" }, h("div", { class: "label" }, "Used by"),
            h("div", {}, plural(review.rules.filter((rule) => (rule.then?.conditions ?? []).includes(template.key)).length, "rule")),
            h("div", {}, button("Remove", { kind: "btn-ghost btn-sm", onclick: () => {
              review.condition_templates.splice(index, 1);
              for (const rule of review.rules) if (rule.then?.conditions) rule.then.conditions = rule.then.conditions.filter((key) => key !== template.key);
              touch();
              draw();
            } })))));
    });
    root.replaceChildren(
      card({ title: "Rules", actions: button("Add a rule", { kind: "btn-sm", iconName: "plus", onclick: () => {
        review.rules.push({ key: unique("rule", new Set(review.rules.map((rule) => rule.key))), name: "New rule", when: {}, then: {} });
        touch();
        draw();
      } }) }, h("div", { class: "stack" },
        h("p", { class: "muted" }, "Every rule that applies to a request adds to what happens to it: the reviews it needs, who decides, how soon, and the conditions it carries. Later rules win where two disagree on who decides or how soon."),
        rules)),
      card({ title: "Standard conditions", actions: button("Add a condition", { kind: "btn-sm", iconName: "plus", onclick: () => {
        review.condition_templates.push({ key: unique("condition", new Set(review.condition_templates.map((t) => t.key))), text: "", kind: "ongoing" });
        touch();
        draw();
      } }) }, h("div", { class: "stack" },
        h("p", { class: "muted" }, "Wording that rules attach to approvals, and that reviewers and deciders can pick from."), templates)));
  };
  draw();
  return root;
}

// --- Vocabularies ---

function wordsTab(state, touch) {
  const { draft, data } = state;
  const names = Object.keys(draft.vocabularies).sort((a, b) => (WORD_NAMES[a] ?? a).localeCompare(WORD_NAMES[b] ?? b));
  let name = state.word ?? names[0];
  const root = h("div", { class: "stack-lg" });
  const draw = () => {
    state.word = name;
    const items = draft.vocabularies[name];
    const before = new Set((data.program.vocabularies[name] ?? []).map((item) => item.key));
    const chooser = select("Vocabulary", names.map((key) => [key, WORD_NAMES[key] ?? key]), { value: name });
    chooser.input.addEventListener("change", () => {
      name = chooser.input.value;
      draw();
    });
    root.replaceChildren(card({ title: "Vocabularies" }, h("div", { class: "stack" },
      h("p", { class: "muted" }, "The lists of values that records and forms choose from. Rename a value freely: records hold its permanent key, so nothing is rewritten. A value that records may already hold is retired, not removed: it stays on the records that have it and is no longer offered."),
      chooser.node,
      name === "data_classes" ? alert("info", icon("info"), h("div", {}, "Data classes are ordered from least to most sensitive. Rules compare them, so keep them in order.")) : null,
      h("div", { class: "stack-sm" }, items.map((item, index) => {
        const fresh = !before.has(item.key);
        const text = h("input", { class: "input", value: item.label ?? "", "aria-label": `Label of value ${index + 1}` });
        text.addEventListener("input", () => {
          item.label = text.value;
          if (fresh) item.key = unique(slug(text.value) || "value", new Set(items.filter((other) => other !== item).map((other) => other.key)));
          touch();
        });
        const about = h("input", { class: "input", value: item.description ?? "", placeholder: "What it means (optional)", "aria-label": `Meaning of ${item.label}` });
        about.addEventListener("input", () => {
          if (about.value) item.description = about.value; else delete item.description;
          touch();
        });
        const retire = fresh ? iconButton("close", `Remove ${item.label}`, { onclick: () => {
          items.splice(index, 1);
          touch();
          draw();
        } }) : (() => {
          const box = checkbox("Retired", { checked: Boolean(item.retired) });
          box.input.addEventListener("change", () => {
            if (box.input.checked) item.retired = true; else delete item.retired;
            touch();
          });
          return box.node;
        })();
        return h("div", { class: "word-row" }, text, about, h("div", { class: "row-sm" }, arrows(items, index, () => { touch(); draw(); }, item.label)), retire);
      })),
      h("div", {}, button("Add a value", { iconName: "plus", onclick: () => {
        items.push({ key: unique("value", new Set(items.map((item) => item.key))), label: "" });
        touch();
        draw();
      } })))));
  };
  draw();
  return root;
}

// --- Versions ---

function versionsTab(state) {
  const list = (title, rows) => card({ title, flush: true }, h("ul", {}, rows.map((row) => h("li", { class: "list-row" },
    h("div", { class: "grow" }, h("div", { class: "cell-main" }, `Version ${row.version}`),
      h("div", { class: "cell-sub" }, [row.published_at ? `Published ${dateTime(row.published_at)}` : null, row.published_by ? `by ${row.published_by}` : null].filter(Boolean).join(" "))),
    row.status === "published" ? pill("In force", "ok") : pill("Kept"))))); 
  const versions = state.data.versions;
  return h("div", { class: "stack-lg" },
    alert("info", icon("info"), h("div", {}, "Every published version is kept. A request already decided keeps the form, scoring model, and rules it was decided under, so changing the program never rewrites the past.")),
    h("div", { class: "grid-3" }, list("Request form", versions.form), list("Tiers", versions.scoring_model), list("Routing rules", versions.review)));
}

// --- Checking and publishing ---

function impactView(impact, tiers) {
  if (!impact.requests) return h("p", { class: "muted" }, "No requests have been submitted yet, so there is nothing to compare against.");
  if (!impact.changed) return alert("ok", icon("check"), h("div", {}, `None of the ${plural(impact.requests, "request")} already submitted would have come out differently.`));
  const counts = impact.counts;
  const lines = [
    counts.tier_up ? `${plural(counts.tier_up, "request")} would have had a higher tier` : null,
    counts.tier_down ? `${plural(counts.tier_down, "request")} would have had a lower tier` : null,
    counts.reviews ? `${plural(counts.reviews, "request")} would have needed different reviews` : null,
    counts.by_rule ? `${plural(counts.by_rule, "request")} would have changed between approval by rule and review by people` : null,
    counts.stopped ? `${plural(counts.stopped, "request")} would have changed between allowed and prohibited` : null,
  ].filter(Boolean);
  return h("div", { class: "impact" },
    alert("warn", icon("alert"), h("div", {}, h("strong", {}, `${impact.changed} of ${plural(impact.requests, "request")} already submitted would have come out differently. `),
      "Publishing does not change what was decided; it applies from the next request.")),
    h("ul", { class: "missing" }, lines.map((line) => h("li", {}, line))),
    impact.tier_moves.length ? h("div", { class: "row-sm wrap" }, impact.tier_moves.map((moved) =>
      h("span", { class: "pill" }, `${moved.from} → ${moved.to}: ${moved.count}`))) : null,
    h("ul", { class: "problem-list" }, impact.examples.map((example) => h("li", {},
      h("a", { class: "row-no", href: `/use-cases/${example.ref}`, target: "_blank", rel: "noopener" }, example.ref),
      h("span", {}, h("span", { class: "cell-main" }, example.name), h("div", { class: "cell-sub" }, example.change))))),
    tiers ? null : null);
}

export function programPage(main) {
  return show(main, {
    title: "Program",
    load: async () => {
      const [program, vocab, unitIndex] = await Promise.all([get("/api/v1/program", null, { fresh: true }), vocabularies(), units()]);
      return { ...program.data, vocab, units: unitIndex };
    },
    view: (data, reload) => {
      const state = { data, draft: clone(data.program), tab: "form" };
      const before = Object.fromEntries(Object.entries(data.program).map(([key, value]) => [key, JSON.stringify(value)]));
      const strip = (value) => JSON.stringify(value, (key, item) => (key === "fresh" ? undefined : item));
      const changes = () => Object.fromEntries(Object.entries(state.draft)
        .filter(([key, value]) => strip(value) !== before[key]).map(([key, value]) => [key, JSON.parse(strip(value))]));
      const status = h("div", { class: "grow" });
      const bar = h("div", { class: "program-bar", "data-dirty": "false", role: "status" });
      const body = h("div");
      let checked = null;
      const check = button("Check", { onclick: async () => {
        check.disabled = true;
        try {
          const found = (await post("/api/v1/program/check", changes())).data;
          checked = !found.problems.length ? JSON.stringify(changes()) : null;
          openOverlay({ title: found.problems.length ? "Not ready to publish" : "Ready to publish", kind: "dialog",
            subtitle: found.problems.length ? "Fix these, then check again." : "What your changes would have done to past requests.",
            render: (panel, footer, close) => {
              panel.append(found.problems.length
                ? h("ul", { class: "problem-list" }, found.problems.map((text) => h("li", {}, h("span", {}, text))))
                : impactView(found.impact));
              footer.replaceChildren(h("div", { class: "row" }, button("Close", { kind: "btn-primary", onclick: close })));
              footer.hidden = false;
            } });
        } finally {
          check.disabled = false;
          touch();
        }
      } });
      const publish = button("Publish", { kind: "btn-primary", onclick: async () => {
        publish.disabled = true;
        try {
          const done = (await put("/api/v1/program", changes())).data.published;
          const parts = [Object.values(done.forms ?? {}).some((value) => value !== "unchanged") ? "the request form" : null,
            done.scoring_model !== "unchanged" ? "the tiers" : null, done.review !== "unchanged" ? "the routing rules" : null,
            (done.vocabularies ?? []).length ? "vocabularies" : null].filter(Boolean);
          toast(parts.length ? `Published: ${parts.join(", ")}.` : "Nothing had changed.");
          reload();
        } catch (error) {
          const problems = Object.values(error.fields ?? {});
          openOverlay({ title: "Not published", kind: "dialog", render: (panel, footer, close) => {
            panel.append(h("ul", { class: "problem-list" }, (problems.length ? problems : [error.detail ?? "It could not be published."]).map((text) => h("li", {}, h("span", {}, text)))));
            footer.replaceChildren(h("div", { class: "row" }, button("Close", { kind: "btn-primary", onclick: close })));
            footer.hidden = false;
          } });
          publish.disabled = false;
        }
      } });
      const discard = button("Discard changes", { kind: "btn-ghost", onclick: () => reload() });
      function touch() {
        const changed = Object.keys(changes());
        const dirty = changed.length > 0;
        bar.setAttribute("data-dirty", String(dirty));
        const names = { forms: "the request form", scoring_model: "the tiers", review: "the routing rules", vocabularies: "vocabularies" };
        status.replaceChildren(dirty
          ? h("span", {}, h("strong", {}, "Unpublished changes "), `to ${changed.map((key) => names[key]).join(", ")}. `,
            checked === JSON.stringify(changes()) ? "Checked." : "Check them to see what they would do.")
          : h("span", { class: "muted" }, "This is the program in force. Changes you make here are a working copy until you publish."));
        check.disabled = !dirty;
        publish.disabled = !dirty || checked !== JSON.stringify(changes());
        discard.hidden = !dirty;
      }
      bar.append(status, discard, check, publish);
      const tabs = h("div", { class: "tabs", role: "tablist" });
      const drawTab = () => {
        tabs.replaceChildren(...TABS.map(([key, text]) => h("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(state.tab === key),
          onclick: () => {
            state.tab = key;
            drawTab();
          } }, text)));
        const draw = { form: formTab, tiers: tiersTab, rules: rulesTab, words: wordsTab, versions: versionsTab }[state.tab];
        body.replaceChildren(draw(state, touch));
      };
      drawTab();
      touch();
      if (!data.program.forms?.length || !data.program.scoring_model || !data.program.review) {
        return h("div", { class: "stack-lg" }, pageHeader({ eyebrow: "Governance", title: "Program" }),
          card({}, emptyState({ iconName: "alert", title: "There is no program yet", text: "Load the default program from the command line: govwren init." })));
      }
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Governance", title: "Program",
          lede: `What is asked, how answers become a tier, and what each tier sets in motion. ${plural(data.responses, "request has", "requests have")} been submitted under it so far.` }),
        bar, tabs, body,
        h("div", { hidden: true }, tierBadge(1), conditionText({}, [])));
    },
  });
}
