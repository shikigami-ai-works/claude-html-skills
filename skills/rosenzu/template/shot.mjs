// 路線図の HTML を、幅 1280 と 375、明と暗の4通りで全高撮り、数を数える（Chrome ヘッドレスを CDP で直接叩く。依存なし）。
// 使い方: node shot.mjs <HTMLの絶対パス> <撮影先フォルダ> [ファイル名の頭]
// 見る数: 横はみ出し（0px であること。はみ出したら原因の要素を5つまで名指しする）、
//         路線数と駅の札の数（build_rosenzu.py の書き出し表示と一致すること）、線の向き（375 で column）。
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { resolve, join, delimiter } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

// Chrome（無ければ Chromium 系）の実行ファイルを探す。環境変数 CHROME_PATH が最優先。
function findChrome() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const env = process.env;
  const cands = [];
  if (process.platform === "win32") {
    for (const base of [env.ProgramFiles, env["ProgramFiles(x86)"], env.LOCALAPPDATA]) {
      if (base) cands.push(join(base, "Google", "Chrome", "Application", "chrome.exe"));
    }
    for (const base of [env["ProgramFiles(x86)"], env.ProgramFiles]) {
      if (base) cands.push(join(base, "Microsoft", "Edge", "Application", "msedge.exe"));
    }
  } else if (process.platform === "darwin") {
    cands.push("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
               "/Applications/Chromium.app/Contents/MacOS/Chromium");
  } else {
    for (const dir of (env.PATH || "").split(delimiter)) {
      for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
        cands.push(join(dir, name));
      }
    }
  }
  return cands.find((c) => existsSync(c)) || cands[0] || "google-chrome";
}

const CHROME = findChrome();
const PORT = 9300 + Math.floor(Math.random() * 600);
const TARGET = process.argv[2];
const OUT = process.argv[3];
const PREFIX = process.argv[4] || "rosenzu";
if (!TARGET || !OUT) { console.error("使い方: node shot.mjs <HTML> <撮影先> [頭]"); process.exit(2); }
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, "--disable-gpu", "--hide-scrollbars",
  "--no-first-run", "--no-default-browser-check",
  `--user-data-dir=${resolve(tmpdir(), "rosenzu-shot-" + PORT)}`, "about:blank",
], { stdio: "ignore" });

async function waitBrowser() {
  for (let i = 0; i < 80; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/json/version`); if (r.ok) return; } catch { /* まだ */ }
    await sleep(300);
  }
  throw new Error("Chrome のデバッグ接続が開かなかった");
}

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map();
    ws.addEventListener("message", (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id === undefined) return;
      const p = this.pending.get(m.id); this.pending.delete(m.id);
      if (p) m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((res, rej) => {
      this.pending.set(id, { resolve: res, reject: rej });
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); rej(new Error("応答なし: " + method)); } }, 30000);
    });
  }
  async value(expression) {
    const r = await this.send("Runtime.evaluate", { expression, returnByValue: true });
    if (r.exceptionDetails) throw new Error("評価で例外: " + JSON.stringify(r.exceptionDetails).slice(0, 300));
    return r.result.value;
  }
}

// はみ出しの原因探し。要素の箱だけでなく、箱からあふれた文字（切れ目の無い長い語）も数える（scrollWidth）。
// 横に流せる入れ物（overflow が auto/scroll/hidden）は、その入れ物自体も中身も数えない。
// 原因のうち一番内側の要素だけを挙げる。
const CULPRITS = `(() => {
  const W = document.documentElement.clientWidth;
  const scrolls = (e) => ["auto", "scroll", "hidden"].includes(getComputedStyle(e).overflowX);
  const clipped = (e) => { for (let p = e.parentElement; p; p = p.parentElement) if (scrolls(p)) return true; return false; };
  const right = (e) => { const r = e.getBoundingClientRect(); return scrolls(e) ? r.right : Math.max(r.right, r.left + e.scrollWidth); };
  const bad = [...document.querySelectorAll("body *")].filter((e) => right(e) > W + 0.5 && !clipped(e));
  return JSON.stringify(bad.filter((e) => !bad.some((o) => o !== e && e.contains(o))).slice(0, 5)
    .map((e) => e.tagName.toLowerCase() + (e.className ? "." + String(e.className).trim().split(/\\s+/).join(".") : "")
      + "「" + (e.textContent || "").trim().slice(0, 40) + "」 右端 " + Math.round(right(e)) + "px"));
})()`;

async function shoot(width, mode) {
  const t = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
  const cdp = new CDP(ws);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 768 });
  await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: mode }] });
  await cdp.send("Page.navigate", { url: pathToFileURL(TARGET).href });
  await sleep(2500);
  const info = JSON.parse(await cdp.value(`JSON.stringify({h: document.documentElement.scrollHeight,
    over: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    lines: document.querySelectorAll('section.ln').length, st: document.querySelectorAll('.tr .st').length,
    x: document.querySelectorAll('.tr .st.x').length,
    dir: getComputedStyle(document.querySelector('.tr') || document.body).flexDirection})`));
  // 画素数が大きすぎると撮影が崩れるので、約 320 万画素に収まるよう縮める
  const scale = Math.min(1, Math.sqrt(3.2e6 / (width * info.h)));
  const shot = await cdp.send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width, height: info.h, scale } });
  const file = resolve(OUT, `${PREFIX}_${width}_${mode}.png`);
  writeFileSync(file, Buffer.from(shot.data, "base64"));
  console.log(`${width}px ${mode === "light" ? "明" : "暗"}: 高さ ${info.h}px、横はみ出し ${info.over}px、路線 ${info.lines}、駅の札 ${info.st}（うち乗換 ${info.x}）、線の向き ${info.dir}、縮尺 ${scale.toFixed(2)} → ${file}`);
  if (info.over > 0) {
    const found = JSON.parse(await cdp.value(CULPRITS));
    if (!found.length) console.log("   はみ出し: 原因の要素を特定できなかった");
    for (const c of found) console.log("   はみ出し: " + c);
  }
  ws.close();
  await fetch(`http://127.0.0.1:${PORT}/json/close/${t.id}`).catch(() => {});
}

(async () => {
  try {
    await waitBrowser();
    for (const w of [1280, 375]) for (const m of ["light", "dark"]) await shoot(w, m);
  } catch (e) { console.error("[shot]", e.message); process.exitCode = 1; }
  finally { try { chrome.kill(); } catch { /* 済み */ } }
})();
