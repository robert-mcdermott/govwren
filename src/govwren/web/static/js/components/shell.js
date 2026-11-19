// The app shell: sidebar, top bar, and the place pages are drawn.

import { del, get, post } from "../core/api.js";
import { h, icon, iconButton } from "../core/dom.js";
import { relative } from "../core/format.js";
import { wren } from "../core/icons.js";
import { onNavigate } from "../core/router.js";
import { can, session } from "../core/session.js";
import { mode, setMode } from "../core/prefs.js";
import { openAppearance } from "./appearance.js";
import { openPalette } from "./cmdk.js";
import { avatar } from "./ui.js";

// Each entry appears only for people who can use it. Sections arrive as the product grows.
export const NAV = [
  {
    items: [
      { href: "/", label: "Home", iconName: "home", exact: true },
      { href: "/catalog", label: "Catalog", iconName: "catalog" },
    ],
  },
  {
    heading: "Inventory",
    items: [
      { href: "/use-cases", label: "Use cases", iconName: "use_case" },
      { href: "/systems", label: "AI systems", iconName: "system" },
      { href: "/vendors", label: "Vendors", iconName: "vendor" },
    ],
  },
  {
    heading: "Governance",
    items: [
      { href: "/dashboard", label: "Dashboard", iconName: "dashboard", when: "read_all" },
      { href: "/reviews", label: "Reviews", iconName: "shield", when: ["review", "read_all"] },
    ],
  },
  {
    heading: "Admin",
    items: [
      { href: "/admin/people", label: "People", iconName: "people", when: "admin" },
      { href: "/admin/units", label: "Units", iconName: "units", when: "admin" },
      { href: "/admin/appearance", label: "Appearance", iconName: "appearance", when: "admin" },
      { href: "/admin/sso", label: "Single sign-on", iconName: "key", when: "admin" },
    ],
  },
];

export function visibleNav() {
  const may = (when) => !when || [when].flat().some((permission) => can(permission));
  return NAV.map((group) => ({ ...group, items: group.items.filter((item) => may(item.when)) }))
    .filter((group) => group.items.length);
}

export function brand(meta, { large = false } = {}) {
  const b = meta.branding;
  const name = b.product_name;
  if (b.logo_light) {
    return [
      h("img", { class: "brand-logo only-light", src: b.logo_light, alt: name }),
      h("img", { class: "brand-logo only-dark", src: b.logo_dark || b.logo_light, alt: "" }),
    ];
  }
  // "GovWren" is set as Gov + Wren; any other name is shown as it is.
  const words = name === "GovWren" ? ["Gov", h("strong", {}, "Wren")] : [h("strong", {}, name)];
  return [wren(large ? "brand-mark" : "brand-mark"), h("span", { class: "brand-name" }, words)];
}

export async function signOut() {
  try {
    await del("/api/v1/session");
  } finally {
    window.location.assign("/");
  }
}

export function commands(meta) {
  const pages = visibleNav().flatMap((group) => group.items.map((item) => ({
    label: item.label, hint: group.heading ?? "Page", iconName: item.iconName, href: item.href,
  })));
  return [
    ...pages,
    { label: "New request", hint: "Action", iconName: "plus", href: "/requests/new", keywords: "ask may i use submit intake" },
    { label: "Your account", hint: "Page", iconName: "user", href: "/account", keywords: "profile password" },
    { label: "Appearance…", hint: "Action", iconName: "appearance", run: () => openAppearance(meta), keywords: "theme palette colors" },
    { label: mode() === "dark" ? "Switch to light" : "Switch to dark", hint: "Action",
      iconName: mode() === "dark" ? "sun" : "moon", run: () => setMode(mode() === "dark" ? "light" : "dark"), keywords: "theme mode" },
    { label: "Sign out", hint: "Action", iconName: "logout", run: signOut },
  ];
}

function bell() {
  const anchor = h("div", { class: "menu-anchor" });
  const count = h("span", { class: "badge bell-count", hidden: true });
  let menu = null;
  const close = () => {
    menu?.remove();
    menu = null;
    toggle.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", outside, true);
  };
  const outside = (event) => {
    if (!anchor.contains(event.target)) close();
  };
  const refresh = async () => {
    try {
      const { unread } = (await get("/api/v1/notifications", null, { fresh: true })).data;
      count.hidden = !unread;
      count.textContent = unread > 9 ? "9+" : String(unread);
      toggle.setAttribute("aria-label", unread ? `Notices, ${unread} unread` : "Notices");
    } catch {
      // the bell is a convenience; the page works without it
    }
  };
  const toggle = h("button", { type: "button", class: "icon-button bell", "aria-haspopup": "menu", "aria-expanded": "false", "aria-label": "Notices",
    onclick: async () => {
      if (menu) {
        close();
        return;
      }
      const { items } = (await get("/api/v1/notifications", null, { fresh: true })).data;
      menu = h("div", { class: "menu notices", role: "menu" },
        h("div", { class: "menu-head cell-main" }, "Notices"),
        items.length ? items.map((item) => h("a", { class: `menu-item notice${item.read ? "" : " notice-new"}`, role: "menuitem", href: item.href ?? "/", onclick: close },
          h("div", { class: "grow" }, h("div", {}, item.title), h("div", { class: "cell-sub" }, relative(item.created_at)))))
          : h("div", { class: "palette-empty" }, "Nothing yet."));
      anchor.append(menu);
      toggle.setAttribute("aria-expanded", "true");
      document.addEventListener("click", outside, true);
      if (items.some((item) => !item.read)) {
        await post("/api/v1/notifications/read", {});
        refresh();
      }
    } }, icon("bell"), count);
  anchor.append(toggle);
  refresh();
  window.addEventListener("govwren:changed", (event) => {
    if (!String(event.detail?.path).includes("/notifications")) refresh();
  });
  return anchor;
}

function userMenu(meta) {
  const me = session();
  const anchor = h("div", { class: "menu-anchor" });
  let menu = null;
  const close = () => {
    menu?.remove();
    menu = null;
    toggle.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", outside, true);
    document.removeEventListener("keydown", onKey, true);
  };
  const outside = (event) => {
    if (!anchor.contains(event.target)) close();
  };
  const onKey = (event) => {
    if (event.key === "Escape") {
      close();
      toggle.focus();
    }
  };
  const item = (label, iconName, attrs) => h(attrs.href ? "a" : "button",
    { class: "menu-item", role: "menuitem", ...(attrs.href ? {} : { type: "button" }), ...attrs,
      onclick: (event) => {
        close();
        attrs.onclick?.(event);
      } }, icon(iconName), label);
  const toggle = h("button", { type: "button", class: "icon-button", "aria-haspopup": "menu", "aria-expanded": "false",
    "aria-label": `Account menu for ${me.account.name}`, title: me.account.name,
    onclick: () => {
      if (menu) {
        close();
        return;
      }
      menu = h("div", { class: "menu", role: "menu" },
        h("div", { class: "menu-head" }, h("div", { class: "cell-main" }, me.account.name),
          h("div", { class: "cell-sub" }, me.account.email)),
        h("div", { class: "menu-sep" }),
        item("Your account", "user", { href: "/account" }),
        item("Appearance…", "appearance", { onclick: () => openAppearance(meta) }),
        h("div", { class: "menu-sep" }),
        item("Sign out", "logout", { onclick: signOut }));
      anchor.append(menu);
      toggle.setAttribute("aria-expanded", "true");
      document.addEventListener("click", outside, true);
      document.addEventListener("keydown", onKey, true);
      menu.querySelector(".menu-item")?.focus();
    } }, avatar(me.account.name));
  anchor.append(toggle);
  return anchor;
}

/** Draw the shell into root and return the element pages are drawn in. */
export function mountShell(root, meta) {
  const main = h("main", { id: "main", tabindex: "-1" });
  const nav = h("nav", { class: "nav", "aria-label": "Main" });
  const brandLink = h("a", { class: "brand", href: "/", "aria-label": `${meta.branding.product_name} home` }, brand(meta));
  const shell = h("div", { class: "shell" });

  const drawNav = () => {
    const path = window.location.pathname;
    nav.replaceChildren(...visibleNav().map((group) => h("div", { class: "nav-group" },
      group.heading ? h("div", { class: "nav-heading" }, group.heading) : null,
      h("ul", {}, group.items.map((item) => {
        const here = item.exact ? path === item.href : path === item.href || path.startsWith(`${item.href}/`);
        return h("li", {}, h("a", { class: "nav-link", href: item.href, "aria-current": here ? "page" : null },
          icon(item.iconName), item.label));
      })))));
  };
  onNavigate(() => {
    drawNav();
    shell.removeAttribute("data-nav");
  });
  drawNav();

  const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
  const search = h("button", { type: "button", class: "search-button", "aria-label": "Open the command palette",
    onclick: () => openPalette(commands(meta)) },
  icon("search", "icon icon-sm"), h("span", {}, "Go to…"), h("kbd", {}, isMac ? "⌘K" : "Ctrl K"));

  const powered = meta.branding.show_powered_by && meta.branding.product_name !== "GovWren"
    ? h("div", { class: "powered" }, "Powered by ", h("a", { href: "https://github.com/robert-mcdermott/govwren", target: "_blank", rel: "noopener" }, "GovWren"))
    : h("div", { class: "powered" }, meta.branding.organization_name || `Version ${meta.version}`);

  shell.append(
    h("aside", { class: "sidebar" }, brandLink, nav, h("div", { class: "sidebar-foot" }, powered)),
    h("div", { class: "main-column" },
      h("header", { class: "topbar" },
        iconButton("menu", "Menu", { class: "icon-button menu-toggle", onclick: () => {
          shell.setAttribute("data-nav", shell.getAttribute("data-nav") === "open" ? "" : "open");
        } }),
        search,
        h("div", { class: "spacer row-sm" },
          meta.demo ? h("span", { class: "demo-flag", title: "A fictional organization. Nothing here is real." }, "Demo data") : null,
          h("a", { class: "btn btn-primary new-request", href: "/requests/new" }, icon("plus", "icon icon-sm"), h("span", {}, "New request")),
          bell(),
          iconButton("appearance", "Appearance", { onclick: () => openAppearance(meta) }),
          userMenu(meta))),
      main));
  shell.addEventListener("click", (event) => {
    if (event.target === shell) shell.removeAttribute("data-nav"); // the dimmed area beside the open menu
  });
  root.replaceChildren(shell);
  return { main, redrawBrand: (next) => brandLink.replaceChildren(...brand(next)) };
}
