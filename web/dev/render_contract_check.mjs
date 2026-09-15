#!/usr/bin/env node
/**
 * No-browser behavioural guard for the M13 panel renderer.
 *
 * Why this exists (falsification finding R2, L3 §9.6): the Playwright-based DOM
 * assertions skip when no browser is available, so in a browser-less CI the
 * renderer regressions they guard have **zero** protection. Static "literal
 * fingerprint" guards do not close that hole either -- they pass under
 * semantically equivalent rewrites (finding R4: `cls || "tab__dot--unverified"`
 * and `... ? value : "unverified"` both slipped past them).
 *
 * So this script executes the real `web/app.js` against a minimal DOM stub and
 * asserts the **observable outcome** (which classes actually land on which
 * elements), not the shape of the source. It needs Node only -- no browser.
 *
 * Usage: node web/dev/render_contract_check.mjs [--json]
 * Exit code 0 = all checks hold; 1 = a check failed.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

//: `--app=<path>` lets a caller run the same checks against a *variant* of the
//: renderer, which is how the test suite proves that a behaviour-preserving
//: rename really is behaviour-preserving (rather than assuming it).
const APP_ARG = process.argv.find((arg) => arg.startsWith("--app="));
const APP_PATH = APP_ARG
  ? resolve(APP_ARG.slice("--app=".length))
  : resolve(ROOT, "web", "app.js");

/* ------------------------------------------------------------------ mini DOM */

const dataAttrName = (key) =>
  "data-" + key.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());

class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.parentNode = null;
    this.children = [];
    this._class = "";
    this._attrs = Object.create(null);
    this.dataset = new Proxy(
      {},
      {
        set: (target, key, value) => {
          target[key] = String(value);
          this._attrs[dataAttrName(String(key))] = String(value);
          return true;
        },
        get: (target, key) => target[key],
        deleteProperty: (target, key) => {
          delete target[key];
          delete this._attrs[dataAttrName(String(key))];
          return true;
        },
      },
    );
    this._text = null;
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.type = "";
    this.placeholder = "";
    this.listeners = Object.create(null);
  }

  get className() {
    return this._class;
  }
  set className(value) {
    this._class = value == null ? "" : String(value);
  }
  get classList() {
    const list = (this._class || "").split(/\s+/).filter(Boolean);
    return { contains: (c) => list.includes(c) };
  }

  get textContent() {
    if (this._text !== null) return this._text;
    return this.children.map((child) => child.textContent ?? "").join("");
  }
  set textContent(value) {
    this._text = value == null ? "" : String(value);
    this.children.forEach((child) => {
      child.parentNode = null;
    });
    this.children = [];
  }

  get firstChild() {
    return this.children[0] ?? null;
  }

  appendChild(node) {
    if (node.parentNode) node.remove();
    node.parentNode = this;
    this.children.push(node);
    this._text = null;
    return node;
  }

  insertBefore(node, ref) {
    if (node.parentNode) node.remove();
    const index = ref ? this.children.indexOf(ref) : -1;
    node.parentNode = this;
    if (index < 0) this.children.push(node);
    else this.children.splice(index, 0, node);
    this._text = null;
    return node;
  }

  remove() {
    if (!this.parentNode) return;
    const siblings = this.parentNode.children;
    const index = siblings.indexOf(this);
    if (index >= 0) siblings.splice(index, 1);
    this.parentNode = null;
  }

  setAttribute(name, value) {
    this._attrs[name] = String(value);
  }
  removeAttribute(name) {
    delete this._attrs[name];
  }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this._attrs, name)
      ? this._attrs[name]
      : null;
  }

  addEventListener(type, handler) {
    (this.listeners[type] ||= []).push(handler);
  }
  dispatch(type) {
    (this.listeners[type] || []).forEach((handler) => handler({ type }));
  }

  hasClass(name) {
    return (this._class || "").split(/\s+/).includes(name);
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  matchesSimple(spec) {
    const [cls, attr] = spec.split("[");
    if (cls && !this.hasClass(cls.replace(/^\./, ""))) return false;
    if (!attr) return true;
    const m = attr.replace(/\]$/, "").match(/^([\w-]+)=["']?(.*?)["']?$/);
    if (!m) return false;
    return this.getAttribute(m[1]) === m[2];
  }

  matches(selector) {
    const parts = String(selector).split(">").map((s) => s.trim());
    if (parts.length === 1) return this.matchesSimple(selector);
    if (!this.matchesSimple(parts[parts.length - 1])) return false;
    let node = this.parentNode;
    for (let i = parts.length - 2; i >= 0; i -= 1) {
      while (node && typeof node.matchesSimple === "function" && !node.matchesSimple(parts[i])) {
        node = node.parentNode;
      }
      if (!node || typeof node.matchesSimple !== "function") return false;
      node = node.parentNode;
    }
    return true;
  }

  querySelectorAll(selector) {
    return this.descendants().filter((node) => node.matches(selector));
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
}

class TextNode {
  constructor(text) {
    this._text = String(text);
    this.parentNode = null;
  }
  get textContent() {
    return this._text;
  }
  get children() {
    return [];
  }
  remove() {
    if (this.parentNode) {
      const i = this.parentNode.children.indexOf(this);
      if (i >= 0) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    }
  }
  descendants() {
    return [];
  }
  matches() {
    return false;
  }
}

function makeDocument(ids) {
  const document = {
    _byId: Object.create(null),
    createElement: (tag) => new El(tag),
    createTextNode: (text) => new TextNode(text),
    getElementById(id) {
      return this._byId[id] ?? null;
    },
    querySelectorAll(selector) {
      return this.body.querySelectorAll(selector);
    },
    querySelector(selector) {
      return this.body.querySelector(selector);
    },
  };
  document.body = new El("body");
  for (const id of ids) {
    const node = new El("div");
    node._attrs.id = id;
    document._byId[id] = node;
    document.body.appendChild(node);
  }
  return document;
}

/* ------------------------------------------------------- run the real renderer */

const PANEL_IDS = ["project", "evidence", "files", "approval"];
const STATES = { project: "verified", evidence: "unverified", files: "blocked", approval: "bogus-state" };

function panel(panelId, state) {
  return {
    panel_id: panelId === "approval" ? "approval" : panelId,
    project_id: "fixture",
    verification_state: state,
    sections: [
      {
        title: panelId + " section",
        refs: [],
        verified: state === "verified",
        unknown_reason: state === "verified" ? null : "fixture reason for " + state,
        verification_state: state,
        facts: {},
      },
    ],
  };
}

function boot() {
  const payload = {
    initial: "project",
    panels: Object.fromEntries(PANEL_IDS.map((id) => [id, panel(id, STATES[id])])),
  };
  const document = makeDocument([
    "snapshot-note",
    "load-btn",
    "project-input",
    "tabs",
    "legend",
    "panels",
  ]);
  const window = { __PANEL_SNAPSHOT__: payload };
  const context = vm.createContext({ window, document, console, fetch: () => {
    throw new Error("fetch must not be called in snapshot mode");
  } });
  const source = readFileSync(APP_PATH, "utf8");
  new vm.Script(source, { filename: APP_PATH }).runInContext(context);
  return document;
}

/* -------------------------------------------------------------------- checks */

const failures = [];
const notes = [];
function check(name, fn) {
  try {
    const detail = fn();
    notes.push(`  ok   ${name}${detail ? "  (" + detail + ")" : ""}`);
  } catch (err) {
    failures.push(name);
    notes.push(`  FAIL ${name}\n         ${err.message}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const document = boot();

function dotOf(panelId) {
  const tab = document.querySelector(`.tab[data-panel="${panelId}"]`);
  assert(tab, `no tab rendered for panel ${panelId}`);
  return { tab, dot: tab.querySelector(".tab__dot") };
}

function dotStateOf(dot) {
  if (!dot) return null;
  const m = String(dot.className).match(/tab__dot--(\w+)/);
  return m ? m[1] : null;
}

check("every real state gets its own dot class", () => {
  const seen = {};
  for (const panelId of ["project", "evidence", "files"]) {
    const { dot } = dotOf(panelId);
    assert(dot, `panel ${panelId} (${STATES[panelId]}) got no dot`);
    seen[panelId] = dotStateOf(dot);
    assert(
      seen[panelId] === STATES[panelId],
      `panel ${panelId}: dot class says ${seen[panelId]} but the state is ${STATES[panelId]}`,
    );
  }
  const distinct = new Set(Object.values(seen));
  assert(
    distinct.size === 3,
    `the three states must map to three distinct classes, got ${JSON.stringify(seen)}`,
  );
  return JSON.stringify(seen);
});

check("an unrecognised state gets no dot at all", () => {
  const { dot } = dotOf("approval");
  assert(
    dot === null,
    "a bogus verification_state must not be given a dot (that would invent a state)",
  );
  const { tab } = dotOf("approval");
  assert(
    tab.getAttribute("data-dot-state") === null,
    "a bogus state must not be recorded as a dot state",
  );
  return "no dot, no data-dot-state";
});

check("an unrecognised state is never laundered into a real one", () => {
  const { tab } = dotOf("approval");
  tab.dispatch("click");
  const chip = document.querySelector(".panel__head > .chip");
  assert(chip, "no panel header chip rendered");
  assert(
    chip.hasClass("chip--invalid"),
    `bogus state rendered chip class "${chip.className}"`,
  );
  const word = chip.textContent;
  assert(word.includes("INVALID-STATE"), `chip word was "${word}"`);
  assert(
    !word.includes("VERIFIED") && !word.includes("UNVERIFIED"),
    `bogus state was presented as a real state: "${word}"`,
  );
  return word;
});

check("selecting a panel rewrites its tab dot from that panel's state", () => {
  // regression for the audited defect: renderPanel must write the dot from the
  // projection. Selecting a panel with state X must leave ITS dot at X -- if
  // renderPanel writes a constant instead, the dot goes wrong the moment the
  // panel is opened (exactly the defect's observable effect).
  document.querySelector('.tab[data-panel="project"]').dispatch("click");
  const projectDot = dotStateOf(dotOf("project").dot);
  assert(
    projectDot === "verified",
    `after opening a verified panel its dot became ${projectDot}`,
  );
  const filesStill = dotStateOf(dotOf("files").dot);
  assert(
    filesStill === "blocked",
    `opening another panel changed the files dot to ${filesStill}`,
  );
  return "project=verified, files=blocked after selection";
});

const asJson = process.argv.includes("--json");
if (asJson) {
  process.stdout.write(
    JSON.stringify({ ok: failures.length === 0, failures, notes }, null, 1) + "\n",
  );
} else {
  console.log("[render-contract] no-browser behavioural checks of " + APP_PATH);
  notes.forEach((line) => console.log(line));
  console.log(
    failures.length === 0
      ? `[render-contract] PASS (${notes.length} checks)`
      : `[render-contract] FAIL (${failures.length}/${notes.length}): ${failures.join(", ")}`,
  );
}
process.exit(failures.length === 0 ? 0 : 1);
