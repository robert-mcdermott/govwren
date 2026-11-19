// Policies: the list, and one policy with its text, versions, the controls that carry it
// out, and who has acknowledged it.

import { get, patch, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { unitOptions, units } from "../core/lookups.js";
import { navigate } from "../core/router.js";
import { can } from "../core/session.js";
import { banner, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill, stat } from "../components/ui.js";
import { show } from "./page.js";

const STATUS = { draft: ["Draft", "warn"], in_force: ["In force", "ok"], retired: ["Retired", ""] };

function minePill(mine) {
  if (!mine) return null;
  if (mine.acknowledged_at) return pill("You acknowledged it", "ok");
  return mine.overdue ? pill("Your acknowledgment is overdue", "danger") : pill(`Acknowledge by ${date(mine.due_on)}`, "warn");
}

/** The policy's text: blank lines part paragraphs, and a line starting with ## is a heading. */
function prose(text) {
  return h("div", { class: "stack prose" }, text.split(/\n\s*\n/).map((block) => (block.startsWith("## ")
    ? h("h3", {}, block.slice(3).trim()) : h("p", { class: "pre-line" }, block.trim()))));
}

function dialog({ title, subtitle = null, fields, action, kind = "dialog", danger = false, run, done }) {
  openOverlay({
    title, subtitle, kind,
    render: (body, footer, shut) => {
      const problem = banner();
      const go = button(action, { kind: danger ? "btn-danger" : "btn-primary" });
      go.addEventListener("click", async () => {
        const result = await submit({ button: go, banner: problem, fields, run });
        if (result) {
          shut();
          done(result);
        }
      });
      body.append(h("div", { class: "stack" }, problem, Object.values(fields).map((each) => each.node)));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function policyList(main) {
  return show(main, {
    title: "Policies",
    load: async () => (await get("/api/v1/policies", null, { fresh: true })).data,
    view: (rows) => {
      const start = () => {
        const title = field("Name", { maxlength: 200 });
        const summary = field("What it is for, in a sentence", { type: "textarea" });
        dialog({ title: "Start a policy", subtitle: "It stays a draft until you publish it.", fields: { title, summary }, action: "Start it",
          run: () => post("/api/v1/policies", { title: title.input.value, summary: summary.input.value }),
          done: (made) => navigate(`/policies/${made.data.ref}`) });
      };
      const add = can("govern") ? button("Start a policy", { kind: "btn-primary", iconName: "plus", onclick: start }) : null;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Policies", lede: "The organization's own rules for AI, each with its current text, an owner, and a date it is next reviewed.", actions: add }),
        rows.length ? h("div", { class: "stack" }, rows.map((policy) => card({
          title: h("a", { href: `/policies/${policy.ref}` }, policy.title),
          actions: h("div", { class: "row-sm wrap" }, minePill(policy.mine), policy.status !== "in_force" ? pill(...STATUS[policy.status]) : null,
            policy.review_due ? pill("Review is due", "warn") : null) },
        h("div", { class: "stack-sm" }, policy.summary ? h("p", {}, policy.summary) : null,
          h("div", { class: "subtle" }, [policy.ref, policy.version ? `Version ${policy.version}` : "Not published yet", policy.owner ? `Owner: ${policy.owner}` : null,
            policy.review_on ? `Review ${date(policy.review_on)}` : null].filter(Boolean).join(" · "))))))
          : emptyState({ iconName: "note", title: "No policies yet", text: can("govern") ? "Start one, write its text, and publish it." : "Policies appear here once they are published.", action: add }));
    },
  });
}

export function policyPage(main, params) {
  return show(main, {
    title: "Policy",
    load: async () => {
      const [policy, tree] = await Promise.all([get(`/api/v1/policies/${params.ref}`, null, { fresh: true }), units()]);
      return { ...policy.data, tree: tree.tree };
    },
    view: (policy, reload) => {
      document.title = `${policy.title} · ${policy.ref}`;
      const at = `/api/v1/policies/${policy.ref}`;
      const after = (words) => () => { toast(words); reload(); };
      const write = () => {
        const body = field(policy.draft ? `Version ${policy.draft.version}` : "The next version", { type: "textarea", rows: 16,
          value: policy.draft?.body ?? policy.body ?? "", hint: "Leave a blank line between paragraphs. Start a line with ## for a heading." });
        const note = field("What changed in this version", { value: policy.draft?.change_note ?? "", hint: "Needed for every version after the first." });
        dialog({ title: "Write the policy", subtitle: policy.title, kind: "drawer", fields: { body, change_note: note }, action: "Save the draft",
          run: () => put(`${at}/draft`, { body: body.input.value, change_note: note.input.value }), done: after("The draft was saved. Publish it to put it in force.") });
      };
      const details = () => {
        const title = field("Name", { value: policy.title, maxlength: 200 });
        const summary = field("What it is for", { type: "textarea", value: policy.summary ?? "" });
        const review = field("Review it again on", { type: "date", value: policy.review_on ?? "" });
        const controls = field("Controls that carry it out", { value: policy.control_keys.join(", "), hint: "Their keys from the control library, separated by commas." });
        dialog({ title: "Details", subtitle: policy.title, fields: { title, summary, review_on: review, control_keys: controls }, action: "Save",
          run: () => patch(at, { title: title.input.value, summary: summary.input.value, review_on: review.input.value || null,
            control_keys: controls.input.value.split(/[\s,]+/).filter(Boolean) }), done: after("Saved.") });
      };
      const ask = () => {
        const unit = select("Who is asked", unitOptions(policy.tree, { blank: "Everyone" }), { hint: "A unit includes the units beneath it." });
        const due = field("Acknowledge by", { type: "date" });
        dialog({ title: "Ask people to acknowledge it", subtitle: `Version ${policy.version} of ${policy.title}`, fields: { unit_id: unit, due_on: due }, action: "Ask them",
          run: () => post(`${at}/ask`, { unit_id: unit.input.value ? Number(unit.input.value) : null, due_on: due.input.value || null }), done: after("They have been asked.") });
      };
      const act = (path, words) => async () => {
        try {
          await post(`${at}/${path}`);
          toast(words);
        } catch (error) {
          toast(Object.values(error.fields ?? {})[0] ?? error.detail ?? "That could not be done.");
        }
        reload();
      };
      const coverage = policy.coverage;
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/policies" }, icon("chevron-left", "icon icon-sm"), "Policies"),
        pageHeader({ eyebrow: `Policy · ${policy.ref}${policy.version ? ` · version ${policy.version}` : ""}`, title: policy.title, lede: policy.summary,
          actions: [pill(...STATUS[policy.status]), minePill(policy.mine),
            policy.mine && !policy.mine.acknowledged_at ? button("I have read it", { kind: "btn-primary", onclick: act("acknowledge", "Recorded. Thank you.") }) : null,
            policy.can.edit ? button(policy.draft ? "Edit the draft" : "Write a new version", { onclick: write }) : null,
            policy.can.publish ? button(`Publish version ${policy.draft.version}`, { kind: "btn-primary", onclick: act("publish", "Published.") }) : null,
            policy.can.ask ? button("Ask for acknowledgment…", { onclick: ask }) : null,
            policy.can.edit ? button("Details…", { kind: "btn-ghost", onclick: details }) : null,
            policy.can.retire ? button("Retire", { kind: "btn-ghost", onclick: act("retire", "Retired.") }) : null] }),
        policy.review_due ? alert("warn", icon("alert"), h("div", {}, h("strong", {}, "Due for review. "), `It was to be reviewed on ${date(policy.review_on)}.`)) : null,
        policy.draft ? alert("info", icon("info"), h("div", {}, `A draft of version ${policy.draft.version} is waiting to be published. Until then the text below stays in force.`)) : null,
        h("div", { class: "split" },
          card({ title: policy.body ? "The policy" : "Not published yet" }, policy.body ? prose(policy.body) : h("p", { class: "muted" }, "Write the text, then publish it.")),
          h("div", { class: "stack-lg" },
            card({ title: "About" }, h("dl", { class: "facts" },
              h("dt", {}, "Owner"), h("dd", {}, policy.owner ?? "Nobody"),
              h("dt", {}, "In force since"), h("dd", {}, policy.published_at ? date(policy.published_at) : "Not yet"),
              h("dt", {}, "Next review"), h("dd", {}, policy.review_on ? date(policy.review_on) : "No date set"))),
            policy.controls.length ? card({ title: "Controls that carry it out" }, h("ul", { class: "rows" }, policy.controls.map((control) =>
              h("li", {}, h("a", { href: `/controls/${control.key}` }, control.title))))) : null,
            coverage && coverage.asked ? card({ title: "Acknowledged" }, h("div", { class: "stack" },
              stat(`${Math.round((coverage.acknowledged / coverage.asked) * 100)}%`, `${coverage.acknowledged} of ${coverage.asked} people`),
              h("ul", { class: "rows" }, coverage.by_unit.slice(0, 8).map((row) => h("li", { class: "row" }, h("span", { class: "grow" }, row.unit),
                h("span", { class: "numeric subtle" }, `${row.acknowledged} of ${row.asked}`)))))) : null,
            policy.versions.length ? card({ title: "Versions" }, h("ul", { class: "rows" }, policy.versions.map((version) => h("li", {},
              h("div", { class: "cell-main" }, `Version ${version.version}`, version.status === "draft" ? " (draft)" : ""),
              h("div", { class: "cell-sub" }, [version.published_at ? date(version.published_at) : null, version.change_note].filter(Boolean).join(" · ") || "The first version"))))) : null)));
    },
  });
}
