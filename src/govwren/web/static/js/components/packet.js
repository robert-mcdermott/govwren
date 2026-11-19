// A review, as each person may see it: the request, why it has its tier, what each reviewer
// found, the discussion, and the decision. Governance triages and decides here; reviewers
// record findings; the requester answers questions.

import { post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime, relative, titleCase } from "../core/format.js";
import { label } from "../core/lookups.js";
import { addEvidence, evidenceList } from "./evidence.js";
import { banner, checkbox, field, submit } from "./form.js";
import { confirmAction, openOverlay } from "./overlay.js";
import { hrefOf, recordChip, standingPill } from "./record.js";
import { tierReasons } from "./tier-panel.js";
import { toast } from "./toast.js";
import { alert, avatar, card, pill, tierBadge } from "./ui.js";

const REVIEW_STATUS = {
  triage: ["Waiting for triage", "info"], in_review: ["With reviewers", "info"],
  with_requester: ["With the requester", "warn"], ready: ["Ready for a decision", "accent"],
  decided: ["Decided", ""], cancelled: ["Cancelled", ""],
};
const FINDINGS = {
  no_concerns: ["No concerns", "ok"], conditions: ["Acceptable with conditions", "warn"], objection: ["Objection", "danger"],
};
const OUTCOMES = {
  approved: "Approved", approved_with_conditions: "Approved with conditions", declined: "Declined",
  returned: "Returned to the requester", withdrawn: "Withdrawn",
};
const KINDS = { before_use: "Before use", by_date: "By a date", ongoing: "Ongoing" };
const AUTHORITY = {
  governance: "Governance decides", committee: "The governance committee decides",
  committee_with_acceptance: "The committee decides, and an executive accepts the risk", rule: "Decided by rule",
  requester: "Withdrawn by the requester",
};

export function reviewStatusPill(status) {
  const [text, tone] = REVIEW_STATUS[status] ?? [titleCase(status), ""];
  return pill(text, tone);
}

export function dueBadge(due, overdue) {
  if (!due) return null;
  return h("span", { class: `due${overdue ? " due-late" : ""}`, title: date(due) },
    overdue ? "Overdue: was due " : "Due ", relative(`${due}T23:59:59`));
}

function conditionRow(condition, actions = null) {
  const tone = condition.status === "met" ? "ok" : condition.status === "waived" ? "" : condition.overdue ? "danger" : "info";
  return h("li", { class: "condition" },
    h("div", { class: "grow" },
      h("div", {}, condition.text),
      h("div", { class: "cell-sub" }, [KINDS[condition.kind], condition.owner ? `Owner: ${condition.owner}` : null,
        condition.due_on ? `Due ${date(condition.due_on)}` : null].filter(Boolean).join(" · ")),
      condition.note ? h("div", { class: "cell-sub" }, `${titleCase(condition.status)}: ${condition.note}`) : null,
      condition.evidence?.length ? evidenceList(condition.evidence) : null),
    pill(condition.status === "open" ? (condition.overdue ? "Overdue" : "Open") : titleCase(condition.status), tone),
    actions);
}

/** A list of conditions, with buttons to close them where the person may. */
export function conditionList(conditions, { canClose = false, canWaive = false, reload } = {}) {
  if (!conditions.length) return h("p", { class: "muted" }, "No conditions.");
  const close = (condition, status) => openOverlay({
    title: status === "met" ? "Mark as met" : "Waive this condition",
    subtitle: condition.text,
    kind: "dialog",
    render: (body, footer, shut) => {
      const note = field(status === "met" ? "How was it met?" : "Why is it waived?", { type: "textarea",
        hint: "This is kept on the record with the condition." });
      const problem = banner();
      const go = button(status === "met" ? "Mark as met" : "Waive", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, fields: { note }, banner: problem,
          run: () => post(`/api/v1/conditions/${condition.id}/close`, { status, note: note.input.value }) });
        if (done) {
          shut();
          toast(status === "met" ? "The condition was marked as met." : "The condition was waived.");
          reload?.();
        }
      });
      body.append(h("div", { class: "stack" }, problem, note.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
  return h("ul", { class: "conditions" }, conditions.map((condition) => conditionRow(condition,
    condition.status === "open" && (canClose || canWaive) ? h("div", { class: "row-sm" },
      canClose ? button("Attach", { kind: "btn-sm btn-ghost", "aria-label": `Attach evidence to: ${condition.text}`,
        onclick: () => addEvidence({ supports: [`condition:${condition.id}`], about: condition.text, onDone: reload }) }) : null,
      canClose ? button("Met", { kind: "btn-sm", onclick: () => close(condition, "met") }) : null,
      canWaive ? button("Waive", { kind: "btn-sm btn-ghost", onclick: () => close(condition, "waived") }) : null) : null)));
}

/** The conversation on a review, and a box to add to it. */
export function discussion(packet, reload) {
  const url = `/api/v1/reviews/${packet.ref}/comments`;
  const list = packet.comments.length
    ? h("ol", { class: "thread" }, packet.comments.map((comment) => h("li", { class: `message${comment.visibility === "internal" ? " message-internal" : ""}` },
      avatar(comment.author),
      h("div", { class: "grow" },
        h("div", { class: "row-sm wrap" }, h("span", { class: "cell-main" }, comment.author),
          comment.is_question ? pill("Question for the requester", "warn") : null,
          comment.visibility === "internal" ? pill("Reviewers only") : null,
          h("time", { class: "subtle", datetime: comment.created_at, title: dateTime(comment.created_at) }, relative(comment.created_at))),
        h("p", { class: "prose" }, comment.body)))))
    : h("p", { class: "muted" }, packet.internal ? "Nothing said yet." : "No messages yet.");
  if (!packet.can.reply && !packet.can.comment_internal) return h("div", { class: "stack" }, list);

  const text = h("textarea", { class: "textarea", rows: 3, "aria-label": "Your message",
    placeholder: packet.can.reply ? "Reply to the reviewers" : "Add to the discussion" });
  const problem = banner();
  let visibility = "internal";
  const audience = packet.can.comment_internal ? h("div", { class: "segmented", role: "group", "aria-label": "Who sees this" }) : null;
  const ask = packet.can.ask ? checkbox("Ask the requester, and pause the clock until they reply", {}) : null;
  const drawAudience = () => {
    audience?.replaceChildren(...[["internal", "Reviewers only"], ["requester", "To the requester"]].map(([key, text_]) =>
      h("button", { type: "button", "aria-pressed": String(visibility === key), onclick: () => {
        visibility = key;
        if (ask) ask.node.hidden = key !== "requester";
        drawAudience();
      } }, text_)));
  };
  drawAudience();
  if (ask) ask.node.hidden = true;
  const send = button(packet.can.reply ? "Send reply" : "Add", { kind: "btn-primary" });
  send.addEventListener("click", async () => {
    const done = await submit({ button: send, banner: problem,
      run: () => post(url, { body: text.value, visibility: packet.can.reply ? "requester" : visibility,
        question: Boolean(ask?.input.checked && visibility === "requester") }) });
    if (done) {
      toast(packet.can.reply ? "Your reply was sent." : "Added.");
      reload();
    }
  });
  return h("div", { class: "stack" }, list,
    h("div", { class: "composer stack-sm" }, problem, text, h("div", { class: "row wrap" }, audience, ask?.node, h("span", { class: "spacer" }, send))));
}

function conditionsPicker(packet, chosen) {
  const boxes = [];
  const custom = [];
  const customList = h("div", { class: "stack-sm" });
  const offered = packet.proposed_conditions.length ? packet.proposed_conditions : [];
  const offeredKeys = new Set(offered.map((item) => item.template_key).filter(Boolean));
  const more = packet.condition_templates.filter((template) => !offeredKeys.has(template.key));
  const row = (item, checked) => {
    const box = checkbox(item.text, { checked, hint: [KINDS[item.kind ?? "ongoing"], item.from].filter(Boolean).join(" · ") });
    boxes.push({ box, item });
    return box.node;
  };
  const addCustom = () => {
    const text = h("input", { class: "input", type: "text", placeholder: "What is required", "aria-label": "Condition" });
    const kind = h("select", { class: "select", "aria-label": "When" }, Object.entries(KINDS).map(([key, text_]) => h("option", { value: key }, text_)));
    kind.value = "ongoing";
    const due = h("input", { class: "input", type: "date", "aria-label": "Due date", hidden: true });
    kind.addEventListener("change", () => {
      due.hidden = kind.value !== "by_date";
    });
    custom.push({ text, kind, due });
    customList.append(h("div", { class: "custom-condition" }, text, kind, due));
    text.focus();
  };
  const node = h("fieldset", {}, h("legend", {}, "Conditions"),
    offered.length ? h("div", { class: "stack-sm" }, offered.map((item) => row(item, chosen))) : null,
    more.length ? h("details", { class: "examples" }, h("summary", {}, "More standard conditions"),
      h("div", { class: "stack-sm more-conditions" }, more.map((template) => row({ template_key: template.key, text: template.text, kind: template.kind }, false)))) : null,
    customList,
    button("Write another condition", { kind: "btn-sm", iconName: "plus", onclick: addCustom }));
  const values = () => [
    ...boxes.filter(({ box }) => box.input.checked).map(({ item }) => ({ template_key: item.template_key ?? null, text: item.text, kind: item.kind ?? "ongoing", due_on: item.due_on ?? null })),
    ...custom.filter(({ text }) => text.value.trim()).map(({ text, kind, due }) => ({ text: text.value.trim(), kind: kind.value, due_on: due.value || null })),
  ];
  return { node, values };
}

function findingForm(packet, task, reload) {
  openOverlay({
    title: `${task.label} review`,
    subtitle: `${packet.ref} · ${packet.subject.name}`,
    render: (body, footer, close) => {
      let finding = "no_concerns";
      const picker = conditionsPicker({ ...packet, proposed_conditions: [] }, false);
      picker.node.hidden = true;
      const options = h("div", { class: "stack-sm", role: "radiogroup", "aria-label": "Finding" },
        Object.entries(FINDINGS).map(([key, [text]]) => h("label", { class: "choice" },
          h("input", { type: "radio", name: "finding", value: key, checked: key === finding, onchange: () => {
            finding = key;
            picker.node.hidden = key !== "conditions";
          } }),
          h("div", { class: "grow" }, h("div", { class: "cell-main" }, text),
            h("div", { class: "cell-sub" }, { no_concerns: "Nothing in your area stands in the way.",
              conditions: "Acceptable if the conditions you name are attached.",
              objection: "It should not go ahead as proposed. Whoever decides must address this." }[key])))));
      const notes = field("Notes", { type: "textarea", hint: "Seen by governance and other reviewers, never by the requester. Needed for conditions or an objection." });
      const problem = banner();
      const save = button("Record finding", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, fields: { notes }, banner: problem,
          run: () => post(`/api/v1/reviews/${packet.ref}/tasks/${task.id}/complete`,
            { finding, notes: notes.input.value, conditions: finding === "conditions" ? picker.values() : [] }) });
        if (done) {
          close();
          toast("Your finding was recorded.");
          reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem, options, picker.node, notes.node));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function decisionForm(packet, outcome, reload) {
  const titles = { approved: "Approve", declined: "Decline", returned: "Return to the requester" };
  const objections = packet.tasks.filter((task) => task.finding === "objection");
  openOverlay({
    title: titles[outcome],
    subtitle: `${packet.ref} · ${packet.subject.name}`,
    render: (body, footer, close) => {
      const picker = outcome === "approved" ? conditionsPicker(packet, true) : null;
      const rationale = field(outcome === "returned" ? "What do you need from them?" : "Reason for the decision", { type: "textarea",
        hint: outcome === "returned" ? "Sent to the requester. The clock stops until they reply."
          : "Shown to the requester and kept on the record. A decision is never edited, only superseded." });
      const problem = banner();
      const save = button(titles[outcome], { kind: outcome === "declined" ? "btn-danger" : "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, fields: { rationale }, banner: problem,
          run: () => post(`/api/v1/reviews/${packet.ref}/decision`,
            { outcome, rationale: rationale.input.value, conditions: picker ? picker.values() : [] }) });
        if (done) {
          close();
          toast({ approved: "Approved.", declined: "Declined.", returned: "Returned to the requester." }[outcome]);
          reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem,
        outcome === "approved" && objections.length ? alert("warn", icon("alert"), h("div", {},
          h("strong", {}, `${objections.map((task) => task.label).join(" and ")} objected. `),
          "You can still approve, but say in your reason how the objection is answered. The record will show the decision was made over it.")) : null,
        rationale.node, picker?.node));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function triagePanel(packet, reload) {
  const remove = packet.tasks.map((task) => ({ task, box: checkbox(task.label, { checked: true, hint: task.required_by }) }));
  const required = new Set(packet.tasks.map((task) => task.function));
  const add = packet.review_functions.filter((item) => !required.has(item.key)).map((item) => ({ item, box: checkbox(item.label, {}) }));
  const reason = field("Reason for the change", { type: "textarea", rows: 2, hint: "Needed only if you change what the rules require." });
  const problem = banner();
  const go = button("Confirm and start", { kind: "btn-primary" });
  go.addEventListener("click", async () => {
    const done = await submit({ button: go, fields: { reason }, banner: problem,
      run: () => post(`/api/v1/reviews/${packet.ref}/triage`, {
        remove: remove.filter(({ box }) => !box.input.checked).map(({ task }) => task.function),
        add: add.filter(({ box }) => box.input.checked).map(({ item }) => item.key), reason: reason.input.value }) });
    if (done) {
      toast(done.data.status === "ready" ? "Triaged. No review is required, so it is ready for a decision." : "Triaged. Reviewers have been notified.");
      reload();
    }
  });
  return card({ title: "Triage" }, h("div", { class: "stack" }, problem,
    h("p", { class: "muted" }, "Confirm the reviews the rules require, or change them with a reason."),
    remove.length ? h("fieldset", {}, h("legend", {}, "Required by the rules"), h("div", { class: "stack-sm" }, remove.map(({ box }) => box.node)))
      : h("p", {}, "The rules require no review. Once confirmed, it is ready for a decision."),
    h("details", { class: "examples" }, h("summary", {}, "Require another review"), h("div", { class: "grid-2 more-conditions" }, add.map(({ box }) => box.node))),
    reason.node, h("div", { class: "form-actions" }, go)));
}

function taskCard(packet, task, reload) {
  const [text, tone] = FINDINGS[task.finding] ?? [];
  const state = task.status === "waived" ? pill("Not required")
    : task.status === "completed" ? (packet.internal && text ? pill(text, tone) : pill("Completed", "ok"))
      : pill(task.overdue ? "Overdue" : "Waiting", task.overdue ? "danger" : "info");
  return h("li", { class: "task" },
    h("div", { class: "row wrap" }, h("span", { class: "cell-main" }, task.label), state,
      task.assignee ? h("span", { class: "muted" }, task.assignee) : packet.internal && task.status === "pending" ? h("span", { class: "subtle" }, "Nobody has taken it") : null,
      h("span", { class: "spacer row-sm" },
        task.can_claim ? button("Take it", { kind: "btn-sm", onclick: async () => {
          await post(`/api/v1/reviews/${packet.ref}/tasks/${task.id}/claim`);
          reload();
        } }) : null,
        task.can_complete ? button("Attach", { kind: "btn-sm btn-ghost", "aria-label": `Attach evidence to the ${task.label} review`,
          onclick: () => addEvidence({ supports: [`review_task:${task.id}`], about: `${task.label} review of ${packet.subject.name}`, onDone: reload }) }) : null,
        task.can_complete ? button("Record finding", { kind: "btn-sm btn-primary", onclick: () => findingForm(packet, task, reload) }) : null)),
    task.required_by ? h("div", { class: "cell-sub" }, task.required_by) : null,
    task.notes ? h("p", { class: "prose task-notes" }, task.notes) : null,
    task.evidence?.length ? evidenceList(task.evidence) : null,
    task.recommended_conditions?.length ? h("ul", { class: "recommended" }, task.recommended_conditions.map((item) => h("li", {}, item.text))) : null);
}

/** The whole packet. ctx: { vocab, units, reload }. */
export function reviewPacket(packet, ctx) {
  const { reload } = ctx;
  const subject = packet.subject;
  const unit = ctx.units.byId.get(subject.org_unit_id);
  const decision = packet.decisions[packet.decisions.length - 1];
  const open = !["decided", "cancelled"].includes(packet.status);
  const decideBar = packet.can.decide && packet.status !== "triage" ? h("div", { class: "decide-bar" },
    h("div", { class: "grow" }, h("div", { class: "cell-main" }, AUTHORITY[packet.authority] ?? "Decision"),
      h("div", { class: "cell-sub" }, packet.status === "ready" ? "Every review is finished." : `Waiting on ${packet.waiting_on}.`)),
    button("Approve…", { kind: "btn-primary", disabled: packet.status !== "ready", onclick: () => decisionForm(packet, "approved", reload) }),
    button("Return…", { disabled: packet.status === "with_requester", onclick: () => decisionForm(packet, "returned", reload) }),
    button("Decline…", { kind: "btn-danger", onclick: () => decisionForm(packet, "declined", reload) })) : null;

  return h("div", { class: "stack-lg packet" },
    h("header", { class: "stack-sm" },
      h("div", { class: "eyebrow" }, `Review · ${packet.ref}`),
      h("h2", { class: "packet-title" }, h("a", { href: hrefOf(subject.ref) }, subject.name)),
      h("div", { class: "row-sm wrap" }, subject.tier ? tierBadge(subject.tier, packet.assessment?.tier_label) : null,
        reviewStatusPill(packet.status), open ? dueBadge(packet.due_on, packet.overdue) : null,
        h("span", { class: "subtle" }, `${subject.ref} · opened ${relative(packet.opened_at)}${packet.opened_by ? ` by ${packet.opened_by}` : ""}`))),
    packet.assessment?.stops.length ? alert("danger", icon("alert"), h("div", {}, h("strong", {}, "A prohibited use. "),
      packet.assessment.stops.map((stop) => stop.reason).join(" "), " It cannot be approved.")) : null,
    packet.can.triage ? triagePanel(packet, reload) : null,
    decideBar,
    decision ? card({ title: OUTCOMES[decision.outcome] ?? "Decision" }, h("div", { class: "stack" },
      h("p", { class: "prose" }, decision.rationale),
      h("div", { class: "subtle" }, [decision.by_rule ? "By rule" : decision.decided_by ? `By ${decision.decided_by}` : null,
        dateTime(decision.decided_at), decision.approved_until ? `Approved until ${date(decision.approved_until)}` : null,
        decision.over_objection ? "Made over an objection" : null].filter(Boolean).join(" · ")),
      packet.conditions.length ? conditionList(packet.conditions) : null)) : null,
    card({ title: "The request" }, h("div", { class: "stack" },
      h("p", { class: "prose" }, subject.purpose ?? "No description."),
      h("dl", { class: "dl" },
        h("dt", {}, "Unit"), h("dd", {}, unit?.name ?? ""),
        h("dt", {}, "Owners"), h("dd", {}, (subject.owners ?? []).map((owner) => owner.name).join(", ")),
        h("dt", {}, "Data"), h("dd", {}, [label(ctx.vocab, "data_classes", subject.data_class),
          ...(subject.data_categories ?? []).map((key) => label(ctx.vocab, "data_categories", key))].filter(Boolean).join(" · ")),
        h("dt", {}, "Systems"), h("dd", {}, subject.systems?.length ? h("div", { class: "stack-sm" }, subject.systems.map((system) =>
          h("div", { class: "row-sm" }, recordChip(system), standingPill(system.catalog_status)))) : "None named"),
        subject.human_oversight ? [h("dt", {}, "Oversight"), h("dd", {}, subject.human_oversight)] : null),
      h("a", { href: `${hrefOf(subject.ref)}?tab=answers` }, "See every answer"))),
    packet.assessment ? card({ title: "Why this tier" }, tierReasons(packet.assessment)) : null,
    card({ title: "Reviews", actions: packet.tasks.length ? h("span", { class: "muted numeric" },
      `${packet.tasks.filter((task) => task.status !== "pending").length} of ${packet.tasks.length} finished`) : null },
    packet.tasks.length ? h("ul", { class: "tasks" }, packet.tasks.map((task) => taskCard(packet, task, reload)))
      : h("p", { class: "muted" }, "No review is required for this request.")),
    card({ title: "Discussion" }, discussion(packet, reload)),
    packet.can.withdraw && packet.can.reply ? h("div", {}, button("Withdraw this request", { kind: "btn-ghost", onclick: () => confirmAction({
      title: "Withdraw this request?", text: "The review will be closed. You can make a new request later.", confirmLabel: "Withdraw", danger: true,
      run: async () => {
        await post(`/api/v1/reviews/${packet.ref}/withdraw`, { reason: "" });
        toast("The request was withdrawn.");
        reload();
      } }) })) : null,
    h("p", { class: "subtle" }, `With reviewers ${packet.time.with_reviewers_days} days · with the requester ${packet.time.with_requester_days} days`));
}

