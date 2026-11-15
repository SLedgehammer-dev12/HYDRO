#!/usr/bin/env node
/**
 * Sekme yönlendirme regresyon testi.
 *
 * Neden var: `AnimatePresence mode="wait"` ile sayfa geçişi bir kez kilitlendiğinde
 * başlık değişiyor ama `<main>` içeriği Dashboard'da kalıyordu. Bu test gerçek
 * tarayıcıda hash değiştirir ve her sekmenin H1'ini doğrular.
 *
 * Kullanım:
 *   1) `npm run dev` (ayrı terminal)
 *   2) `npm run verify:tabs`
 *
 * Chrome yolu: CHROME_BIN ortam değişkeni veya Playwright önbelleği.
 * Node 22+ gerekir (global WebSocket).
 */
import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

const APP_URL = process.env.HYDRO_APP_URL ?? "http://127.0.0.1:5173";
const CDP_PORT = Number(process.env.CDP_PORT ?? 9223);
const SLEEP = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const ROUTES = [
  ["projects", "Proje kayıtları ve kesit envanteri", "projects"],
  ["geometry", "Kesit, segmentler, kotlar ve saha profili", "geometry"],
  ["field", "Kesit, segmentler, kotlar ve saha profili", "geometry"],
  ["coefficients", "A/B hazırlama", "coefficients"],
  ["coefficient-detail", "Üç kaynak, backend ve A onarım", "coefficient_detail"],
  ["air", "Hava içerik değerlendirmesi", "air"],
  ["pressure", "Basınç değişim değerlendirmesi", "pressure"],
  ["reports", "Rapor önizleme", "reports"],
  ["ocr", "Test Raporu Kontrolü", "ocr"],
  ["settings", "Hesaplama, görünüm ve oturum", "settings"],
  ["dashboard", "Merhaba", "dashboard"],
];

function findChrome() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  const cache = path.join(os.homedir(), "Library/Caches/ms-playwright");
  if (fs.existsSync(cache)) {
    for (const folder of fs.readdirSync(cache)) {
      if (!folder.startsWith("chromium_headless_shell")) continue;
      const dir = path.join(cache, folder);
      for (const inner of fs.readdirSync(dir)) {
        const binary = path.join(dir, inner, "chrome-headless-shell");
        if (fs.existsSync(binary)) return binary;
      }
    }
  }
  try {
    return execSync("command -v chromium || command -v google-chrome || command -v chromium-browser", {
      encoding: "utf8",
    }).trim();
  } catch {
    return "";
  }
}

function request(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, (response) => {
        let body = "";
        response.on("data", (chunk) => (body += chunk));
        response.on("end", () => resolve({ status: response.statusCode ?? 0, body }));
      })
      .on("error", reject);
  });
}

async function openTarget() {
  const response = await request(`http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent(APP_URL)}`);
  // Bazı Chrome sürümleri GET yerine PUT ister.
  if (response.status >= 400) {
    const put = await new Promise((resolve, reject) => {
      const req = http.request(
        `http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent(APP_URL)}`,
        { method: "PUT" },
        (res) => {
          let body = "";
          res.on("data", (chunk) => (body += chunk));
          res.on("end", () => resolve(JSON.parse(body)));
        },
      );
      req.on("error", reject);
      req.end();
    });
    return put;
  }
  return JSON.parse(response.body);
}

async function main() {
  const chrome = findChrome();
  if (!chrome) {
    console.error("Chrome bulunamadı. CHROME_BIN ortam değişkenini ayarlayın.");
    process.exit(2);
  }

  try {
    const health = await request(APP_URL);
    if (health.status !== 200) throw new Error(`HTTP ${health.status}`);
  } catch (error) {
    console.error(`Dev sunucusu yanıt vermiyor (${APP_URL}). Önce 'npm run dev' çalıştırın.`);
    process.exit(2);
  }

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "hydro-tabs-"));
  const child = spawn(
    chrome,
    [
      "--headless",
      "--disable-gpu",
      "--no-sandbox",
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  try {
    let ready = false;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      try {
        await request(`http://127.0.0.1:${CDP_PORT}/json/version`);
        ready = true;
        break;
      } catch {
        await SLEEP(250);
      }
    }
    if (!ready) throw new Error(`Chrome CDP ${CDP_PORT} portunda açılmadı.`);

    const target = await openTarget();
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    let id = 1;
    const pending = new Map();
    const errors = [];

    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        const { resolve, reject } = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
        return;
      }
      if (message.method === "Runtime.exceptionThrown") {
        errors.push(message.params.exceptionDetails?.text ?? "exception");
      }
      if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
        errors.push(message.params.args?.map((arg) => arg.value ?? arg.description).join(" "));
      }
    };

    await new Promise((resolve, reject) => {
      socket.onopen = resolve;
      socket.onerror = reject;
    });

    const send = (method, params = {}) =>
      new Promise((resolve, reject) => {
        const requestId = id++;
        pending.set(requestId, { resolve, reject });
        socket.send(JSON.stringify({ id: requestId, method, params }));
      });

    const evaluate = async (expression) => {
      const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    };

    await send("Page.enable");
    await send("Runtime.enable");
    await send("Page.navigate", { url: `${APP_URL}/#/` });
    await SLEEP(1_800);

    const failures = [];
    for (const [route, expectedTitle, expectedPage = route] of ROUTES) {
      const hash = route === "dashboard" ? "#/" : `#/${route}`;
      await evaluate(`location.hash = ${JSON.stringify(hash)}`);
      await SLEEP(450);
      const state = await evaluate(`(() => {
        const main = document.querySelector("main");
        const page = main ? main.querySelector("[data-page]") : null;
        const h1 = main ? main.querySelector("h1") : null;
        return {
          dataPage: page ? page.getAttribute("data-page") : null,
          h1: h1 ? h1.textContent.trim() : "",
          greeting: main ? main.innerText.includes("Merhaba") : false,
        };
      })()`);

      const okPage = state.dataPage === expectedPage;
      const okTitle = state.h1.includes(expectedTitle);
      const okGreeting = route === "dashboard" ? state.greeting : !state.greeting;
      if (!okPage || !okTitle || !okGreeting) {
        failures.push({ route, expectedPage, expectedTitle, ...state, okPage, okTitle, okGreeting });
      }
      console.log(
        `${okPage && okTitle && okGreeting ? "PASS" : "FAIL"}  ${route.padEnd(20)} ${state.h1}`,
      );
    }

    socket.close();
    if (failures.length > 0) {
      console.error("\nBaşarısız sekmeler:", JSON.stringify(failures, null, 2));
      process.exitCode = 1;
    }
    if (errors.length > 0) {
      console.error("\nKonsol hataları:", errors.slice(0, 10));
      process.exitCode = 1;
    }
  } finally {
    child.kill("SIGTERM");
    await SLEEP(300);
    try {
      fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 150 });
    } catch {
      // Chrome profili geçici dizinde kalabilir; test sonucunu etkilemez.
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
