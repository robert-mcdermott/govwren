// Spot checks: a sample of the approvals that rules made by themselves, each given a second
// look by a person.

import { get, post } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { date } from "../core/format.js";
import { units } from "../core/lookups.js";
import { banner, field, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { card, emptyState, pageHeader, pill, stat, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

function record(check, agree, reload) {
  openOverlay({
    title: agree ? "Agree with the rule" : "Disagree with the rule", subtitle: check.use_case.name, kind: "dialog",
    render: (body, footer, shut) => {
      const note = field(agree ? "A note, if you like" : "What did the rule get wrong?", { type: "textarea",
        hint: agree ? null : "A review of this use opens, with what you say here. Its approval stands until that review is decided." });
      const problem = banner();
      const go = button(agree ? "Record agreement" : "Call it in for review", { kind: agree ? "btn-primary" : "btn-danger" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem, fields: { note }, run: () => post(`/api/v1/spot-checks/${check.id}`, { agree, note: note.input.value }) });
        if (done) {
          shut();
          toast(agree ? "Recorded." : "A review was opened.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, note.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function spotChecks(main) {
  return show(main, {
    title: "Spot checks",
    load: async () => {
      const [found, tree] = await Promise.all([get("/api/v1/spot-checks", null, { fresh: true }), units()]);
      return { ...found.data, units: tree };
    },
    view: (data, reload) => {
      const draw = data.can_draw ? button("Draw five more", { kind: "btn-primary", disabled: !data.available, onclick: async () => {
        try {
          const drawn = await post("/api/v1/spot-checks", { count: 5 });
          toast(`${drawn.meta.drawn} drawn.`);
        } catch (error) {
          toast(error.detail ?? "No sample could be drawn.");
        }
        reload();
      } }) : null;
      const row = (check) => h("tr", {},
        h("td", {}, h("a", { class: "cell-main", href: `/use-cases/${check.use_case.ref}` }, check.use_case.name),
          h("div", { class: "cell-sub" }, [check.use_case.ref, data.units.byId.get(check.use_case.org_unit_id)?.name].filter(Boolean).join(" · "))),
        h("td", {}, check.use_case.tier ? tierBadge(check.use_case.tier) : null),
        h("td", {}, h("div", {}, check.rule), h("div", { class: "cell-sub" }, `Approved ${date(check.decided_at)}`)),
        h("td", {}, check.status === "pending" ? (check.can_check ? h("div", { class: "row-sm wrap" },
          button("Agree", { kind: "btn-sm", "aria-label": `Agree with the approval of ${check.use_case.name}`, onclick: () => record(check, true, reload) }),
          button("Disagree…", { kind: "btn-sm btn-ghost", "aria-label": `Disagree with the approval of ${check.use_case.name}`, onclick: () => record(check, false, reload) }))
          : pill("Waiting"))
          : h("div", {}, check.status === "agreed" ? pill("Agreed", "ok") : pill("Disagreed", "danger"),
            h("div", { class: "cell-sub" }, [check.checked_by, check.checked_at ? date(check.checked_at) : null].filter(Boolean).join(" · ")),
            check.note ? h("div", { class: "cell-sub" }, check.note) : null,
            check.followup ? h("a", { href: `/reviews?open=${check.followup}` }, `Review ${check.followup}`) : null)));
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Spot checks", lede: "A sample of the approvals that rules made by themselves, each given a second look. It is how you know the rules decide what a person would.",
          actions: draw }),
        h("div", { class: "grid-3" }, stat(String(data.pending), "Waiting to be checked"), stat(String(data.checked), "Checked"),
          stat(data.agreement == null ? "—" : `${data.agreement}%`, "Agreed with the rule")),
        h("p", { class: "muted" }, `The scheduler draws about one automatic approval in ten. ${data.available} more from the last four months ${data.available === 1 ? "has" : "have"} not been drawn.`),
        data.checks.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Use case"), h("th", { scope: "col" }, "Tier"), h("th", { scope: "col" }, "Approved by"), h("th", { scope: "col" }, "Check"))),
          h("tbody", {}, data.checks.map(row)))))
          : emptyState({ iconName: "check", title: "Nothing has been drawn yet", text: "Draw a sample, or wait for the scheduler to draw its share.", action: draw }));
    },
  });
}
