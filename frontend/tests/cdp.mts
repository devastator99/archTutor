/**
 * A browser, driven over the Chrome DevTools Protocol.
 *
 * The point of this file is the one thing the rest of the suite cannot do:
 * click. Every other test in this project calls the app's own modules, which
 * means a broken event handler, a canvas that never mounts, or a controlled
 * input that ignores typing would all pass. This driver opens a real page and
 * performs the real gestures a student performs.
 *
 * It speaks CDP directly over Node's built-in WebSocket rather than pulling in
 * a browser-automation dependency. The protocol is a JSON request/response
 * channel, and the handful of commands below are all this project's needs. A
 * dependency would add a browser download and a version matrix to a project
 * that deliberately has neither.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter((path): path is string => typeof path === "string" && path.length > 0);

/** Where this machine's browser is, or null if it is not installed. */
export function findChrome(): string | null {
  return CHROME_CANDIDATES.find((path) => existsSync(path)) ?? null;
}

interface Pending {
  resolve: (value: Record<string, unknown>) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
  method: string;
}

class Connection {
  private nextId = 1;
  private readonly pending = new Map<number, Pending>();
  private readonly listeners = new Set<(message: Record<string, unknown>) => void>();

  // A plain field, not a parameter property: Node strips types from tests
  // rather than compiling them, and it does not transform constructor syntax.
  private readonly socket: WebSocket;

  constructor(socket: WebSocket) {
    this.socket = socket;
    socket.addEventListener("message", (event: MessageEvent) => {
      const message = JSON.parse(String(event.data)) as Record<string, unknown>;
      const id = message.id as number | undefined;
      if (typeof id === "number") {
        const entry = this.pending.get(id);
        if (entry) {
          this.pending.delete(id);
          clearTimeout(entry.timer);
          if (message.error) {
            const error = message.error as { message?: string; data?: string };
            entry.reject(
              new Error(
                `${entry.method} failed: ${error.data ?? error.message ?? "unknown error"}`,
              ),
            );
          } else {
            entry.resolve((message.result ?? {}) as Record<string, unknown>);
          }
        }
        return;
      }
      for (const listener of this.listeners) {
        listener(message);
      }
    });
  }

  onMessage(listener: (message: Record<string, unknown>) => void): void {
    this.listeners.add(listener);
  }

  send(
    method: string,
    params: Record<string, unknown> = {},
    sessionId?: string,
  ): Promise<Record<string, unknown>> {
    const id = this.nextId++;
    const payload: Record<string, unknown> = { id, method, params };
    if (sessionId) {
      payload.sessionId = sessionId;
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timed out`));
      }, 30_000);
      this.pending.set(id, { resolve, reject, timer, method });
      this.socket.send(JSON.stringify(payload));
    });
  }
}

async function waitForEndpoint(child: ChildProcess): Promise<string> {
  const line = await new Promise<string>((resolve, reject) => {
    let seen = "";
    const timer = setTimeout(() => {
      reject(new Error(`Chrome did not report a debugging endpoint:\n${seen}`));
    }, 30_000);
    child.stderr?.on("data", (chunk: Buffer) => {
      seen += chunk.toString();
      const match = /DevTools listening on (ws:\/\/\S+)/.exec(seen);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Chrome exited with code ${code} before listening:\n${seen}`));
    });
  });
  return line;
}

export type ClickOutcome = "clicked" | "missing" | "disabled";

/**
 * A page-side function. It is serialised, so it must be self-contained: it can
 * only use browser globals and the arguments it is given.
 */
export type PageExpression<A extends unknown[] = unknown[]> = (...args: A) => unknown;

export interface Page {
  /** Navigate and wait until the page has finished loading. */
  goto(url: string): Promise<void>;
  /** Run a function inside the page and return its result. */
  evaluate<T, A extends unknown[]>(fn: (...args: A) => T, ...args: A): Promise<T>;
  /**
   * Poll a page expression until it is truthy, or fail with the page's text so
   * the reason is visible. `args` are passed to the expression, which is how a
   * predicate can compare against a value known outside the browser.
   */
  waitFor(
    expression: PageExpression<never[]>,
    message: string,
    options?: { timeoutMs?: number; args?: unknown[] },
  ): Promise<void>;
  /** Click the first button whose label contains `text`. */
  clickText(text: string): Promise<ClickOutcome>;
  /** The visible text of the page, or of one element. */
  text(selector?: string): Promise<string>;
  /** Save a PNG of the whole page, not just the viewport. */
  screenshot(file: string): Promise<void>;
  /** Uncaught JavaScript errors the page raised, in order. */
  readonly errors: string[];
  close(): Promise<void>;
}

export async function openPage(): Promise<Page> {
  const executable = findChrome();
  if (!executable) {
    throw new Error("no Chrome or Chromium executable found; set CHROME_PATH");
  }
  const profile = await mkdtemp(join(tmpdir(), "archtutor-e2e-"));
  const child = spawn(
    executable,
    [
      // Plain ``--headless`` is the new headless mode in current Chrome; the
      // older ``--headless=new`` spelling has been deprecated.
      "--headless",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--window-size=1400,1800",
      `--user-data-dir=${profile}`,
      // Port 0 lets the OS pick, so parallel runs cannot collide.
      "--remote-debugging-port=0",
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );

  const socket = new WebSocket(await waitForEndpoint(child));
  await new Promise<void>((resolve, reject) => {
    socket.addEventListener("open", () => resolve());
    socket.addEventListener("error", () => reject(new Error("could not open the CDP socket")));
  });
  const connection = new Connection(socket);

  const { targetId } = (await connection.send("Target.createTarget", {
    url: "about:blank",
  })) as { targetId: string };
  const { sessionId } = (await connection.send("Target.attachToTarget", {
    targetId,
    flatten: true,
  })) as { sessionId: string };

  const errors: string[] = [];
  connection.onMessage((message) => {
    if (message.method !== "Runtime.exceptionThrown") {
      return;
    }
    const details = (message.params as { exceptionDetails?: { text?: string; exception?: { description?: string } } })
      .exceptionDetails;
    errors.push(
      details?.exception?.description ?? details?.text ?? "uncaught exception",
    );
  });

  await connection.send("Page.enable", {}, sessionId);
  await connection.send("Runtime.enable", {}, sessionId);

  const evaluate = async <T, A extends unknown[]>(
    fn: (...args: A) => T,
    ...args: A
  ): Promise<T> => {
    const serialized = args
      .map((arg) => JSON.stringify(arg === undefined ? null : arg))
      .join(",");
    const response = (await connection.send(
      "Runtime.evaluate",
      {
        expression: `(${fn.toString()})(${serialized})`,
        awaitPromise: true,
        returnByValue: true,
      },
      sessionId,
    )) as {
      result?: { value?: T };
      exceptionDetails?: { text?: string; exception?: { description?: string } };
    };
    if (response.exceptionDetails) {
      throw new Error(
        `page evaluation threw: ${
          response.exceptionDetails.exception?.description ??
          response.exceptionDetails.text ??
          "unknown"
        }`,
      );
    }
    return response.result?.value as T;
  };

  const page: Page = {
    errors,
    evaluate,
    async goto(url: string) {
      await connection.send("Page.navigate", { url }, sessionId);
      await page.waitFor(
        () => document.readyState === "complete",
        `the page at ${url} to load`,
      );
    },
    async waitFor(expression, message, options = {}) {
      const deadline = Date.now() + (options.timeoutMs ?? 30_000);
      for (;;) {
        if (await evaluate(expression as PageExpression, ...(options.args ?? []))) {
          return;
        }
        if (Date.now() > deadline) {
          const seen = await page.text();
          throw new Error(
            `timed out waiting for ${message}. Page text:\n${seen.slice(0, 2000)}`,
          );
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    },
    clickText(text: string) {
      return evaluate(CLICK_BY_TEXT, text);
    },
    text(selector?: string) {
      return evaluate(TEXT_OF, selector ?? null);
    },
    async screenshot(file: string) {
      const { data } = (await connection.send(
        "Page.captureScreenshot",
        { format: "png", captureBeyondViewport: true },
        sessionId,
      )) as { data: string };
      await mkdir(dirname(file), { recursive: true });
      await writeFile(file, Buffer.from(data, "base64"));
    },
    async close() {
      try {
        await connection.send("Target.closeTarget", { targetId });
      } catch {
        // The browser may already be gone; the process kill below is the
        // guarantee that nothing is left running.
      }
      socket.close();
      child.kill();
      // Chrome keeps writing to its profile for a moment after SIGTERM, and
      // removing a directory it is still writing to fails. Wait for the exit,
      // then retry, and never let cleanup mask the test's own result.
      await new Promise<void>((resolve) => {
        if (child.exitCode !== null || child.signalCode !== null) {
          resolve();
          return;
        }
        const timer = setTimeout(resolve, 5_000);
        child.once("exit", () => {
          clearTimeout(timer);
          resolve();
        });
      });
      await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(
        () => {},
      );
    },
  };
  return page;
}

const CLICK_BY_TEXT = (text: string): ClickOutcome => {
  const buttons = Array.from(document.querySelectorAll("button"));
  const button = buttons.find((candidate) =>
    (candidate.textContent ?? "").includes(text),
  );
  if (!button) {
    return "missing";
  }
  if ((button as HTMLButtonElement).disabled) {
    return "disabled";
  }
  button.click();
  return "clicked";
};

const TEXT_OF = (selector: string | null): string => {
  const target = selector ? document.querySelector(selector) : document.body;
  return target?.textContent ?? "";
};
