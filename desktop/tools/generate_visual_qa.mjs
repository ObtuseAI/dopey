import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(toolRoot, "..");
const sourceHtmlPath = path.join(desktopRoot, "dist", "index.html");
const fixturePath = path.join(desktopRoot, "visual-qa", "control-state.json");
const outputPath = path.join(desktopRoot, "visual-qa", "index.html");

const sha256Source = (source) =>
  `sha256-${createHash("sha256").update(source, "utf8").digest("base64")}`;

const escapeInlineJson = (value) =>
  JSON.stringify(value).replaceAll("<", "\\u003c").replaceAll(">", "\\u003e");

const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const fixtureSource = [
  `const DOPEY_VISUAL_FIXTURE=${escapeInlineJson(fixture)};`,
  "const DOPEY_SYMBOL_LAB_FIXTURE=DOPEY_VISUAL_FIXTURE.visual_qa_symbol_lab;",
  "const rejected=async()=>{throw new Error('qa_fixture_read_only')};",
  "window.pywebview={api:{",
  "get_state:async()=>DOPEY_VISUAL_FIXTURE,",
  "get_chart:async()=>{throw new Error('qa_fixture_chart_not_loaded')},",
  "get_symbol_lab:async()=>DOPEY_SYMBOL_LAB_FIXTURE,",
  "set_instrument_mode:rejected,set_llm_provider:rejected,set_openrouter_api_key:rejected,",
  "set_research_core:rejected,minimize_window:rejected,toggle_maximize_window:rejected,close_window:rejected",
  "}};",
].join("");

let html = await readFile(sourceHtmlPath, "utf8");
const cspPattern = /script-src ([^;]+);/;
const cspMatch = html.match(cspPattern);
if (cspMatch === null) {
  throw new Error(`Visual QA source is missing a script-src CSP: source=${sourceHtmlPath}`);
}
html = html
  .replace(cspPattern, `script-src ${cspMatch[1]} '${sha256Source(fixtureSource)}';`)
  .replace("<div id=\"root\"></div>", `<script>${fixtureSource}</script>\n    <div id=\"root\"></div>`);
if (!html.includes("DOPEY_VISUAL_FIXTURE") || !html.includes("qa_fixture_read_only")) {
  throw new Error("Visual QA fixture injection failed closed");
}

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, html, "utf8");
process.stdout.write(`${JSON.stringify({
  status: "pass",
  output: outputPath,
  fixture: fixturePath,
  fixture_script_sha256: sha256Source(fixtureSource),
  mutation_authority: "none",
})}\n`);
