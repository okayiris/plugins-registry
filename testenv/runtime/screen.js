// Draws a plugin's window or screen in Chromium and checks it, for testenv/sim.py screen.
//
// A small server gives the page the stand-in kit, the plugin's .jsx, its texts, and the house endpoints
// the screens use: POST /commands/run runs the plugin's own command in its simulated home, and fixed
// answers for other house paths come from the scenario ("house": {"/mail": {...}}).
// Checked: no page errors, nothing wider than the window or its tile, every text key in lang-en.json,
// and the actions in the scenario (click, expect, said, shot).
const fs = require("fs");
const path = require("path");
const http = require("http");
const { spawn, execFileSync } = require("child_process");
const esbuild = require("esbuild");
const { chromium } = require("playwright-core");

const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const PLUGINS = path.join(__dirname, "..", "..", "plugins");
const folder = path.join(PLUGINS, spec.plugin);
const manifest = JSON.parse(fs.readFileSync(path.join(folder, "plugin.json"), "utf8"));
const views = [["window", manifest.window], ["screen", manifest.screen]].filter(([, f]) => f);
const lang = spec.lang || "en";
const readJson = (f) => { try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch (e) { return {}; } };
const texts = { ...(readJson(path.join(folder, "lang-en.json")).texts || {}),
                ...(lang !== "en" ? readJson(path.join(folder, `lang-${lang}.json`)).texts || {} : {}) };
const problems = [];

function chromePath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const base = "/opt/pw-browsers";
  if (fs.existsSync(base)) {
    const dir = fs.readdirSync(base).find((d) => /^chromium-\d+$/.test(d));
    if (dir) return path.join(base, dir, "chrome-linux", "chrome");
  }
  return undefined; // playwright's own download, when there is one
}

// Split a command line like a shell would for plain words and "quoted parts".
function words(line) {
  const out = [];
  line.replace(/"([^"]*)"|'([^']*)'|(\S+)/g, (m, a, b, c) => out.push(a ?? b ?? c));
  return out;
}

function runCommand(cmd, args) {
  return new Promise((resolve) => {
    const p = spawn(cmd, words(args || ""), { cwd: spec.home, env: spec.env });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("error", (e) => resolve({ ok: false, tekst: String(e) }));
    p.on("close", (code) => {
      if (/Traceback \(most recent call last\)/.test(out + err)) problems.push(`${cmd} ${args} crashed: ${(err || out).trim().split("\n").pop()}`);
      resolve({ ok: code === 0, tekst: code === 0 ? out : (err || out) });
    });
  });
}

async function bundle(file) {
  const entry = `import "${path.join(__dirname, "kit.js").replace(/\\/g, "/")}";
import View from "${path.join(folder, file).replace(/\\/g, "/")}";
window.SIM_VIEW = View;
render(h(View), document.getElementById("tile"));`;
  const result = await esbuild.build({
    stdin: { contents: entry, resolveDir: path.join(__dirname, ".."), loader: "js" },
    bundle: true, write: false, jsxFactory: "h", jsxFragment: "Fragment",
    loader: { ".jsx": "jsx" }, nodePaths: [path.join(__dirname, "..", "node_modules")], logLevel: "silent",
  });
  return result.outputFiles[0].text;
}

const CSS = `
:root{--fg:#e8ecf1;--dim:#9aa4b2;--faint:#5b6572;--accent:#7cc4ff;--good:#5bd69b;--warn:#f5b85a;--bad:#ff6b6b;
--glass:rgba(255,255,255,.05);--edge:rgba(255,255,255,.12)}
*{box-sizing:border-box}body{margin:0;background:#0b0e13;color:var(--fg);font:15px/1.45 system-ui,sans-serif}
#stage{padding:16px}#tile{border:1px dashed var(--faint);border-radius:14px;overflow:hidden;padding:.8rem;margin:0 auto}
.k-screen header h1{margin:0;font-size:1.5rem}.k-dim{color:var(--dim)}
.k-card{border:1px solid var(--edge);border-radius:1rem;padding:.9rem 1rem;margin:.8rem 0;background:var(--glass)}
.k-label{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}.k-card h2{margin:.2rem 0 .4rem;font-size:1.1rem}
.k-row{display:flex;justify-content:space-between;gap:1rem;padding:.4rem 0;border-top:1px solid var(--edge)}
.k-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(7rem,1fr));gap:.6rem;margin:.8rem 0}
.k-stat{border:1px solid var(--edge);border-radius:.8rem;padding:.6rem .8rem;display:flex;flex-direction:column}.k-stat b{font-size:1.2rem}
.k-buttons{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0;align-items:center}
.k-btn{font:inherit;font-size:.85rem;padding:.35rem .7rem;border-radius:.6rem;border:1px solid var(--edge);background:var(--glass);color:var(--fg);cursor:pointer}
.k-btn:disabled{opacity:.45;cursor:default}.k-primary{background:var(--accent);color:#06121e;border-color:transparent;font-weight:600}
.k-icon{display:inline-block;border-radius:4px;background:var(--faint);vertical-align:middle}.k-list{margin:.3rem 0;padding-left:1.2rem}`;

function page(tileWidth) {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>${CSS}#tile{width:${tileWidth}}</style><script>window.SIM_LANG=${JSON.stringify(texts)};</script></head>
<body><div id="stage"><div id="tile"></div></div><script src="/view.js"></script></body></html>`;
}

async function main() {
  if (!views.length) { console.log(`- ${spec.plugin}: no window or screen`); return 0; }
  fs.mkdirSync(spec.out, { recursive: true });
  const house = spec.house || {};
  let code = null, tileWidth = "100%";
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    if (url.pathname === "/view.js") { res.setHeader("content-type", "text/javascript"); return res.end(code); }
    if (url.pathname === "/" || url.pathname === "/index.html") { res.setHeader("content-type", "text/html"); return res.end(page(tileWidth)); }
    if (url.pathname === "/commands/run" && req.method === "POST") {
      let body = ""; req.on("data", (d) => (body += d)); await new Promise((r) => req.on("end", r));
      let ask = {}; try { ask = JSON.parse(body); } catch (e) {}
      const own = Object.keys(manifest.commands || {});
      const answer = own.includes(ask.cmd) ? await runCommand(ask.cmd, ask.args)
        : { ok: false, tekst: `${ask.cmd} is not a command of ${spec.plugin}` };
      res.setHeader("content-type", "application/json"); return res.end(JSON.stringify(answer));
    }
    const fixed = house[url.pathname + url.search] ?? house[url.pathname];
    if (fixed !== undefined) { res.setHeader("content-type", "application/json"); return res.end(JSON.stringify(fixed)); }
    res.statusCode = 404; res.end("not in this test house");
  });
  await new Promise((r) => server.listen(spec.port || 0, "127.0.0.1", r));
  const port = server.address().port;
  const browser = await chromium.launch({ executablePath: chromePath() });
  let failed = false;

  for (const [kind, file] of views) {
    try {
      code = await bundle(file);
    } catch (e) {
      problems.push(`${file} does not build: ${String(e.message || e).split("\n").slice(0, 3).join(" ")}`);
      continue;
    }
    // Keys the view asks for that lang-en.json lacks.
    const src = fs.readFileSync(path.join(folder, file), "utf8");
    for (const [, key] of src.matchAll(/\btext\(\s*["']([^"']+)["']/g)) {
      if (!(key in texts)) problems.push(`${file}: text "${key}" has no entry in lang-en.json`);
    }
    // A window lives in a tile the owner resizes; a screen fills the page. Both go on a phone too.
    const sizes = kind === "window"
      ? [["narrow", "20rem", 1024, 800], ["wide", "40rem", 1024, 800], ["phone", "100%", 390, 844]]
      : [["desktop", "100%", 1280, 900], ["phone", "100%", 390, 844]];
    for (const [label, width, vw, vh] of sizes) {
      tileWidth = width;
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh } });
      const p = await ctx.newPage();
      const errors = [];
      p.on("pageerror", (e) => errors.push(String(e.message || e)));
      await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, async (route) => {
        if (spec.images && route.request().resourceType() === "image") {
          try {
            const body = execFileSync("curl", ["-sS", "-m", "20", route.request().url()], { maxBuffer: 20e6 });
            return route.fulfill({ status: 200, body });
          } catch (e) { /* fall through */ }
        }
        return route.abort();
      });
      await p.goto(`http://127.0.0.1:${port}/`);
      await p.waitForTimeout(spec.settle || 1500);
      const actions = label === sizes[0][0] ? spec.actions || [] : [];
      for (const a of actions) {
        try {
          if (a.click) await p.locator(a.click).first().click({ timeout: 8000 });
          if (a.wait) await p.waitForTimeout(a.wait);
          if (a.expect) await p.locator(a.expect).first().waitFor({ timeout: a.timeout || 10000 });
          if (a.gone && (await p.locator(a.gone).count())) problems.push(`${kind}: still shows ${a.gone}`);
          if (a.said) {
            const said = await p.evaluate(() => window.SIM_SAID);
            if (!said.some((s) => s.includes(a.said))) problems.push(`${kind}: nothing said with "${a.said}" (said: ${said.join(" | ") || "nothing"})`);
          }
          if (a.shot) await p.screenshot({ path: path.join(spec.out, `${kind}-${a.shot}.png`), fullPage: true });
          if (!a.click && !a.expect) continue;
          await p.waitForTimeout(a.settle || 600);
        } catch (e) {
          problems.push(`${kind}: ${JSON.stringify(a)} failed: ${String(e.message || e).split("\n")[0]}`);
          break;
        }
      }
      await p.screenshot({ path: path.join(spec.out, `${kind}-${label}.png`), fullPage: true });
      const over = await p.evaluate(() => {
        const tile = document.getElementById("tile");
        const wide = [];
        for (const el of tile.querySelectorAll("*")) {
          const r = el.getBoundingClientRect(), t = tile.getBoundingClientRect();
          if (r.width > 0 && r.right > t.right + 1 && getComputedStyle(el).position !== "fixed") wide.push(el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(" ")[0] : ""));
        }
        return { page: document.documentElement.scrollWidth > window.innerWidth + 1, tile: [...new Set(wide)].slice(0, 4) };
      });
      if (over.page) problems.push(`${kind} ${label}: the page scrolls sideways`);
      if (over.tile.length) problems.push(`${kind} ${label}: wider than its tile: ${over.tile.join(", ")}`);
      for (const e of errors) problems.push(`${kind} ${label}: page error: ${e}`);
      await ctx.close();
    }
  }
  await browser.close();
  if (spec.keep) {
    tileWidth = "100%";
    console.log(`Open http://127.0.0.1:${port}/ ; stop with Ctrl+C.`);
    return new Promise(() => {});
  }
  server.close();
  const unique = [...new Set(problems)];
  failed = unique.length > 0;
  console.log(`${failed ? "FAIL" : "ok  "} ${spec.plugin}: ${views.map(([k, f]) => `${k} ${f}`).join(", ")}; screenshots in ${path.relative(process.cwd(), spec.out)}`);
  for (const p of unique) console.log(`     ${p}`);
  return failed ? 1 : 0;
}

main().then((c) => process.exit(c), (e) => { console.error(e); process.exit(2); });
