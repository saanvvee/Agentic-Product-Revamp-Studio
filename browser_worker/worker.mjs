// Browser worker for revamp/tools/browser.py.
//
// Why Node: the Python playwright package cannot be installed on the campus network
// (PyPI is TLS-intercepted), while npm works. Python's playwright is itself a wrapper
// around this same Node driver, so nothing is lost.
//
// Protocol: one JSON job on stdin, one JSON result on stdout. Errors -> {"error": "..."}.
//   {"op": "axe",     "urls": [...], "tags": [...]}
//   {"op": "journey", "urls": [...], "shotDir": "..."}
//   {"op": "text",    "url": "..."}

import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const AXE_SOURCE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const VIEWPORT = { width: 1280, height: 800 };
const TIMEOUT = 60_000;

async function readJob() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function axe(page, job) {
  const out = [];
  for (const url of job.urls) {
    const resp = await page.goto(url, { waitUntil: "load", timeout: TIMEOUT });
    await page.addScriptTag({ content: AXE_SOURCE });
    const result = await page.evaluate(
      (tags) => axe.run(document, { runOnly: { type: "tag", values: tags } }),
      job.tags,
    );
    out.push({ url, status: resp ? resp.status() : 0, result });
  }
  return out;
}

async function journey(page, job) {
  const out = [];
  let consoleErrors = [];
  let failed = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("requestfailed", (r) => failed.push(r.url()));
  for (const [i, url] of job.urls.entries()) {
    consoleErrors = [];
    failed = [];
    const t0 = Date.now();
    let status = 0;
    let error = null;
    try {
      const resp = await page.goto(url, { waitUntil: "load", timeout: TIMEOUT });
      status = resp ? resp.status() : 0;
    } catch (e) {
      error = String(e).slice(0, 300);
    }
    const loadMs = Date.now() - t0;
    const shot = path.join(job.shotDir, `${String(i + 1).padStart(2, "0")}.png`);
    await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
    out.push({ url, status, loadMs, error, consoleErrors: [...consoleErrors],
               failedRequests: [...failed], screenshot: shot });
  }
  return out;
}

async function text(page, job) {
  await page.goto(job.url, { waitUntil: "networkidle", timeout: TIMEOUT });
  return { url: job.url, text: await page.innerText("body") };
}

const OPS = { axe, journey, text };

const job = await readJob();
const browser = await chromium.launch({ headless: true });
try {
  const page = await (await browser.newContext({ viewport: VIEWPORT })).newPage();
  if (!OPS[job.op]) throw new Error(`unknown op ${job.op}`);
  process.stdout.write(JSON.stringify(await OPS[job.op](page, job)));
} catch (e) {
  process.stdout.write(JSON.stringify({ error: String(e).slice(0, 500) }));
} finally {
  await browser.close();
}
