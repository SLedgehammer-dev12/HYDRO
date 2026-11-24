#!/usr/bin/env node
/**
 * Verifies that `src/lib/api-types.generated.ts` matches `../docs/openapi.json`.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const openapiPath = path.resolve(frontendDir, "../docs/openapi.json");
const committedPath = path.resolve(frontendDir, "src/lib/api-types.generated.ts");

if (!fs.existsSync(committedPath)) {
  console.error("FAIL: src/lib/api-types.generated.ts missing. Run `npm run gen:api-types`.");
  process.exit(1);
}

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "hydro-api-types-"));
const tmpOut = path.join(tmpDir, "api-types.generated.ts");

try {
  const bin = path.resolve(
    frontendDir,
    "node_modules",
    ".bin",
    process.platform === "win32" ? "openapi-typescript.cmd" : "openapi-typescript",
  );
  execFileSync(bin, [openapiPath, "-o", tmpOut], { cwd: frontendDir, stdio: "pipe" });
  const expected = fs.readFileSync(tmpOut, "utf8");
  const actual = fs.readFileSync(committedPath, "utf8");
  if (expected !== actual) {
    console.error(
      "FAIL: src/lib/api-types.generated.ts is out of date with webapp/docs/openapi.json.\n" +
        "Run: npm --prefix webapp/frontend run gen:api-types",
    );
    process.exit(1);
  }
  console.log("API TypeScript types OK: matches webapp/docs/openapi.json.");
} finally {
  fs.rmSync(tmpDir, { recursive: true, force: true });
}
