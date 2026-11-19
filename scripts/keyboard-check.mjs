#!/usr/bin/env node
// The keyboard and assistive-technology check. It opens every scene in a fresh demo
// organization and does what a person without a mouse, or with a screen reader, would:
//
//   - Tab from the top. The first stop is the skip link, and it can be seen.
//   - Tab through the whole page. Every stop can be seen, shows where focus is, and the
//     walk reaches every control without getting stuck.
//   - In a dialog, focus starts inside it and stays inside it, Escape closes it, and focus
//     goes back to where it came from.
//   - Read the page as assistive technology is given it: the landmarks are there, there is
//     one main heading, every control has a role and a name, and every table has headers.
//
//   node scripts/keyboard-check.mjs            every scene
//   node scripts/keyboard-check.mjs catalog    scenes whose name contains "catalog"
//
// It exits with 1 if anything is found. It does not replace listening to the pages with a
// screen reader, which the release checklist still asks a person to do.

import { openBrowser } from "./lib/browser.mjs";
import { signInAs, startDemo } from "./lib/demo-server.mjs";
import { SCENES } from "./lib/scenes.mjs";

const MAX_TABS = 1200;

const FOCUS = String.raw`(() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const box = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  const ringed = (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== "none";
  const text = (el.getAttribute("aria-label") || el.textContent || el.value || el.name || el.type || "").trim().replace(/\s+/g, " ").slice(0, 40);
  if (!el.dataset.kbd) el.dataset.kbd = String(Math.random()).slice(2);
  return { id: el.dataset.kbd, tag: el.tagName.toLowerCase(), text, seen: box.width > 0 && box.height > 0 && style.visibility === "visible",
    ringed, inDialog: Boolean(el.closest("[role=dialog], dialog")), skip: /skip/i.test(el.textContent || "") };
})()`;

// Begin where a person arriving at the page begins: before everything.
const START = String.raw`(() => {
  document.activeElement?.blur();
  getSelection().removeAllRanges();
  document.body.setAttribute("tabindex", "-1");
  document.body.focus();
  document.body.removeAttribute("tabindex");
  scrollTo(0, 0);
  return true;
})()`;

const TABBABLE = String.raw`(() => {
  const scope = document.querySelector("[role=dialog], dialog[open]") || document;
  const all = [...scope.querySelectorAll("a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex]")];
  return all.filter((el) => {
    if (el.disabled || el.getAttribute("tabindex") === "-1" || el.closest("[hidden], [inert]")) return false;
    if (el.closest("details:not([open])") && el.tagName !== "SUMMARY") return false;
    if (el.type === "radio" && el.name && !el.checked && scope.querySelector('input[type=radio][name="' + el.name + '"]:checked')) return false;
    if (el.type === "radio" && el.name && !el.checked && scope.querySelector('input[type=radio][name="' + el.name + '"]') !== el) return false;
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility === "visible" && (box.width > 0 || box.height > 0 || el.classList.contains("skip-link") || el.closest(".sr-only"));
  }).length;
})()`;

async function walk(page, findings, scene, inDialog, plain = false) {
  const seen = new Map();
  let stuck = 0;
  let away = 0;
  let last = null;
  if (!inDialog) await page.evaluate(START);
  for (let press = 0; press < MAX_TABS; press += 1) {
    await page.key("Tab");
    const at = await page.evaluate(FOCUS);
    if (!at) {
      away += 1; // focus is on the browser's own controls, between the last stop and the first
      if (away > 3) break;
      continue;
    }
    away = 0;
    if (at.id === last) {
      stuck += 1; // a date field has a stop for each of its parts
      if (stuck > 8) break;
      continue;
    }
    stuck = 0;
    last = at.id;
    if (seen.has(at.id)) break; // back at the start: the whole page was walked
    seen.set(at.id, at);
    if (seen.size === 1 && !inDialog && !at.skip && !plain) findings.push(`${scene}: the first stop is not the skip link (${at.tag} "${at.text}")`);
    if (!at.seen) findings.push(`${scene}: focus goes somewhere that cannot be seen (${at.tag} "${at.text}")`);
    else if (!at.ringed) findings.push(`${scene}: nothing shows where focus is (${at.tag} "${at.text}")`);
    if (inDialog && !at.inDialog) findings.push(`${scene}: focus left the open dialog (${at.tag} "${at.text}")`);
  }
  const expected = await page.evaluate(TABBABLE);
  if (seen.size < expected) findings.push(`${scene}: the keyboard reaches ${seen.size} of ${expected} controls`);
  return seen.size;
}

function readTree(nodes, findings, scene) {
  const live = nodes.filter((node) => !node.ignored);
  const role = (node) => node.role?.value;
  const name = (node) => (node.name?.value ?? "").trim();
  const count = (wanted) => live.filter((node) => role(node) === wanted).length;
  if (count("main") !== 1) findings.push(`${scene}: assistive technology finds ${count("main")} main landmarks`);
  if (live.filter((node) => role(node) === "heading" && node.properties?.some((p) => p.name === "level" && p.value.value === 1)).length !== 1) {
    findings.push(`${scene}: there is not exactly one level-one heading`);
  }
  for (const node of live) {
    if (["button", "link", "textbox", "combobox", "checkbox", "radio", "searchbox", "spinbutton", "tab", "menuitem", "switch"].includes(role(node)) && !name(node)) {
      findings.push(`${scene}: a ${role(node)} has no name for a screen reader`);
    }
    if (role(node) === "image" && !name(node)) findings.push(`${scene}: an image has no name`);
  }
  const tables = count("table") + count("grid");
  if (tables && !count("columnheader")) findings.push(`${scene}: a table has no column headers`);
  return live.length;
}

const words = process.argv.slice(2);
const scenes = SCENES.filter((scene) => !words.length || words.some((word) => scene.name.includes(word)));
const demo = await startDemo();
const browser = await openBrowser();
const findings = [];
let stops = 0;
try {
  await browser.size(1280, 800);
  await browser.scheme("light");
  let signedInAs;
  for (const scene of scenes) {
    if (scene.as !== signedInAs) {
      await signInAs(browser, demo.base, scene.as ?? null);
      signedInAs = scene.as;
    }
    await browser.goto(demo.base + (typeof scene.path === "function" ? await scene.path(browser) : scene.path));
    await browser.settled();
    const before = findings.length;
    if (scene.step) {
      const opener = await browser.evaluate(`(() => { ${scene.step}; return true; })()`);
      await new Promise((resolve) => setTimeout(resolve, 400));
      const open = await browser.evaluate(`Boolean(document.querySelector("[role=dialog], dialog[open]"))`);
      if (opener && open) {
        const first = await browser.evaluate(FOCUS);
        if (!first?.inDialog) findings.push(`${scene.name}: the dialog opens without taking focus`);
        stops += await walk(browser, findings, scene.name, true);
        readTree(await browser.accessibilityTree(), findings, scene.name);
        await browser.key("Escape");
        await new Promise((resolve) => setTimeout(resolve, 300));
        if (await browser.evaluate(`Boolean(document.querySelector("[role=dialog], dialog[open]"))`)) findings.push(`${scene.name}: Escape does not close the dialog`);
        else if (!(await browser.evaluate(FOCUS))) findings.push(`${scene.name}: focus is lost when the dialog closes`);
      } else {
        stops += await walk(browser, findings, scene.name, false);
        readTree(await browser.accessibilityTree(), findings, scene.name);
      }
    } else {
      // A page of the published register is a short document outside the app, with no menu to skip.
      stops += await walk(browser, findings, scene.name, false, String(scene.path).startsWith("/api/"));
      readTree(await browser.accessibilityTree(), findings, scene.name);
    }
    console.log(`${findings.length === before ? "✓" : "✗"} ${scene.name}`);
  }
} catch (error) {
  findings.push(`The check stopped: ${error.message}`);
} finally {
  await browser.close();
  demo.stop();
}
for (const finding of findings) console.log(`  ${finding}`);
console.log(findings.length ? `\n${findings.length} findings.` : `\nNo findings in ${scenes.length} scenes, over ${stops} keyboard stops.`);
process.exit(findings.length ? 1 : 0);
