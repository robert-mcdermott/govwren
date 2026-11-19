// Admin → Single sign-on: how the connection is set up, and which of the provider's groups
// give which roles here.

import { get, put } from "../core/api.js";
import { button, h, icon, iconButton } from "../core/dom.js";
import { options, unitOptions, units, vocabularies } from "../core/lookups.js";
import { banner, submit } from "../components/form.js";
import { toast } from "../components/toast.js";
import { alert, card, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const ROLES = [
  ["member", "Member of a unit"], ["steward", "Steward of a unit"], ["reviewer", "Reviewer"],
  ["governance", "Governance"], ["auditor", "Auditor"], ["admin", "Administrator"],
];

function connection(data) {
  if (!data.enabled) {
    return card({ title: "Connection", actions: pill("Not set up") },
      h("div", { class: "stack" },
        h("p", {}, "People sign in with a password that GovWren keeps. To let them sign in with the account they already have, connect an OpenID Connect provider."),
        h("ol", { class: "steps-list" },
          h("li", {}, "Register GovWren with your identity provider as a web application, with this redirect address:",
            h("div", {}, h("code", { class: "copyable" }, data.redirect_uri))),
          h("li", {}, "Put the provider's issuer address and the client ID it gives you in the ", h("code", {}, "[sso]"), " section of ", h("code", {}, "govwren.toml"), "."),
          h("li", {}, "Put the client secret in the environment variable that section names, and restart GovWren."),
          h("li", {}, "Come back here to say which groups give which roles."))));
  }
  const rows = [["Issuer", data.issuer], ["Client ID", data.client_id], ["Redirect address", data.redirect_uri],
    ["Groups are read from", `the “${data.groups_claim}” claim`],
    ["Passwords", data.local_sign_in ? "Anyone with a password may still use it" : "Kept for administrators only"],
    ["Joining existing accounts", data.trust_email ? "By the address the provider sends" : "Only by an address the provider marks as verified"]];
  return card({ title: "Connection", actions: pill("Connected", "ok"),
    footer: h("span", { class: "subtle" }, "These are set in govwren.toml on the server, not here.") },
  h("dl", { class: "facts" }, rows.map(([term, value]) => [h("dt", {}, term), h("dd", {}, value)])));
}

function mappings(data, reload) {
  const body = h("tbody");
  const rows = [];
  const add = (mapping = { claim_value: "", role: "member", org_unit_id: "", review_function: "" }) => {
    const value = h("input", { class: "input", value: mapping.claim_value, "aria-label": "Group or application role", placeholder: "As the provider sends it" });
    const role = h("select", { class: "select", "aria-label": "Role" },
      ROLES.map(([key, text]) => h("option", { value: key, selected: key === mapping.role }, text)));
    const unit = h("select", { class: "select", "aria-label": "Unit" },
      unitOptions(data.units.tree, { blank: "Choose a unit" }).map(([key, text]) => h("option", { value: key, selected: String(key) === String(mapping.org_unit_id ?? "") }, text)));
    const fn = h("select", { class: "select", "aria-label": "Review function" },
      options(data.vocab, "review_functions", { blank: "Choose a function" }).map(([key, text]) => h("option", { value: key, selected: key === (mapping.review_function ?? "") }, text)));
    const scope = h("td");
    const sync = () => scope.replaceChildren(...(["member", "steward"].includes(role.value) ? [unit]
      : role.value === "reviewer" ? [fn] : [h("span", { class: "subtle" }, "Everywhere")]));
    role.addEventListener("change", sync);
    sync();
    const row = { value, role, unit, fn };
    const tr = h("tr", {}, h("td", {}, value), h("td", {}, role), scope,
      h("td", { class: "cell-actions" }, iconButton("trash", "Remove this mapping", { onclick: () => {
        rows.splice(rows.indexOf(row), 1);
        tr.remove();
      } })));
    rows.push(row);
    body.append(tr);
  };
  data.mappings.forEach((mapping) => add(mapping));
  const problem = banner();
  const save = button("Save", { kind: "btn-primary" });
  save.addEventListener("click", async () => {
    const done = await submit({ button: save, banner: problem, run: () => put("/api/v1/sso/mappings", {
      mappings: rows.filter((row) => row.value.value.trim()).map((row) => ({
        claim_value: row.value.value.trim(), role: row.role.value,
        org_unit_id: ["member", "steward"].includes(row.role.value) && row.unit.value ? Number(row.unit.value) : null,
        review_function: row.role.value === "reviewer" ? row.fn.value || null : null })) }) });
    if (done) {
      toast("Saved. The roles apply the next time each person signs in.");
      reload();
    }
  });
  return card({ title: "Groups and roles",
    footer: h("div", { class: "row" }, save, button("Add a mapping", { iconName: "plus", onclick: () => add() })) },
  h("div", { class: "stack" },
    h("p", { class: "muted" }, "Each line gives a role here to everyone the provider says is in a group. Roles given this way are set again at every sign-in, so removing someone from the group removes the role. Roles given by hand under People are left alone."),
    problem,
    h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Group or application role"), h("th", { scope: "col" }, "Role in GovWren"),
        h("th", { scope: "col" }, "For"), h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Remove")))),
      body))));
}

export function adminSso(main) {
  return show(main, {
    title: "Single sign-on",
    load: async () => {
      const [sso, vocab, unitIndex] = await Promise.all([
        get("/api/v1/sso", null, { fresh: true }), vocabularies(), units()]);
      return { ...sso.data, vocab, units: unitIndex };
    },
    view: (data, reload) => h("div", { class: "stack-lg" },
      pageHeader({ title: "Single sign-on", lede: "Let people sign in with the account your organization already gives them." }),
      connection(data),
      data.enabled ? mappings(data, reload)
        : alert("info", icon("info"), h("div", {}, "Mappings from groups to roles can be set once the connection is in place."))),
  });
}
