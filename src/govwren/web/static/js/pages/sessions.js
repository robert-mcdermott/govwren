// Committee sessions: the list, and one session with its agenda, the decisions made in it,
// who attended, and its minutes.

import { get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime } from "../core/format.js";
import { navigate } from "../core/router.js";
import { can } from "../core/session.js";
import { banner, checkbox, field, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { REVIEW_KINDS, reviewStatusPill } from "../components/packet.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

const ACCEPTANCE = { needed: ["Risk acceptance needed", "warn"], requested: ["Risk acceptance asked for", "warn"],
  accepted: ["Risk accepted", "ok"], declined: ["Risk not accepted", "danger"] };

function pickReviews(candidates, chosen = []) {
  const boxes = candidates.map((row) => [row.ref, checkbox(`${row.name} (${row.ref})`, { checked: chosen.includes(row.ref),
    hint: row.status === "ready" ? "Ready for a decision" : "Still with reviewers" })]);
  return { node: boxes.length ? h("fieldset", { class: "stack-sm" }, h("legend", { class: "label" }, "Reviews that a committee decides"), boxes.map(([, box]) => box.node))
    : h("p", { class: "muted" }, "No review is waiting for a committee at the moment."),
  values: () => boxes.filter(([, box]) => box.input.checked).map(([ref]) => ref) };
}

function planSession(candidates) {
  openOverlay({
    title: "Plan a session", subtitle: "Put the reviews the committee will consider on its agenda.", kind: "drawer",
    render: (body, footer, shut) => {
      const title = field("Name", { maxlength: 200, hint: "Such as: Governance committee, December." });
      const held = field("Date of the meeting", { type: "date" });
      const picks = pickReviews(candidates, candidates.filter((row) => row.status === "ready").map((row) => row.ref));
      const problem = banner();
      const go = button("Plan the session", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const made = await submit({ button: go, banner: problem, fields: { title, held_on: held },
          run: () => post("/api/v1/sessions", { title: title.input.value, held_on: held.input.value || null, reviews: picks.values() }) });
        if (made) {
          shut();
          navigate(`/sessions/${made.data.ref}`);
        }
      });
      body.append(h("div", { class: "stack" }, problem, title.node, held.node, picks.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function sessionList(main) {
  return show(main, {
    title: "Sessions",
    load: async () => {
      const found = await get("/api/v1/sessions", null, { fresh: true });
      return { rows: found.data, candidates: found.meta.candidates };
    },
    view: ({ rows, candidates }) => {
      const plan = can("govern") ? button("Plan a session", { kind: "btn-primary", iconName: "plus", onclick: () => planSession(candidates) }) : null;
      const waiting = candidates.filter((row) => row.status === "ready").length;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Sessions", lede: "Meetings of the committee: what was on the agenda, what was decided, and the minutes.", actions: plan }),
        waiting ? alert("info", icon("info"), h("div", {}, `${waiting} review${waiting === 1 ? " is" : "s are"} ready for a committee decision and on no agenda yet.`)) : null,
        rows.length ? card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Session"), h("th", { scope: "col" }, "Date"), h("th", { scope: "col" }, "Agenda"), h("th", { scope: "col" }, "Record"))),
          h("tbody", {}, rows.map((row) => h("tr", {},
            h("td", {}, h("a", { class: "cell-main", href: `/sessions/${row.ref}` }, row.title), h("div", { class: "cell-sub" }, row.ref)),
            h("td", { class: "nowrap" }, date(row.held_on)),
            h("td", {}, `${row.decided} of ${row.items} decided`),
            h("td", {}, row.status === "closed" ? pill("Closed", "ok") : pill("Planned", "accent"))))))))
          : emptyState({ iconName: "note", title: "No sessions yet", text: "Plan one to gather the reviews a committee decides into an agenda.", action: plan }));
    },
  });
}

export function sessionPage(main, params) {
  return show(main, {
    title: "Session",
    load: async () => (await get(`/api/v1/sessions/${params.ref}`, null, { fresh: true })).data,
    view: (meeting, reload) => {
      document.title = `${meeting.title} · ${meeting.ref}`;
      const at = `/api/v1/sessions/${meeting.ref}`;
      const editAgenda = () => openOverlay({
        title: "Change the agenda", subtitle: meeting.title, kind: "drawer",
        render: (body, footer, shut) => {
          const on = meeting.agenda.map((item) => ({ ref: item.review, name: item.use_case.name, status: item.status }));
          const picks = pickReviews([...on, ...meeting.candidates], on.map((row) => row.ref));
          const problem = banner();
          const go = button("Save the agenda", { kind: "btn-primary" });
          go.addEventListener("click", async () => {
            const done = await submit({ button: go, banner: problem, fields: {}, run: () => put(`${at}/agenda`, { reviews: picks.values() }) });
            if (done) {
              shut();
              toast("The agenda was saved.");
              reload();
            }
          });
          body.append(h("div", { class: "stack" }, problem, picks.node));
          footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
          footer.hidden = false;
        },
      });
      const attendees = field("Who attended", { type: "textarea", value: meeting.attendees ?? "", hint: "Names, and anyone who stepped out for an item." });
      const minutes = field("Minutes", { type: "textarea", value: meeting.minutes ?? "", rows: 10, hint: "What was discussed and agreed. Decisions on requests are recorded with each item above." });
      const problem = banner();
      const save = (close) => async (event) => {
        const done = await submit({ button: event.currentTarget, banner: problem, fields: { attendees, minutes },
          run: () => put(at, { attendees: attendees.input.value, minutes: minutes.input.value, close }) });
        if (done) {
          toast(close ? "The session is closed." : "Saved.");
          reload();
        }
      };
      const undecided = meeting.agenda.filter((item) => !item.decision).length;
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/sessions" }, icon("chevron-left", "icon icon-sm"), "Sessions"),
        pageHeader({ eyebrow: `Committee session · ${meeting.ref}`, title: meeting.title, lede: `${meeting.status === "closed" ? "Held" : "Meets"} ${date(meeting.held_on)}`,
          actions: [meeting.status === "closed" ? pill("Closed", "ok") : pill("Planned", "accent"),
            meeting.can_edit ? button("Change the agenda", { onclick: editAgenda }) : null] }),
        card({ title: "Agenda" }, meeting.agenda.length ? h("ol", { class: "agenda" }, meeting.agenda.map((item) => h("li", { class: "stack-sm" },
          h("div", { class: "row wrap" },
            h("div", { class: "grow" }, h("a", { class: "cell-main", href: `/reviews?open=${item.review}` }, item.use_case.name),
              h("div", { class: "cell-sub" }, `${REVIEW_KINDS[item.kind] ?? "Review"} ${item.review} · ${item.use_case.ref}`)),
            h("div", { class: "row-sm wrap" }, item.tier ? tierBadge(item.tier) : null,
              item.decision ? pill(item.decision.words, item.decision.outcome.startsWith("approved") ? "ok" : item.decision.outcome === "declined" ? "danger" : "warn") : reviewStatusPill(item.status))),
          h("div", { class: "row-sm wrap subtle" },
            item.objections ? pill(`${item.objections} objection${item.objections === 1 ? "" : "s"}`, "danger") : null,
            item.with_conditions ? h("span", {}, `${item.with_conditions} reviewer${item.with_conditions === 1 ? "" : "s"} asked for conditions`) : null,
            item.no_concerns ? h("span", {}, `${item.no_concerns} with no concerns`) : null,
            item.acceptance ? pill(...ACCEPTANCE[item.acceptance]) : null),
          item.decision ? h("div", { class: "stack-sm" }, h("p", { class: "prose" }, item.decision.rationale),
            h("div", { class: "subtle" }, [item.decision.decided_by ? `Recorded by ${item.decision.decided_by}` : null, item.decision.over_objection ? "Made over an objection" : null].filter(Boolean).join(" · ")))
            : meeting.can_edit ? h("div", {}, h("a", { class: "btn btn-sm", href: `/reviews?open=${item.review}` }, "Open the packet to decide")) : null)))
          : h("p", { class: "muted" }, "Nothing is on the agenda yet.")),
        meeting.can_edit ? card({ title: "Record of the meeting" }, h("div", { class: "stack" }, problem, attendees.node, minutes.node,
          undecided ? h("p", { class: "muted" }, `${undecided} item${undecided === 1 ? " has" : "s have"} no decision yet. Closing leaves ${undecided === 1 ? "it" : "them"} open for a later session.`) : null,
          h("div", { class: "row wrap" }, button("Save", { onclick: save(false) }), button("Close the session", { kind: "btn-primary", onclick: save(true) }),
            h("span", { class: "subtle" }, "Once closed, the record cannot be changed."))))
          : card({ title: "Record of the meeting", footer: meeting.closed_at ? h("span", { class: "subtle" }, `Closed ${dateTime(meeting.closed_at)}${meeting.closed_by ? ` by ${meeting.closed_by}` : ""}`) : null },
            h("div", { class: "stack" },
              h("div", { class: "stack-sm" }, h("h3", {}, "Attended"), h("p", { class: "prose" }, meeting.attendees ?? "Not recorded.")),
              h("div", { class: "stack-sm" }, h("h3", {}, "Minutes"), h("p", { class: "prose pre-line" }, meeting.minutes ?? "Not recorded.")))));
    },
  });
}
