// One inventory record: what it is, who answers for it, what it is connected to, and its history.

import { get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime, relative } from "../core/format.js";
import { label, units, vocabularies } from "../core/lookups.js";
import { query, setQuery } from "../core/router.js";
import { showing } from "../core/scoring.js";
import { can } from "../core/session.js";
import { banner, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { conditionList, discussion, dueBadge, reviewStatusPill } from "../components/packet.js";
import { peoplePicker } from "../components/people-picker.js";
import { answerText } from "../components/questions.js";
import { recordChip, standingPill, TYPES } from "../components/record.js";
import { EDITORS } from "../components/record-forms.js";
import { tierReasons } from "../components/tier-panel.js";
import { toast } from "../components/toast.js";
import { alert, avatar, card, emptyState, pill, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

function facts(pairs) {
  const shown = pairs.filter(([, value]) => value != null && value !== "" && !(Array.isArray(value) && !value.length));
  if (!shown.length) return h("p", { class: "muted" }, "Nothing recorded yet.");
  return h("dl", { class: "dl" }, shown.map(([term, value]) => [h("dt", {}, term), h("dd", {}, value)]));
}

function many(vocab, name, keys) {
  return (keys ?? []).length ? h("div", { class: "row-sm wrap" }, keys.map((key) => pill(label(vocab, name, key)))) : null;
}

function prose(text) {
  return text ? h("p", { class: "prose" }, text) : null;
}

function editOwners(record, ctx) {
  const type = record.type;
  let owners = record.owners.map((owner) => ({ ...owner }));
  openOverlay({
    title: "Owners",
    subtitle: `${record.ref} · ${record.name}`,
    render: (body, footer, close) => {
      const list = h("div", { class: "stack-sm" });
      const problem = banner();
      const kinds = ctx.vocab.owner_kinds.map((item) => [item.key, item.label]);
      const draw = () => {
        list.replaceChildren(...owners.map((owner, index) => {
          const kind = select("Capacity", kinds, { value: owner.kind });
          kind.input.setAttribute("aria-label", `Capacity of ${owner.name}`);
          kind.input.addEventListener("change", () => {
            owners[index].kind = kind.input.value;
          });
          return h("div", { class: "owner-row" }, avatar(owner.name),
            h("div", { class: "grow" }, h("div", { class: "cell-main" }, owner.name), h("div", { class: "cell-sub" }, owner.email)),
            kind.input,
            button("Remove", { kind: "btn-ghost btn-sm", onclick: () => {
              owners.splice(index, 1);
              draw();
            } }));
        }));
        if (!owners.length) list.replaceChildren(h("p", { class: "muted" }, "Nobody yet."));
      };
      draw();
      const picker = peoplePicker({ label: "Add a person",
        exclude: (account) => owners.some((owner) => owner.account_id === account.id),
        onPick: (account) => {
          owners.push({ account_id: account.id, name: account.display_name, email: account.email,
            kind: owners.some((o) => o.kind === "accountable") ? "technical" : "accountable" });
          draw();
        } });
      const save = button("Save", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, banner: problem,
          run: () => put(`/api/v1/${TYPES[type].path}/${record.ref}/owners`,
            { owners: owners.map((owner) => ({ account_id: owner.account_id, kind: owner.kind })) }) });
        if (done) {
          close();
          toast("The owners were saved.");
          ctx.reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem,
        h("p", { class: "muted" }, "The accountable owner answers for the record. Technical owners can edit it too. A contact is someone to ask."),
        list, picker));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function editSystems(record, ctx) {
  let chosen = record.systems.map((system) => ({ ...system }));
  openOverlay({
    title: "AI systems used",
    subtitle: `${record.ref} · ${record.name}`,
    render: async (body, footer, close) => {
      const all = (await get("/api/v1/systems", { sort: "name", limit: 200 }, { fresh: true })).data;
      const problem = banner();
      const list = h("div", { class: "stack-sm" });
      const search = h("input", { class: "input", type: "search", placeholder: "Find an AI system", "aria-label": "Find an AI system" });
      const results = h("div", { class: "pick-results" });
      const draw = () => {
        list.replaceChildren(...(chosen.length ? chosen.map((system, index) => h("div", { class: "owner-row" },
          h("div", { class: "grow" }, recordChip(system, { link: false })), standingPill(system.catalog_status),
          button("Remove", { kind: "btn-ghost btn-sm", onclick: () => {
            chosen.splice(index, 1);
            draw();
          } }))) : [h("p", { class: "muted" }, "None yet.")]));
        const words = search.value.toLowerCase().trim();
        const offered = all.filter((s) => !chosen.some((c) => c.ref === s.ref)
          && (!words || `${s.name} ${s.ref} ${s.edition ?? ""}`.toLowerCase().includes(words))).slice(0, 8);
        results.replaceChildren(...offered.map((system) => h("button", { type: "button", class: "pick-item", onclick: () => {
          chosen.push(system);
          search.value = "";
          draw();
        } }, icon("system"), h("span", {}, h("span", { class: "cell-main" }, system.name),
          h("span", { class: "cell-sub" }, ` ${[system.ref, system.edition].filter(Boolean).join(" · ")}`)),
        h("span", { class: "spacer" }, standingPill(system.catalog_status)))));
      };
      search.addEventListener("input", draw);
      draw();
      const save = button("Save", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, banner: problem,
          run: () => put(`/api/v1/use-cases/${record.ref}/systems`, { systems: chosen.map((system) => system.ref) }) });
        if (done) {
          close();
          toast("Saved.");
          ctx.reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem, list,
        h("div", { class: "field" }, h("div", { class: "label" }, "Add"), search, results),
        h("p", { class: "subtle" }, "Not listed? Add it under AI systems first.")));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function ownersCard(record, ctx) {
  const canEdit = record.can?.edit;
  return card({ title: "Owners", actions: canEdit ? button("Edit", { kind: "btn-sm", onclick: () => editOwners(record, ctx) }) : null },
    record.orphaned ? alert("warn", icon("alert"), h("div", {}, "Its accountable owner's account is disabled. Name a new owner.")) : null,
    record.owners.length ? h("div", { class: "stack" }, record.owners.map((owner) => h("div", { class: "row" },
      avatar(owner.name), h("div", { class: "grow" }, h("div", { class: "cell-main" }, owner.name),
        h("div", { class: "cell-sub" }, owner.kind ? label(ctx.vocab, "owner_kinds", owner.kind) : "Accountable owner")))))
      : h("p", { class: "muted" }, "Nobody is named."));
}

function linkList(title, records, empty, actions = null, note = null) {
  return card({ title, actions },
    records.length ? h("div", { class: "stack-sm" }, records.map((r) => h("div", { class: "row" },
      h("div", { class: "grow" }, recordChip(r)), r.catalog_status ? standingPill(r.catalog_status) : r.status ? standingPill(r.status) : null)))
      : h("p", { class: "muted" }, empty),
    note ? h("p", { class: "subtle" }, note) : null);
}

function changeTier(record, ctx) {
  const why = ctx.intake.assessment;
  openOverlay({
    title: "Change the tier",
    subtitle: `${record.ref} · worked out as ${why.computed_label}`,
    kind: "dialog",
    render: (body, footer, close) => {
      const tier = select("Tier", why.tiers.map((t) => [t.level, t.label]), { value: why.final_tier });
      const reason = field("Reason", { type: "textarea",
        hint: "Why the worked-out tier is wrong for this request. It is kept on the record beside the tier." });
      const problem = banner();
      const save = button("Change tier", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, fields: { tier, reason }, banner: problem,
          run: () => post(`/api/v1/use-cases/${record.ref}/tier`, { tier: Number(tier.input.value), reason: reason.input.value }) });
        if (done) {
          close();
          toast(`The tier is now ${done.data.tier_label}.`);
          ctx.reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, tier.node, reason.node));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function tierCard(record, ctx) {
  const intake = ctx.intake;
  if (!intake && record.tier_source !== "catalog") return null;
  if (record.tier_source === "catalog") {
    return card({ title: "Why this tier" }, h("p", { class: "muted" },
      "This use was registered from the catalog. It uses an approved tool for everyday work, with data the tool is approved for, so it is Minimal and was approved under the tool's terms of use."));
  }
  if (!intake.assessment) {
    return card({ title: "Tier" }, h("p", { class: "muted" },
      intake.can_edit ? "The tier is worked out when the request is submitted." : "This use case has not been through intake, so it has no tier."),
    intake.can_edit ? h("a", { class: "btn btn-primary", href: `/use-cases/${record.ref}/request` }, "Continue the request") : null);
  }
  return card({ title: "Why this tier",
    actions: can("review") ? button("Change", { kind: "btn-sm", onclick: () => changeTier(record, ctx) }) : null },
  tierReasons(intake.assessment));
}

function answers(record, ctx) {
  const intake = ctx.intake;
  const schema = intake.form.schema;
  const { keys } = showing(schema, intake.answers);
  const visible = new Set(keys);
  const sections = schema.sections
    .map((section) => ({ ...section, questions: section.questions.filter((question) => visible.has(question.key)) }))
    .filter((section) => section.questions.length);
  return card({ title: intake.state === "submitted" ? "What was submitted" : "Answers so far",
    actions: intake.can_edit ? h("a", { class: "btn btn-sm btn-primary", href: `/use-cases/${record.ref}/request` }, "Continue the request") : null,
    footer: h("span", { class: "subtle" }, `Form version ${intake.form.version}`,
      intake.submitted_at ? ` · submitted ${dateTime(intake.submitted_at)}` : "") },
  h("div", { class: "answers" }, sections.map((section) => h("section", {},
    h("h3", {}, section.title),
    h("dl", {}, section.questions.map((question) => {
      const text = answerText(question, intake.answers[question.key], ctx.vocab, ctx);
      return h("div", {}, h("dt", {}, question.label), h("dd", {}, text ?? h("span", { class: "subtle" }, "Not answered")));
    }))))));
}

const OUTCOMES = { approved: "Approved", approved_with_conditions: "Approved with conditions", declined: "Declined",
  returned: "Returned to you", withdrawn: "Withdrawn" };

function reviewCard(record, ctx) {
  const review = ctx.review;
  if (!review) return null;
  const decision = review.decisions[review.decisions.length - 1];
  const open = !["decided", "cancelled"].includes(review.status);
  const waiting = review.all_conditions.filter((c) => c.kind === "before_use" && c.status === "open").length;
  return card({ title: open ? "Review" : "Decision",
    actions: h("div", { class: "row-sm" }, open ? reviewStatusPill(review.status) : null,
      review.internal ? h("a", { class: "btn btn-sm", href: `/reviews?open=${review.ref}` }, "Open the review") : null) },
  h("div", { class: "stack" },
    review.status === "with_requester" && review.can.reply ? alert("warn", icon("info"),
      h("div", {}, h("strong", {}, "The reviewers need something from you. "), "Reply below, or update your answers.",
        " The clock is stopped until you do.")) : null,
    open ? h("div", { class: "row-sm wrap" }, h("span", { class: "muted" }, `Waiting on ${review.waiting_on}.`), dueBadge(review.due_on, review.overdue)) : null,
    open && review.tasks.length ? h("div", { class: "row-sm wrap" }, review.tasks.map((task) =>
      pill(`${task.label}: ${task.status === "pending" ? "waiting" : task.status === "waived" ? "not required" : "done"}`,
        task.status === "completed" ? "ok" : ""))) : null,
    decision && !open ? h("div", { class: "stack-sm" },
      h("div", { class: "cell-main" }, OUTCOMES[decision.outcome] ?? decision.outcome, decision.by_rule ? " by rule" : ""),
      h("p", { class: "prose" }, decision.rationale),
      h("div", { class: "subtle" }, [decision.decided_by ? `By ${decision.decided_by}` : decision.by_rule,
        dateTime(decision.decided_at), decision.over_objection ? "Made over an objection" : null].filter(Boolean).join(" · "))) : null,
    waiting ? alert("warn", icon("alert"), h("div", {}, h("strong", {}, "Not in effect yet. "),
      `${waiting} condition${waiting === 1 ? "" : "s"} must be met before this is used.`)) : null,
    review.all_conditions.length ? h("div", { class: "stack-sm" }, h("h3", {}, "Conditions"),
      conditionList(review.all_conditions, { canClose: review.can_close_conditions, canWaive: review.can_waive_conditions, reload: ctx.reload })) : null,
    open || review.comments.length ? h("div", { class: "stack-sm" }, h("h3", {}, "Discussion"), discussion(review, ctx.reload)) : null,
    review.can.reply && review.status === "with_requester" ? h("div", {},
      h("a", { class: "btn btn-sm", href: `/use-cases/${record.ref}/request` }, "Update your answers")) : null));
}

function overview(record, ctx) {
  const v = ctx.vocab;
  const unit = ctx.units.byId.get(record.org_unit_id);
  const canEdit = record.can?.edit;
  if (record.type === "use_case") {
    const full = record.sight === "full";
    return h("div", { class: "split" },
      h("div", { class: "stack-lg" },
        full ? null : alert("info", icon("info"), h("div", {}, "You are seeing a summary. The people in its unit, its owners, and governance see the rest.")),
        full ? reviewCard(record, ctx) : null,
        card({ title: "Purpose" }, prose(record.purpose) ?? h("p", { class: "muted" }, "Not described yet.")),
        full ? card({ title: "Data" }, facts([
          ["Highest class", record.data_class ? label(v, "data_classes", record.data_class) : null],
          ["Kinds of data", many(v, "data_categories", record.data_categories)],
        ])) : null,
        full ? card({ title: "People and decisions" }, facts([
          ["How outputs are used", label(v, "decision_roles", record.decision_role)],
          ["Who is affected", many(v, "affected_groups", record.affected_groups)],
          ["Outputs are used for", many(v, "outputs_used_for", record.outputs_used_for)],
          ["Human oversight", prose(record.human_oversight)],
        ])) : null),
      h("div", { class: "stack-lg" },
        full ? tierCard(record, ctx) : null,
        card({ title: "At a glance" }, facts([
          ["Unit", unit?.name], ["Domain", label(v, "domains", record.domain)], ["Stage", label(v, "stages", record.stage)],
          ["Approved until", date(record.approved_until)], ["Next review", date(record.next_review_on)],
        ])),
        ownersCard(record, ctx),
        linkList("AI systems used", record.systems, "None named yet.",
          canEdit ? button("Edit", { kind: "btn-sm", onclick: () => editSystems(record, ctx) }) : null)));
  }
  if (record.type === "system") {
    const handling = record.data_handling ?? {};
    const trains = { yes: "Yes", no: "No", unknown: "Not known" }[handling.trains_on_inputs];
    return h("div", { class: "split" },
      h("div", { class: "stack-lg" },
        card({ title: "In the catalog", actions: standingPill(record.catalog_status) }, facts([
          ["May be used with", record.permitted_data_class ? `Data up to ${label(v, "data_classes", record.permitted_data_class)}` : null],
          ["Never with", many(v, "data_categories", record.excluded_data_categories)],
          ["Terms of use", prose(record.terms)],
        ])),
        record.summary ? card({ title: "About" }, prose(record.summary)) : null,
        card({ title: "How it handles data" }, facts([
          ["Trains on what is entered", trains], ["Inputs are kept", handling.retention], ["Processed in", handling.regions],
        ])),
        linkList("Used by", record.used_by.map((u) => ({ ...u })), "No use cases use it yet.", null,
          record.used_by_hidden ? `And ${record.used_by_hidden} more that you do not have access to.` : null)),
      h("div", { class: "stack-lg" },
        card({ title: "At a glance" }, facts([
          ["Kind", label(v, "system_kinds", record.kind)],
          ["Vendor", record.vendor ? recordChip(record.vendor) : null],
          ["Edition", record.edition], ["Reached through", label(v, "access_paths", record.access_path)],
          ["Hosting", label(v, "hosting", record.hosting)], ["Version", record.version_label],
          ["Inside", record.embedded_in], ["Unit", unit?.name],
          ["Address", record.url ? h("a", { href: record.url, target: "_blank", rel: "noopener noreferrer" }, record.url.replace(/^https?:\/\//, "")) : null],
        ])),
        ownersCard(record, ctx)));
  }
  return h("div", { class: "split" },
    h("div", { class: "stack-lg" },
      record.summary ? card({ title: "About" }, prose(record.summary)) : null,
      linkList("AI systems supplied", record.systems, "None recorded yet."),
      record.notes ? card({ title: "Notes" }, prose(record.notes)) : null),
    h("div", { class: "stack-lg" },
      card({ title: "At a glance" }, facts([
        ["Standing", standingPill(record.status)], ["Due diligence", standingPill(record.due_diligence_status)],
        ["Website", record.website ? h("a", { href: record.website, target: "_blank", rel: "noopener noreferrer" }, record.website.replace(/^https?:\/\//, "")) : null],
      ])),
      card({ title: "Contacts" }, record.contacts.length ? h("div", { class: "stack" }, record.contacts.map((c) => h("div", {},
        h("div", { class: "cell-main" }, c.name ?? c.email), h("div", { class: "cell-sub" }, [c.role, c.name ? c.email : null].filter(Boolean).join(" · ")))))
        : h("p", { class: "muted" }, "None recorded."))));
}

function timeline(entries) {
  if (!entries.length) return emptyState({ iconName: "history", title: "No history yet" });
  return h("ol", { class: "timeline" }, entries.map((entry) => h("li", {},
    h("div", { class: "timeline-dot", "aria-hidden": "true" }),
    h("div", { class: "grow" },
      h("div", { class: "row wrap" }, h("span", { class: "cell-main" }, entry.title),
        h("span", { class: "muted" }, `by ${entry.actor}`),
        h("time", { class: "subtle spacer", datetime: entry.at, title: dateTime(entry.at) }, relative(entry.at))),
      entry.lines.length ? h("dl", { class: "changes" }, entry.lines.map((line) => [
        h("dt", {}, line.label),
        h("dd", {}, line.before != null ? h("del", {}, String(line.before)) : h("span", { class: "subtle" }, "empty"),
          h("span", { "aria-hidden": "true" }, " → "), h("span", { class: "sr-only" }, " became "),
          line.after != null ? h("ins", {}, String(line.after)) : h("span", { class: "subtle" }, "empty")),
      ])) : null))));
}

export function recordPage(main, type, params) {
  const meta = TYPES[type];
  const wanted = query().get("tab");
  const tab = wanted === "history" || (wanted === "answers" && type === "use_case") ? wanted : "overview";
  return show(main, {
    title: params.ref,
    load: async () => {
      const [record, vocab, unitIndex] = await Promise.all([
        get(`/api/v1/${meta.path}/${params.ref}`, null, { fresh: true }), vocabularies(), units()]);
      const full = record.data.sight === "full";
      const [entries, vendors, intake, review] = await Promise.all([
        tab === "history" && full ? get(`/api/v1/${meta.path}/${params.ref}/history`, null, { fresh: true }) : null,
        type === "system" && record.data.can?.edit ? get("/api/v1/vendors", { sort: "name", limit: 200 }) : null,
        type === "use_case" && full ? get(`/api/v1/use-cases/${params.ref}/intake`, null, { fresh: true }).catch(() => null) : null,
        type === "use_case" && full ? get(`/api/v1/use-cases/${params.ref}/review`, null, { fresh: true }).catch(() => null) : null,
      ]);
      return { record: record.data, vocab, units: unitIndex, history: entries?.data ?? [], vendors: vendors?.data ?? [],
        intake: intake?.data ?? null, review: review?.data ?? null };
    },
    view: (data, reload) => {
      const record = data.record;
      document.title = `${record.name} · ${record.ref}`;
      const ctx = { vocab: data.vocab, units: data.units, reload, intake: data.intake, review: data.review,
        systems: new Map((record.systems ?? []).map((system) => [system.ref, `${system.name} (${system.ref})`])) };
      const resume = data.intake?.can_edit && data.intake.state === "draft"
        ? h("a", { class: "btn btn-primary", href: `/use-cases/${record.ref}/request` }, "Continue the request") : null;
      const full = record.sight === "full";
      const edit = record.can?.edit ? button("Edit", { iconName: "edit", onclick: () =>
        EDITORS[type]({ record, vocab: data.vocab, units: data.units, vendors: data.vendors, onDone: reload }) }) : null;
      const tabLink = (key, text) => h("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(tab === key),
        onclick: () => setQuery({ tab: key === "overview" ? null : key }, { replace: false }) }, text);
      return h("div", { class: "stack" },
        h("a", { class: "back-link", href: `/${meta.path}` }, icon("chevron-left", "icon icon-sm"), meta.plural),
        h("header", { class: "record-header" },
          h("div", { class: "record-icon", "data-record": type }, icon(meta.iconName, "icon icon-lg")),
          h("div", { class: "grow" },
            h("div", { class: "eyebrow" }, `${meta.label} · ${record.ref}`),
            h("h1", { tabindex: "-1" }, record.name),
            h("div", { class: "row-sm wrap record-badges" },
              type === "use_case" ? (record.tier ? tierBadge(record.tier) : pill("Tier not set")) : null,
              standingPill(type === "system" ? record.catalog_status : record.status),
              record.restricted ? h("span", { class: "pill" }, icon("lock"), "Restricted") : null,
              full ? h("span", { class: "subtle" }, `Updated ${relative(record.updated_at)}`) : null)),
          h("div", { class: "row-sm wrap" }, resume, edit)),
        full ? h("div", { class: "tabs", role: "tablist" }, tabLink("overview", "Overview"),
          type === "use_case" && data.intake && data.intake.state !== "none" ? tabLink("answers", "Answers") : null, tabLink("history", "History")) : null,
        tab === "history" && full ? card({ flush: true }, timeline(data.history))
          : tab === "answers" && full && data.intake && data.intake.state !== "none" ? answers(record, ctx) : overview(record, ctx));
    },
  });
}

