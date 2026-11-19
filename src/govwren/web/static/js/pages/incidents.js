// Incidents: the register, reporting one, and one incident with its triage, the records it
// involves, its actions, and how it ended.

import { get, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime } from "../core/format.js";
import { navigate, query, setQuery } from "../core/router.js";
import { can } from "../core/session.js";
import { banner, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { peoplePicker } from "../components/people-picker.js";
import { standingPill } from "../components/record.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const STATUS = { reported: ["Waiting for triage", "warn"], open: ["Open", "accent"], contained: ["Contained", "ok"],
  closed: ["Closed", ""], dismissed: ["Not an incident", ""] };
const SEVERITY = { low: ["Low", ""], moderate: ["Moderate", "warn"], high: ["High", "danger"], critical: ["Critical", "danger"] };
const severityPill = (incident) => (incident.severity ? pill(`${SEVERITY[incident.severity][0]} severity`, SEVERITY[incident.severity][1]) : null);

function dialog({ title, subtitle = null, fields, extra = null, action, danger = false, kind = "dialog", run, done }) {
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
      body.append(h("div", { class: "stack" }, problem, Object.values(fields).map((each) => each.node), extra));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

const refs = (text) => text.split(/[\s,]+/).map((part) => part.trim()).filter(Boolean);

function reportIncident(about = "") {
  const title = field("What happened, in a few words", { maxlength: 200 });
  const description = field("Describe it", { type: "textarea", hint: "What happened, how it was noticed, and what has been done so far. Do not paste sensitive data here." });
  const when = field("When did it happen?", { type: "date", hint: "Leave empty if you are not sure." });
  const records = field("Which records does it involve?", { value: about, hint: "Their references, such as UC-0142 or SYS-0031, separated by commas. Leave empty if you do not know." });
  dialog({ title: "Report an incident", subtitle: "Near misses count. Governance is told at once.", kind: "drawer",
    fields: { title, description, occurred_on: when, records }, action: "Report it",
    run: () => post("/api/v1/incidents", { title: title.input.value, description: description.input.value,
      occurred_on: when.input.value || null, records: refs(records.input.value) }),
    done: (made) => {
      toast(`${made.data.ref} was reported. Thank you.`);
      navigate(`/incidents/${made.data.ref}`);
    } });
}

export function incidentList(main) {
  const wanted = query().get("show") === "all" ? "all" : "open";
  const about = query().get("report");
  return show(main, {
    title: "Incidents",
    load: async () => (await get("/api/v1/incidents", wanted === "open" ? { status: "open" } : null, { fresh: true })).data,
    view: (rows) => {
      if (about) queueMicrotask(() => { setQuery({ report: null }); reportIncident(about); });
      const tab = (key, text) => h("button", { type: "button", "aria-pressed": String(wanted === key),
        onclick: () => setQuery({ show: key === "open" ? null : key }, { replace: false }) }, text);
      const report = button("Report an incident", { kind: "btn-primary", iconName: "plus", onclick: () => reportIncident() });
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Incidents", lede: "Something went wrong with an AI use, or nearly did. Anyone can report it; reporting is how the program learns.",
          actions: [h("div", { class: "segmented", role: "group", "aria-label": "Which incidents" }, tab("open", "Open"), tab("all", "All")), report] }),
        rows.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Incident"), h("th", { scope: "col" }, "Kind"), h("th", { scope: "col" }, "Standing"),
            h("th", { scope: "col" }, "Reported"), h("th", { scope: "col" }, "Lead"))),
          h("tbody", {}, rows.map((row) => h("tr", {},
            h("td", {}, h("a", { class: "cell-main", href: `/incidents/${row.ref}` }, row.title), h("div", { class: "cell-sub" }, row.ref)),
            h("td", {}, row.category_label ?? h("span", { class: "subtle" }, "Not triaged")),
            h("td", {}, h("div", { class: "row-sm wrap" }, pill(...STATUS[row.status]), severityPill(row))),
            h("td", { class: "nowrap" }, date(row.reported_at), row.reported_by ? h("div", { class: "cell-sub" }, row.reported_by) : null),
            h("td", {}, row.lead ?? "")))))))
          : emptyState({ iconName: "check", title: wanted === "open" ? "No incidents are open" : "No incidents have been reported",
            text: can("read_all") ? "Reports from anyone in the organization arrive here." : "You see the incidents you report, and any that involve a record you are responsible for.", action: report }));
    },
  });
}

export function incidentPage(main, params) {
  return show(main, {
    title: "Incident",
    load: async () => (await get(`/api/v1/incidents/${params.ref}`, null, { fresh: true })).data,
    view: (incident, reload) => {
      document.title = `${incident.title} · ${incident.ref}`;
      const at = `/api/v1/incidents/${incident.ref}`;
      const after = (words) => () => { toast(words); reload(); };

      const triage = () => {
        const category = select("What kind of incident is it?", [["", "Choose…"], ...incident.categories.map((c) => [c.key, c.label])], { value: incident.category ?? "" });
        const severity = select("How serious is it?", [["", "Choose…"], ...Object.entries(SEVERITY).map(([key, [text]]) => [key, text])], { value: incident.severity ?? "" });
        const records = field("Records it involves", { value: incident.records.map((r) => r.ref).join(", "), hint: "References, separated by commas. Linking a model or a tool shows the incident on everything that relies on it." });
        dialog({ title: "Triage", subtitle: incident.title, fields: { category, severity, records }, action: "Save",
          run: () => post(`${at}/triage`, { category: category.input.value, severity: severity.input.value, records: refs(records.input.value) }),
          done: after("Triaged.") });
      };
      const dismiss = () => {
        const reason = field("Why is it not an incident?", { type: "textarea", hint: "Shown to whoever reported it." });
        dialog({ title: "Not an incident", subtitle: incident.title, fields: { dismiss: reason }, action: "Close the report", danger: true,
          run: () => post(`${at}/triage`, { dismiss: reason.input.value }), done: after("The report was closed.") });
      };
      const onRecord = (record, path, { title, label, hint, action, danger = false, words }) => {
        const reason = field(label, { type: "textarea", hint });
        dialog({ title, subtitle: record.name, fields: { reason }, action, danger,
          run: () => post(`${at}/${path}`, { record: record.ref, reason: reason.input.value }), done: after(words) });
      };
      const progress = (status) => {
        const closing = status === "closed";
        const containment = field("What was done to stop it or limit it?", { type: "textarea", value: incident.containment ?? "" });
        const cause = field("What caused it?", { type: "textarea" });
        const lessons = field("What will be done differently?", { type: "textarea" });
        dialog({ title: closing ? "Close the incident" : "Mark as contained", subtitle: incident.title, kind: closing ? "drawer" : "dialog",
          fields: closing ? { containment, cause, lessons } : { containment }, action: closing ? "Close it" : "Mark as contained",
          run: () => post(`${at}/progress`, { status, containment: containment.input.value, cause: cause.input.value, lessons: lessons.input.value }),
          done: after(closing ? "The incident is closed." : "Marked as contained.") });
      };
      const addAction = () => {
        const title = field("What must be done?", { maxlength: 300 });
        const due = field("By when?", { type: "date" });
        let owner = null;
        const chosen = h("div", { class: "subtle", "aria-live": "polite" }, "Nobody chosen yet.");
        const picker = peoplePicker({ label: "Who will do it?", onPick: (account) => { owner = account.id; chosen.textContent = `${account.display_name} will do it.`; } });
        dialog({ title: "Set an action", subtitle: incident.title, fields: { title, due_on: due }, extra: h("div", { class: "stack-sm" }, picker, chosen), action: "Set the action",
          run: () => post(`${at}/actions`, { title: title.input.value, owner_id: owner, due_on: due.input.value || null }), done: after("The action was set.") });
      };
      const closeAction = (action, status) => {
        const note = field(status === "done" ? "What was done?" : "Why is it not needed?", { type: "textarea" });
        dialog({ title: status === "done" ? "Mark as done" : "Cancel this action", subtitle: action.title, fields: { note }, action: status === "done" ? "Mark as done" : "Cancel it",
          danger: status !== "done", run: () => post(`/api/v1/actions/${action.id}/close`, { status, note: note.input.value }), done: after(status === "done" ? "Done." : "Cancelled.") });
      };

      const part = (title, text) => (text ? h("div", { class: "stack-sm" }, h("h3", {}, title), h("p", { class: "prose" }, text)) : null);
      const mayTriage = incident.can.triage;
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/incidents" }, icon("chevron-left", "icon icon-sm"), "Incidents"),
        pageHeader({ eyebrow: `Incident · ${incident.ref}`, title: incident.title,
          lede: [incident.category_label, incident.occurred_on ? `Happened ${date(incident.occurred_on)}` : null,
            `Reported ${date(incident.reported_at)}${incident.reported_by ? ` by ${incident.reported_by}` : ""}`].filter(Boolean).join(" · "),
          actions: [pill(...STATUS[incident.status]), severityPill(incident),
            mayTriage ? button(incident.status === "reported" ? "Triage…" : "Change the triage…", { kind: incident.status === "reported" ? "btn-primary" : "", onclick: triage }) : null,
            mayTriage && incident.status === "reported" ? button("Not an incident…", { kind: "btn-ghost", onclick: dismiss }) : null,
            incident.can.progress && incident.status === "open" ? button("Mark as contained…", { onclick: () => progress("contained") }) : null,
            incident.can.progress ? button("Close…", { kind: incident.status === "contained" ? "btn-primary" : "", onclick: () => progress("closed") }) : null] }),
        incident.status === "reported" && !mayTriage ? alert("info", icon("info"), h("div", {}, "Thank you for reporting this. Governance has been told and will look at it.")) : null,
        h("div", { class: "split" },
          h("div", { class: "stack-lg" },
            card({ title: "What happened" }, h("p", { class: "prose" }, incident.description)),
            card({ title: "Records involved" }, incident.records.length ? h("ul", { class: "conditions" }, incident.records.map((record) => h("li", { class: "row wrap" },
              h("div", { class: "grow" }, h("div", { class: "cell-main" }, record.href ? h("a", { href: record.href }, record.name) : record.name),
                h("div", { class: "row-sm wrap" }, h("span", { class: "subtle" }, record.ref), record.type === "use_case" ? standingPill(record.status) : null,
                  record.review ? h("a", { href: `/reviews?open=${record.review}` }, `Review ${record.review}`) : null)),
              h("div", { class: "row-sm wrap" },
                record.can_suspend ? button("Suspend…", { kind: "btn-sm btn-danger", "aria-label": `Suspend the approval of ${record.name}`, onclick: () => onRecord(record, "suspend",
                  { title: "Suspend this approval", label: "Why is it suspended?", hint: "Its owners are told. It stays suspended until you lift it or a review decides.", action: "Suspend", danger: true, words: "The approval is suspended." }) }) : null,
                record.can_lift ? button("Lift the suspension…", { kind: "btn-sm", "aria-label": `Lift the suspension of ${record.name}`, onclick: () => onRecord(record, "lift",
                  { title: "Lift the suspension", label: "Why is it lifted?", hint: "The use goes back to the standing it had.", action: "Lift it", words: "The suspension is lifted." }) }) : null,
                record.can_review ? button("Open a review…", { kind: "btn-sm", "aria-label": `Open a review of ${record.name}`, onclick: () => onRecord(record, "review",
                  { title: "Open a review", label: "What should the review look at?", hint: "It goes to triage with the reviews the rules require.", action: "Open the review", words: "The review is open." }) }) : null))))
              : h("p", { class: "muted" }, mayTriage ? "None linked yet. Link them at triage." : "None linked yet.")),
            incident.containment || incident.cause || incident.lessons ? card({ title: incident.status === "dismissed" ? "Why it was closed" : "What was found" }, h("div", { class: "stack" },
              part("What was done to stop it", incident.containment), part("Cause", incident.cause),
              part(incident.status === "dismissed" ? "Reason" : "What will be done differently", incident.lessons))) : null),
          h("div", { class: "stack-lg" },
            card({ title: "Actions", actions: incident.can.act ? button("Set an action", { kind: "btn-sm", onclick: addAction }) : null },
              incident.actions.length ? h("ul", { class: "conditions" }, incident.actions.map((action) => h("li", { class: "stack-sm" },
                h("div", { class: "cell-main" }, action.title),
                h("div", { class: "row-sm wrap" }, action.status === "open" ? (action.overdue ? pill(`Was due ${date(action.due_on)}`, "danger") : pill(`Due ${date(action.due_on)}`))
                  : pill(action.status === "done" ? "Done" : "Cancelled", action.status === "done" ? "ok" : ""), h("span", { class: "subtle" }, action.owner ?? "")),
                action.note ? h("div", { class: "cell-sub" }, action.note) : null,
                action.can_close || action.can_cancel ? h("div", { class: "row-sm" },
                  action.can_close ? button("Done…", { kind: "btn-sm", "aria-label": `Mark as done: ${action.title}`, onclick: () => closeAction(action, "done") }) : null,
                  action.can_cancel ? button("Cancel…", { kind: "btn-sm btn-ghost", "aria-label": `Cancel: ${action.title}`, onclick: () => closeAction(action, "cancelled") }) : null) : null)))
                : h("p", { class: "muted" }, "No actions have been set.")),
            card({ title: "Handling" }, h("dl", { class: "facts" },
              h("dt", {}, "Lead"), h("dd", {}, incident.lead ?? "Not set"),
              h("dt", {}, "Reported"), h("dd", {}, dateTime(incident.reported_at)),
              incident.closed_at ? [h("dt", {}, "Closed"), h("dd", {}, [dateTime(incident.closed_at), incident.closed_by].filter(Boolean).join(" · "))] : null)))));
    },
  });
}
