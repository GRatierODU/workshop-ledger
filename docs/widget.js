// Workshop Ledger widget for Scriptable (iPhone / iPad).
// Small: rotates through a global page and one page per mod (next page on each refresh).
// Medium: totals + top mods. Large: totals + every mod + best rankings.
// Tap the widget to open the dashboard. Data refreshes on its own about every 10–15 min
// (iOS decides the exact moment).

const SITE = "https://gratierodu.github.io/workshop-ledger/";
const GOLD = new Color("#d4ab4f"), INK = new Color("#ece8df"), MUTED = new Color("#9a948a");
const UP = new Color("#6cc27a"), DOWN = new Color("#e57373"), BG = new Color("#15161a");

async function getJSON(path) {
  const r = new Request(SITE + path + "?t=" + Date.now());
  r.timeoutInterval = 20;
  return await r.loadJSON();
}

const plural = (n, word) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
const fmt = (n) => (n == null ? "–" : Number(n).toLocaleString("en-US"));
const short = (t) => t.replace(/^AGOT\s*-\s*/i, "").replace(/^The\s+/i, "");
const pct = (m) => (m.up != null && m.up + m.down > 0 ? Math.round((m.up / (m.up + m.down)) * 100) + "%" : "–");
const stars = (m) => (m.stars ? "★".repeat(m.stars) + "☆".repeat(5 - m.stars) : "");
function ago(t) {
  const s = Date.now() / 1000 - t;
  if (s < 90) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return Math.round(s / 86400) + " d ago";
}

function text(stack, str, size, color, bold) {
  const t = stack.addText(str);
  t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.textColor = color || INK;
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.7;
  return t;
}

function delta(stack, v, size) {
  if (v == null || v === 0) return;
  text(stack, (v > 0 ? " +" : " ") + fmt(v), size, v > 0 ? UP : DOWN, true);
}

// Page dots for the rotating small widget (gold = this page), with the data age.
function dots(w, page, pages, stats) {
  w._dots = { page, pages, stats };
}
function drawDots(w) {
  if (!w._dots) return;
  const { page, pages } = w._dots;
  w.addSpacer(4);
  const row = w.addStack();
  row.centerAlignContent();
  row.addSpacer();
  for (let i = 0; i < pages; i++) {
    text(row, "●", i === page ? 8 : 6, i === page ? GOLD : MUTED);
    if (i < pages - 1) row.addSpacer(3);
  }
  row.addSpacer();
}

const RANK_LABELS = { trend_agot: "trending AGOT", trend_all: "trending CK3", subs_agot: "AGOT by subs", subs_all: "CK3 by subs" };

function bestRank(ins, id) {
  const r = ins && ins.ranks && ins.ranks[id];
  if (!r) return null;
  const k = Object.keys(RANK_LABELS).filter((k) => r[k]).sort((a, b) => r[a] - r[b])[0];
  return k ? `#${r[k]} ${RANK_LABELS[k]}` : null;
}

function stat(row, value, label) {
  const col = row.addStack();
  col.layoutVertically();
  text(col, value, 14, INK, true);
  text(col, label, 8, MUTED);
}

function globalPage(w, mods, page, pages, ins, stats, d1, up, down) {
  w.url = SITE;
  const head = w.addStack();
  head.centerAlignContent();
  text(head, "WORKSHOP LEDGER", 10, GOLD, true);
  head.addSpacer();
  text(head, ago(stats.fetched), 9, MUTED);
  w.addSpacer(3);
  const tot = w.addStack();
  tot.bottomAlignContent();
  text(tot, fmt(mods.reduce((a, m) => a + (m.subs || 0), 0)), 24, INK, true);
  delta(tot, d1, 11);
  text(w, "subscribers" + (up + down ? ` · ${Math.round((up / (up + down)) * 100)}% positive` : ""), 10, MUTED);
  w.addSpacer(6);
  const row = w.addStack();
  stat(row, fmt(mods.reduce((a, m) => a + (m.favorites || 0), 0)), "FAVS");
  row.addSpacer();
  stat(row, fmt(mods.reduce((a, m) => a + (m.comments || 0), 0)), "COMMENTS");
  row.addSpacer();
  stat(row, fmt(up + down), "RATINGS");
  w.addSpacer(5);
  // best ranking across all mods
  let best = null;
  for (const m of mods) {
    const r = ins && ins.ranks && ins.ranks[m.id];
    if (!r) continue;
    for (const k of Object.keys(RANK_LABELS)) if (r[k] && (!best || r[k] < best.rank)) best = { rank: r[k], k, m };
  }
  if (best) text(w, `#${best.rank} ${RANK_LABELS[best.k]} · ${short(best.m.title)}`, 10, INK);
  w.addSpacer();
  dots(w, page, pages, stats);
  drawDots(w);
  return w;
}

function modPage(w, m, page, pages, ins, stats) {
  w.url = "https://steamcommunity.com/sharedfiles/filedetails/?id=" + m.id;
  const head = w.addStack();
  head.centerAlignContent();
  text(head, short(m.title).toUpperCase(), 10, GOLD, true);
  w.addSpacer(2);
  text(w, `${fmt(m.visitors)} views`, 10, MUTED);
  const subs = w.addStack();
  subs.bottomAlignContent();
  text(subs, fmt(m.subs), 24, INK, true);
  delta(subs, m.d1 && m.d1.subs, 11);
  text(w, "subscribers", 10, MUTED);
  w.addSpacer(4);
  const rate = w.addStack();
  rate.centerAlignContent();
  if (m.stars) text(rate, stars(m) + "  ", 10, GOLD);
  else text(rate, "no stars yet  ", 9, MUTED);
  text(rate, pct(m), 10, INK, true);
  text(w, `${fmt(m.favorites)} favs · ${plural(m.comments, "comment")}`, 10, MUTED);
  const rank = bestRank(ins, m.id);
  if (rank) text(w, rank, 10, INK);
  w.addSpacer();
  dots(w, page, pages, stats);
  drawDots(w);
  return w;
}

async function build() {
  const w = new ListWidget();
  w.backgroundColor = BG;
  w.url = SITE;
  w.setPadding(12, 14, 12, 14);
  w.refreshAfterDate = new Date(Date.now() + 10 * 60 * 1000);

  let stats, ins = null;
  try {
    stats = await getJSON("data/stats.json");
    try { ins = await getJSON("data/insights.json"); } catch (e) {}
  } catch (e) {
    text(w, "Workshop Ledger", 13, GOLD, true);
    w.addSpacer(6);
    text(w, "Can't reach the dashboard right now.", 12, MUTED);
    return w;
  }

  const mods = stats.mods.slice().sort((a, b) => b.subs - a.subs);
  const total = mods.reduce((a, m) => a + (m.subs || 0), 0);
  const haveD1 = mods.some((m) => m.d1);
  const d1 = haveD1 ? mods.reduce((a, m) => a + ((m.d1 && m.d1.subs) || 0), 0) : null;
  const up = mods.reduce((a, m) => a + (m.up || 0), 0), down = mods.reduce((a, m) => a + (m.down || 0), 0);
  const fam = config.widgetFamily || "medium";

  // Small widget rotates: page 0 = global, then one page per mod (most subscribed first).
  // Each refresh shows the next page. A widget parameter pins a page: "global", a number
  // (1 = biggest mod) or part of a mod name.
  if (fam === "small") {
    const pages = mods.length + 1;
    const param = ((typeof args !== "undefined" && args.widgetParameter) || "").trim().toLowerCase();
    let page;
    if (param === "global") page = 0;
    else if (/^\d+$/.test(param)) page = Math.min(Number(param), mods.length);
    else if (param) page = Math.max(0, mods.findIndex((m) => m.title.toLowerCase().includes(param)) + 1);
    else {
      const KEY = "workshop-ledger-page";
      const last = Keychain.contains(KEY) ? Number(Keychain.get(KEY)) : -1;
      page = config.runsInWidget ? (last + 1) % pages : Math.max(0, last);
      Keychain.set(KEY, String(page));
      w.refreshAfterDate = new Date(Date.now() + 60 * 1000); // as soon as iOS allows
    }
    if (page > 0) return modPage(w, mods[page - 1], page, pages, ins, stats);
    return globalPage(w, mods, page, pages, ins, stats, d1, up, down);
  }

  // Header
  const head = w.addStack();
  head.centerAlignContent();
  text(head, "WORKSHOP LEDGER", 10, GOLD, true);
  head.addSpacer();
  text(head, ago(stats.fetched), 9, MUTED);
  w.addSpacer(4);

  // Totals
  const tot = w.addStack();
  tot.bottomAlignContent();
  text(tot, fmt(total), fam === "small" ? 26 : 24, INK, true);
  delta(tot, d1, 12);
  text(w, "subscribers" + (up + down ? ` · ${Math.round((up / (up + down)) * 100)}% positive` : ""), 10, MUTED);

  if (fam === "small") {
    w.addSpacer();
    text(w, `${fmt(mods.reduce((a, m) => a + (m.favorites || 0), 0))} favs · ${fmt(mods.reduce((a, m) => a + (m.comments || 0), 0))} comments`, 10, MUTED);
    drawDots(w);
    return w;
  }

  w.addSpacer(6);
  const list = fam === "large" ? mods : mods.slice(0, 4);
  for (const m of list) {
    const row = w.addStack();
    row.centerAlignContent();
    text(row, short(m.title), 12, INK, true);
    row.addSpacer(6);
    if (m.stars) text(row, stars(m) + " ", 9, GOLD);
    text(row, pct(m) + " ", 10, MUTED);
    row.addSpacer();
    text(row, fmt(m.subs), 12, INK, true);
    delta(row, m.d1 && m.d1.subs, 10);
    w.addSpacer(fam === "large" ? 5 : 3);
  }

  if (fam === "large" && ins && ins.ranks) {
    w.addSpacer(4);
    text(w, "BEST RANKINGS", 10, GOLD, true);
    w.addSpacer(3);
    const labels = { trend_agot: "trending AGOT", trend_all: "trending CK3", subs_agot: "AGOT by subs", subs_all: "CK3 by subs" };
    const best = [];
    for (const [id, r] of Object.entries(ins.ranks)) {
      const m = mods.find((x) => x.id === id);
      if (!m) continue;
      // each mod's single best ranking
      const k = Object.keys(labels).filter((k) => r[k]).sort((a, b) => r[a] - r[b])[0];
      if (k) best.push({ title: short(m.title), rank: r[k], label: labels[k] });
    }
    best.sort((a, b) => a.rank - b.rank);
    for (const b of best.slice(0, 4)) {
      const row = w.addStack();
      text(row, `#${b.rank}`, 12, GOLD, true);
      row.addSpacer(6);
      text(row, `${b.title} · ${b.label}`, 11, INK);
      w.addSpacer(2);
    }
  }
  w.addSpacer();
  return w;
}

const widget = await build();
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  await widget.presentSmall(); // preview when you run it inside Scriptable
}
Script.complete();
