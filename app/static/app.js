"use strict";

/* ============================================================ helpers */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pct = (x) => `${Math.round(x * 100)}%`;
const tone = (s) => (s >= 85 ? "found" : s >= 60 ? "missing" : "wrong");
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const BULLET = /^\s*(?:[•●▪◦–-]|\d{1,2}[.)])\s+/;
/* Runs fn inside a View Transition when it's safe to; resolves once the new screen is showing. */
let transition = null;
// Inside another page's window (starcrossed.cloud's frosted-glass windows), Chrome draws the
// transition snapshot blurred, so there the screens fade with plain CSS instead.
const EMBEDDED = window.self !== window.top;
if (EMBEDDED) document.documentElement.classList.add("embedded");
function swap(fn) {
  if (EMBEDDED || !document.startViewTransition || transition || document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    fn();
    return Promise.resolve();
  }
  const t = (transition = document.startViewTransition(fn));
  t.ready.catch(() => {});
  return t.finished.catch(() => {}).finally(() => { if (transition === t) transition = null; });
}
const joinList = (a) => (a.length < 2 ? a.join("") : `${a.slice(0, -1).join(", ")} ${T("and_word")} ${a.at(-1)}`);

/* The letter page speaks the letter's language. Its English texts live in static/ui_en.json; the
   server sends the same keys translated (c.ui) when a non-English letter is read. The front page and
   the top bar never change. */
let UI_EN = {};
function localUI() {
  const c = state.cur;
  if (!c) return null;
  const pick = readPick(c);
  if (pick) {  // the Reader view, in the language the reader picked
    if (sameLang(pick, "English")) return null;
    if (sameLang(pick, c.fact.language)) return c.ui || null;
    const r = c.readCache && c.readCache[pick];
    if (r && r.ui) return r.ui;
  }
  return c.ui && state.uiLang !== "en" ? c.ui : null;
}

/* "Read it in my language": in the Reader view, the person reading picks a language and the whole
   letter page follows (the letter itself stays as it was written). The pick is remembered. */
const READ_IN = [["English", "English"], ["Chinese", "中文"], ["Malay", "Bahasa Melayu"], ["Tamil", "தமிழ்"],
  ["Hindi", "हिन्दी"], ["Bengali", "বাংলা"], ["Burmese", "မြန်မာ"], ["Filipino", "Filipino"], ["Indonesian", "Bahasa Indonesia"],
  ["Vietnamese", "Tiếng Việt"], ["Thai", "ไทย"], ["Japanese", "日本語"], ["Korean", "한국어"], ["Russian", "Русский"], ["Spanish", "Español"]];
const sameLang = (a, b) => String(a || "").toLowerCase() === String(b || "").toLowerCase();
// the language picked for the Reader view, or null when the usual English / letter-language switch applies
const readPick = (c) => (state.mode === "reader" && c && c.test && c.fact && state.readPref) || null;
function T(key, vars) {
  let text = (localUI() || {})[key] || UI_EN[key] || key;
  if (vars) text = text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
  return text;
}
const english = () => !localUI();

// Dates on the letter page follow the letter's language when the page is shown in it.
const LOCALES = { chinese: "zh-CN", malay: "ms-MY", russian: "ru-RU", hindi: "hi-IN", tamil: "ta-IN", indonesian: "id-ID",
  japanese: "ja-JP", korean: "ko-KR", spanish: "es-ES", french: "fr-FR", german: "de-DE", vietnamese: "vi-VN",
  burmese: "my-MM", thai: "th-TH", bengali: "bn-BD", filipino: "fil-PH" };
const pageLocale = () => (!english() && state.cur && state.cur.fact && LOCALES[String(state.cur.fact.language || "").toLowerCase()]) || "en-GB";
function fmtDate(iso, time = false, locale = "en-GB") {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return "";
  const day = d.toLocaleDateString(locale, { day: "numeric", month: "short" });
  return time ? `${day}, ${d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}` : day;
}

async function api(path, body) {
  // relative, so the app also works from a sub-folder such as /misread/
  const res = await fetch(path.replace(/^\//, ""), body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `The server answered ${res.status}.`);
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove("show"), 4500);
}

function countUp(el, to, from = 0, ms = 900) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || document.hidden) { el.textContent = Math.round(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, Math.max(0, (t - t0) / ms));
    el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  setTimeout(() => { el.textContent = Math.round(to); }, ms + 150); // throttled frames must still land on the real number
}

/* ============================================================ words */
const VIEWS = [
  { id: "full", label: "Full read", note: "full read — every word" },
  { id: "skim", label: "Skim", note: "skim — headings, bold text, first lines" },
  { id: "glance20", label: "Glance", note: "glance — about 1 word in 5, top to bottom" },
  { id: "phone", label: "Phone", note: "phone — first screen, no scrolling" },
];
const BUSY = ["skim", "glance20", "phone"];
const VIEW_LABEL = Object.fromEntries(VIEWS.map((v) => [v.id, v.label]));
const SLOTS = ["action", "deadline", "consequence", "contact"];
const SLOT_LABEL = { need_to_act: "Need to act?", action: "What to do", deadline: "Deadline", consequence: "If they don't", contact: "Who to contact" };
const SLOT_PHRASE = { need_to_act: "whether to act", action: "what to do", deadline: "the deadline", consequence: "what happens if they don't", contact: "who to contact" };
const FEATURED = ["cms_nomnc", "id_talenta_livein_id", "us_edd_id_ru"];
const TEST_STEPS = [
  { match: /finding/i, label: "step_find", model: "Nemotron 3 Super" },
  { match: /reading/i, label: "step_read12", model: "Nemotron 3.5 Lightning + 3 Super" },
  { match: /checking/i, label: "step_check", model: "Nemotron 3 Super" },
  { match: /explaining/i, label: "step_explain", model: "Nemotron 3 Ultra" },
];
const FIX_STEPS = [
  { match: /finding/i, label: "step_find", model: "Nemotron 3 Super" },
  { match: /original/i, label: "step_original", model: "Nemotron 3.5 Lightning" },
  { match: /rewrite/i, label: "step_rewrite", model: "Nemotron 3 Ultra" },
  { match: /trying/i, label: "step_try", model: "Nemotron 3.5 Lightning + 3 Super" },
  { match: /re-check/i, label: "step_recheck", model: "Nemotron 3.5 Lightning + 3 Super" },
];

// ?mode=reader in the address opens the reader's view (handy for demo links); otherwise the last choice.
const savedMode = new URLSearchParams(location.search).get("mode")
  || (() => { try { return localStorage.getItem("misread.mode"); } catch { return null; } })();
const state = { status: { live: false }, samples: [], cur: null, view: "full", version: "original", job: null,
  mode: savedMode === "reader" ? "reader" : "writer", uiLang: "local",
  // ?read=Chinese in the address opens the Reader view in that language (for demo links); otherwise the last pick
  readPref: (() => {
    const asked = new URLSearchParams(location.search).get("read");
    const hit = asked && READ_IN.find(([v]) => sameLang(v, asked));
    if (hit) return hit[0];
    try { return localStorage.getItem("misread.readIn"); } catch { return null; }
  })() };
const READER_LABEL = { action: "What to do", deadline: "By when", consequence: "If you don't", contact: "Who to contact" };
const unstated = (v) => !v || /^\W*not stated/i.test(v);

/* ============================================================ start + routing */
async function init() {
  try { UI_EN = await fetch("static/ui_en.json").then((r) => r.json()); } catch { /* keys show as-is */ }
  try { state.status = await api("/api/status"); } catch { /* defaults */ }
  try { state.samples = await api("/api/samples"); } catch (e) { toast(e.message); }
  renderHome();
  wireUpload();
  $("#homeLink").onclick = (e) => { e.preventDefault(); goHome(); };
  $("#backBtn").onclick = () => goHome("examples");
  $("#allBtn").onclick = () => {
    const more = $("#allLetters");
    swap(() => { more.hidden = !more.hidden; $("#allBtn").textContent = more.hidden ? "See all 13" : "Show fewer"; });
  };
  document.querySelectorAll("[data-home-anchor]").forEach((a) => {
    a.onclick = (e) => { e.preventDefault(); goHome(a.getAttribute("href").slice(1)); };
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#changesPop, #changesChip")) $("#changesPop").hidden = true;
  });
  window.onhashchange = () => swap(route);
  route();
}

function goHome(anchor) {
  const scroll = () => anchor && document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" });
  if (location.hash) {
    history.pushState(null, "", location.pathname);
    swap(showHome).then(scroll);
  } else if ($("#home").hidden) swap(showHome).then(scroll);
  else scroll();
}

function route() {
  const m = location.hash.match(/^#\/letter\/([a-z0-9_]+)(?:\/(full|skim|glance20|phone))?(?:\/(fixed))?$/);
  if (m) return openSample(m[1], m[2], m[3]);
  if (location.hash === "#/yours" && state.cur && !state.cur.id) return showWork();
  showHome();
}

function showHome() {
  $("#work").hidden = true;
  $("#home").hidden = false;
  document.title = "Misread";
  window.scrollTo(0, 0);
}

/* ============================================================ home */
function exampleCard(s, i) {
  const t = s.busy == null ? null : tone(s.busy);
  const teaser = s.teaser
    ? `<p class="quote"><small>${esc(s.teaser.label)} · they said</small>“${esc(cap(s.teaser.said))}”</p>`
    : `<p class="ex-sum">${esc(s.summary)}</p>`;
  return `<button class="ex" style="animation-delay:${i * 50}ms" data-id="${esc(s.id)}">
    <div class="ex-top"><span class="chip">${esc(s.short || s.category)}</span>${t ? `<span class="score-badge b-${t}" title="Busy-reader score">${s.busy}</span>` : ""}</div>
    <h3>${esc(s.title)}</h3>${teaser}</button>`;
}

function renderHome() {
  const s = state.status;
  const note = $("#liveNote");
  note.hidden = s.live && !s.mock;
  note.textContent = s.mock ? "Demo mode: a fake model answers, results mean nothing." : "Live testing is off on this server. The examples still work.";
  $("#dropzone").classList.toggle("busy", !s.live);

  const byId = Object.fromEntries(state.samples.map((x) => [x.id, x]));
  const featured = FEATURED.map((id) => byId[id]).filter(Boolean);
  const rest = state.samples.filter((x) => !FEATURED.includes(x.id)).sort((a, b) => (a.busy ?? 999) - (b.busy ?? 999));
  $("#featured").innerHTML = featured.map(exampleCard).join("");
  $("#allLetters").innerHTML = rest.map(exampleCard).join("");
  $("#allBtn").hidden = !rest.length;
  for (const grid of [$("#featured"), $("#allLetters")]) {
    grid.onclick = (e) => { const b = e.target.closest(".ex"); if (b) location.hash = `#/letter/${b.dataset.id}`; };
  }
}

/* ============================================================ upload */
const PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs";
const PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs";
const MAMMOTH = "https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js";
const MAX_WORDS = 10000;
// as on the server: Chinese, Japanese and Korean have no spaces, so two characters count as one word
const CJK_CHAR = /[぀-ヿ㐀-鿿가-힯]/g;
const DENSE = { thai: /[฀-໿ក-៿]/g, my: /[က-အဣ-ဪဿ၌-၏၀-၉](?![်္])/g };
// Thai, Lao and Khmer: about six letters a word; Burmese: about 2.5 syllables (as on the server)
const wordCount = (t) => {
  const n = (re) => (t.match(re) || []).length;
  const spaced = t.replace(CJK_CHAR, " ").replace(/[฀-໿ក-៿က-႟]+/g, " ").match(/\S+/g) || [];
  return spaced.length + Math.floor(n(CJK_CHAR) / 2) + Math.round(n(DENSE.thai) / 6) + Math.round(n(DENSE.my) / 2.5);
};

function wireUpload() {
  const dz = $("#dropzone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); if (state.status.live) dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) handleFile(f); });
  $("#fileInput").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) handleFile(f); });
  $("#pasteBtn").onclick = () => {
    if (!state.status.live) return toast($("#liveNote").textContent);
    swap(() => { $("#pasteBox").hidden = false; $(".drop-inner").hidden = true; });
    $("#pasteText").focus();
  };
  $("#pasteCancel").onclick = () => swap(() => { $("#pasteBox").hidden = true; $(".drop-inner").hidden = false; });
  $("#pasteGo").onclick = () => {
    const text = $("#pasteText").value.trim();
    const err = checkText(text);
    if (err) return toast(err);
    startYourLetter({ title: "Your letter", text, upload: { name: "Pasted text", words: wordCount(text) } });
  };
}

const KIND = {
  newsletter: { chip: "Newsletter", note: "This reads like a newsletter with many topics. Misread works best on a letter about one thing, so treat these scores as rough." },
  template: { chip: "Template", note: "This looks like a blank template. Fill in the blanks with sample values first." },
  not_a_letter: { chip: "Not a letter", note: "This doesn't read like a letter. It's more like a guide, slides or a report, so the scores may not mean much." },
};

/* Some PDFs' fonts hide their real letters (common with Tamil and other Indian scripts): the text
   comes back with vowel signs that start a word, or with placeholder symbols. Readers and the
   answer key would be guessing, so the writer is told to check the key or paste clean text. */
function looksScrambled(text) {
  const letters = (text.match(/\p{L}/gu) || []).length;
  const junk = /[�-]|\(cid:\d+\)/;
  if ((text.match(new RegExp(junk.source, "g")) || []).length > Math.max(50, letters)) return true;  // hardly any real letters
  if (letters < 50) return false;
  const orphans = (text.match(/(?:^|[\s(\[“"'])\p{M}/gmu) || []).length;
  // junk inside a word, touching a letter; a symbol font's checkboxes and bullets stand on their own
  const inWords = (text.match(new RegExp(`\\p{L}(?:${junk.source})|(?:${junk.source})\\p{L}`, "gu")) || []).length;
  return (orphans + inWords) / letters > 0.003;
}

/* Templates and multi-letter packets give readers nothing concrete to get right or wrong. */
function templateNotes(text) {
  const notes = looksScrambled(text) ? [{ key: "note_scrambled" }] : [];
  const blanks = text.match(/\[[^\]\n]{2,40}\]|_{5,}/g) || [];
  if (blanks.length >= 3) notes.push({ key: "note_template", vars: { n: blanks.length, eg: blanks.find((b) => b.startsWith("[")) || "____" } });
  const letters = new Set((text.match(/\b(?:sample|template)\s+letter\s+[A-Z0-9]\b/gi) || []).map((x) => x.toLowerCase())).size;
  const openings = (text.match(/^\s*Dear\b/gim) || []).length;
  const n = Math.max(letters, openings);
  if (n >= 2) notes.push({ key: "note_letters", vars: { n } });
  return notes;
}

function checkText(text) {
  const n = wordCount(text);
  if (n < 20) return "That's too short to test — paste the whole letter.";
  if (n > MAX_WORDS) return `That's ${n.toLocaleString()} words. The limit is ${MAX_WORDS.toLocaleString()} — try just the letter pages.`;
  return null;
}

async function handleFile(file) {
  if (!state.status.live) return toast($("#liveNote").textContent);
  const dz = $("#dropzone");
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  dz.classList.add("busy");
  try {
    let text, pages;
    if (ext === "pdf") ({ text, pages } = await readPdf(file));
    else if (ext === "docx") text = await readDocx(file);
    else if (["txt", "md", "text"].includes(ext)) text = await file.text();
    else throw new Error("Use a PDF, Word (.docx) or text file.");
    text = (text || "").trim();
    if (!text) throw new Error("No readable text in that file. If it's a scan, try a PDF with selectable text.");
    const err = checkText(text);
    if (err) throw new Error(err);
    const title = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim() || "Your letter";
    startYourLetter({ title, text, upload: { name: file.name, pages, words: wordCount(text) } });
  } catch (e) {
    toast(e.message);
  } finally {
    dz.classList.toggle("busy", !state.status.live);
  }
}

/* Reads a PDF in the browser, keeping bold (**…**) and large text (## …) for the skim reader. */
async function readPdf(file) {
  const pdfjs = await import(PDFJS);
  pdfjs.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
  const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const pages = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    try { await page.getOperatorList(); } catch { /* fonts unavailable: no bold */ }
    const tc = await page.getTextContent();
    const items = tc.items.filter((it) => it.str && it.str.trim());
    if (!items.length) continue;
    const size = (it) => Math.hypot(it.transform[2], it.transform[3]) || it.height || 10;
    const sorted = items.map(size).sort((a, b) => a - b);
    const body = sorted[Math.floor(sorted.length / 2)];
    const bold = (it) => {
      let name = "";
      try { name = page.commonObjs.get(it.fontName)?.name || ""; } catch { /* not loaded */ }
      return /bold|black|heavy|semibold/i.test(`${name} ${(tc.styles[it.fontName] || {}).fontFamily || ""}`);
    };
    const rows = [];
    for (const it of items) {
      const y = it.transform[5];
      let row = rows.find((r) => Math.abs(r.y - y) < body * 0.45);
      if (!row) rows.push((row = { y, parts: [] }));
      row.parts.push({ x: it.transform[4], w: it.width, s: it.str, b: bold(it), h: size(it) });
    }
    rows.sort((a, b) => b.y - a.y);
    const lines = [];
    let prevY = null;
    for (const r of rows) {
      r.parts.sort((a, b) => a.x - b.x);
      if (prevY != null && prevY - r.y > body * 1.9) lines.push("");
      prevY = r.y;
      const runs = [];
      let lastEnd = null;
      for (const p of r.parts) {
        const space = lastEnd != null && p.x - lastEnd > body * 0.15 ? " " : "";
        const last = runs.at(-1);
        if (last && last.b === p.b) last.t += space + p.s;
        else runs.push({ b: p.b, t: (space && last ? " " : "") + p.s });
        lastEnd = p.x + p.w;
      }
      let text = runs.map((u) => {
        const t = u.t.replace(/\s+/g, " ");
        const core = t.trim();
        return core && u.b ? t.replace(core, `**${core}**`) : t;
      }).join("").replace(/\s+/g, " ").trim();
      if (r.parts.reduce((a, p) => a + p.h, 0) / r.parts.length > body * 1.25) text = "## " + text.replace(/\*\*/g, "");
      lines.push(text);
    }
    pages.push(lines.join("\n"));
  }
  return { text: pages.join("\n\n").replace(/\n{3,}/g, "\n\n"), pages: doc.numPages };
}

function loadScript(src) {
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => fail(new Error("Couldn't load the Word reader. Try saving the letter as a PDF."));
    document.head.appendChild(s);
  });
}

async function readDocx(file) {
  if (!window.mammoth) await loadScript(MAMMOTH);
  const { value } = await window.mammoth.convertToHtml({ arrayBuffer: await file.arrayBuffer() });
  const dom = new DOMParser().parseFromString(value, "text/html");
  const inline = (el) => [...el.childNodes].map((n) => (n.nodeType === 3 ? n.textContent
    : /^(STRONG|B)$/.test(n.nodeName) ? `**${n.textContent.trim()}**` : inline(n))).join("");
  const blocks = [];
  for (const el of dom.body.children) {
    if (/^H[1-6]$/.test(el.nodeName)) blocks.push("## " + el.textContent.trim());
    else if (/^(UL|OL)$/.test(el.nodeName)) blocks.push([...el.children].map((li) => "• " + inline(li).trim()).join("\n"));
    else if (el.nodeName === "TABLE") blocks.push([...el.querySelectorAll("tr")].map((tr) => [...tr.children].map((c) => c.textContent.trim()).join(" | ")).join("\n"));
    else blocks.push(inline(el).trim());
  }
  return blocks.filter(Boolean).join("\n\n");
}

/* ============================================================ your letter */
async function startYourLetter({ title, text, upload }) {
  const cur = { id: null, title, category: "Your letter", source: null, upload, text, fact: null, test: null, fix: null, ui: null,
    keyState: "loading", notes: templateNotes(text) };
  state.cur = cur;
  state.view = "full";
  state.version = "original";
  state.uiLang = "local";
  location.hash = "#/yours";
  try {
    const res = await api("/api/extract", { text });
    cur.ui = res.ui || null;
    delete res.ui;
    cur.fact = res;
    cur.keyState = "review";
  } catch (e) {
    cur.keyState = "error";
    cur.keyError = e.message;
  }
  if (state.cur === cur) swap(renderWork);
}

/* ============================================================ letter page */
async function openSample(id, view, fixed) {
  try {
    const s = state.cur && state.cur.id === id ? state.cur : await api(`/api/sample/${id}`);
    const same = state.cur === s && !$("#work").hidden;
    state.cur = s;
    state.view = view || "full";
    state.version = fixed && s.fix ? "fixed" : "original";
    if (same) return renderWork();
    showWork();
    if (s.test && !s.test.located && state.status.live && !state.status.mock) {
      api("/api/locate", { sample_id: id }).then((r) => {
        if (state.cur === s && r.located) { s.test.located = r.located; renderViewer(); renderSide(); }
      }).catch(() => {});
    }
  } catch (e) {
    toast(e.message);
    goHome();
  }
}

function showWork() {
  $("#home").hidden = true;
  $("#work").hidden = false;
  window.scrollTo(0, 0);
  renderWork();
}

function renderWork() {
  const c = state.cur;
  if (!c) return;
  const title = !c.id && c.upload && c.upload.name === "Pasted text" ? T("your_letter") : c.title;
  document.title = `${title} · Misread`;
  $("#docTitle").textContent = title;
  renderChips();
  renderMode();
  renderViewer();
  renderSide();
}

/* For the writer: what went wrong and how to fix it. For the reader: what the letter asks, and
   the parts to read. Only once there are results. */
/* For the writer: what went wrong and how to fix it. For the reader: what the letter asks, and
   the parts to read. Only once there are results. */
function renderMode() {
  const c = state.cur;
  const seg = $("#modeSeg");
  seg.hidden = !c.test;
  if (!c.test) return;
  seg.innerHTML = [["writer", T("mode_writer")], ["reader", T("mode_reader")]].map(([id, label]) =>
    `<button role="tab" data-mode="${id}" aria-selected="${state.mode === id}">${esc(label)}</button>`).join("");
  seg.onclick = (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b || b.dataset.mode === state.mode) return;
    state.mode = b.dataset.mode;
    try { localStorage.setItem("misread.mode", state.mode); } catch { /* not saved, that's fine */ }
    if (state.mode === "reader") { state.view = "full"; state.version = "original"; }
    swap(() => { renderMode(); renderViewer(); renderSide(); });
  };
}



function renderChips() {
  const c = state.cur;
  const live = state.status.live;
  const job = state.job && state.job.letter === c ? state.job : null;
  const chips = [];
  if (c.source) {
    const s = c.source;
    chips.push(`<a class="chip" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(T("source_original", { name: s.publisher_short || s.publisher }))}</a>`);
    if (s.changes && !/^None\.?$/.test(s.changes)) chips.push(`<button class="chip" id="changesChip" type="button">${esc(T("sample_values"))}</button>`);
  } else if (c.upload) {
    chips.push(`<span class="chip">${esc(c.upload.name === "Pasted text" ? T("pasted_text") : c.upload.name)}</span>`);
    const words = T("words_n", { n: c.upload.words.toLocaleString() });
    chips.push(`<span class="chip">${c.upload.pages ? `${esc(T("pages_n", { n: c.upload.pages }))} · ` : ""}${esc(words)}</span>`);
  }
  const kind = c.fact && c.fact.kind && c.fact.kind !== "letter" && UI_EN[`kind_${c.fact.kind}_chip`];
  if (kind) chips.push(`<span class="chip" title="${esc(T(`kind_${c.fact.kind}_note`))}">⚠ ${esc(T(`kind_${c.fact.kind}_chip`))}</span>`);
  if ((c.notes || []).some((n) => n.key === "note_scrambled")) chips.push(`<span class="chip" title="${esc(T("note_scrambled"))}">⚠ ${esc(T("scrambled_chip"))}</span>`);
  if (job) chips.push(`<span class="chip y">${esc(T("running_live"))}</span>`);
  if (c.test && live && !job) chips.push(`<button class="chip y" data-act="test" type="button">${esc(T("run_again"))}</button>`);
  $("#docChips").innerHTML = chips.join("") + langSwitch(c);
  bindActions($("#docChips"));
  bindLang($("#docChips"));
  const pop = $("#changesPop");
  pop.hidden = true;
  const chip = $("#changesChip");
  if (chip) {
    const local = !english();  // the source note in the letter's language, when the page is
    const doc = (local && c.source.document_local) || c.source.document;
    const changes = (local && c.source.changes_local) || c.source.changes;
    pop.innerHTML = `<b>${esc(doc)}</b>${esc(changes)} <span class="mono small muted">${esc(T("retrieved_on", { date: fmtDate(c.source.retrieved, false, pageLocale()) }))}</span>`;
    chip.onclick = () => { pop.hidden = !pop.hidden; };
  }
}

function bindLang(root) {
  root.querySelectorAll("[data-lang]").forEach((b) => {
    b.onclick = () => { if (b.dataset.lang !== state.uiLang) { state.uiLang = b.dataset.lang; swap(renderWork); } };
  });
  root.querySelectorAll(".read-in").forEach(bindReadMenu);
}

function readSelect(c) {
  const cur = state.readPref || (state.uiLang === "en" ? "English" : c.fact.language || "English");
  const known = READ_IN.some(([v]) => sameLang(v, c.fact.language));
  const own = known ? [] : [[c.fact.language, (c.ui && c.ui._native_name) || c.fact.language]];
  const all = [...own, ...READ_IN];
  const pick = all.find(([v]) => sameLang(v, cur)) || all[0];
  const busy = !!c.readPending;
  const opts = all.map(([v, label]) => {
    const on = sameLang(v, cur);
    const sub = sameLang(label, v) ? "" : `<span class="ri-en">${esc(v)}</span>`;
    return `<li role="option" tabindex="-1" data-read-lang="${esc(v)}" aria-selected="${on}"><span class="ri-native">${esc(label)}</span>${sub}</li>`;
  }).join("");
  return `<div class="read-in">
    <span class="read-in-label">${esc(T("read_in"))}</span>
    <button type="button" class="read-in-btn" data-read-toggle aria-haspopup="listbox" aria-expanded="false"${busy ? " disabled" : ""}>
      <span>${esc(busy ? T("translating") : pick[1])}</span>
      <svg viewBox="0 0 12 8" aria-hidden="true"><path d="M1 1.5 6 6.5 11 1.5"/></svg></button>
    <ul class="read-in-menu" role="listbox" aria-label="${esc(T("read_in"))}" hidden>${opts}</ul></div>`;
}

/* The Reader view's language menu: a button that opens a listbox (mouse, touch and keyboard). */
function bindReadMenu(box) {
  const btn = box.querySelector("[data-read-toggle]"), menu = box.querySelector(".read-in-menu");
  if (!btn || !menu) return;
  const items = () => [...menu.querySelectorAll("[data-read-lang]")];
  const open = (focusIt) => {
    menu.hidden = false; btn.setAttribute("aria-expanded", "true");
    if (focusIt) (menu.querySelector('[aria-selected="true"]') || items()[0]).focus();
  };
  const close = (focusBtn) => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); if (focusBtn) btn.focus(); };
  btn.onclick = (e) => { e.stopPropagation(); menu.hidden ? open(false) : close(false); };
  btn.onkeydown = (e) => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); open(true); } };
  menu.onclick = (e) => {
    const li = e.target.closest("[data-read-lang]");
    if (li) { close(false); chooseReadIn(li.dataset.readLang); }
  };
  menu.onkeydown = (e) => {
    const list = items(), i = list.indexOf(document.activeElement);
    const go = (j) => { e.preventDefault(); list[(j + list.length) % list.length].focus(); };
    if (e.key === "ArrowDown") go(i + 1);
    else if (e.key === "ArrowUp") go(i - 1);
    else if (e.key === "ArrowRight") go(i + 1);
    else if (e.key === "ArrowLeft") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(list.length - 1);
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if ((e.key === "Enter" || e.key === " ") && i >= 0) { e.preventDefault(); close(false); chooseReadIn(list[i].dataset.readLang); }
    else if (e.key === "Tab") close(false);
  };
}
document.addEventListener("click", (e) => {
  if (e.target.closest(".read-in")) return;
  document.querySelectorAll(".read-in-menu:not([hidden])").forEach((m) => {
    m.hidden = true;
    m.parentElement.querySelector("[data-read-toggle]")?.setAttribute("aria-expanded", "false");
  });
});

function chooseReadIn(lang) {
  const c = state.cur;
  state.readPref = lang;
  try { localStorage.setItem("misread.readIn", lang); } catch { /* remembered for this visit only */ }
  if (needsReadIn(c)) loadReadIn(c);
  else swap(renderWork);
}

const needsReadIn = (c) => {
  const pick = readPick(c);
  return !!pick && !sameLang(pick, "English") && !sameLang(pick, c.fact.language) && !(c.readCache && pick in c.readCache);
};

async function loadReadIn(c) {
  const lang = state.readPref;
  if (c.readPending) return;
  c.readPending = lang;
  renderSide();  // shows "translating" next to the menu
  c.readCache = c.readCache || {};
  try {
    const body = c.id ? { sample_id: c.id, language: lang }
      : { language: lang, fact: c.fact, cards: c.test.cards.map((q) => ({ said: q.said, truth: q.truth })) };
    c.readCache[lang] = await api("/api/read_in", body);
  } catch (e) {
    c.readCache[lang] = null;  // not retried on every redraw; picking the language again retries
    toast(e.message);
  } finally {
    c.readPending = null;
  }
  if (state.cur === c) swap(renderWork);
}

/* ---------------------------------------------------------- the letter window */
function scoreFor(id) {
  const c = state.cur;
  if (state.version === "fixed" && c.fix) return id === "full" ? null : c.fix.after.by_view[id];
  return c.test ? c.test.views[id].score : null;
}

function renderViewer() {
  const c = state.cur;
  const tested = !!c.test;
  const reader = tested && state.mode === "reader";
  $("#viewTabs").innerHTML = reader ? `<span class="tabs-note">${esc(T("tabs_note"))}</span>` : VIEWS.map((v) => {
    const sc = scoreFor(v.id);
    const off = !tested && v.id !== "full";
    return `<button role="tab" data-view="${v.id}" aria-selected="${state.view === v.id}" ${off ? `aria-disabled="true" title="${esc(T("after_test"))}"` : ""}>
      ${esc(T("view_" + v.id))}${sc == null ? "" : `<span class="n ${tone(sc)}">${Math.round(sc)}</span>`}</button>`;
  }).join("");
  $("#viewTabs").onclick = (e) => {
    const b = e.target.closest("button[data-view]");
    if (!b || b.getAttribute("aria-disabled") === "true" || b.dataset.view === state.view) return;
    state.view = b.dataset.view;
    swap(renderViewer);
  };

  const seg = $("#versionSeg");
  seg.hidden = !c.fix || reader;
  if (c.fix && !reader) {
    seg.innerHTML = `<button data-version="original" aria-selected="${state.version === "original"}">${esc(T("original"))}</button>
      <button data-version="fixed" aria-selected="${state.version === "fixed"}">${esc(T("fixed"))}</button>`;
    seg.onclick = (e) => {
      const b = e.target.closest("button[data-version]");
      if (!b || b.dataset.version === state.version) return;
      state.version = b.dataset.version;
      swap(() => { renderViewer(); renderSide(); });
    };
  }

  const fixed = state.version === "fixed" && c.fix && !reader;

  const text = fixed ? c.fix.fixed_views[state.view] : tested ? c.test.views[state.view].text : state.view === "full" ? c.text : "";
  const located = !fixed && tested && c.test.located;
  const marks = !located || state.view !== "full" ? []
    : reader ? SLOTS.filter((s) => located[s] && !unstated(c.fact.facts[s])).map((s) => ({ slot: s, text: located[s].replace(BULLET, ""), cls: "read", label: T(READER_KEY[s]) }))
    : SLOTS.filter((s) => located[s] && c.test.status[s]).map((s) => ({ slot: s, text: located[s].replace(BULLET, ""), cls: c.test.status[s], label: T("slot_" + s) }));
  const heading = (c.fix && c.fix.box_heading) || (c.fact && c.fact.box_heading) || "What you need to do";
  const says = tested && c.test.checklist ? c.test.checklist.some((i) => i.key === "ck_rep_no" || /repeats itself/.test(i.title || "")) : undefined;
  const body = renderLetter(text || "", marks, c.fix ? c.fix.change.keeps_wording : true, heading, says);
  const busy = !!(state.job && state.job.letter === c) || c.keyState === "loading";
  $("#stage").className = `stage${busy ? " scanning" : ""}`;
  $("#stage").innerHTML = state.view === "phone"
    ? `<div class="phone"><div class="notch"></div><div class="content">${body}</div><div class="cut"><span class="chip">${esc(T("stop_here"))}</span></div></div>`
    : `<article class="page ${state.view === "full" ? "" : "partial"}">${body}</article>`;
}

const OPEN = (i) => `${i}`;
const CLOSE = "";

// Exact repeats: a paragraph or sentence that already appeared earlier in the letter.
// Spacing, capitals and punctuation are ignored; short bits ("Dear Member,") never count.
const normal = (s) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
// Chinese, Japanese and Korean have no spaces: about two characters make a word
const wordsIn = (k) => Math.max(k.split(" ").length, Math.round((k.match(/[぀-ヿ㐀-鿿가-힯]/g) || []).length / 2));
const substantial = (k) => wordsIn(k) >= 4;
// a short repeat is usually a form's labels or table headers, not a copy-paste mistake
const REPEAT_SENTENCE = 8, REPEAT_RUN = 25;
// page furniture (a form number or footer printed on every page) is mostly codes and numbers
const furniture = (s) => {
  const words = s.trim().split(/\s+/);
  return words.filter((w) => /\d/.test(w) || /^[A-Z][A-Z.-]+$/.test(w)).length >= words.length * 0.4;
};
const isBoxBlock = (block, heading) => {
  const first = block.trim().split("\n")[0].trim();
  return first === "## " + heading || first === "## What you need to do";
};

function findRepeats(text, heading, says) {
  const seen = new Set(), seenBlocks = new Set(), blocks = new Set(), spots = [];
  const breaks = /\n\s*\n/g;
  const ranges = [];
  let start = 0, m;
  while ((m = breaks.exec(text))) { ranges.push([start, m.index]); start = m.index + m[0].length; }
  ranges.push([start, text.length]);
  const size = [], inside = [];
  let total = 0, repeated = 0;  // the share of words said twice, as in the letter checklist
  const once = new Set();
  ranges.forEach(([from, to], b) => {
    const block = text.slice(from, to);
    if (isBoxBlock(block, heading)) return;  // the added summary box restates the letter on purpose
    const sentence = /(?:[^\n.!?。！？]|[.!?](?=\S))+[.!?。！？]*/gu;
    let subs = 0;
    const reps = [];
    while ((m = sentence.exec(block))) {
      const key = normal(m[0]);
      if (!key) continue;
      total += wordsIn(key);
      if (once.has(key)) repeated += wordsIn(key);
      once.add(key);
      if (!substantial(key) || furniture(m[0])) continue;
      subs++;
      const lead = m[0].length - m[0].trimStart().length;
      if (seen.has(key) && wordsIn(key) >= REPEAT_SENTENCE) reps.push({ at: from + m.index + lead, end: from + m.index + m[0].trimEnd().length });
      seen.add(key);
    }
    const whole = normal(block);
    size[b] = wordsIn(whole);
    inside[b] = reps;
    if ((subs && reps.length === subs) || (size[b] >= 4 && seenBlocks.has(whole))) blocks.add(b);
    else spots.push(...reps);
    seenBlocks.add(whole);
  });
  // a lone short repeated paragraph is shown sentence by sentence instead of boxed
  for (let b = 0; b < ranges.length; b++) {
    if (!blocks.has(b)) continue;
    const run = [];
    while (blocks.has(b)) run.push(b++);
    if (run.length < 2 && size[run[0]] < REPEAT_RUN) run.forEach((x) => { blocks.delete(x); spots.push(...inside[x]); });
  }
  // flag nothing unless the letter checklist says the letter repeats itself (10% or more);
  // before a test there is no checklist yet, so the same share is worked out here
  if (says === false || (says == null && (!total || repeated / total < 0.1))) return { blocks: new Set(), spots: [] };
  return { blocks, spots };
}

function renderLetter(text, marks, keepsWording, heading = "What you need to do", says) {
  const rep = findRepeats(text, heading, says);
  marks = marks.concat(rep.spots.map(() => ({ slot: "", cls: "repeat", label: T("repeated") })));
  const spots = [];
  marks.forEach((m, i) => {
    if (m.cls === "repeat") return;
    const at = text.indexOf(m.text);
    if (at >= 0 && !spots.some((s) => at < s.end && at + m.text.length > s.at)) spots.push({ at, end: at + m.text.length, i });
  });
  rep.spots.forEach((r, j) => {
    if (!spots.some((s) => r.at < s.end && r.end > s.at)) spots.push({ ...r, i: marks.length - rep.spots.length + j });
  });
  spots.sort((a, b) => b.at - a.at);
  for (const s of spots) text = text.slice(0, s.at) + OPEN(s.i) + text.slice(s.at, s.end) + CLOSE + text.slice(s.end);
  const lead = /^(?:\d+)?/;
  const parts = esc(text).split(/\n\s*\n/).map((block) => {
    const lines = block.split("\n").filter((l) => l.trim());
    const first = (lines[0] || "").replace(lead, "").trim();
    const isBox = first === "## " + esc(heading) || first === "## What you need to do";
    const inner = lines.map((line) => {
      const m = line.match(lead)[0];
      const rest = line.slice(m.length);
      if (rest.startsWith("## ")) return `<h3>${m}${inline(rest.slice(3))}</h3>`;
      if (/^\s*(?:[•●▪◦–-]|\d{1,2}[.)])\s/.test(rest)) return `<div class="li">${m}${inline(rest)}</div>`;
      return `<p>${m}${inline(rest)}</p>`;
    }).join("");
    if (isBox) return `<div class="fixbox"><span class="fixbox-tag">${esc(T(keepsWording ? "added_same" : "added_reworded"))}</span>${inner}</div>`;
    return `<div class="blk">${inner}</div>`;
  });
  // runs of repeated paragraphs share one red box
  let html = "";
  for (let b = 0; b < parts.length; b++) {
    if (!rep.blocks.has(b)) { html += parts[b]; continue; }
    let run = "";
    while (rep.blocks.has(b)) run += parts[b++];
    b--;
    html += `<div class="repeat-box"><span class="repeat-tag">${esc(T("repeated_block"))}</span>${run}</div>`;
  }
  return html
    .replace(/(\d+)/g, (_, i) => `<mark class="hl-m ${marks[i].cls}" data-slot="${marks[i].slot}" data-label="${esc(marks[i].label)}">`)
    .replace(//g, "</mark>");
}

function inline(s) {
  return s.replace(/\s##\s+/g, " ").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*\*/g, "")
    .replace(/…/g, `<span class="skip">${esc(T("skipped"))}</span>`);
}

/* ---------------------------------------------------------- side tiles */
function renderSide() {
  const c = state.cur;
  const job = state.job && state.job.letter === c ? state.job : null;
  const tiles = [];
  if (!c.test) {
    if (job) tiles.push(progressTile(job, T("prog_test"), TEST_STEPS, true));
    else if (c.id) tiles.push(runTile());
    else tiles.push(keyTile(c));
  } else if (state.mode === "reader") {
    if (needsReadIn(c) && !c.readPending) setTimeout(() => loadReadIn(c), 0);
    tiles.push(readerTile(c));
    if (c.test.cards.length) tiles.push(watchTile(c));
  } else if (c.test.testable === false) {
    tiles.push(nothingTile());
    if (c.test.checklist) tiles.push(checklistTile(c.test));
  } else if (state.version === "fixed" && c.fix) {
    tiles.push(scoreTile(c.fix.after.score, T(c.fix.after.misread_rate === 0 ? "fix_none_wrong" : "fix_fewer"), T("was_before", { n: Math.round(c.fix.before.score) })));
    tiles.push(fixTile(c));
  } else {
    if (job && job.kind === "test") tiles.push(progressTile(job, T("prog_test"), TEST_STEPS, true));
    else tiles.push(scoreTile(c.test.overall.busy, verdict(c.test), T("full_read_n", { n: Math.round(c.test.overall.careful) }), c.test.readers_blank));
    tiles.push(mistakesTile(c.test));
    tiles.push(job && job.kind === "fix" ? progressTile(job, T("prog_fix"), FIX_STEPS, false) : fixTile(c));
    if (c.test.checklist) tiles.push(checklistTile(c.test));
  }
  if ((c.test || c.fact) && state.mode !== "reader") tiles.push(detailsTile(c));
  const side = $("#side");
  side.innerHTML = tiles.join("");
  bindActions(side);
  side.querySelectorAll(".mistake[data-slot]").forEach((b) => { b.onclick = () => jumpTo(b.dataset.slot); });
  bindLang(side);
  const form = $("#keyForm");
  if (form) form.onsubmit = submitKey;
  requestAnimationFrame(() => {
    side.querySelectorAll("[data-count]").forEach((el) => countUp(el, +el.dataset.count, +(el.dataset.from || 0)));
    side.querySelectorAll(".mini-bars .tr i").forEach((b) => { b.style.width = b.dataset.w; });
  });
}

function bindActions(root) {
  root.querySelectorAll("[data-act]").forEach((b) => { b.onclick = () => ACTIONS[b.dataset.act](b); });
}

function verdict(t) {
  const wrong = SLOTS.filter((s) => t.status[s] === "wrong");
  if (t.cards.some((q) => q.slot === "need_to_act")) wrong.unshift("need_to_act");
  const missed = SLOTS.filter((s) => t.status[s] === "missing");
  if (wrong.length) return T("verdict_wrong", { list: joinList(wrong.map((s) => T("phrase_" + s))) });
  if (missed.length) return T("verdict_missed", { list: joinList(missed.map((s) => T("phrase_" + s))) });
  return T("verdict_ok");
}

function scoreTile(score, line, sub, blank) {
  const s = Math.round(score);
  return `<div class="tile score-tile s-${tone(s)}">
    <div class="score-num"><span data-count="${s}">${s}</span><small>/100</small></div>
    <div><p>${esc(line)}</p><span class="mono small">${esc(sub)}</span>${blank ? `<p class="warn">${esc(T("note_blank_readers"))}</p>` : ""}</div></div>`;
}

/* A card's texts in the chosen language: the reader's view translations hold both versions. */
function cardText(c, i, field, fallback) {
  const i18n = c.test && c.test.reader_i18n;
  const pick = i18n && i18n[state.uiLang === "en" ? "en" : "local"];
  return (pick && pick[`card${i}_${field}`]) || fallback;
}

function mistakesTile(t) {
  const c = state.cur;
  if (!t.cards.length) {
    return `<div class="tile goodnews"><h2>${esc(T("wrong_title"))}</h2><p>${esc(T("nothing_wrong"))} ${esc(T(t.overall.busy < 85 ? "missed_no_wrong" : "all_understood"))}</p></div>`;
  }
  const located = t.located || {};
  return `<div class="tile"><h2>${esc(T("wrong_title"))} <span class="chip">${t.cards.length}</span></h2>${t.cards.map((q, i) => {
    const jump = q.slot !== "need_to_act" && located[q.slot];
    const truth = cardText(c, i, "truth", q.truth);
    return `<button class="mistake" ${jump ? `data-slot="${q.slot}" title="${esc(T("show_in_letter"))}"` : "disabled"}>
      <span class="mistake-head"><span class="tag">${esc(T("slot_" + q.slot))}</span><span class="mono small muted">${esc(T("view_" + q.view).toLowerCase())} · ${q.count}/${q.of}</span></span>
      <span class="said">“${esc(cap(cardText(c, i, "said", q.said)))}”</span>
      <span class="truth" title="${esc(truth)}"><b>${esc(T("actually"))}</b>${esc(truth)}</span>${coachHtml(q.coach)}</button>`;
  }).join("")}</div>`;
}

function coachHtml(tip) {
  if (!tip) return "";
  const en = state.uiLang === "en" && (tip.why_en || tip.fix_en);
  const why = en ? tip.why_en || tip.why : tip.why, fix = en ? tip.fix_en || tip.fix : tip.fix;
  return `<span class="coach"><b>${esc(T("coach_why"))}</b>${esc(why)}</span><span class="coach"><b>${esc(T("coach_fix"))}</b>${esc(fix)}</span>`;
}

function checklistTile(t) {
  const title = (i) => (i.key ? T(i.key + "_title", i.vars) : i.title);
  const detail = (i) => (i.key ? T((i.detail_key || i.key) + "_detail", i.vars) : i.detail);
  return `<div class="tile"><h2>${esc(T("checklist_title"))}</h2><ul class="checklist">${t.checklist.map((i) =>
    `<li class="${i.ok ? "ok" : "no"}"><span class="ic">${i.ok ? "✓" : "!"}</span><div><b>${esc(title(i))}</b><span>${esc(detail(i))}</span></div></li>`).join("")}</ul></div>`;
}

function nothingTile() {
  return `<div class="tile score-tile s-none"><div class="score-num">—</div>
    <div><p>${esc(T("nothing_title"))}</p><span class="mono small">${esc(T("nothing_detail"))}</span></div></div>`;
}

/* The reader's view, in English or in the letter's own language (when it isn't English). */
const READER_TEXT = {
  in_short: "In short", what_to_do: "What to do", by_when: "By when", if_you_dont: "If you don't",
  who_to_contact: "Who to contact", nothing_to_do: "Nothing you need to do right now.",
  highlights: "The highlighted parts of the letter say this.",
  mistakes_title: "Mistakes people make when they skim this", skim_think: "If you only skim, you might think", actually: "But actually",
};
const READER_KEY = { action: "what_to_do", deadline: "by_when", consequence: "if_you_dont", contact: "who_to_contact" };

function readerText(c) {
  const lang = readPick(c);
  const r = lang && c.readCache && c.readCache[lang];
  if (r && r.text) return (key, fallback) => r.text[key] || fallback || T(key);
  const i18n = c.test && c.test.reader_i18n;
  const en = lang ? sameLang(lang, "English") : state.uiLang === "en";
  const pick = i18n && i18n[en ? "en" : "local"];
  return (key, fallback) => (pick && pick[key]) || fallback || T(key);
}

/* English | the letter's language, for the whole letter page (never the front page or top bar). */
function langSwitch(c, where) {
  if (state.mode === "reader" && c.test) return where === "reader" ? readSelect(c) : "";
  if (!c.ui) return "";
  const local = state.uiLang !== "en";
  return `<span class="lang-seg" role="tablist" aria-label="Language">
    <button type="button" data-lang="en" aria-selected="${!local}">English</button>
    <button type="button" data-lang="local" aria-selected="${local}">${esc(c.ui._native_name || c.fact.language)}</button></span>`;
}

function readerTile(c) {
  const f = c.fact, t = readerText(c);
  const rows = SLOTS.filter((s) => !unstated(f.facts[s]) && !(s === "action" && f.action_required === false))
    .map((s) => `<dt>${esc(T(READER_KEY[s]))}</dt><dd>${esc(t("fact_" + s, f.facts[s]))}</dd>`).join("");
  const none = f.action_required === false ? `<p class="ok-note">${esc(T("nothing_to_do"))}</p>` : "";
  const gist = t("summary", f.summary || (c.source && c.source.summary) || "");
  return `<div class="tile reader-tile"><h2>${esc(T("in_short"))}${langSwitch(c, "reader")}</h2>${gist ? `<p class="gist">${esc(gist)}</p>` : ""}${none}
    ${rows ? `<dl class="todo">${rows}</dl>` : ""}
    <span class="mono small muted">${esc(T("highlights"))}</span></div>`;
}

function watchTile(c) {
  const t = readerText(c);
  return `<div class="tile"><h2>${esc(T("mistakes_title"))}${langSwitch(c)}</h2>${c.test.cards.map((q, i) => `<div class="watch">
    <span class="mono small muted">${esc(T("skim_think"))}</span>
    <span class="said">“${esc(cap(t(`card${i}_said`, q.said)))}”</span>
    <span class="truth"><b>${esc(T("but_actually"))}</b>${esc(t(`card${i}_truth`, q.truth))}</span></div>`).join("")}</div>`;
}

function runTile() {
  const live = state.status.live;
  return `<div class="tile"><h2>${esc(T("test_this"))}</h2>
    <button class="btn primary big" data-act="test" ${live ? "" : "disabled"}>${esc(T("run_test"))}</button>
    ${live ? "" : `<span class="mono small muted">${esc(T("live_off"))}</span>`}</div>`;
}

function keyTile(c) {
  if (c.keyState === "loading") {
    // the letter's language isn't known yet: for a letter not written in Latin letters, show no English words
    const letters = c.text.match(/\p{L}/gu) || [];
    const latin = letters.filter((ch) => /[A-Za-z]/.test(ch)).length;
    const words = !letters.length || latin / letters.length >= 0.5;
    return `<div class="tile">${words ? `<p class="prog-title">${esc(T("key_loading_title"))}</p>` : ""}
      <span class="mono small muted">Nemotron 3 Ultra${words ? ` · ${esc(T("key_loading_sub"))}` : ""}</span>
      <div class="bar"><i style="width:100%"></i></div></div>`;
  }
  if (c.keyState === "error") {
    return `<div class="tile"><h2>${esc(T("key_error_title"))}</h2><p>${esc(c.keyError)}</p><button class="btn" data-act="retryKey">${esc(T("try_again"))}</button></div>`;
  }
  const f = c.fact;
  const need = f.action_required === true ? "yes" : f.action_required === false ? "no" : "conditional";
  const area = (s, rows = 2) => `<label for="k_${s}">${esc(T("slot_" + s))}</label><textarea id="k_${s}" name="${s}" rows="${rows}">${esc(f.facts[s])}</textarea>`;
  const kindNote = f.kind && f.kind !== "letter" && UI_EN[`kind_${f.kind}_note`] && !(f.kind === "template" && (c.notes || []).length)
    ? [T(`kind_${f.kind}_note`)] : [];
  const notes = [...kindNote, ...(c.notes || []).map((n) => T(n.key, n.vars))].map((n) => `<p class="warn">${esc(n)}</p>`).join("");
  return `<div class="tile form"><h2>${esc(T("key_title"))}</h2>
    <span class="mono small muted">${esc(T("key_sub"))}</span>${notes}
    <form id="keyForm">
      <label for="k_need">${esc(T("need_label"))}</label>
      <select id="k_need" name="need">
        <option value="yes" ${need === "yes" ? "selected" : ""}>${esc(T("opt_yes"))}</option>
        <option value="no" ${need === "no" ? "selected" : ""}>${esc(T("opt_no"))}</option>
        <option value="conditional" ${need === "conditional" ? "selected" : ""}>${esc(T("opt_some"))}</option>
      </select>
      ${area("action", 3)}${area("deadline")}${area("consequence")}${area("contact")}
      <div style="margin-top:16px"><button class="btn primary big" type="submit">${esc(T("run_test"))}</button></div>
    </form></div>`;
}

function submitKey(e) {
  e.preventDefault();
  const c = state.cur;
  const f = e.target;
  // keep everything the answer key already knows (language, summary, box heading...)
  c.fact = {
    ...c.fact, title: c.fact.title || c.title, design: "unknown",
    action_required: f.need.value === "yes" ? true : f.need.value === "no" ? false : "conditional",
    facts: Object.fromEntries(SLOTS.map((s) => [s, f[s].value.trim() || "Not stated in the letter."])),
  };
  runJob("test");
}

function progressTile(job, title, steps, readersGrid) {
  const now = steps.findIndex((s) => s.match.test(job.label || ""));
  const list = steps.map((s, i) => {
    const done = now > i;
    const cls = done ? "done" : i === now ? "now" : "";
    return `<li class="${cls}"><span class="ic">${done ? "✓" : i + 1}</span><span>${esc(T(s.label))}<span class="model">${s.model}</span></span></li>`;
  }).join("");
  const w = job.total ? Math.max(4, Math.round((100 * job.done) / job.total)) : 4;
  const secs = job.seconds || 0;
  let grid = "";
  if (readersGrid) {
    const done = job.done || 0;
    grid = `<div class="readers">${VIEWS.map((v, r) => `<span>${esc(T("view_" + v.id).split(" ")[0])}</span>${[0, 1, 2].map((k) => {
      const i = r * 3 + k;
      return `<span class="cell ${i < done ? "done" : i === done && now === 1 ? "now" : ""}"></span>`;
    }).join("")}`).join("")}</div>`;
  }
  return `<div class="tile" id="prog"><p class="prog-title">${esc(title)}</p>${grid}<ol class="steps">${list}</ol>
    <div class="bar"><i style="width:${w}%"></i></div>
    <div class="bar-label"><span>${esc(job.total ? T("readings_n", { done: job.done, total: job.total }) : T("starting"))}</span><span>${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}</span></div></div>`;
}

function describeChange(desc) {
  return desc.replace(/(\d+) key sentence\(s\)/, (_, n) => (n === "1" ? "1 key sentence" : `${n} key sentences`))
    .replace(/^REWORD the /, "Reword the ").replace(/ \(changes wording, needs review\)/, "");
}

function fixTile(c) {
  const f = c.fix;
  const live = state.status.live;
  if (!f) {
    return `<div class="tile fix-tile"><h2>${esc(T("fix_title"))}</h2>
      <p>${esc(T("fix_pitch"))}</p>
      <button class="btn primary big" data-act="fix" ${live ? "" : "disabled"}>${esc(T("fix_button"))}</button></div>`;
  }
  const local = !english();
  const desc = (d, dl) => (local && dl ? dl : describeChange(d));
  const b = Math.round(f.before.score), a = Math.round(f.after.score);
  const bars = BUSY.map((v) => {
    const vb = f.before.by_view[v] ?? 0, va = f.after.by_view[v] ?? 0;
    return `<div class="r"><span>${esc(T("view_" + v).toLowerCase())}</span><span class="tr"><i data-w="${va}%"></i><s style="left:${vb}%" title="${esc(T("before_n", { n: Math.round(vb) }))}"></s></span><span>${Math.round(va)}</span></div>`;
  }).join("");
  const words = [...new Set(f.warnings.map((w) => `“${w.word}”`))].join(", ");
  const warn = f.warnings.length ? `<p class="warn"><b>${esc(T("check_label"))}</b> ${esc(T("points_wrong", { words }))}</p>` : "";
  const tried = f.tried.map((t) => `<li class="${t.desc === f.change.desc ? "picked" : ""}">${esc(desc(t.desc, t.desc_local))} — ${Math.round(t.confirm ?? t.screen)}</li>`).join("");
  return `<div class="tile fix-tile">
    <h2>${esc(T("the_fix"))} <span class="chip">${esc(T(f.change.keeps_wording ? "same_words" : "reworded"))}</span></h2>
    <div class="ba"><span class="n c-${tone(b)}">${b}</span><span class="arrow">→</span><span class="n c-${tone(a)}" data-count="${a}" data-from="${b}">${a}</span></div>
    <p class="fix-what">${esc(desc(f.change.desc, f.change.desc_local))}</p>
    <div class="mini-bars">${bars}</div>
    ${warn}
    <div class="row">
      <button class="btn dark" data-act="toggleFixed">${esc(T(state.version === "fixed" ? "back_original" : "see_fixed"))}</button>
      <button class="btn small" data-act="download">${esc(T("download"))}</button>
    </div>
    <details class="more"><summary>${esc(T("changes_tried", { n: f.tried.length }))}</summary><ol>${tried}</ol></details>
    ${live ? `<button class="btn ghost small" data-act="fix">${esc(T("fix_again"))}</button>` : ""}</div>`;
}

function detailsTile(c) {
  const parts = [];
  const t = c.test;
  const pip = { found: T("pip_right"), missing: T("pip_missed"), wrong: T("pip_wrong") };
  if (t) {
    const cols = ["full", ...BUSY];
    parts.push(`<details class="more"><summary>${esc(T("every_answer"))}</summary><table class="dots-table"><tr><th></th>${cols.map((v) => `<th>${esc(T("view_" + v).split(" ")[0])}</th>`).join("")}</tr>${t.slots.map((s) => `<tr><td>${esc(T("slot_" + s))}</td>${cols.map((v) => `<td><span class="pips">${(t.grid[s][v] || []).map((l) => `<i class="${l}" title="${esc(pip[l] || l)}"></i>`).join("")}</span></td>`).join("")}</tr>`).join("")}</table></details>`);
  }
  if (c.fact && c.fact.facts && t) {
    const f = c.fact;
    parts.push(`<details class="more"><summary>${esc(T("answer_key"))}</summary><dl>${SLOTS.map((s) => `<dt>${esc(T("slot_" + s))}</dt><dd>${esc(f.facts[s])}</dd>`).join("")}</dl></details>`);
  }
  return parts.length ? `<div class="tile">${parts.join("")}</div>` : "";
}

function jumpTo(slot) {
  const go = () => {
    const m = document.querySelector(`#stage mark[data-slot="${slot}"]`);
    if (!m) return toast(T("not_highlighted"));
    m.scrollIntoView({ block: "center", behavior: "smooth" });
    m.classList.remove("flash");
    void m.offsetWidth;
    m.classList.add("flash");
  };
  if (state.view !== "full" || state.version !== "original") {
    state.view = "full";
    state.version = "original";
    swap(() => { renderViewer(); renderSide(); }).then(go);
  } else go();
}

/* ============================================================ actions + jobs */
const ACTIONS = {
  test: () => runJob("test"),
  fix: () => runJob("fix"),
  retryKey: () => { const c = state.cur; startYourLetter({ title: c.title, text: c.text, upload: c.upload }); },
  toggleFixed: () => {
    state.version = state.version === "fixed" ? "original" : "fixed";
    state.view = "full";
    swap(() => { renderViewer(); renderSide(); });
    $("#window").scrollIntoView({ behavior: "smooth", block: "start" });
  },
  download: () => {
    const c = state.cur;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([c.fix.fixed_text.replace(/^## /gm, "").replace(/\*\*/g, "")], { type: "text/plain" }));
    a.download = `${(c.id || c.title).replace(/\s+/g, "-").toLowerCase()}-fixed.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

async function runJob(kind) {
  const letter = state.cur;
  if (state.job) return toast(T("one_run"));
  let id;
  try {
    ({ job: id } = await api(`/api/${kind}`, { text: letter.test ? letter.test.letter : letter.text, fact: letter.fact, sample_id: letter.id }));
  } catch (e) {
    return toast(e.message);
  }
  state.job = { id, kind, letter, label: "Starting", done: 0, total: 0, seconds: 0 };
  if (state.cur === letter) swap(() => { renderChips(); renderViewer(); renderSide(); });
  for (;;) {
    await sleep(800);
    let j;
    try { j = await api(`/api/job/${id}`); } catch { continue; }
    Object.assign(state.job, j);
    if (j.status === "running") {
      const p = $("#prog");
      if (p && state.cur === letter) {
        p.outerHTML = kind === "test" ? progressTile(state.job, "Reading it 12 ways", TEST_STEPS, true) : progressTile(state.job, "Trying fixes", FIX_STEPS, false);
        $("#prog").style.animation = "none";
      }
      continue;
    }
    state.job = null;
    if (j.status === "error") {
      toast(T("run_stopped", { msg: j.error }));
    } else {
      letter[kind] = j.result;
      if (kind === "fix") { state.version = "fixed"; state.view = "full"; }
      const row = state.samples.find((r) => r.id === letter.id);
      if (row && kind === "test") {
        row.busy = Math.round(j.result.overall.busy);
        row.teaser = j.result.cards[0] ? { label: j.result.cards[0].label, said: j.result.cards[0].said, truth: j.result.cards[0].truth } : null;
      }
      if (row && kind === "fix") row.has_fix = true;
      renderHome();
    }
    if (state.cur === letter) swap(renderWork);
    return;
  }
}

init();
