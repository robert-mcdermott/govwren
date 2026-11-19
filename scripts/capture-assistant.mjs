#!/usr/bin/env node
// Screenshots of the optional assistant, which the ordinary demo does not have switched on.
// Starts a stand-in model server that gives fixed answers, starts a demo configured to use
// it, and walks the two places the assistant appears. This also proves the whole path: the
// page, GovWren's API, and a real request to a model server.
//
//   node scripts/capture-assistant.mjs

import { createServer } from "node:http";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { openBrowser } from "./lib/browser.mjs";
import { signInAs, startDemo } from "./lib/demo-server.mjs";

const OUT = process.env.OUT ?? join(resolve(dirname(fileURLToPath(import.meta.url)), ".."), "docs", "images");
const ANSWERS = { name: "Summarizing recorded seminars", purpose: "Turn our recorded weekly seminars into short written summaries that the lab can search.",
  domain: "research", stage: "proposed", data_class: "internal", impact: "none" };
// The stand-in "summarizes" by restating what it was sent, so that the picture is true to the packet.
function summarize(packet) {
  const said = (question) => packet.answers.find((item) => item.question.startsWith(question))?.answer;
  const reviews = packet.reviews.map((review) => `${review.function}: ${review.finding ? String(review.finding).replace(/_/g, " ") : "not yet reviewed"}`);
  return [`- The request is "${packet.request}", at tier ${packet.tier}.`,
    `- It involves ${said("What is the most sensitive class") ?? "unstated"} data: ${[said("Does it involve any of these kinds")].flat().filter(Boolean).join(", ") || "no special kinds"}.`,
    `- People affected: ${[said("Who could be affected")].flat().filter(Boolean).join(", ") || "not stated"}.`,
    `- Reviews so far: ${reviews.join("; ") || "none required"}.`].join("\n");
}

const seen = [];
const model = createServer((request, response) => {
  let body = "";
  request.on("data", (chunk) => { body += chunk; });
  request.on("end", () => {
    const asked = JSON.parse(body);
    seen.push(asked);
    const drafting = asked.messages[0].content.includes("fill in a form");
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ choices: [{ message: { role: "assistant", content: drafting ? JSON.stringify(ANSWERS) : summarize(JSON.parse(asked.messages[1].content)) } }] }));
  });
});
await new Promise((ready) => model.listen(8038, "127.0.0.1", ready));

const demo = await startDemo({ port: 8037, env: {
  GOVWREN_ASSISTANT_URL: "http://127.0.0.1:8038/v1", GOVWREN_ASSISTANT_MODEL: "local-model", GOVWREN_ASSISTANT_MAX_DATA_CLASS: "restricted" } });
const page = await openBrowser();
const failures = [];
const expect = (ok, what) => { if (!ok) failures.push(what); };
try {
  await page.size(1280, 800);
  await page.scheme("light");
  await signInAs(page, demo.base, "member");
  await page.goto(`${demo.base}/requests/new`);
  await page.settled();
  await page.evaluate(`(() => { const box = document.querySelector("textarea"); box.value = "We record our weekly seminars and would like short written summaries of each one."; return true; })()`);
  await page.evaluate(`[...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Suggest answers").click()`);
  await page.waitFor(`document.body.innerText.includes("answers were suggested")`, "the suggested answers");
  expect(await page.evaluate(`[...document.querySelectorAll("input")].some((i) => i.value === "Summarizing recorded seminars")`), "the form was not filled in");
  await page.screenshot(join(OUT, "assistant-draft-light.webp"));

  await signInAs(page, demo.base, "governance");
  await page.goto(`${demo.base}/reviews`);
  await page.settled();
  const ref = await page.evaluate(`fetch("/api/v1/reviews").then((r) => r.json()).then((j) => j.data[0].ref)`);
  await page.goto(`${demo.base}/reviews?open=${ref}`);
  await page.settled();
  await page.evaluate(`[...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Summarize with the assistant").click()`);
  await page.waitFor(`document.body.innerText.includes("Written by an AI assistant")`, "the summary");
  await page.evaluate(`[...document.querySelectorAll("h2")].find((h) => h.textContent.trim() === "Summary").scrollIntoView({ block: "start" }); window.scrollBy(0, -90)`);
  await page.screenshot(join(OUT, "assistant-summary-light.webp"));

  await signInAs(page, demo.base, "auditor");
  await page.goto(`${demo.base}/assistant`);
  await page.settled();
  expect(await page.evaluate(`document.body.innerText.includes("Summary of ${ref}")`), "the exchange is not in the log");
  await page.evaluate(`document.querySelector("details").open = true`);
  await page.screenshot(join(OUT, "assistant-log-light.webp"));
  expect(seen.length === 2 && seen[0].model === "local-model", `the model server was asked ${seen.length} times`);
} catch (error) {
  const where = await page.evaluate(`location.pathname + " :: " + (document.querySelector("main")?.innerText ?? "").slice(0, 200)`).catch(() => "?");
  failures.push(`${error.message} (${where})`);
} finally {
  await page.close();
  demo.stop();
  model.close();
}
for (const failure of failures) console.log(`✗ ${failure}`);
console.log(failures.length ? `\n${failures.length} problems.` : "\n3 screenshots, and the assistant answered through the whole path.");
process.exit(failures.length ? 1 : 0);
