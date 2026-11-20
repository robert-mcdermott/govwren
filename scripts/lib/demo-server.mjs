// Build a fresh demo organization in a temporary directory and serve it, for the audit and
// the screenshot capture. Nothing here touches an installation you care about.

import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

export async function startDemo({ port = 8019, seed = 1, env = {} } = {}) {
  const home = mkdtempSync(join(tmpdir(), "govwren-demo-"));
  const built = spawnSync("uv", ["run", "govwren", "demo", home, "--seed", String(seed), "--port", String(port)],
    { cwd: ROOT, encoding: "utf8" });
  if (built.status !== 0) throw new Error(`The demo did not build:\n${built.stdout}${built.stderr}`);
  // To audit or capture with a brand of your own, name a file that holds a [branding] section
  // (and nothing else) in GOVWREN_DEMO_BRANDING. Give its images as full paths.
  if (process.env.GOVWREN_DEMO_BRANDING) {
    appendFileSync(join(home, "govwren.toml"), `\n${readFileSync(process.env.GOVWREN_DEMO_BRANDING, "utf8")}\n`);
  }
  const server = spawn("uv", ["run", "govwren", "--config", join(home, "govwren.toml"), "serve"],
    { cwd: ROOT, stdio: "ignore", detached: true, env: { ...process.env, ...env } }); // its own group, so that stopping it stops the server it starts
  const kill = () => { try { process.kill(-server.pid); } catch { /* already gone */ } };
  const base = `http://127.0.0.1:${port}`;
  const until = Date.now() + 30000;
  for (;;) {
    try {
      if ((await fetch(`${base}/api/v1/health/ready`)).ok) break;
    } catch { /* not up yet */ }
    if (Date.now() > until) { kill(); throw new Error("The demo server did not start"); }
    await new Promise((r) => setTimeout(r, 200));
  }
  return { base, stop() { kill(); rmSync(home, { recursive: true, force: true }); } };
}

/** Sign the page in as one of the demo's sample people, by the key the demo gives them. */
export async function signInAs(page, base, key) {
  await page.goto(`${base}/api/v1/meta`); // any page of the demo: the request must come from it
  if (key == null) {
    await page.evaluate(`fetch("/api/v1/session", { method: "DELETE" }).then(() => true)`);
    return;
  }
  const ok = await page.evaluate(`(async () => {
    const meta = (await (await fetch("/api/v1/meta")).json()).data;
    const person = meta.demo.accounts.find((p) => p.key === ${JSON.stringify(key)});
    const done = await fetch("/api/v1/session/demo", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: person.email }) });
    return done.ok;
  })()`);
  if (!ok) throw new Error(`Could not sign in as ${key}`);
}
