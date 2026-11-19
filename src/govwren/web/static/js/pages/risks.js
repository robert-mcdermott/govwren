// The risk register: every risk, highest first, the grid of likelihood against impact, and
// one risk with its scores before and after treatment.

import { get, patch, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { navigate, query, setQuery } from "../core/router.js";
import { banner, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const LEVELS = { low: ["Low", ""], moderate: ["Moderate", "accent"], high: ["High", "warn"], critical: ["Critical", "danger"] };
const STATUS = { open: ["Not treated yet", "warn"], treated: ["Treated", "ok"], accepted: ["Accepted", "accent"], closed: ["Closed", ""] };
const SCALE = [["", "Choose…"], ["1", "1 · Very low"], ["2", "2 · Low"], ["3", "3 · Medium"], ["4", "4 · High"], ["5", "5 · Very high"]];
const TREATMENTS = [["", "Choose…"], ["mitigate", "Reduce it"], ["transfer", "Pass it to someone else"], ["avoid", "Stop doing what causes it"], ["accept", "Accept it as it stands"]];
const levelPill = (name) => (name ? pill(LEVELS[name][0], LEVELS[name][1]) : pill("Not scored"));
const number = (control) => (control.input.value ? Number(control.input.value) : null);
const bandOf = (score) => (score <= 4 ? "low" : score <= 9 ? "moderate" : score <= 16 ? "high" : "critical");

function grid(counts) {
  const rows = [5, 4, 3, 2, 1].map((impact) => h("tr", {},
    h("th", { scope: "row" }, String(impact)),
    [1, 2, 3, 4, 5].map((likelihood) => {
      const count = counts[impact - 1][likelihood - 1];
      return h("td", { "data-level": bandOf(impact * likelihood), "aria-label": `Impact ${impact}, likelihood ${likelihood}: ${count}` }, count ? String(count) : "");
    })));
  return h("table", { class: "risk-grid" },
    h("caption", {}, "Open risks by how likely and how bad, as they stand now"),
    h("tbody", {}, rows),
    h("tfoot", {}, h("tr", {}, h("td", {}), [1, 2, 3, 4, 5].map((n) => h("th", { scope: "col" }, String(n))))));
}

async function addRisk(about, done) {
  const statements = (await get("/api/v1/risk-library")).data;
  const categories = [...new Map(statements.map((s) => [s.category, s.category_label]))];
  openOverlay({
    title: "Record a risk", subtitle: about ? `On ${about}` : "For the organization as a whole", kind: "drawer",
    render: (body, footer, shut) => {
      const from = select("Draw it from the library", [["", "Write my own"], ...statements.map((s) => [s.key, `${s.category_label}: ${s.title}`])]);
      const title = field("What could go wrong", { maxlength: 300 });
      const description = field("In more words", { type: "textarea" });
      const category = select("Category", [["", "Choose…"], ...categories]);
      const likelihood = select("How likely, before anything is done", SCALE);
      const impact = select("How bad, if it happens", SCALE);
      const hint = h("p", { class: "subtle" });
      from.input.addEventListener("change", () => {
        const drawn = statements.find((s) => s.key === from.input.value);
        if (!drawn) return;
        title.input.value = drawn.title;
        description.input.value = drawn.description;
        category.input.value = drawn.category;
        hint.textContent = drawn.treatment ? `What usually answers it: ${drawn.treatment}` : "";
      });
      const problem = banner();
      const go = button("Record the risk", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const made = await submit({ button: go, banner: problem, fields: { title, category, inherent_likelihood: likelihood, inherent_impact: impact, library_key: from },
          run: () => post("/api/v1/risks", { record: about || null, library_key: from.input.value || null, title: title.input.value,
            description: description.input.value, category: category.input.value, inherent_likelihood: number(likelihood), inherent_impact: number(impact) }) });
        if (made) {
          shut();
          toast(`${made.data.ref} was recorded.`);
          done(made.data.ref);
        }
      });
      body.append(h("div", { class: "stack" }, problem, from.node, title.node, description.node, hint, category.node, likelihood.node, impact.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function riskList(main) {
  const params = query();
  const status = params.get("show") === "all" ? "all" : "live";
  const record = params.get("record");
  const mine = params.get("mine") === "true";
  return show(main, {
    title: "Risks",
    load: async () => {
      const found = await get("/api/v1/risks", { status, record, mine: mine ? "true" : null }, { fresh: true });
      return { rows: found.data, ...found.meta };
    },
    view: (data) => {
      const toggle = (name, current, pairs, label) => h("div", { class: "segmented", role: "group", "aria-label": label },
        pairs.map(([key, text, value]) => h("button", { type: "button", "aria-pressed": String(current === key), onclick: () => setQuery({ [name]: value }, { replace: false }) }, text)));
      const add = button(record ? `Add a risk to ${record}` : "Record a risk", { kind: "btn-primary", iconName: "plus", onclick: () => addRisk(record, (ref) => navigate(`/risks/${ref}`)) });
      return h("div", { class: "stack-lg" },
        pageHeader({ title: record ? `Risks on ${record}` : "Risks", lede: "What could go wrong, how likely and how bad, what is done about it, and what is left.",
          actions: [toggle("mine", mine ? "mine" : "all", [["all", "All", null], ["mine", "Mine", "true"]], "Whose risks"),
            toggle("show", status, [["live", "Open", null], ["all", "With closed", "all"]], "Which risks"), add] }),
        record ? h("a", { class: "back-link", href: "/risks" }, icon("chevron-left", "icon icon-sm"), "Every risk") : null,
        data.rows.length ? h("div", { class: "stack-lg" },
          card({ title: "Where they stand" }, h("div", { class: "risk-summary" }, grid(data.grid), h("div", { class: "stack" },
            h("div", { class: "row-sm wrap" }, Object.entries(data.by_level).reverse().map(([name, count]) => pill(`${count} ${LEVELS[name][0].toLowerCase()}`, LEVELS[name][1]))),
            h("p", { class: "subtle" }, "Impact runs up the side, likelihood along the bottom. A treated risk is counted where it stands after treatment.")))),
          card({ flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Risk"), h("th", { scope: "col" }, "On"), h("th", { scope: "col" }, "Now"), h("th", { scope: "col" }, "Owner"))),
            h("tbody", {}, data.rows.map((risk) => h("tr", {},
              h("td", {}, h("a", { class: "cell-main", href: `/risks/${risk.ref}` }, risk.title), h("div", { class: "cell-sub" }, `${risk.ref} · ${risk.category_label}`)),
              h("td", {}, risk.record ? h("a", { href: risk.record.href }, risk.record.name) : risk.organization ? "The organization" : h("span", { class: "subtle" }, "A record you cannot see")),
              h("td", {}, h("div", { class: "row-sm wrap" }, levelPill(risk.level), pill(...STATUS[risk.status])),
                risk.review_due ? h("div", { class: "due due-late" }, `Review was due ${date(risk.review_on)}`) : null),
              h("td", {}, risk.owner ?? h("span", { class: "subtle" }, "Nobody")))))))))
          : emptyState({ iconName: "shield", title: "No risks recorded", text: "Record what could go wrong, draw the wording from the library, and say what is done about it.", action: add }));
    },
  });
}

function treat(risk, reload) {
  openOverlay({
    title: "What is done about it", subtitle: risk.title, kind: "drawer",
    render: (body, footer, shut) => {
      const treatment = select("Treatment", TREATMENTS.filter(([key]) => key !== "accept" || risk.can.accept), { value: risk.treatment ?? "" });
      const note = field("What is done, and by whom", { type: "textarea", value: risk.treatment_note ?? "" });
      const likelihood = select("How likely now", SCALE, { value: String(risk.residual.likelihood ?? "") });
      const impact = select("How bad now", SCALE, { value: String(risk.residual.impact ?? "") });
      const review = field("Look at it again on", { type: "date", value: risk.review_on ?? "" });
      const problem = banner();
      const go = button("Save", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem, fields: { treatment, treatment_note: note, residual_likelihood: likelihood, residual_impact: impact, review_on: review },
          run: () => patch(`/api/v1/risks/${risk.ref}`, { treatment: treatment.input.value || null, treatment_note: note.input.value,
            residual_likelihood: number(likelihood), residual_impact: number(impact), review_on: review.input.value || null }) });
        if (done) {
          shut();
          toast("Saved.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, treatment.node, note.node, likelihood.node, impact.node, review.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

function closeRisk(risk, reload) {
  openOverlay({
    title: "Close this risk", subtitle: risk.title, kind: "dialog",
    render: (body, footer, shut) => {
      const reason = field("Why does it no longer apply?", { type: "textarea" });
      const problem = banner();
      const go = button("Close it", { kind: "btn-danger" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem, fields: { reason }, run: () => post(`/api/v1/risks/${risk.ref}/close`, { reason: reason.input.value }) });
        if (done) {
          shut();
          toast("The risk is closed.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, reason.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function riskPage(main, params) {
  return show(main, {
    title: "Risk",
    load: async () => (await get(`/api/v1/risks/${params.ref}`, null, { fresh: true })).data,
    view: (risk, reload) => {
      document.title = `${risk.title} · ${risk.ref}`;
      const score = (title, part) => h("div", { class: "stack-sm" }, h("h3", {}, title),
        part.level ? h("div", { class: "row-sm wrap" }, levelPill(part.level), h("span", { class: "muted" }, `Likelihood ${part.likelihood} of 5 · impact ${part.impact} of 5`))
          : h("p", { class: "muted" }, "Not scored yet."));
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/risks" }, icon("chevron-left", "icon icon-sm"), "Risks"),
        pageHeader({ eyebrow: `Risk · ${risk.ref} · ${risk.category_label}`, title: risk.title,
          lede: risk.record ? h("span", {}, "On ", h("a", { href: risk.record.href }, risk.record.name), ` (${risk.record.ref})`) : risk.organization ? "A risk to the organization as a whole" : null,
          actions: [levelPill(risk.level), pill(...STATUS[risk.status]),
            risk.can.change ? button(risk.treatment ? "Change the treatment…" : "Say what is done about it…", { kind: risk.treatment ? "" : "btn-primary", onclick: () => treat(risk, reload) }) : null,
            risk.can.close ? button("Close…", { kind: "btn-ghost", onclick: () => closeRisk(risk, reload) }) : null] }),
        risk.review_due ? alert("warn", icon("alert"), h("div", {}, h("strong", {}, "Due to be looked at again. "), `It was to be reviewed on ${date(risk.review_on)}.`)) : null,
        h("div", { class: "split" },
          h("div", { class: "stack-lg" },
            risk.description ? card({ title: "What could go wrong" }, h("p", { class: "prose" }, risk.description)) : null,
            card({ title: "What is done about it", actions: risk.treatment_label ? pill(risk.treatment_label) : null },
              risk.treatment_note ? h("p", { class: "prose" }, risk.treatment_note) : h("p", { class: "muted" }, risk.treatment ? "No note." : "Nothing has been recorded yet."))),
          h("div", { class: "stack-lg" },
            card({ title: "How it scores" }, h("div", { class: "stack" }, score("Before anything is done", risk.inherent), score("As it stands after treatment", risk.residual))),
            card({ title: "Ownership" }, h("dl", { class: "facts" },
              h("dt", {}, "Owner"), h("dd", {}, risk.owner ?? "Nobody"),
              h("dt", {}, "Look again"), h("dd", {}, risk.review_on ? date(risk.review_on) : "No date set"),
              risk.source ? [h("dt", {}, "Raised from"), h("dd", {}, risk.source)] : null,
              h("dt", {}, "Recorded"), h("dd", {}, date(risk.created_at)))))));
    },
  });
}
