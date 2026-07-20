export type OpenApiSource =
  | { kind: "file"; path: string }
  | { kind: "url"; url: string };

/**
 * Vercel/CI builds use the committed openapi/schema.json (no network).
 * Set API_OPENAPI_URL to refresh the schema from a running API.
 */
export function resolveOpenApiSource(
  env: NodeJS.ProcessEnv = process.env,
  committedSchemaPath: string,
): OpenApiSource {
  const url = env.API_OPENAPI_URL?.trim();
  if (url) {
    return { kind: "url", url };
  }
  return { kind: "file", path: committedSchemaPath };
}
