// Dates are shown as the day they name, and every script in the web app parses as a module.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { date } from "../../src/govwren/web/static/js/core/format.js";

const ROOT = fileURLToPath(new URL("../../src/govwren/web/static/js", import.meta.url));

test("a day with no time is the same day in every time zone", () => {
  const shown = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(2026, 6, 1));
  assert.equal(date("2026-07-01"), shown);
  assert.equal(date(""), "");
  assert.equal(date(null), "");
});

test("every script parses as a module", () => {
  const scripts = readdirSync(ROOT, { recursive: true }).filter((name) => name.endsWith(".js"));
  assert.ok(scripts.length > 40);
  for (const name of scripts) {
    const checked = spawnSync(process.execPath, ["--check", "--input-type=module"], { input: readFileSync(join(ROOT, name)), encoding: "utf8" });
    assert.equal(checked.status, 0, `${name}\n${checked.stderr}`);
  }
});
