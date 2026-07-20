import { execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { resolveOpenApiSource } from "./openapi-source";

const rootDir = path.resolve(__dirname, "..");
const schemaPath = path.join(rootDir, "openapi", "schema.json");
const outputPath = path.join(rootDir, "src", "lib", "api", "schema.d.ts");

async function loadSchemaJson(): Promise<unknown> {
  const source = resolveOpenApiSource(process.env, schemaPath);
  if (source.kind === "file") {
    return JSON.parse(readFileSync(source.path, "utf8"));
  }
  const response = await fetch(source.url);
  if (!response.ok) {
    throw new Error(`Failed to fetch OpenAPI schema from ${source.url}`);
  }
  return response.json();
}

async function main() {
  const schema = await loadSchemaJson();
  mkdirSync(path.dirname(schemaPath), { recursive: true });
  writeFileSync(schemaPath, JSON.stringify(schema, null, 2));

  execSync(`npx openapi-typescript "${schemaPath}" -o "${outputPath}"`, {
    cwd: rootDir,
    stdio: "inherit",
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
