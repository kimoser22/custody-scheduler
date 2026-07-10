import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const openapiUrl =
  process.env.API_OPENAPI_URL ?? "http://localhost:8000/openapi.json";
const rootDir = path.resolve(__dirname, "..");
const schemaPath = path.join(rootDir, "openapi", "schema.json");
const outputPath = path.join(rootDir, "src", "lib", "api", "schema.d.ts");

async function main() {
  const response = await fetch(openapiUrl);
  if (!response.ok) {
    throw new Error(`Failed to fetch OpenAPI schema from ${openapiUrl}`);
  }

  const schema = await response.json();
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
