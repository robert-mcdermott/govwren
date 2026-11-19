// The web app's entry point: find out about the product and who is signed in, then draw.

import { get, peek } from "./core/api.js";
import { h } from "./core/dom.js";
import { apply, setOrganizationPalette } from "./core/prefs.js";
import { fallback, route, start } from "./core/router.js";
import { can, setSession } from "./core/session.js";
import { openPalette } from "./components/cmdk.js";
import { commands, findRecords, mountShell } from "./components/shell.js";
import { emptyState } from "./components/ui.js";
import { setProduct, setTitle } from "./pages/page.js";

apply(); // paint with the remembered mode and palette before anything else
const root = document.getElementById("app");

function applyBranding(meta) {
  setProduct(meta.branding.product_name);
  setOrganizationPalette(meta.branding.palette);
  document.getElementById("favicon").href = meta.branding.favicon || "/img/wren-mark.svg";
}

async function boot() {
  let meta;
  try {
    meta = (await get("/api/v1/meta", null, { fresh: true })).data;
  } catch {
    root.replaceChildren(h("div", { class: "page" }, emptyState({ iconName: "alert",
      title: "The server is not responding", text: "Check that it is running, then reload this page." })));
    return;
  }
  applyBranding(meta);

  let me = null;
  try {
    me = (await peek("/api/v1/session")).data;
  } catch (error) {
    if (error.status !== 401) throw error;
  }
  if (!me) {
    const path = window.location.pathname + window.location.search;
    if (window.location.pathname !== "/sign-in") {
      history.replaceState({}, "", path === "/" ? "/sign-in" : `/sign-in?next=${encodeURIComponent(path)}`);
    }
    (await import("./pages/sign-in.js")).signIn(root, meta);
    return;
  }
  setSession(me);
  if (window.location.pathname === "/sign-in") history.replaceState({}, "", "/");

  const { main, redrawBrand } = mountShell(root, meta);
  const page = (file, name, ...extra) => async (params) => (await import(`./pages/${file}.js`))[name](main, ...extra, params);

  route("/", page("home", "home", meta));
  route("/account", page("account", "account", meta));
  route("/reviews", page("reviews", "reviews"));
  route("/catalog", page("catalog", "catalog"));
  route("/evidence", page("evidence", "evidencePage"));
  route("/assessments/:ref/:template", page("assessment", "assessmentPage"));
  route("/units/:id/report", page("portfolio", "unitReportPage"));
  route("/dossier/:ref", page("dossier", "dossierPage"));
  route("/my-unit", page("portfolio", "myUnit"));
  route("/policies", page("policies", "policyList"));
  route("/policies/:ref", page("policies", "policyPage"));
  route("/controls", page("controls", "controlList"));
  route("/controls/:key", page("controls", "controlPage"));
  route("/risks", page("risks", "riskList"));
  route("/risks/:ref", page("risks", "riskPage"));
  route("/incidents", page("incidents", "incidentList"));
  route("/incidents/:ref", page("incidents", "incidentPage"));
  route("/actions", page("actions", "actionList"));
  route("/exceptions", page("exceptions", "exceptionList"));
  route("/exceptions/:ref", page("exceptions", "exceptionPage"));
  route("/campaigns", page("campaigns", "campaignList"));
  route("/campaigns/:ref", page("campaigns", "campaignPage"));
  if (can("read_all")) route("/duplicates", page("duplicates", "duplicatesPage"));
  if (can("configure")) route("/program", page("program", "programPage"));
  if (can("read_all")) route("/dashboard", page("dashboard", "dashboard"));
  if (can("read_all")) {
    route("/measures", page("measures", "measuresPage"));
    route("/portfolio", page("portfolio", "portfolioPage"));
    route("/frameworks", page("frameworks", "frameworkList"));
    route("/frameworks/:key", page("frameworks", "frameworkPage"));
    route("/sessions", page("sessions", "sessionList"));
    route("/sessions/:ref", page("sessions", "sessionPage"));
    route("/spot-checks", page("spot-checks", "spotChecks"));
  }
  route("/requests/new", page("intake", "intake"));
  route("/use-cases/:ref/request", page("intake", "intake"));
  for (const [type, path] of [["use_case", "use-cases"], ["system", "systems"], ["model", "models"], ["dataset", "datasets"], ["vendor", "vendors"]]) {
    route(`/${path}`, page("records", "recordList", type));
    route(`/${path}/:ref`, page("record", "recordPage", type));
  }
  if (can("admin")) {
    route("/admin/people", page("admin-people", "adminPeople"));
    route("/admin/units", page("admin-units", "adminUnits"));
    route("/admin/appearance", page("admin-appearance", "adminAppearance"));
    route("/admin/sso", page("admin-sso", "adminSso"));
    route("/admin/email", page("admin-email", "adminEmail"));
    route("/admin/jobs", page("admin-jobs", "adminJobs"));
  }
  fallback(page("not-found", "notFound"));

  window.addEventListener("govwren:signed-out", () => window.location.reload());
  window.addEventListener("govwren:branding", async () => {
    const next = (await get("/api/v1/meta", null, { fresh: true })).data;
    Object.assign(meta, next);
    applyBranding(meta);
    redrawBrand(meta);
    const theme = document.getElementById("theme");
    theme.href = `/theme.css?v=${Date.now()}`;
    setTitle(document.querySelector("h1")?.textContent ?? "");
  });
  document.addEventListener("keydown", (event) => {
    const typing = event.target.closest?.("input, textarea, select, [contenteditable]");
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openPalette(commands(meta), findRecords);
    } else if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      openPalette(commands(meta), findRecords);
    }
  });
  await start();
}

boot();
