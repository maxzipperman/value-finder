// Draws one screen of the page (vfdash/static/app.js) from a saved JSON answer, with a small stand-in for the
// browser, and prints what it drew as JSON: {tag, cls, kids} for elements and {text} for text. Tests only: it
// reads the two files it is given and nothing else, and makes no network request.
//   node render_page.mjs <app.js> <#hash> <answer.json> [hover]
// With "hover", every element that listens for the pointer is also moved over at a few points, and what each
// hover read-out then says is printed too, under "hovers". The page is drawn 640 pixels wide (a chart's width in a
// 700-pixel window), or RENDER_WIDTH pixels when that is set.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const [, , appPath, hash, answerPath] = process.argv;
const WIDTH = Number(process.env.RENDER_WIDTH || 640);
const answer = JSON.parse(readFileSync(answerPath, "utf8"));

class Base { constructor() { this.kids = []; } }
class Text extends Base { constructor(t) { super(); this.text = String(t); } }
class El extends Base {
  constructor(tag) { super(); this.tag = tag; this.className = ""; this.attrs = {}; this.style = {}; this.dataset = {}; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(type, fn) { (this.listeners ||= {})[type] = fn; }
  append(...kids) { for (const k of kids) this.kids.push(k instanceof Base ? k : new Text(k)); }
  replaceChildren(...kids) { this.kids = []; this.append(...kids); }
  set textContent(t) { this.kids = [new Text(t)]; }
  get textContent() { return this.kids.map((k) => (k instanceof Text ? k.text : k.textContent)).join(""); }
  get clientWidth() { return WIDTH; }
  get namespaceURI() { return "http://www.w3.org/2000/svg"; }
  insertAdjacentHTML() { this.append(new El("svg")); }
  querySelector(sel) { return this.kids.find((k) => k instanceof El && k.tag === sel) || null; }
  getBoundingClientRect() { return { left: 0, top: 0, width: WIDTH, height: 190 }; }
}
const byId = { main: new El("main"), stamp: new El("div"), banner: new El("div") };
Object.assign(globalThis, {
  Node: Base,
  document: {
    hidden: false, title: "Value Finder", getElementById: (id) => byId[id], createElement: (t) => new El(t),
    createElementNS: (_ns, t) => new El(t), createTextNode: (t) => new Text(t), querySelectorAll: () => [],
    addEventListener() {},
  },
  window: { addEventListener() {}, scrollY: 0, scrollTo() {} },
  location: { hash },
  setInterval: () => 0,
  fetch: async () => ({ json: async () => answer }),
});
vm.runInThisContext(readFileSync(appPath, "utf8"), { filename: "app.js" });
await new Promise((r) => setTimeout(r, 50));
const out = (n) => (n instanceof Text ? { text: n.text } : { tag: n.tag, cls: n.className, attrs: n.attrs,
  kids: n.kids.map(out) });
// with "hover": move the pointer over every element that listens for it, and read each read-out it shows
const hovers = [];
if (process.argv[5] === "hover") {
  const walk = (n, fn) => { if (n instanceof El) { fn(n); for (const k of n.kids) walk(k, fn); } };
  const tips = [];
  walk(byId.main, (n) => { if (n.className === "tip" || n.attrs.class === "tip") tips.push(n); });
  walk(byId.main, (n) => {
    const move = n.listeners && n.listeners.pointermove;
    if (!move) return;
    for (const f of [0.1, 0.5, 0.9]) {
      move({ clientX: WIDTH * f, clientY: 190 * f });
      for (const t of tips) if (t.hidden === false) hovers.push(t.textContent);
      for (const t of tips) t.hidden = true;
    }
  });
}
// the main part of the page as drawn, and the browser tab's title
process.stdout.write(JSON.stringify({ ...out(byId.main), doc_title: document.title, hovers }));
