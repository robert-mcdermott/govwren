// Declaring a change and retiring a record: the two dialogs, loaded when one is opened.

import { post } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { navigate } from "../core/router.js";
import { banner, field, select, submit } from "./form.js";
import { openOverlay } from "./overlay.js";
import { TYPES } from "./record.js";
import { toast } from "./toast.js";

function reasonDialog({ title, subtitle, label, hint, action, danger = false, run, done }) {
  openOverlay({
    title, subtitle, kind: "dialog",
    render: (body, footer, shut) => {
      const reason = field(label, { type: "textarea", hint });
      const problem = banner();
      const go = button(action, { kind: danger ? "btn-danger" : "btn-primary" });
      go.addEventListener("click", async () => {
        const result = await submit({ button: go, banner: problem, fields: { reason, summary: reason, statement: reason }, run: () => run(reason.input.value) });
        if (result) {
          shut();
          done(result);
        }
      });
      body.append(h("div", { class: "stack" }, problem, reason.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function declareChange(record) {
  reasonDialog({
    title: "Declare a change", subtitle: record.name, label: "What is changing?",
    hint: "A sentence is enough. Next you correct the answers that are different now. If nothing the approval rested on has changed, it stands, and the change is recorded.",
    action: "Continue to the answers",
    run: (summary) => post(`/api/v1/use-cases/${record.ref}/change`, { summary }),
    done: () => navigate(`/use-cases/${record.ref}/request`),
  });
}

export function retireRecord(record, dependents, reload) {
  const others = dependents ? ` The owners of the ${dependents === 1 ? "record that relies" : `${dependents} records that rely`} on it will be told.` : "";
  reasonDialog({
    title: `Retire this ${TYPES[record.type].label.toLowerCase()}`, subtitle: record.name, label: "Why is it no longer in use?",
    hint: `It stays in the inventory, with its history, marked as retired.${others}`,
    action: "Retire it", danger: true,
    run: (reason) => post(`/api/v1/records/${record.ref}/retire`, { reason }),
    done: () => {
      toast("Retired.");
      reload();
    },
  });
}

export function requestException(record) {
  openOverlay({
    title: "Ask for an exception", subtitle: record.name, kind: "drawer",
    render: (body, footer, shut) => {
      const title = field("A short name for it", { maxlength: 200, hint: "Such as: Use before the security assessment is finished." });
      const requirement = field("Which requirement cannot be met?", { type: "textarea" });
      const justification = field("Why can it not be met for now?", { type: "textarea" });
      const measures = field("What is done instead?", { type: "textarea", hint: "What keeps the risk down while the exception is in force." });
      const until = field("When does it end?", { type: "date", hint: "An exception always ends. A year at most; it can be renewed." });
      // On a use, an exception can set aside one of GovWren's own rules. Only one granted for
      // that rule does.
      const rule = record.type === "use_case" ? select("Is it an exception to one of GovWren's own rules?",
        [["", "No: to a requirement of our own"], ["health_agreement", "Yes: health information needs a covering agreement"]],
        { hint: "Choose the rule only if it is the one that stops this use being approved." }) : null;
      const problem = banner();
      const go = button("Ask for the exception", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const made = await submit({ button: go, banner: problem, fields: { title, requirement, justification, measures, ends_on: until, ...(rule ? { rule } : {}) },
          run: () => post("/api/v1/exceptions", { record: record.ref, title: title.input.value, requirement: requirement.input.value,
            justification: justification.input.value, measures: measures.input.value, ends_on: until.input.value || null,
            rule: rule?.input.value || null }) });
        if (made) {
          shut();
          toast(`${made.data.ref} was sent to governance.`);
          navigate(`/exceptions/${made.data.ref}`);
        }
      });
      body.append(h("div", { class: "stack" }, problem, title.node, rule?.node, requirement.node, justification.node, measures.node, until.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

function answerRisk(packet, reload, accept) {
  reasonDialog({
    title: accept ? "Accept the risk" : "Decline to accept the risk", subtitle: packet.subject.name,
    label: accept ? "What you accept, in your own words" : "Why you do not accept it",
    hint: "Kept on the record with your name and the date.", action: accept ? "I accept the risk" : "I do not accept it", danger: !accept,
    run: (statement) => post(`/api/v1/reviews/${packet.ref}/acceptance/answer`, { accept, statement }),
    done: () => {
      toast(accept ? "Recorded. Thank you." : "Recorded.");
      reload();
    },
  });
}
export const acceptRisk = (packet, reload) => answerRisk(packet, reload, true);
export const declineRisk = (packet, reload) => answerRisk(packet, reload, false);

export async function askAcceptance(packet, reload) {
  const { peoplePicker } = await import("./people-picker.js");
  openOverlay({
    title: "Ask someone to accept the risk", subtitle: packet.subject.name, kind: "dialog",
    render: (body, footer, shut) => {
      const problem = banner();
      const ask = async (account) => {
        try {
          await post(`/api/v1/reviews/${packet.ref}/acceptance`, { account_id: account.id });
          shut();
          toast(`${account.display_name} was asked.`);
          reload();
        } catch (error) {
          problem.textContent = error.fields?.account_id ?? error.detail ?? "They could not be asked.";
          problem.hidden = false;
        }
      };
      body.append(h("div", { class: "stack" }, problem,
        h("p", { class: "muted" }, "Choose the person accountable for this risk, such as the head of the division. It cannot be someone who made or owns the request."),
        peoplePicker({ label: "Who will accept it?", onPick: ask })));
      footer.replaceChildren(h("div", { class: "row" }, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}
