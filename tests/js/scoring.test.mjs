// The browser's preview of which questions show and what tier results must agree with the
// server on every shared case, for the default program.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { assess, route, showing } from "../../src/govwren/web/static/js/core/scoring.js";

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const pack = read("../../src/govwren/resources/packs/default-program.json");
const cases = read("../parity/scoring.json");

for (const { name, answers, expect } of cases) {
  test(name, () => {
    const seen = showing(pack.forms[0], answers);
    assert.deepEqual(seen.keys, expect.showing);
    assert.deepEqual(seen.kept, expect.kept);
    const result = assess(pack.scoring_model, seen.kept);
    assert.deepEqual(result, expect.assessment);
    assert.deepEqual(route(pack.review, result.final_tier, seen.kept, result.stops), expect.routing);
  });
}
