import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const openapiPath = resolve(__dirname, "../../docs/openapi.json");
const apiTsPath = resolve(__dirname, "../src/lib/api.ts");
const ocrApiTsPath = resolve(__dirname, "../src/features/ocr/ocrApi.ts");

const openapi = JSON.parse(readFileSync(openapiPath, "utf8"));
const knownTemplates = Object.keys(openapi.paths || {}).map((p) => {
  const escaped = p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = "^" + escaped.replace(/\\\{[^}]+\\\}/g, "[^/?]+") + "$";
  return { raw: p, regex: new RegExp(pattern) };
});

function extractClientPaths(source) {
  const results = new Set();
  const re = /(?:apiFetch|apiDownload|requestJson)\s*(?:<[\s\S]*?>)?\s*\(\s*([`'"])(\/[^`'"]*)\1/g;
  let match;
  while ((match = re.exec(source)) !== null) {
    let raw = match[2];
    const qIdx = raw.indexOf("?");
    if (qIdx >= 0) raw = raw.slice(0, qIdx);
    // Replace path-segment interpolations (`/${id}`) with `/PARAM`, and strip trailing query interpolations (`${qs...}`)
    const normalized =
      "/api" + raw.replace(/\/\$\{[^}]+\}/g, "/PARAM").replace(/\$\{[\s\S]*$/g, "");
    results.add(normalized);
  }
  return [...results];
}

const clientPaths = [
  ...extractClientPaths(readFileSync(apiTsPath, "utf8")),
  ...extractClientPaths(readFileSync(ocrApiTsPath, "utf8")),
];

const missing = clientPaths.filter((cp) => !knownTemplates.some((kt) => kt.regex.test(cp)));
if (missing.length > 0) {
  console.error("OpenAPI contract mismatch — frontend calls unknown endpoints:", missing);
  process.exit(1);
}
console.log(
  `API contract OK: verified ${clientPaths.length} frontend endpoint templates against ${knownTemplates.length} OpenAPI paths.`,
);
