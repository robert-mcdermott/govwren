// Attestation campaigns: the list, and one campaign with its coverage and what is yours to answer.

import { get, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, dateTime, plural } from "../core/format.js";
import { unitOptions, units } from "../core/lookups.js";
import { can } from "../core/session.js";
import { navigate } from "../core/router.js";
import { banner, checkbox, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { standingPill } from "../components/record.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill, stat, tierBadge } from "../components/ui.js";
import { show } from "./page.js";

const KINDS = { owner_confirmation: "Owner confirmation", unit_completeness: "Unit completeness" };
const ASKS = {
  owner_confirmation: "Owners say whether each of their records is still true.",
  unit_completeness: "Stewards say whether their unit's list is complete.",
};
const TYPES = { use_case: "Use cases", system: "AI systems", model: "Models", dataset: "Datasets" };
const RESPONSES = { confirmed: ["Confirmed", "ok"], changed: ["Changed", "warn"], retired: ["No longer in use", ""], attested: ["Attested", "ok"] };

const share = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

function meter(part, whole, label) {
  const bar = h("div", { class: "meter", role: "img", "aria-label": `${label}: ${part} of ${whole}` }, h("span"));
  bar.style.setProperty("--share", `${share(part, whole)}%`);
  return bar;
}

function duePill(campaign) {
  if (campaign.status === "closed") return pill("Closed");
  return campaign.overdue ? pill(`Was due ${date(campaign.due_on)}`, "danger") : pill(`Due ${date(campaign.due_on)}`, "accent");
}

function newCampaign(tree, done) {
  openOverlay({
    title: "Start a campaign",
    subtitle: "Everyone it asks is told at once, and reminded before the date.",
    kind: "dialog",
    render: (body, footer, shut) => {
      const kind = select("What it asks", Object.entries(KINDS).map(([key, text]) => [key, text]), { hint: ASKS.owner_confirmation });
      const title = field("Name", { hint: "People see this in their list of things to do.", maxlength: 200 });
      const scope = select("Which part of the organization", unitOptions(tree, { blank: "All of it" }), { hint: "A unit includes every unit beneath it." });
      const due = field("Answers wanted by", { type: "date" });
      const note = field("A note to the people asked", { type: "textarea", hint: "Optional. Shown at the top of the campaign." });
      const kinds = Object.entries(TYPES).map(([key, text]) => [key, checkbox(text, { checked: key === "use_case" })]);
      const which = h("fieldset", { class: "stack-sm" }, h("legend", { class: "label" }, "Records to confirm"), kinds.map(([, box]) => box.node));
      kind.input.addEventListener("change", () => {
        which.hidden = kind.input.value !== "owner_confirmation";
        kind.node.querySelector(".hint").textContent = ASKS[kind.input.value];
      });
      const problem = banner();
      const go = button("Start the campaign", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const made = await submit({ button: go, banner: problem, fields: { kind, title, due_on: due, scope_unit_id: scope },
          run: () => post("/api/v1/campaigns", { kind: kind.input.value, title: title.input.value, due_on: due.input.value || null,
            scope_unit_id: scope.input.value ? Number(scope.input.value) : null, note: note.input.value,
            record_types: kinds.filter(([, box]) => box.input.checked).map(([key]) => key) }) });
        if (made) {
          shut();
          toast(`${made.data.ref} has started. ${made.data.total} ${plural(made.data.total, "question")} went out.`);
          done(made.data.ref);
        }
      });
      body.append(h("div", { class: "stack" }, problem, kind.node, title.node, which, scope.node, due.node, note.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function campaignList(main) {
  return show(main, {
    title: "Attestations",
    load: async () => {
      const [list, tree] = await Promise.all([get("/api/v1/campaigns", null, { fresh: true }), units()]);
      return { list: list.data, tree: tree.tree };
    },
    view: (data) => {
      const start = can("govern") ? button("Start a campaign", { kind: "btn-primary", iconName: "plus",
        onclick: () => newCampaign(data.tree, (ref) => navigate(`/campaigns/${ref}`)) }) : null;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Attestations", lede: "The people closest to the work say whether the inventory is still true.", actions: start }),
        data.list.length ? h("div", { class: "stack" }, data.list.map((campaign) => card({
          title: h("a", { href: `/campaigns/${campaign.ref}` }, campaign.title),
          actions: h("div", { class: "row-sm wrap" }, campaign.mine_waiting ? pill(`${campaign.mine_waiting} waiting on you`, "warn") : null, duePill(campaign)) },
        h("div", { class: "stack-sm" },
          h("div", { class: "subtle" }, `${campaign.ref} · ${KINDS[campaign.kind]} · started ${date(campaign.opened_at)}`),
          meter(campaign.answered, campaign.total, "Answered"),
          h("div", { class: "muted" }, `${campaign.answered} of ${campaign.total} answered (${share(campaign.answered, campaign.total)}%)`)))))
          : emptyState({ iconName: "check", title: "No campaigns yet",
            text: can("govern") ? "Start one to ask owners to confirm their records, or stewards to attest that their unit's list is complete."
              : "When governance asks you to confirm your records, it will be listed here.", action: start }));
    },
  });
}

function answerDialog(campaign, item, response, reload) {
  const changed = response === "changed";
  openOverlay({
    title: changed ? "What has changed?" : "No longer in use",
    subtitle: item.name,
    kind: "dialog",
    render: (body, footer, shut) => {
      const note = field(changed ? "What is different now" : "Why it has ended", { type: "textarea",
        hint: changed ? (item.type === "use_case" ? "Next you correct the answers that are different now. The rules decide whether the change needs a review."
          : "Governance is told, and decides whether it needs another look.") : "The record is retired. It stays in the inventory, with its history." });
      const problem = banner();
      const go = button(changed ? "Report the change" : "Retire it", { kind: changed ? "btn-primary" : "btn-danger" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem, fields: { note },
          run: () => post(`/api/v1/campaigns/${campaign.ref}/answers`, { items: [{ id: item.id, response, note: note.input.value }] }) });
        if (done) {
          shut();
          toast(changed ? "Reported as changed." : "Retired.");
          if (changed && item.type === "use_case" && item.ref) navigate(`/use-cases/${item.ref}/request`);
          else reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, note.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

function answerPill(item) {
  if (!item.response) return pill("Not answered");
  const [text, tone] = RESPONSES[item.response];
  return pill(text, tone);
}

function recordRows(campaign, items, reload) {
  const open = items.filter((item) => item.can_answer);
  const boxes = new Map();
  const confirm = button("Confirm the ones ticked", { kind: "btn-primary", disabled: true });
  const sync = () => {
    const count = [...boxes.values()].filter((box) => box.checked).length;
    confirm.disabled = !count;
    confirm.textContent = count ? `Confirm ${count} as still accurate` : "Confirm the ones ticked";
  };
  const all = h("input", { type: "checkbox", "aria-label": "Tick every record", onchange: () => {
    for (const box of boxes.values()) box.checked = all.checked;
    sync();
  } });
  confirm.addEventListener("click", async () => {
    confirm.disabled = true;
    const picked = [...boxes].filter(([, box]) => box.checked).map(([id]) => ({ id, response: "confirmed" }));
    try {
      await post(`/api/v1/campaigns/${campaign.ref}/answers`, { items: picked });
      toast(`${picked.length} ${plural(picked.length, "record")} confirmed.`);
    } catch (error) {
      toast(error.detail ?? "They could not be confirmed.");
    }
    reload();
  });
  const row = (item) => {
    let box = null;
    if (item.can_answer) {
      box = h("input", { type: "checkbox", "aria-label": `Tick ${item.name}`, onchange: sync });
      boxes.set(item.id, box);
    }
    return h("tr", {},
      h("td", {}, box),
      h("td", {}, h("div", { class: "cell-main" }, item.ref ? h("a", { href: `/${item.path}/${item.ref}` }, item.name) : item.name),
        h("div", { class: "cell-sub" }, [item.ref, item.unit].filter(Boolean).join(" · "))),
      h("td", {}, h("div", { class: "row-sm wrap" }, item.tier ? tierBadge(item.tier) : null, item.status && item.type === "use_case" ? standingPill(item.status) : null)),
      h("td", {}, item.response ? h("div", {}, answerPill(item), h("div", { class: "cell-sub" }, [item.answered_by, item.answered_at ? date(item.answered_at) : null].filter(Boolean).join(" · ")),
        item.note ? h("div", { class: "cell-sub" }, item.note) : null)
        : item.can_answer ? h("div", { class: "row-sm wrap" },
          button("Changed…", { kind: "btn-sm", "aria-label": `Report a change to ${item.name}`, onclick: () => answerDialog(campaign, item, "changed", reload) }),
          button("No longer in use…", { kind: "btn-sm btn-ghost", "aria-label": `Report ${item.name} as no longer in use`, onclick: () => answerDialog(campaign, item, "retired", reload) }))
          : h("div", {}, answerPill(item), item.waiting_on.length ? h("div", { class: "cell-sub" }, `Waiting on ${item.waiting_on.join(", ")}`) : null)));
  };
  return h("div", { class: "stack" },
    open.length ? h("div", { class: "row wrap" }, confirm, h("span", { class: "subtle" }, "Tick the records that are still as described, then confirm them together.")) : null,
    h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, open.length ? all : h("span", { class: "sr-only" }, "Tick")), h("th", { scope: "col" }, "Record"),
        h("th", { scope: "col" }, "Standing"), h("th", { scope: "col" }, "Answer"))),
      h("tbody", {}, items.map(row)))));
}

function unitCards(campaign, items, reload) {
  return h("div", { class: "stack" }, items.map((item) => {
    const holds = Object.entries(TYPES).map(([key, text]) => `${item.holds?.[key] ?? 0} ${text.toLowerCase()}`).join(" · ");
    const attest = item.can_answer ? button("Attest that the list is complete", { kind: "btn-primary btn-sm", onclick: async () => {
      try {
        await post(`/api/v1/campaigns/${campaign.ref}/answers`, { items: [{ id: item.id, response: "attested" }] });
        toast(`${item.name}: attested.`);
      } catch (error) {
        toast(error.detail ?? "It could not be recorded.");
      }
      reload();
    } }) : null;
    return card({ title: item.name, actions: answerPill(item) }, h("div", { class: "stack-sm" },
      h("div", { class: "muted" }, `${item.response ? "Held when attested" : "Holds now"}: ${holds}`),
      item.response ? h("div", { class: "subtle" }, `${item.answered_by ?? "Someone"} · ${dateTime(item.answered_at)}`)
        : item.waiting_on.length ? h("div", { class: "subtle" }, `Waiting on ${item.waiting_on.join(", ")}`) : null,
      item.can_answer ? h("div", { class: "row wrap" },
        h("a", { class: "btn btn-sm", href: `/use-cases?unit=${item.org_unit_id}` }, "See the unit's use cases"),
        h("a", { class: "btn btn-sm", href: "/requests/new" }, "Add a use that is missing"), attest) : null));
  }));
}

export function campaignPage(main, params) {
  return show(main, {
    title: "Campaign",
    load: async () => (await get(`/api/v1/campaigns/${params.ref}`, null, { fresh: true })).data,
    view: (campaign, reload) => {
      document.title = `${campaign.title} · ${campaign.ref}`;
      const records = campaign.kind === "owner_confirmation";
      const mine = campaign.items.filter((item) => item.mine);
      const others = campaign.items.filter((item) => !item.mine);
      const list = (items) => (records ? recordRows(campaign, items, reload) : unitCards(campaign, items, reload));
      const close = campaign.can_close ? button("Close the campaign", { onclick: async () => {
        await post(`/api/v1/campaigns/${campaign.ref}/close`);
        toast("The campaign is closed.");
        reload();
      } }) : null;
      const answers = Object.entries(campaign.by_response).map(([key, count]) => `${count} ${RESPONSES[key][0].toLowerCase()}`).join(" · ");
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/campaigns" }, icon("chevron-left", "icon icon-sm"), "Attestations"),
        pageHeader({ eyebrow: `${KINDS[campaign.kind]} · ${campaign.ref}`, title: campaign.title,
          lede: [ASKS[campaign.kind], campaign.scope_unit ? `Covers ${campaign.scope_unit} and the units beneath it.` : null].filter(Boolean).join(" "),
          actions: [duePill(campaign), close] }),
        campaign.note ? alert("info", icon("info"), h("div", {}, campaign.note)) : null,
        h("div", { class: "grid-3" }, stat(`${share(campaign.answered, campaign.total)}%`, "Answered"),
          stat(`${campaign.answered} of ${campaign.total}`, records ? "Records" : "Units"), stat(String(campaign.total - campaign.answered), "Still waiting")),
        answers ? h("p", { class: "muted" }, `So far: ${answers}.`) : null,
        mine.length ? card({ title: records ? "Your records" : "Your units" }, list(mine)) : null,
        records && campaign.sees_all && campaign.by_unit.length ? card({ title: "Coverage by unit", flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Unit"), h("th", { scope: "col" }, "Answered"), h("th", { scope: "col" }, "Share"))),
          h("tbody", {}, campaign.by_unit.map((row) => h("tr", {},
            h("td", { class: "cell-main" }, row.unit), h("td", { class: "numeric" }, `${row.answered} of ${row.total}`),
            h("td", {}, h("div", { class: "row-sm" }, h("div", { class: "grow" }, meter(row.answered, row.total, row.unit)),
              h("span", { class: "numeric subtle" }, `${share(row.answered, row.total)}%`))))))))) : null,
        others.length ? card({ title: mine.length ? "Everything else" : records ? "Records" : "Units" }, list(others)) : null);
    },
  });
}
