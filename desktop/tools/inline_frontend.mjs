import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(toolRoot, "..");
const distRoot = path.join(desktopRoot, "dist");
const indexPath = path.join(distRoot, "index.html");

const sha256Source = (source) =>
  `sha256-${createHash("sha256").update(source, "utf8").digest("base64")}`;

const resolveAsset = (relativeSource) => {
  const normalized = relativeSource.replace(/^\.\//, "");
  const resolved = path.resolve(distRoot, normalized);
  const relative = path.relative(distRoot, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Compiled asset escapes desktop/dist: source=${relativeSource}`);
  }
  return resolved;
};

let html = await readFile(indexPath, "utf8");
const scriptPattern = /<script type="module" crossorigin src="([^"]+)"><\/script>/g;
const stylePattern = /<link rel="stylesheet" crossorigin href="([^"]+)">/g;
const scripts = [...html.matchAll(scriptPattern)];
const styles = [...html.matchAll(stylePattern)];
if (scripts.length !== 1 || styles.length !== 1) {
  throw new Error(
    `Expected one compiled script and one stylesheet: scripts=${scripts.length}, styles=${styles.length}`,
  );
}

const scriptSource = await readFile(resolveAsset(scripts[0][1]), "utf8");
const styleSource = await readFile(resolveAsset(styles[0][1]), "utf8");
if (scriptSource.includes("</script") || styleSource.includes("</style")) {
  throw new Error("Compiled frontend contains an unsafe inline closing tag");
}

const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src '${sha256Source(scriptSource)}'`,
  `style-src '${sha256Source(styleSource)}' 'unsafe-inline'`,
  "img-src 'self' data:",
  "connect-src 'none'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
].join("; ");

html = html
  .replace(scripts[0][0], "")
  .replace(styles[0][0], () => `<style>${styleSource}</style>`)
  .replace("</body>", () => `  <script>${scriptSource}</script>\n  </body>`)
  .replace(
    /content="default-src[^\"]+"/,
    `content="${contentSecurityPolicy}"`,
  );

await writeFile(indexPath, html, "utf8");
process.stdout.write(
  `${JSON.stringify({ status: "pass", index: indexPath, script_sha256: sha256Source(scriptSource), style_sha256: sha256Source(styleSource) })}\n`,
);
