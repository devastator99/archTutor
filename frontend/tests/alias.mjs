/**
 * A resolver for the project's `@/` path alias, so Node's own test runner can
 * import the same modules the app imports.
 *
 * The app resolves `@/lib/...` through TypeScript's `paths` and Next's bundler.
 * Node does not read tsconfig, and adding a test framework to teach it a four
 * character prefix would be a dependency bought for a one-line mapping. This is
 * that mapping: one hook, no dependencies, and it fails loudly on an alias that
 * does not exist rather than silently resolving to nothing.
 */

import { existsSync } from "node:fs";
import { dirname, join, resolve as resolvePath } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolvePath(dirname(fileURLToPath(import.meta.url)), "..");

/** Extensions the app's modules use, in the order a bundler would try them. */
const CANDIDATES = ["", ".ts", ".tsx", "/index.ts", "/index.tsx"];

function resolveAlias(specifier) {
  const base = join(root, specifier.slice(2));
  for (const suffix of CANDIDATES) {
    const candidate = `${base}${suffix}`;
    if (existsSync(candidate)) {
      return pathToFileURL(candidate).href;
    }
  }
  throw new Error(`@/ alias does not resolve: ${specifier}`);
}

export function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("@/")) {
    return nextResolve(resolveAlias(specifier), context);
  }
  return nextResolve(specifier, context);
}
