// The request form: one section at a time, questions that appear only when earlier answers
// call for them, and the likely tier shown as the answers change. Saved as you go.

import { get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { units, vocabularies } from "../core/lookups.js";
import { navigate } from "../core/router.js";
import { assess, route, showing } from "../core/scoring.js";
import { label } from "../core/lookups.js";
import { renderQuestion } from "../components/questions.js";
import { previewView, tierReasons } from "../components/tier-panel.js";
import { toast } from "../components/toast.js";
import { alert, card } from "../components/ui.js";
import { show } from "./page.js";

const SAVE_AFTER_MS = 900;

export function intake(main, params) {
  return show(main, {
    title: "New request",
    load: async () => {
      const [program, vocab, unitIndex] = await Promise.all([
        params.ref ? get(`/api/v1/use-cases/${params.ref}/intake`, null, { fresh: true }) : get("/api/v1/intake", null, { fresh: true }),
        vocabularies(), units()]);
      return { program: program.data, vocab, units: unitIndex };
    },
    view: (data) => {
      const { form, scoring } = data.program;
      const schema = form.schema;
      if (params.ref && !data.program.can_edit) {
        queueMicrotask(() => navigate(`/use-cases/${params.ref}?tab=answers`, { replace: true }));
        return h("div");
      }
      const answers = { ...(data.program.answers ?? {}) };
      const ctx = { units: data.units };
      let ref = params.ref ?? null;
      let step = 0;
      let errors = {};
      let timer = null;
      let saving = Promise.resolve();
      let dirty = false;

      const status = h("span", { class: "subtle", "aria-live": "polite" }, ref ? "Saved" : "Not saved yet");
      const body = h("div", { class: "stack-lg" });
      const rail = h("ol", { class: "steps" });
      const panel = h("div");
      const title = h("h1", { tabindex: "-1" }, answers.name || "New request");

      const sections = () => {
        const { keys } = showing(schema, answers);
        const visible = new Set(keys);
        return schema.sections
          .map((section) => ({ ...section, questions: section.questions.filter((question) => visible.has(question.key)) }))
          .filter((section) => section.questions.length);
      };
      const missing = (section) => section.questions.filter((question) => question.required
        && (answers[question.key] == null || answers[question.key] === "" || (Array.isArray(answers[question.key]) && !answers[question.key].length)));

      const drawPanel = () => {
        const { kept } = showing(schema, answers);
        const answered = Object.keys(kept).length;
        const result = assess(scoring.definition, kept);
        const view = previewView(scoring.definition, result);
        const rules = data.program.review?.definition;
        const next = rules ? route(rules, result.final_tier, kept, result.stops) : null;
        const who = { governance: "Governance decides.", committee: "The governance committee decides.",
          committee_with_acceptance: "The committee decides, and an executive accepts the risk." };
        const after = !next ? null : next.auto_approve
          ? h("p", {}, h("strong", {}, "Approved as soon as you submit. "), "No review is needed for a request like this. Standard conditions apply.")
          : h("div", { class: "stack-sm" },
            next.require.length ? h("p", {}, h("strong", {}, "Reviewed by: "),
              next.require.map((entry) => label(data.vocab, "review_functions", entry.function)).join(", "), ".")
              : h("p", {}, "No specialist review is needed."),
            h("p", { class: "muted" }, who[next.authority], next.due_days ? ` Usually within ${next.due_days} working days.` : ""));
        panel.replaceChildren(card({ title: "Likely tier" },
          answered < 4
            ? h("p", { class: "muted" }, "As you answer, the likely risk tier and the reasons for it appear here.")
            : tierReasons(view, { preview: true }),
          h("p", { class: "subtle" }, "The tier decides how much review a request gets. It is confirmed when you submit.")),
        answered >= 4 && after ? card({ title: "What happens next" }, after) : null);
      };

      const save = () => {
        clearTimeout(timer);
        if (!dirty) return saving;
        dirty = false;
        status.textContent = "Saving…";
        saving = saving.then(async () => {
          try {
            if (!ref) {
              if (!answers.name || !answers.unit) {
                status.textContent = "Not saved yet";
                dirty = true;
                return;
              }
              const made = await post("/api/v1/intake", { answers });
              ref = made.data.ref;
              history.replaceState({}, "", `/use-cases/${ref}/request`);
            } else {
              const saved = await put(`/api/v1/use-cases/${ref}/intake`, { answers });
              errors = { ...saved.data.errors };
            }
            status.textContent = `Saved as ${ref}`;
          } catch (error) {
            errors = { ...errors, ...(error.fields ?? {}) };
            status.textContent = error.status === 422 ? "Not saved yet" : "Could not save. Your answers are still here.";
            dirty = true;
            markErrors();
          }
        });
        return saving;
      };

      let controls = new Map();
      const markErrors = () => {
        for (const [key, control] of controls) control.setError(errors[key] ?? null);
      };
      const changed = (key, control) => {
        answers[key] = control.get();
        delete errors[key];
        control.setError(null);
        dirty = true;
        if (key === "name") title.textContent = answers.name || "New request";
        drawPanel();
        clearTimeout(timer);
        timer = setTimeout(() => {
          save();
          // An answer may have opened or closed later sections: redraw the steps, not the questions.
          drawRail();
        }, SAVE_AFTER_MS);
        syncConditional();
      };

      // Show or hide the questions of the current section as answers in it change.
      let lastShown = "";
      const syncConditional = () => {
        const current = sections()[step];
        const shown = current ? current.questions.map((question) => question.key).join(",") : "";
        if (shown !== lastShown) drawSection({ keepFocus: true });
        else drawRail();
      };

      const drawRail = () => {
        const list = sections();
        rail.replaceChildren(...list.map((section, index) => {
          const left = missing(section).length;
          const state = index === step ? "current" : left ? "todo" : "done";
          return h("li", { "data-state": state },
            h("button", { type: "button", class: "step", "aria-current": index === step ? "step" : null, onclick: () => go(index) },
              h("span", { class: "step-mark", "aria-hidden": "true" }, state === "done" ? icon("check", "icon icon-sm") : String(index + 1)),
              h("span", { class: "grow" }, h("span", { class: "step-title" }, section.title),
                left && index !== step ? h("span", { class: "subtle step-note" }, `${left} to answer`) : null)));
        }));
      };

      const go = async (index) => {
        step = Math.max(0, Math.min(index, sections().length - 1));
        drawSection();
        await save();
        window.scrollTo({ top: 0 });
      };

      const submit = async (submitButton) => {
        const list = sections();
        const firstGap = list.findIndex((section) => missing(section).length);
        if (firstGap !== -1) {
          for (const question of missing(list[firstGap])) errors[question.key] = "Answer this question.";
          step = firstGap;
          drawSection();
          controls.get(missing(list[firstGap])[0].key)?.focus();
          return;
        }
        submitButton.disabled = true;
        dirty = true;
        await save();
        if (!ref) {
          submitButton.disabled = false;
          return;
        }
        try {
          const done = await post(`/api/v1/use-cases/${ref}/submit`);
          toast(`${ref} was submitted. Its tier is ${done.data.assessment.tier_label}.`);
          navigate(`/use-cases/${ref}`);
        } catch (error) {
          errors = { ...(error.fields ?? {}) };
          const bad = sections().findIndex((section) => section.questions.some((question) => errors[question.key]));
          if (bad !== -1) step = bad;
          drawSection();
          if (!Object.keys(errors).length) toast(error.detail || "The request could not be submitted.");
          submitButton.disabled = false;
        }
      };

      const drawSection = ({ keepFocus = false } = {}) => {
        const list = sections();
        step = Math.min(step, list.length - 1);
        const section = list[step];
        const focused = keepFocus ? document.activeElement?.closest?.("[data-question]")?.getAttribute("data-question") : null;
        lastShown = section.questions.map((question) => question.key).join(",");
        controls = new Map();
        const nodes = section.questions.map((question) => {
          const control = renderQuestion(question, answers[question.key], () => changed(question.key, control), data.vocab, ctx);
          controls.set(question.key, control);
          return control.node;
        });
        const last = step === list.length - 1;
        const submitButton = button("Submit request", { kind: "btn-primary", onclick: () => submit(submitButton) });
        const gaps = list.reduce((sum, each) => sum + missing(each).length, 0);
        body.replaceChildren(
          h("div", {}, h("div", { class: "eyebrow" }, `Step ${step + 1} of ${list.length}`), h("h2", {}, section.title),
            section.intro ? h("p", { class: "muted" }, section.intro) : null),
          h("div", { class: "stack-lg" }, nodes),
          last && gaps ? alert("info", icon("info"), h("div", {}, `${gaps} required question${gaps === 1 ? "" : "s"} still to answer before you can submit.`)) : null,
          h("div", { class: "form-actions" },
            step > 0 ? button("Back", { iconName: "chevron-left", onclick: () => go(step - 1) }) : null,
            last ? submitButton : button("Continue", { kind: "btn-primary", onclick: () => go(step + 1) }),
            h("span", { class: "spacer" }, status)));
        markErrors();
        drawRail();
        if (focused) controls.get(focused)?.focus();
      };

      drawSection();
      drawPanel();
      return h("div", { class: "stack-lg" },
        h("header", { class: "page-header" }, h("div", { class: "grow" },
          h("div", { class: "eyebrow" }, ref ? `Request · ${ref}` : "Request"), title,
          h("p", { class: "lede" }, schema.intro ?? ""))),
        h("div", { class: "intake" },
          h("nav", { class: "intake-rail", "aria-label": "Sections of the form" }, rail),
          card({}, body),
          h("aside", { class: "intake-panel" }, panel)));
    },
  });
}

