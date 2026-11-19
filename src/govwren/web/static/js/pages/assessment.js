// An assessment of one record: the questions of its template, the answers, and the review.

import { get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { dateTime } from "../core/format.js";
import { banner, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { alert, card, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const STATUS = { missing: ["Not started", ""], draft: ["Draft", "warn"], submitted: ["Submitted", "accent"], reviewed: ["Reviewed", "ok"] };

export function assessmentPage(main, params) {
  const at = `/api/v1/assessments/${params.ref}/${params.template}`;
  return show(main, {
    title: "Assessment",
    load: async () => (await get(at, null, { fresh: true })).data,
    view: (data, reload) => {
      document.title = `${data.template.title} · ${data.record.ref}`;
      const editing = data.can.answer && data.status !== "reviewed";
      const controls = new Map();
      const answer = (question) => {
        const value = data.answers[question.key] ?? "";
        if (!editing) {
          const text = question.type === "choice" ? question.options.find((option) => option.key === value)?.label : value;
          return h("div", { class: "stack-sm" }, h("h3", {}, question.label), h("p", { class: "prose pre-line" }, text || h("span", { class: "subtle" }, "Not answered")));
        }
        const label = question.required ? question.label : `${question.label} (optional)`;
        const control = question.type === "choice"
          ? select(label, [["", "Choose…"], ...question.options.map((option) => [option.key, option.label])], { value, hint: question.help ?? null })
          : field(label, { type: "textarea", value, hint: question.help ?? null });
        controls.set(question.key, control);
        return control.node;
      };
      const sections = data.template.sections.map((section) => card({ title: section.title }, h("div", { class: "stack-lg" }, section.questions.map(answer))));
      const problem = banner();
      const send = (submitting) => async (event) => {
        const answers = Object.fromEntries([...controls].map(([key, control]) => [key, control.input.value]));
        const done = await submit({ button: event.currentTarget, banner: problem, fields: Object.fromEntries(controls), run: () => put(at, { answers, submit: submitting }) });
        if (done) {
          toast(submitting ? "Submitted." : "Saved as a draft.");
          reload();
        }
      };
      const review = () => openOverlay({
        title: "Record your review", subtitle: `${data.template.title} · ${data.record.name}`, kind: "dialog",
        render: (body, footer, shut) => {
          const note = field("What you concluded", { type: "textarea", hint: "Kept with the assessment." });
          const trouble = banner();
          const go = button("Mark as reviewed", { kind: "btn-primary" });
          go.addEventListener("click", async () => {
            const done = await submit({ button: go, banner: trouble, fields: { note }, run: () => post(`${at}/review`, { note: note.input.value }) });
            if (done) {
              shut();
              toast("Reviewed.");
              reload();
            }
          });
          body.append(h("div", { class: "stack" }, trouble, note.node));
          footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
          footer.hidden = false;
        },
      });
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: data.record.href }, icon("chevron-left", "icon icon-sm"), data.record.name),
        pageHeader({ eyebrow: `${data.template.title} · ${data.record.ref}`, title: data.record.name, lede: data.template.intro,
          actions: [pill(...STATUS[data.status]), data.can.review ? button("Record your review…", { kind: "btn-primary", onclick: review }) : null] }),
        data.status === "submitted" ? alert("info", icon("info"), h("div", {}, `Submitted${data.submitted_by ? ` by ${data.submitted_by}` : ""}, ${dateTime(data.submitted_at)}. ${editing ? "It can still be corrected until it is reviewed." : "Waiting for governance to review it."}`)) : null,
        data.status === "reviewed" ? alert("ok", icon("check"), h("div", {}, h("strong", {}, `Reviewed${data.reviewed_by ? ` by ${data.reviewed_by}` : ""}, ${dateTime(data.reviewed_at)}. `), data.review_note ?? "")) : null,
        problem, sections,
        editing ? h("div", { class: "form-actions" }, button("Save as a draft", { onclick: send(false) }),
          button(data.status === "submitted" ? "Submit again" : "Submit", { kind: "btn-primary", onclick: send(true) })) : null);
    },
  });
}
