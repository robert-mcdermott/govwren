// Exceptions: the register, and one exception with what was asked, what was decided, and
// what can be done with it now.

import { get, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime } from "../core/format.js";
import { query, setQuery } from "../core/router.js";
import { banner, field, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const STATUS = {
  requested: ["Waiting for a decision", "warn"], approved: ["In force", "ok"], declined: ["Declined", "danger"],
  withdrawn: ["Withdrawn", ""], expired: ["Ended", ""], revoked: ["Revoked", "danger"],
};
const statusPill = (exception) => (exception.ending_soon ? pill(`Ends ${date(exception.ends_on)}`, "warn") : pill(...STATUS[exception.status]));

export function exceptionList(main) {
  const wanted = query().get("show") === "all" ? "all" : "open";
  return show(main, {
    title: "Exceptions",
    load: async () => (await get("/api/v1/exceptions", wanted === "open" ? { status: "open" } : null, { fresh: true })).data,
    view: (rows) => {
      const tab = (key, text) => h("button", { type: "button", class: "segment", "aria-pressed": String(wanted === key),
        onclick: () => setQuery({ show: key === "open" ? null : key }, { replace: false }) }, text);
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Exceptions", lede: "Approved, time-limited departures from a requirement. Every one has a reason, something done instead, and an end date.",
          actions: h("div", { class: "segmented", role: "group", "aria-label": "Which exceptions" }, tab("open", "Open"), tab("all", "All")) }),
        rows.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Exception"), h("th", { scope: "col" }, "On"), h("th", { scope: "col" }, "Standing"),
            h("th", { scope: "col" }, "Ends"), h("th", { scope: "col" }, "Asked for by"))),
          h("tbody", {}, rows.map((row) => h("tr", {},
            h("td", {}, h("a", { class: "cell-main", href: `/exceptions/${row.ref}` }, row.title), h("div", { class: "cell-sub" }, row.ref)),
            h("td", {}, row.record ? h("a", { href: `/${row.record.path}/${row.record.ref}` }, row.record.name) : "A record that is gone"),
            h("td", {}, pill(...STATUS[row.status])),
            h("td", { class: "numeric nowrap" }, date(row.ends_on)),
            h("td", {}, row.requested_by ?? "")))))))
          : emptyState({ iconName: "check", title: wanted === "open" ? "No exceptions are open" : "No exceptions yet",
            text: "An exception is asked for from the page of the record it applies to." }));
    },
  });
}

function reasonDialog({ title, subtitle, fields, action, danger = false, run, done }) {
  openOverlay({
    title, subtitle, kind: "dialog",
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

export function exceptionPage(main, params) {
  return show(main, {
    title: "Exception",
    load: async () => (await get(`/api/v1/exceptions/${params.ref}`, null, { fresh: true })).data,
    view: (exception, reload) => {
      document.title = `${exception.title} · ${exception.ref}`;
      const at = `/api/v1/exceptions/${exception.ref}`;
      const decide = (outcome) => {
        const note = field(outcome === "approved" ? "Why it is acceptable" : "Why it is declined", { type: "textarea", hint: "Shown to whoever asked." });
        const until = field("Ends on", { type: "date", value: exception.ends_on, hint: "You may bring the date forward. A year at most." });
        reasonDialog({ title: outcome === "approved" ? "Approve this exception" : "Decline this exception", subtitle: exception.title,
          fields: outcome === "approved" ? { note, ends_on: until } : { note }, action: outcome === "approved" ? "Approve" : "Decline", danger: outcome !== "approved",
          run: () => post(`${at}/decision`, { outcome, note: note.input.value, ends_on: outcome === "approved" ? until.input.value || null : null }),
          done: () => { toast(outcome === "approved" ? "Approved." : "Declined."); reload(); } });
      };
      const end = (revoke) => {
        const reason = field(revoke ? "Why it is being revoked" : "A note, if you like", { type: "textarea" });
        reasonDialog({ title: revoke ? "Revoke this exception" : "Withdraw this request", subtitle: exception.title, fields: { reason },
          action: revoke ? "Revoke" : "Withdraw", danger: true, run: () => post(`${at}/end`, { reason: reason.input.value }),
          done: () => { toast(revoke ? "Revoked." : "Withdrawn."); reload(); } });
      };
      const renew = () => {
        const justification = field("Why more time is needed", { type: "textarea" });
        const until = field("New end date", { type: "date", hint: "A year at most from today." });
        reasonDialog({ title: "Ask for more time", subtitle: exception.title, fields: { justification, ends_on: until }, action: "Ask for a renewal",
          run: () => post(`${at}/renewal`, { justification: justification.input.value, ends_on: until.input.value || null }),
          done: (made) => { toast(`${made.data.ref} was requested.`); reload(); } });
      };
      const can = exception.can;
      const actions = [
        can.decide ? button("Approve…", { kind: "btn-primary", onclick: () => decide("approved") }) : null,
        can.decide ? button("Decline…", { kind: "btn-danger", onclick: () => decide("declined") }) : null,
        can.renew ? button("Ask for more time…", { onclick: renew }) : null,
        can.revoke ? button("Revoke…", { kind: "btn-ghost", onclick: () => end(true) }) : null,
        can.withdraw && !can.decide ? button("Withdraw", { kind: "btn-ghost", onclick: () => end(false) }) : null,
      ];
      const part = (title, text) => h("div", { class: "stack-sm" }, h("h3", {}, title), h("p", { class: "prose" }, text));
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/exceptions" }, icon("chevron-left", "icon icon-sm"), "Exceptions"),
        pageHeader({ eyebrow: `Exception · ${exception.ref}`, title: exception.title,
          lede: exception.record ? h("span", {}, "On ", h("a", { href: `/${exception.record.path}/${exception.record.ref}` }, exception.record.name), ` (${exception.record.ref})`) : null,
          actions: [statusPill(exception), ...actions] }),
        exception.renews ? alert("info", icon("link"), h("div", {}, "This renews ", h("a", { href: `/exceptions/${exception.renews}` }, exception.renews), ".")) : null,
        exception.renewed_by ? alert("info", icon("link"), h("div", {}, "A renewal has been asked for: ", h("a", { href: `/exceptions/${exception.renewed_by}` }, exception.renewed_by), ".")) : null,
        h("div", { class: "split" },
          card({ title: "What was asked" }, h("div", { class: "stack" },
            part("The requirement that cannot be met", exception.requirement),
            part("Why", exception.justification),
            part("What is done instead", exception.measures))),
          h("div", { class: "stack-lg" },
            card({ title: "Dates" }, h("dl", { class: "facts" },
              h("dt", {}, "Asked for"), h("dd", {}, [exception.requested_by, dateTime(exception.requested_at)].filter(Boolean).join(" · ")),
              h("dt", {}, exception.status === "approved" || exception.status === "requested" ? "Ends" : "Was to end"), h("dd", {}, date(exception.ends_on)),
              exception.closed_at ? [h("dt", {}, "Closed"), h("dd", {}, dateTime(exception.closed_at))] : null)),
            exception.decided_at ? card({ title: "Decision", actions: pill(...STATUS[exception.status === "approved" || exception.status === "declined" ? exception.status : "approved"]) },
              h("div", { class: "stack-sm" }, h("p", { class: "prose" }, exception.decision_note),
                h("div", { class: "subtle" }, [exception.decided_by ? `By ${exception.decided_by}` : null, dateTime(exception.decided_at)].filter(Boolean).join(" · ")))) : null)));
    },
  });
}
