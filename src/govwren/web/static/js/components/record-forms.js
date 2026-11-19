// The forms that add and edit inventory records.

import { patch, post } from "../core/api.js";
import { button, h, uid } from "../core/dom.js";
import { options, unitOptions } from "../core/lookups.js";
import { navigate } from "../core/router.js";
import { can, session } from "../core/session.js";
import { banner, checkbox, field, select, submit } from "./form.js";
import { openOverlay } from "./overlay.js";
import { standingLabel, TYPES } from "./record.js";
import { toast } from "./toast.js";

/** A set of tick boxes for a vocabulary. Returns { node, values }. */
function manyOf(legend, vocab, name, chosen = [], hint = null) {
  const boxes = (vocab[name] ?? []).filter((item) => !item.retired || chosen.includes(item.key))
    .map((item) => checkbox(item.label, { checked: chosen.includes(item.key), value: item.key }));
  return {
    node: h("fieldset", {}, h("legend", {}, legend), hint ? h("p", { class: "hint subtle" }, hint) : null,
      h("div", { class: "grid-2" }, boxes.map((box) => box.node))),
    values: () => boxes.filter((box) => box.input.checked).map((box) => box.input.value),
  };
}

/**
 * The data class: one choice from an ordered list, each with its meaning and, on request,
 * examples. People pick the right class when they can recognize their own data in it.
 */
function dataClass(legend, vocab, chosen, hint) {
  const name = uid("data-class");
  let value = chosen ?? "";
  const cards = (vocab.data_classes ?? []).filter((item) => !item.retired).map((item) => {
    const examples = Object.entries(item.examples ?? {});
    return h("label", { class: "choice" },
      h("input", { type: "radio", name, value: item.key, checked: item.key === value, onchange: () => {
        value = item.key;
      } }),
      h("div", { class: "grow" },
        h("div", { class: "cell-main" }, item.label),
        h("div", { class: "cell-sub" }, item.description),
        examples.length ? h("details", { class: "examples" },
          h("summary", {}, "Examples"),
          h("dl", {}, examples.map(([group, list]) => [h("dt", {}, group), h("dd", {}, list.join(" · "))]))) : null));
  });
  return {
    node: h("fieldset", {}, h("legend", {}, legend), hint ? h("p", { class: "hint subtle" }, hint) : null,
      h("div", { class: "stack-sm" }, cards)),
    value: () => value || null,
  };
}

function section(title, ...children) {
  return h("div", { class: "form-section stack" }, h("h3", {}, title), children);
}

/** Only what the editor changed is sent, so a field someone may not change is never touched. */
function changed(record, values) {
  const plain = (value) => JSON.stringify(value === "" || value == null || (Array.isArray(value) && !value.length) ? null : value);
  return Object.fromEntries(Object.entries(values).filter(([key, value]) => !(key in record) || plain(value) !== plain(record[key])));
}

async function save({ type, record, values, fields, problem, saveButton, close, onDone }) {
  const path = `/api/v1/${TYPES[type].path}`;
  const done = await submit({ button: saveButton, fields, banner: problem,
    run: () => (record ? patch(`${path}/${record.ref}`, { version: record.version, ...changed(record, values) }) : post(path, values)) });
  if (!done) return;
  close();
  if (record) {
    toast("Saved.");
    onDone?.(done.data);
  } else {
    toast(`${done.data.ref} was added.`);
    navigate(`/${TYPES[type].path}/${done.data.ref}`);
  }
}

function frame({ type, record, body, footer, close, build, onDone }) {
  const problem = banner();
  const saveButton = button(record ? "Save" : "Add", { kind: "btn-primary" });
  const { nodes, fields, values } = build();
  const form = h("form", { class: "stack-lg", novalidate: true, onsubmit: (event) => {
    event.preventDefault();
    saveButton.click();
  } }, problem, nodes);
  saveButton.addEventListener("click", () => save({ type, record, values: values(), fields, problem, saveButton, close, onDone }));
  body.append(form);
  footer.replaceChildren(h("div", { class: "row" }, saveButton, button("Cancel", { kind: "btn-ghost", onclick: close })));
  footer.hidden = false;
}

export function editUseCase({ record = null, vocab, units, onDone }) {
  const me = session();
  const own = new Set([...(me.member_units ?? []), ...me.steward_units]);
  openOverlay({
    title: record ? "Edit use case" : "Add a use case",
    subtitle: record ? record.ref : "It starts as a draft that only you can see.",
    render: (body, footer, close) => frame({ type: "use_case", record, body, footer, close, onDone, build: () => {
      const name = field("Name", { value: record?.name ?? "", required: true,
        hint: "What the AI is used for, in a few words. For example: Summarize lab meeting notes." });
      const offered = can("edit_all") || !own.size ? null : own;
      const unit = select("Unit", unitOptions(units.tree, { only: offered, blank: "Choose a unit" }),
        { value: record?.org_unit_id ?? "" });
      const purpose = field("Purpose", { type: "textarea", value: record?.purpose ?? "",
        hint: "What it does, and the problem it helps with. Do not paste sensitive data here." });
      const domain = select("Domain", options(vocab, "domains", { blank: "Not said" }), { value: record?.domain ?? "" });
      const stage = select("Stage", options(vocab, "stages"), { value: record?.stage ?? "proposed" });
      const role = select("How outputs are used", options(vocab, "decision_roles", { blank: "Not said" }),
        { value: record?.decision_role ?? "" });
      const oversight = field("Human oversight", { type: "textarea", value: record?.human_oversight ?? "",
        hint: "Who checks the outputs, and how, before anyone relies on them." });
      const klass = dataClass("Highest class of data involved", vocab, record?.data_class,
        "If several kinds of data are involved, choose the most sensitive.");
      const categories = manyOf("Kinds of data", vocab, "data_categories", record?.data_categories ?? []);
      const affected = manyOf("Who is affected", vocab, "affected_groups", record?.affected_groups ?? []);
      const outputs = manyOf("What outputs are used for", vocab, "outputs_used_for", record?.outputs_used_for ?? []);
      const restricted = checkbox("Restricted", { checked: record?.restricted ?? false,
        hint: "Known only to its owners, the unit's stewards, governance, and auditors." });
      return {
        nodes: [
          section("What and where", name.node, unit.node, purpose.node, h("div", { class: "grid-2" }, domain.node, stage.node)),
          section("Data", klass.node, categories.node),
          section("People and decisions", role.node, affected.node, outputs.node, oversight.node),
          section("Visibility", restricted.node),
        ],
        fields: { name, org_unit_id: unit, purpose, domain, stage, decision_role: role, human_oversight: oversight },
        values: () => ({
          name: name.input.value, org_unit_id: unit.input.value ? Number(unit.input.value) : null,
          purpose: purpose.input.value, domain: domain.input.value || null, stage: stage.input.value,
          decision_role: role.input.value || null, human_oversight: oversight.input.value,
          data_class: klass.value(), data_categories: categories.values(), affected_groups: affected.values(),
          outputs_used_for: outputs.values(), restricted: restricted.input.checked,
        }),
      };
    } }),
  });
}

const CATALOG = ["not_listed", "under_evaluation", "approved", "approved_with_restrictions", "not_approved", "retired"];

export function editSystem({ record = null, vocab, units, vendors = [], onDone }) {
  openOverlay({
    title: record ? "Edit AI system" : "Add an AI system",
    subtitle: record ? record.ref : "A tool, product, service, or application that uses AI.",
    render: (body, footer, close) => frame({ type: "system", record, body, footer, close, onDone, build: () => {
      const name = field("Name", { value: record?.name ?? "", required: true });
      const kind = select("Kind", options(vocab, "system_kinds"), { value: record?.kind ?? "vendor_product" });
      const vendor = select("Vendor", [["", "None, or not known"], ...vendors.map((v) => [v.ref, v.name])],
        { value: record?.vendor?.ref ?? "", hint: "Add the vendor first, under Vendors, if it is not listed." });
      const edition = field("Edition", { value: record?.edition ?? "",
        hint: "The exact plan or license tier, such as Enterprise or Free. A different edition is a different system." });
      const access = select("Reached through", options(vocab, "access_paths", { blank: "Not said" }), { value: record?.access_path ?? "" });
      const hosting = select("Hosting", options(vocab, "hosting", { blank: "Not said" }), { value: record?.hosting ?? "" });
      const version = field("Version", { value: record?.version_label ?? "" });
      const url = field("Address", { type: "url", value: record?.url ?? "", placeholder: "https://" });
      const inside = field("Inside which product", { value: record?.embedded_in ?? "",
        hint: "For an AI feature that is part of other software." });
      const summary = field("Summary", { type: "textarea", value: record?.summary ?? "" });
      const handling = record?.data_handling ?? {};
      const trains = select("Does the supplier train on what is entered?",
        [["unknown", "Not known"], ["no", "No"], ["yes", "Yes"]], { value: handling.trains_on_inputs ?? "unknown" });
      const retention = field("How long inputs are kept", { value: handling.retention ?? "" });
      const regions = field("Where data is processed", { value: handling.regions ?? "" });
      const nodes = [
        section("What it is", name.node, h("div", { class: "grid-2" }, kind.node, vendor.node),
          h("div", { class: "grid-2" }, edition.node, access.node), h("div", { class: "grid-2" }, hosting.node, version.node),
          url.node, inside.node, summary.node),
        section("How it handles data", trains.node, h("div", { class: "grid-2" }, retention.node, regions.node)),
      ];
      const fields = { name, kind, vendor, edition, url, access_path: access, hosting };
      let catalog = () => ({});
      if (can("edit_all")) {
        const standing = select("Catalog standing", CATALOG.map((key) => [key, standingLabel(key)]),
          { value: record?.catalog_status ?? "not_listed" });
        const upTo = select("May be used with data up to", options(vocab, "data_classes", { blank: "Not decided" }),
          { value: record?.permitted_data_class ?? "" });
        const excluded = manyOf("Never to be used with", vocab, "data_categories", record?.excluded_data_categories ?? []);
        const terms = field("Terms of use", { type: "textarea", value: record?.terms ?? "",
          hint: "The conditions that apply to everyone who uses it. Shown in the catalog." });
        nodes.push(section("Catalog", standing.node, upTo.node, excluded.node, terms.node));
        Object.assign(fields, { catalog_status: standing, permitted_data_class: upTo, terms });
        catalog = () => ({ catalog_status: standing.input.value, permitted_data_class: upTo.input.value || null,
          excluded_data_categories: excluded.values(), terms: terms.input.value });
      }
      return { nodes, fields, values: () => ({
        name: name.input.value, kind: kind.input.value, vendor: vendor.input.value || null,
        edition: edition.input.value, access_path: access.input.value || null, hosting: hosting.input.value || null,
        version_label: version.input.value, url: url.input.value, embedded_in: inside.input.value,
        summary: summary.input.value,
        data_handling: { trains_on_inputs: trains.input.value, retention: retention.input.value, regions: regions.input.value },
        ...catalog(),
      }) };
    } }),
  });
}

const VENDOR_STATUSES = ["prospective", "active", "offboarding", "former"];
const DILIGENCE = ["not_started", "in_progress", "complete"];

export function editVendor({ record = null, onDone }) {
  openOverlay({
    title: record ? "Edit vendor" : "Add a vendor",
    subtitle: record ? record.ref : "An outside supplier of an AI system or model.",
    render: (body, footer, close) => frame({ type: "vendor", record, body, footer, close, onDone, build: () => {
      const name = field("Name", { value: record?.name ?? "", required: true, hint: "The supplier's legal or trading name." });
      const website = field("Website", { type: "url", value: record?.website ?? "", placeholder: "https://" });
      const summary = field("Summary", { type: "textarea", value: record?.summary ?? "" });
      const notes = field("Notes", { type: "textarea", value: record?.notes ?? "" });
      const first = record?.contacts?.[0] ?? {};
      const contactName = field("Contact name", { value: first.name ?? "" });
      const contactEmail = field("Contact email", { type: "email", value: first.email ?? "" });
      const nodes = [section("Who they are", name.node, website.node, summary.node),
        section("Contact", h("div", { class: "grid-2" }, contactName.node, contactEmail.node), notes.node)];
      const fields = { name, website };
      let standing = () => ({});
      if (can("edit_all")) {
        const status = select("Standing", VENDOR_STATUSES.map((key) => [key, standingLabel(key)]), { value: record?.status ?? "prospective" });
        const diligence = select("Due diligence", DILIGENCE.map((key) => [key, standingLabel(key)]),
          { value: record?.due_diligence_status ?? "not_started" });
        nodes.push(section("Standing", h("div", { class: "grid-2" }, status.node, diligence.node)));
        standing = () => ({ status: status.input.value, due_diligence_status: diligence.input.value });
      }
      return { nodes, fields, values: () => {
        const rest = (record?.contacts ?? []).slice(1);
        const contact = { name: contactName.input.value, email: contactEmail.input.value, role: first.role ?? null };
        return { name: name.input.value, website: website.input.value, summary: summary.input.value,
          notes: notes.input.value, contacts: [contact, ...rest], ...standing() };
      } };
    } }),
  });
}

export const EDITORS = { use_case: editUseCase, system: editSystem, vendor: editVendor };
