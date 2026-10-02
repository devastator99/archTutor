/**
 * Test bootstrap: register the `@/` alias hook before the runner imports
 * anything. Kept separate from `alias.mjs` because `register` itself must not be
 * part of the module the hook lives in.
 */

import { register } from "node:module";

register("./alias.mjs", import.meta.url);
