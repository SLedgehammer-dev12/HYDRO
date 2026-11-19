import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const DIST = path.resolve("dist");
const HTML_PATH = path.join(DIST, "index.html");

if (!fs.existsSync(HTML_PATH)) {
  console.error(`Missing build output at ${HTML_PATH}. Run 'npm run build' first.`);
  process.exit(1);
}

const html = fs.readFileSync(HTML_PATH, "utf8");
const initialRefs = new Set(
  [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1].replace(/^\//, "")),
);

const BUDGETS = {
  initialJsGzipKB: 200,
  initialCssGzipKB: 30,
  maxAsyncChunkGzipKB: 300,
  allowSourcemaps: process.env.HYDRO_SOURCEMAP === "true",
};

const assetsDir = path.join(DIST, "assets");
const files = fs.existsSync(assetsDir) ? fs.readdirSync(assetsDir) : [];
const gzipKB = (rel) => zlib.gzipSync(fs.readFileSync(path.join(DIST, rel))).length / 1024;

let initialJs = 0;
let initialCss = 0;
const failures = [];
const breakdown = [];

for (const file of files) {
  const rel = `assets/${file}`;
  if (file.endsWith(".map")) {
    if (!BUDGETS.allowSourcemaps) {
      failures.push(`Unexpected sourcemap in dist/: ${rel}`);
    }
    continue;
  }
  const kb = gzipKB(rel);
  if (initialRefs.has(rel)) {
    breakdown.push(`${file} (${kb.toFixed(1)} kB gzip, initial)`);
    if (file.endsWith(".js")) initialJs += kb;
    if (file.endsWith(".css")) initialCss += kb;
  } else if (file.endsWith(".js") && kb > BUDGETS.maxAsyncChunkGzipKB) {
    failures.push(`Async chunk ${file} (${kb.toFixed(1)} kB gzip) > ${BUDGETS.maxAsyncChunkGzipKB} kB`);
  }
}

if (initialJs === 0) {
  failures.push("No initial JS references found in dist/index.html");
}
if (initialJs > BUDGETS.initialJsGzipKB) {
  failures.push(`Initial JS total (${initialJs.toFixed(1)} kB gzip) > ${BUDGETS.initialJsGzipKB} kB`);
}
if (initialCss > BUDGETS.initialCssGzipKB) {
  failures.push(`Initial CSS total (${initialCss.toFixed(1)} kB gzip) > ${BUDGETS.initialCssGzipKB} kB`);
}

console.log(
  `Bundle budget: initial JS ${initialJs.toFixed(1)} kB gzip | initial CSS ${initialCss.toFixed(1)} kB gzip`,
);
if (breakdown.length) {
  console.log(`Initial refs: ${breakdown.join(", ")}`);
}
if (failures.length) {
  console.error("Bundle budget FAILED:\n - " + failures.join("\n - "));
  process.exit(1);
}
