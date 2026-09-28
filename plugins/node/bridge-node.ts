// Node hub: the bridge half of the "node" plugin.
//
// A node is a computer (a Mac, a server, a Raspberry Pi) that pairs once with a one-time key and then
// holds a long poll open to the bridge. When Iris runs something on that node the bridge hands the job
// to the waiting poll and the node sends the output back. No approval per command: the pairing is the
// approval. Revoke the node and the next poll is refused within a second.
//
// Wire it into src/voice.ts next to the other route handlers:
//
//   import { nodeRoute } from "./node";
//   ...
//   if (nodeRoute(req, res)) return;                 // before the page routes
//
// To use the house's own phone key as the gate for the house side (the pair/run/revoke routes), pass it:
//
//   if (nodeRoute(req, res, (r) => telefoonSleutelKlopt(r))) return;
//
// Nothing else is needed: state is kept under DATA/nodes.json and the agent is served from
// node-agent.py (NODE_AGENT_FILE points elsewhere if the plugin lives somewhere else).
//
// On a small server of its own (also how the tests run it):
//   node bridge-node.ts --port 8799 --data /tmp/iris-node --house-key secret
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

// Tunables, all overridable for tests and small installs.
const POLL_MS = Number(process.env.NODE_POLL_MS || 25_000);
const KEY_TTL_MS = Number(process.env.NODE_KEY_TTL_MS || 10 * 60_000);
const OFFLINE_MS = Number(process.env.NODE_OFFLINE_MS || 90_000);
const RESULT_GRACE_MS = 15_000;
const MAX_BYTES = Number(process.env.NODE_MAX_OUTPUT || 256 * 1024);
const MAX_BODY = 4 * 1024 * 1024;

let dataDir = process.env.NODE_DATA || process.env.DATA || join(homedir(), ".iris-node-bridge");
let agentFile = process.env.NODE_AGENT_FILE || join(HERE, "node-agent.py");

type NodeRec = {
  id: string;
  name: string;
  os: string;
  host: string;
  hash: string;
  allow: string[];
  created: number;
  lastSeen: number;
  askedAt: number;
};

type KeyRec = { hash: string; label: string; created: number; expires: number; used: boolean };

type Job = {
  id: string;
  nodeId: string;
  cmd: string;
  timeout: number;
  cwd: string;
  created: number;
  result: Record<string, unknown> | null;
  wacht: Array<(r: Record<string, unknown>) => void>;
};

type Waiter = { res: ServerResponse; timer: ReturnType<typeof setTimeout> };

let nodes: NodeRec[] = [];
let keys: KeyRec[] = [];
let banen = new Map<string, Job>();
let wachtrijen = new Map<string, Job[]>(); // nodeId -> jobs waiting for a poll
let wachtenden = new Map<string, Waiter>(); // nodeId -> the long poll that is open right now
let geladen = false;

const now = (): number => Date.now();
const sha = (s: string): string => createHash("sha256").update(s).digest("hex");
const id = (n = 6): string => randomBytes(n).toString("hex"); // 12 hex characters
const tekst = (v: unknown, max = 200): string => String(v ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max);

function laad(): void {
  geladen = true;
  if (!existsSync(dataDir)) {
    mkdirSync(dataDir, { recursive: true, mode: 0o700 });
  }
  try {
    const d = JSON.parse(readFileSync(join(dataDir, "nodes.json"), "utf8"));
    nodes = Array.isArray(d.nodes) ? d.nodes : [];
    keys = Array.isArray(d.keys) ? d.keys : [];
  } catch {
    nodes = [];
    keys = [];
  }
  // A bridge restart loses no pairing, but no /node/run is in flight across it: drop half-made jobs so a
  // waiting request does not hang. Every poll that comes back gets a fresh state.
  banen = new Map();
  wachtrijen = new Map();
  wachtenden = new Map();
}

function bewaar(): void {
  if (!existsSync(dataDir)) mkdirSync(dataDir, { recursive: true, mode: 0o700 });
  const p = join(dataDir, "nodes.json");
  writeFileSync(p, JSON.stringify({ nodes, keys }, null, 2), { mode: 0o600 });
  try {
    chmodSync(p, 0o600);
  } catch {
    /* best effort */
  }
}

function uniekeNaam(wanted: string): string {
  const basis = tekst(wanted, 60) || "node";
  let naam = basis;
  let i = 2;
  while (nodes.some((n) => n.name.toLowerCase() === naam.toLowerCase())) naam = `${basis}-${i++}`;
  return naam;
}

function vindNode(ref: unknown): NodeRec | null {
  const r = tekst(ref, 80).toLowerCase();
  if (!r) return null;
  return nodes.find((n) => n.id === r || n.name.toLowerCase() === r)
    || nodes.find((n) => n.name.toLowerCase().startsWith(r))
    || null;
}

function authNode(req: IncomingMessage): NodeRec | null {
  const h = String(req.headers.authorization || "");
  const secret = h.startsWith("Bearer ") ? h.slice(7).trim() : "";
  if (!secret) return null;
    const rec = nodes.find((n) => n.hash === sha(secret));
  if (!rec) return null;
  rec.lastSeen = now();
  return rec;
}

function defaultHouseOk(req: IncomingMessage): boolean {
  const want = String(process.env.NODE_HOUSE_KEY || process.env.IRIS_HOUSE_KEY || "");
  if (!want) return true; // no key configured: meant for a loopback-only hub
  const got = String(req.headers["x-nova-sleutel"] || "");
  return got.length === want.length && timingSafeEqual(Buffer.from(got), Buffer.from(want));
}

function leesBody(req: IncomingMessage): Promise<Record<string, unknown> | null> {
  return new Promise((resolve) => {
    let b = "";
    let teGroot = false;
    req.on("data", (c) => {
      b += c;
      if (b.length > MAX_BODY) {
        teGroot = true;
        req.destroy();
        resolve(null);
      }
    });
    req.on("end", () => {
      if (teGroot) return resolve(null);
      try {
        const d = b ? JSON.parse(b) : {};
        resolve(d && typeof d === "object" ? (d as Record<string, unknown>) : null);
      } catch {
        resolve(null);
      }
    });
    req.on("error", () => resolve(null));
  });
}

function zend(res: ServerResponse, code: number, body: unknown, type = "application/json"): void {
  const s = type === "application/json" ? JSON.stringify(body) : String(body);
  if (res.headersSent || res.writableEnded) return;
  res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(s);
}

const fout = (res: ServerResponse, code: number, why: string): void => zend(res, code, { fout: why });

function publiek(n: NodeRec): Record<string, unknown> {
  return {
    id: n.id,
    name: n.name,
    os: n.os,
    host: n.host,
    allow: n.allow,
    created: n.created,
    lastSeen: n.lastSeen,
    online: now() - n.lastSeen < OFFLINE_MS,
  };
}

function publicJob(j: Job): Record<string, unknown> {
  return { id: j.id, nodeId: j.nodeId, cmd: j.cmd, timeout: Math.round(j.timeout / 1000), cwd: j.cwd, created: j.created };
}

// What goes to the node: timeout in whole seconds, the unit the agent counts in.
function draadJob(j: Job): Record<string, unknown> {
  return { id: j.id, cmd: j.cmd, timeout: Math.round(j.timeout / 1000), cwd: j.cwd };
}

function kiesJob(nodeId: string): Job | null {
  return wachtrijen.get(nodeId)?.shift() ?? null;
}

function biedAan(nodeId: string): void {
  const w = wachtenden.get(nodeId);
  if (!w) return;
  const job = kiesJob(nodeId);
  if (!job) return;
  wachtenden.delete(nodeId);
  clearTimeout(w.timer);
  zend(w.res, 200, { job: draadJob(job) });
}

function maakJob(node: NodeRec, cmd: string, timeoutMs: number, cwd: string): Job {
  const job: Job = {
    id: id(),
    nodeId: node.id,
    cmd,
    timeout: timeoutMs,
    cwd,
    created: now(),
    result: null,
    wacht: [],
  };
  banen.set(job.id, job);
  const q = wachtrijen.get(node.id) ?? [];
  q.push(job);
  wachtrijen.set(node.id, q);
  biedAan(node.id);
  return job;
}

function wachtOp(job: Job, ms: number): Promise<Record<string, unknown>> {
  if (job.result) return Promise.resolve(job.result);
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      const i = job.wacht.indexOf(klaar);
      if (i >= 0) job.wacht.splice(i, 1);
      reject(new Error(`node answered not in time (${Math.round(ms / 1000)}s)`));
    }, ms);
    function klaar(r: Record<string, unknown>): void {
      clearTimeout(t);
      resolve(r);
    }
    job.wacht.push(klaar);
  });
}

function maakResult(job: Job, r: Record<string, unknown>): void {
  if (job.result) return;
  job.result = r;
  for (const k of job.wacht.splice(0)) k(r);
  // Keep a finished job around briefly so `node result` can still read it, then clean up.
  setTimeout(() => banen.delete(job.id), 5 * 60_000);
}

function stopNode(n: NodeRec): void {
  nodes = nodes.filter((x) => x.id !== n.id);
  // The open long poll of this node gets a clear "you are gone", so the agent stops at once.
  const w = wachtenden.get(n.id);
  if (w) {
    wachtenden.delete(n.id);
    clearTimeout(w.timer);
    fout(w.res, 401, "koppeling ingetrokken");
  }
  const q = wachtrijen.get(n.id) ?? [];
  wachtrijen.delete(n.id);
  for (const job of [...q, ...banen.values()]) {
    if (job.nodeId === n.id && !job.result) {
      maakResult(job, { fout: "koppeling ingetrokken" });
    }
  }
  for (const [jid, job] of banen) if (job.nodeId === n.id) banen.delete(jid);
  bewaar();
}

async function bedien(req: IncomingMessage, res: ServerResponse, url: URL, houseOk: (r: IncomingMessage) => boolean): Promise<void> {
  if (!geladen) laad();
  const path = url.pathname.replace(/\/+$/, "") || "/node";
  const method = (req.method || "GET").toUpperCase();

  // --- public: the agent source, so a device installs with one command ---
  if ((path === "/node/agent" || path === "/node/agent.py") && method === "GET") {
    if (!existsSync(agentFile)) return fout(res, 404, "agent file not found");
    return zend(res, 200, readFileSync(agentFile, "utf8"), "text/plain; charset=utf-8");
  }

  // --- node side: paired by secret, no house key ---
  if (path === "/node/pair" && method === "POST") {
    const b = await leesBody(req);
    if (!b) return fout(res, 400, "bad body");
    const k = keys.find((x) => x.hash === sha(tekst(b.key, 200)) && !x.used && x.expires > now());
    if (!k) return fout(res, 403, "pairing key unknown, already used, or expired");
    k.used = true;
    const secret = randomBytes(32).toString("hex");
    const rec: NodeRec = {
      id: id(),
      name: uniekeNaam(tekst(b.name, 60)),
      os: tekst(b.os, 40),
      host: tekst(b.host, 80),
      hash: sha(secret),
      allow: Array.isArray(b.allow) ? b.allow.slice(0, 50).map((a) => tekst(a, 200)) : [],
      created: now(),
      lastSeen: now(),
      askedAt: now(),
    };
    nodes.push(rec);
    bewaar();
    return zend(res, 200, { node: { id: rec.id, name: rec.name }, secret });
  }

  if (path === "/node/next" && method === "GET") {
    const node = authNode(req);
    if (!node) return fout(res, 401, "unknown or revoked node");
    bewaar();
    const job = kiesJob(node.id);
    if (job) return zend(res, 200, { job: draadJob(job) });
    const w: Waiter = {
      res,
      timer: setTimeout(() => {
        if (wachtenden.get(node.id) === w) {
          wachtenden.delete(node.id);
          zend(res, 204, {});
        }
      }, POLL_MS),
    };
    wachtenden.set(node.id, w);
    req.on("close", () => {
      if (wachtenden.get(node.id) === w) {
        wachtenden.delete(node.id);
        clearTimeout(w.timer);
      }
    });
    return;
  }

  if (path === "/node/result" && method === "POST") {
    const node = authNode(req);
    if (!node) return fout(res, 401, "unknown or revoked node");
    const b = await leesBody(req);
    if (!b) return fout(res, 400, "bad body");
    const job = banen.get(tekst(b.id, 40));
    if (!job || job.nodeId !== node.id) return fout(res, 404, "no such job");
    let out = typeof b.stdout === "string" ? b.stdout : "";
    let err = typeof b.stderr === "string" ? b.stderr : "";
    let afgekapt = Boolean(b.truncated);
    if (Buffer.byteLength(out, "utf8") > MAX_BYTES) {
      out = out.slice(0, MAX_BYTES);
      afgekapt = true;
    }
    if (Buffer.byteLength(err, "utf8") > MAX_BYTES) {
      err = err.slice(0, MAX_BYTES);
      afgekapt = true;
    }
    maakResult(job, {
      id: job.id,
      exit: Number.isFinite(Number(b.exit)) ? Number(b.exit) : 0,
      stdout: out,
      stderr: err,
      truncated: afgekapt,
      timedOut: Boolean(b.timedOut),
      ms: Number.isFinite(Number(b.ms)) ? Number(b.ms) : 0,
    });
    return zend(res, 200, { ok: true });
  }

  if (path === "/node/bye" && method === "POST") {
    const node = authNode(req);
    if (!node) return fout(res, 401, "unknown or revoked node");
    stopNode(node);
    return zend(res, 200, { ok: true, revoked: true });
  }

  if (path === "/node/me" && method === "GET") {
    const node = authNode(req);
    if (!node) return fout(res, 401, "unknown or revoked node");
    bewaar();
    return zend(res, 200, publiek(node));
  }

  // --- house side: the assistant's own routes, behind the house key ---
  if (!houseOk(req)) return fout(res, 401, "house key missing or wrong");

  if (path === "/node" && method === "GET") {
    return zend(res, 200, {
      nodes: nodes.map(publiek),
      keys: keys.filter((k) => !k.used && k.expires > now()).map((k) => ({ label: k.label, created: k.created, expires: k.expires })),
      pollMs: POLL_MS,
      publicUrl: String(process.env.NODE_PUBLIC_URL || ""),
      agent: "/node/agent",
    });
  }

  if (path === "/node/key" && method === "POST") {
    const b = (await leesBody(req)) ?? {};
    const label = tekst(b.label, 60) || `node-${keys.length + 1}`;
    const raw = randomBytes(16).toString("hex");
    const ttl = Math.min(60 * 60_000, Math.max(60_000, Number(b.ttl) || KEY_TTL_MS));
    keys = keys.filter((k) => !k.used && k.expires > now());
    keys.push({ hash: sha(raw), label, created: now(), expires: now() + ttl, used: false });
    bewaar();
    return zend(res, 200, { key: raw, label, expires: now() + ttl });
  }

  if ((path === "/node/key/rm" || (path === "/node/key" && method === "DELETE")) && method !== "GET") {
    const b = (await leesBody(req)) ?? {};
    const label = tekst(b.label, 60).toLowerCase();
    const voor = keys.length;
    keys = keys.filter((k) => k.label.toLowerCase() !== label);
    bewaar();
    return zend(res, 200, { removed: voor - keys.length });
  }

  if (path === "/node/run" && method === "POST") {
    const b = await leesBody(req);
    if (!b) return fout(res, 400, "bad body");
    const node = vindNode(b.id ?? b.name);
    if (!node) return fout(res, 404, `no node "${tekst(b.id ?? b.name, 80)}"`);
    if (now() - node.lastSeen > OFFLINE_MS) return fout(res, 409, `node "${node.name}" is not connected`);
    const cmd = String(b.cmd ?? "");
    if (!cmd.trim()) return fout(res, 400, "no command");
    const timeoutMs = Math.min(600, Math.max(1, Number(b.timeout) || 60)) * 1000;
    const job = maakJob(node, cmd, timeoutMs, tekst(b.cwd, 300));
    if (b.wait === false) return zend(res, 202, { job: job.id });
    try {
      const r = await wachtOp(job, timeoutMs + RESULT_GRACE_MS);
      if (r.fout) return fout(res, 502, String(r.fout));
      return zend(res, 200, r);
    } catch (e) {
      return fout(res, 504, String((e as Error).message || e));
    }
  }

  if (path === "/node/job" && method === "GET") {
    const job = banen.get(url.searchParams.get("id") || "");
    if (!job) return fout(res, 404, "no such job");
    if (!job.result) return zend(res, 200, { job: publicJob(job), done: false });
    return zend(res, 200, { job: publicJob(job), done: true, result: job.result });
  }

  if (path === "/node/revoke" && method === "POST") {
    const b = await leesBody(req);
    if (!b) return fout(res, 400, "bad body");
    const node = vindNode(b.id ?? b.name);
    if (!node) return fout(res, 404, `no node "${tekst(b.id ?? b.name, 80)}"`);
    const naam = node.name;
    stopNode(node);
    return zend(res, 200, { revoked: true, name: naam });
  }

  return fout(res, 404, "unknown node route");
}

export function nodeRoute(
  req: IncomingMessage,
  res: ServerResponse,
  houseOk: (r: IncomingMessage) => boolean = defaultHouseOk,
): boolean {
  let url: URL;
  try {
    url = new URL(req.url || "/", "http://bridge");
  } catch {
    return false;
  }
  if (!url.pathname.startsWith("/node")) return false;
  void bedien(req, res, url, houseOk).catch((e) => {
    // A crashed handler must never take the whole bridge down.
    try {
      fout(res, 500, String((e as Error).message || e));
    } catch {
      /* already gone */
    }
  });
  return true;
}

// ---------------------------------------------------------------------------------------------------------
// Standalone: enough of a hub to test the plugin (and to run on a small server of its own).
// ---------------------------------------------------------------------------------------------------------
function startStandalone(argv: string[]): void {
  let port = Number(process.env.NODE_PORT || 8799);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--port") port = Number(argv[++i]);
    else if (argv[i] === "--data") dataDir = argv[++i];
    else if (argv[i] === "--agent") agentFile = argv[++i];
    else if (argv[i] === "--house-key") process.env.NODE_HOUSE_KEY = argv[++i];
  }
  geladen = false;
  const server = createServer((req, res) => {
    if (!nodeRoute(req, res)) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("only /node lives here\n");
    }
  });
  server.listen(port, "127.0.0.1", () => {
    console.log(`node hub on http://127.0.0.1:${port} (data ${dataDir})`);
  });
  process.on("SIGTERM", () => server.close(() => process.exit(0)));
  process.on("SIGINT", () => server.close(() => process.exit(0)));
}

const isMain = (() => {
  const a = process.argv[1];
  if (!a) return false;
  try {
    return pathToFileURL(a).href === import.meta.url;
  } catch {
    return false;
  }
})();

if (isMain) startStandalone(process.argv.slice(2));
