#!/usr/bin/env node
// PasseFiltre launcher — one cross-platform entry point (Windows, macOS, Linux), no extra tool needed.
//
//   npm run setup     install everything: Python venv + deps, Chromium for Scrapling, frontend deps, .env
//   npm start         start the API + the web app (auto-reload while you edit the code)
//   npm run prod      build the web app and start both in production mode
//   npm test          backend tests + frontend type-check + frontend unit tests
//
// Configuration lives in a single `.env` file at the repository root (copied from .env.example by setup).

import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync, readFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = join(ROOT, "backend");
const FRONTEND = join(ROOT, "frontend");
const WIN = process.platform === "win32";
const VENV_PY = join(BACKEND, ".venv", WIN ? "Scripts/python.exe" : "bin/python");
// Call Next.js and TypeScript through node directly: no .cmd shims (some corporate policies block them).
const NEXT = join("node_modules", "next", "dist", "bin", "next");
const TSC = join("node_modules", "typescript", "bin", "tsc");

const paint = (code) => (s) => (process.stdout.isTTY ? `\x1b[${code}m${s}\x1b[0m` : s);
const [blue, red, green, bold, dim] = ["34", "31", "32", "1", "2"].map(paint);
const step = (msg) => console.log(`\n${blue("▸")} ${bold(msg)}`);
const fail = (msg) => {
  console.error(`\n${red("✖")} ${msg}`);
  process.exit(1);
};

function run(cmd, args, cwd = ROOT, { env = process.env, shell = false } = {}) {
  const r = spawnSync(cmd, args, { cwd, env, stdio: "inherit", shell });
  if (r.status !== 0) fail(`La commande a échoué : ${cmd} ${args.join(" ")}`);
}

/** Root .env + sensible defaults. Real environment variables always win. */
function loadEnv() {
  const env = { ...process.env };
  const file = join(ROOT, ".env");
  if (existsSync(file)) {
    for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*$/);
      if (m && env[m[1]] === undefined) env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, "$2");
    }
  }
  env.BACKEND_PORT ||= "8000";
  env.FRONTEND_PORT ||= "3000";
  env.NEXT_PUBLIC_API_URL ||= `http://localhost:${env.BACKEND_PORT}`;
  env.CORS_ORIGINS ||= `http://localhost:${env.FRONTEND_PORT},http://127.0.0.1:${env.FRONTEND_PORT}`;
  // This machine only by default. Opening to the network also requires PASSEFILTRE_TOKEN (the API checks it).
  env.BACKEND_HOST ||= "127.0.0.1";
  env.FRONTEND_HOST ||= "127.0.0.1";
  return env;
}

function findPython() {
  const candidates = WIN
    ? [["py", ["-3.12"]], ["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3.12", []], ["python3", []], ["python", []]];
  for (const [cmd, pre] of candidates) {
    const r = spawnSync(cmd, [...pre, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], { encoding: "utf8" });
    const [major, minor] = (r.stdout ?? "").trim().split(".").map(Number);
    if (r.status === 0 && major === 3 && minor >= 10) return { cmd, pre, version: `${major}.${minor}` };
  }
  fail("Python 3.10 ou plus est introuvable. Installez-le (https://www.python.org/downloads/) puis relancez « npm run setup ».");
}

function setup() {
  const nodeMajor = Number(process.versions.node.split(".")[0]);
  if (nodeMajor < 20) fail(`Node.js 20 ou plus est requis (version actuelle : ${process.versions.node}).`);

  const py = findPython();
  step(`Backend : Python ${py.version}, environnement virtuel backend/.venv`);
  if (!existsSync(VENV_PY)) run(py.cmd, [...py.pre, "-m", "venv", join(BACKEND, ".venv")]);
  run(VENV_PY, ["-m", "pip", "install", "--quiet", "--upgrade", "pip"], BACKEND);
  // Pinned + hash-checked dependencies (requirements-dev.lock, generated from requirements*.txt).
  run(VENV_PY, ["-m", "pip", "install", "--quiet", "--require-hashes", "-r", "requirements-dev.lock"], BACKEND);

  step("Navigateur Chromium utilisé par Scrapling");
  run(VENV_PY, ["-m", "playwright", "install", "chromium"], BACKEND);
  if (process.platform === "linux") {
    if (process.getuid?.() === 0) run(VENV_PY, ["-m", "playwright", "install-deps", "chromium"], BACKEND);
    else console.log(dim(`  Si Chromium refuse de démarrer, installez ses bibliothèques système :\n  sudo ${VENV_PY} -m playwright install-deps chromium`));
  }

  step("Frontend : dépendances npm");
  run("npm", [existsSync(join(FRONTEND, "package-lock.json")) ? "ci" : "install", "--no-audit", "--no-fund"], FRONTEND, { shell: WIN });

  if (!existsSync(join(ROOT, ".env"))) {
    copyFileSync(join(ROOT, ".env.example"), join(ROOT, ".env"));
    step("Fichier .env créé à partir de .env.example (à adapter si besoin)");
  }
  console.log(`\n${green("✔")} Installation terminée. Lancez ${bold("npm start")}.`);
}

function portFree(port) {
  return new Promise((resolve) => {
    const srv = createServer().once("error", () => resolve(false)).once("listening", () => srv.close(() => resolve(true)));
    srv.listen(Number(port), "127.0.0.1");
  });
}

function launch(name, color, cmd, args, cwd, env) {
  // Own process group on Unix so the whole tree (uvicorn reloader, Next workers) can be stopped together.
  const child = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"], detached: !WIN });
  const prefix = paint(color)(`[${name}]`);
  for (const stream of [child.stdout, child.stderr]) {
    let buffer = "";
    stream.on("data", (chunk) => {
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      for (const line of lines) console.log(`${prefix} ${line}`);
    });
  }
  return child;
}

function killTree(child) {
  if (child.exitCode !== null) return;
  if (WIN) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      /* already gone */
    }
  }
}

async function start(prod) {
  if (!existsSync(VENV_PY) || !existsSync(join(FRONTEND, "node_modules"))) fail("Lancez d'abord « npm run setup ».");
  const env = loadEnv();
  for (const [label, port, key] of [["API", env.BACKEND_PORT, "BACKEND_PORT"], ["interface", env.FRONTEND_PORT, "FRONTEND_PORT"]]) {
    if (!(await portFree(port)))
      fail(`Le port ${port} (${label}) est déjà utilisé : PasseFiltre tourne peut-être déjà. Arrêtez-le ou changez ${key} dans .env.`);
  }
  if (prod) {
    step("Build de l'interface");
    run(process.execPath, [NEXT, "build"], FRONTEND, { env });
  } else {
    env.API_DOCS ||= "1"; // interactive API docs (/docs) in development only
  }
  const children = [
    launch("api", "36", VENV_PY, ["-m", "uvicorn", "app.main:app", "--host", env.BACKEND_HOST, "--port", env.BACKEND_PORT, ...(prod ? [] : ["--reload"])], BACKEND, env),
    // Next.js listens on every interface by default (the whole network): pin it to FRONTEND_HOST.
    launch("web", "35", process.execPath, [NEXT, prod ? "start" : "dev", "-p", env.FRONTEND_PORT, "-H", env.FRONTEND_HOST], FRONTEND, env),
  ];
  const docs = env.API_DOCS === "1" ? dim(`   API : http://localhost:${env.BACKEND_PORT}/docs`) : "";
  console.log(`\n  ${bold("PasseFiltre")}  ${blue(`http://localhost:${env.FRONTEND_PORT}`)}${docs}`);
  console.log(dim("  Ctrl+C pour tout arrêter.\n"));

  let stopping = false;
  const stop = (code = 0) => {
    if (stopping) return;
    stopping = true;
    children.forEach(killTree);
    process.exit(code);
  };
  process.on("SIGINT", () => stop());
  process.on("SIGTERM", () => stop());
  for (const child of children)
    child.on("exit", (code) => {
      if (!stopping) {
        console.error(red(`\nUn service s'est arrêté (code ${code}) : arrêt de PasseFiltre.`));
        stop(code || 1);
      }
    });
}

function test() {
  if (!existsSync(VENV_PY)) fail("Lancez d'abord « npm run setup ».");
  step("Tests du backend");
  run(VENV_PY, ["-m", "pytest", "-q"], BACKEND);
  step("Vérification des types du frontend");
  run(process.execPath, [TSC, "--noEmit", "-p", "."], FRONTEND);
  step("Tests du frontend");
  run(process.execPath, ["--experimental-strip-types", "--test", "tests/**/*.test.ts"], FRONTEND);
  console.log(`\n${green("✔")} Tout est vert.`);
}

const command = process.argv[2];
if (command === "setup") setup();
else if (command === "start") await start(false);
else if (command === "prod") await start(true);
else if (command === "test") test();
else {
  console.log("Usage : node scripts/passefiltre.mjs <setup | start | prod | test>");
  process.exit(command ? 1 : 0);
}
