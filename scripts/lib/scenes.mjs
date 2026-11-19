// The screens the documentation shows and the accessibility audit walks. One line each:
// a name, who is signed in (a key from the demo's sample people), a path, and optionally a
// step to run in the page first (a JavaScript expression), such as opening a drawer.
//
// A path may be a function of the page, for addresses that depend on what the demo holds.

const first = (api, pick = "(rows) => rows[0].ref") => async (page) => page.evaluate(
  `fetch(${JSON.stringify(api)}).then((r) => r.json()).then((body) => (${pick})(body.data))`);
const click = (text) => `[...document.querySelectorAll("button, a")].find((el) => el.textContent.trim() === ${JSON.stringify(text)})?.click()`;

export const SCENES = [
  { name: "home-member", as: "member", path: "/" },
  { name: "home-governance", as: "governance", path: "/" },
  { name: "catalog", as: "member", path: "/catalog" },
  { name: "catalog-register", as: "member", path: "/catalog?q=brightfen", step: click("Register my use") },
  { name: "intake", as: "member", path: "/requests/new" },
  { name: "intake-draft", as: "member",
    path: async (page) => `/use-cases/${await first("/api/v1/use-cases?mine=true&status=draft")(page)}/request` },
  { name: "use-cases", as: "governance", path: "/use-cases" },
  { name: "use-case", as: "governance",
    path: async (page) => `/use-cases/${await first("/api/v1/use-cases?q=study+visit")(page)}` },
  { name: "use-case-history", as: "governance",
    path: async (page) => `/use-cases/${await first("/api/v1/use-cases?q=study+visit")(page)}?tab=history` },
  { name: "use-case-answers", as: "governance",
    path: async (page) => `/use-cases/${await first("/api/v1/use-cases?q=study+visit")(page)}?tab=answers` },
  { name: "systems", as: "governance", path: "/systems" },
  { name: "system", as: "governance",
    path: async (page) => `/systems/${await first("/api/v1/systems?q=brightfen+assistant")(page)}` },
  { name: "agent", as: "governance",
    path: async (page) => `/systems/${await first("/api/v1/systems?q=deskhand")(page)}` },
  { name: "models", as: "governance", path: "/models" },
  { name: "model", as: "governance",
    path: async (page) => `/models/${await first("/api/v1/models?q=variant+effect")(page)}` },
  { name: "model-open", as: "member",
    path: async (page) => `/models/${await first("/api/v1/models?q=wrenlet+70b")(page)}` },
  { name: "model-add", as: "governance", path: "/models", step: click("Add a model") },
  { name: "datasets", as: "governance", path: "/datasets" },
  { name: "dataset", as: "governance",
    path: async (page) => `/datasets/${await first("/api/v1/datasets?q=controlled-access+cohort")(page)}` },
  { name: "vendors", as: "governance", path: "/vendors" },
  { name: "vendor", as: "governance",
    path: async (page) => `/vendors/${await first("/api/v1/vendors?q=brightfen")(page)}` },
  { name: "reviews", as: "governance", path: "/reviews" },
  { name: "reviews-reviewer", as: "privacy", path: "/reviews" },
  { name: "dashboard", as: "governance", path: "/dashboard" },
  { name: "people", as: "admin", path: "/admin/people" },
  { name: "units", as: "admin", path: "/admin/units" },
  { name: "appearance", as: "admin", path: "/admin/appearance" },
  { name: "single-sign-on", as: "admin", path: "/admin/sso" },
  { name: "account", as: "member", path: "/account" },
  { name: "auditor-use-cases", as: "auditor", path: "/use-cases" },
];
