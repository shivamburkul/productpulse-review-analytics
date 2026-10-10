const $ = id => document.getElementById(id);
const PAL = ["#38bdf8", "#a78bfa", "#f472b6", "#34d399", "#fbbf24", "#fb7185", "#22d3ee", "#818cf8", "#a3e635", "#94a3b8"];
const SC = {positive: "#34d399", negative: "#fb7185", neutral: "#94a3b8", mixed: "#fbbf24"};
const LABELS = ["positive", "negative", "neutral", "mixed"], NICE = {positive: "Positive", negative: "Negative", neutral: "Neutral", mixed: "Mixed"};
let A = null, charts = {}, mode = "single", jobTimer = null, chosenFile = null;
Chart.defaults.color = "#a8b3d6"; Chart.defaults.borderColor = "rgba(255,255,255,.08)"; Chart.defaults.font.family = "Inter,Segoe UI,sans-serif";
Chart.defaults.animation.duration = 900; Chart.defaults.maintainAspectRatio = false; Chart.defaults.plugins.legend.labels.usePointStyle = true;

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const fmt = v => (v > 0 ? "+" : "") + Number(v).toFixed(3);
async function api(url, opts) {
  let r, j = {};
  try { r = await fetch(url, opts); j = await r.json(); } catch (e) { if (!r) throw new Error("Could not reach the server. Is it still running?"); }
  if (!r.ok) throw Object.assign(new Error(j.error || "Request failed"), {data: j});
  return j;
}
const post = (u, b) => api(u, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b || {})});
function toast(msg, type) {
  const t = document.createElement("div"); t.className = "toast " + (type || ""); t.textContent = msg; $("toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = 0; t.style.transition = ".5s"; setTimeout(() => t.remove(), 500); }, 3600);
}
const grad = (c1, c2) => ctx => { const a = ctx.chart.chartArea; if (!a) return c1; const g = ctx.chart.ctx.createLinearGradient(a.left, a.bottom, a.right, a.top); g.addColorStop(0, c2); g.addColorStop(1, c1); return g; };
function emptyState(id, msg) {
  const cv = $("cv-" + id), c = $(id); let e = $("em-" + id);
  if (!e) { e = document.createElement("div"); e.id = "em-" + id; e.className = "empty"; cv.appendChild(e); }
  e.textContent = msg || ""; e.style.display = msg ? "" : "none"; c.style.display = msg ? "none" : "";
  if (msg && charts[id]) { charts[id].destroy(); delete charts[id]; }
}
function draw(id, type, labels, datasets, opts = {}, h) {
  emptyState(id);
  if (h) $("cv-" + id).style.height = h + "px";
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), {type, data: {labels, datasets}, options: Object.assign({responsive: true, plugins: {legend: {display: datasets.length > 1}}}, opts)});
}
const axes = (x, y, extra = {}) => ({scales: {x: Object.assign({title: {display: !!x, text: x}}, extra.x), y: Object.assign({title: {display: !!y, text: y}}, extra.y)}});
const hbarH = n => Math.max(200, n * 30 + 80);
function donut(id, vals) {
  const t = vals.reduce((a, b) => a + b, 0) || 1;
  draw(id, "doughnut", LABELS.map(l => NICE[l]), [{data: vals, backgroundColor: LABELS.map(l => SC[l]), borderWidth: 0, hoverOffset: 8}], {cutout: "68%", plugins: {
    legend: {display: false},
    tooltip: {callbacks: {label: c => `${c.label}: ${c.raw.toLocaleString()} reviews (${(c.raw / t * 100).toFixed(1)}%)`}}}}, 210);
  let lg = $("lg-" + id);
  if (!lg) { lg = document.createElement("div"); lg.id = "lg-" + id; lg.className = "donut-legend"; $("cv-" + id).insertAdjacentElement("afterend", lg); }
  lg.innerHTML = LABELS.map((l, i) => `<span><i style="background:${SC[l]}"></i>${NICE[l]} <b>${(vals[i] / t * 100).toFixed(1)}%</b></span>`).join("");
}
function fillSelect(sel, items, emptyMsg, all) {
  if (!items.length) { sel.innerHTML = `<option>${emptyMsg}</option>`; sel.disabled = true; return; }
  sel.disabled = false; sel.innerHTML = (all ? '<option value="">All products</option>' : "") + items.map(i => `<option>${esc(i)}</option>`).join("");
}
function countUp(el) {
  const target = parseFloat(el.dataset.count), t0 = performance.now();
  (function step(t) { const p = Math.min((t - t0) / 1000, 1); el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))).toLocaleString(); if (p < 1) requestAnimationFrame(step); })(t0);
}
document.addEventListener("click", e => {
  const b = e.target.closest("button,.btn"); if (!b || b.disabled) return;
  const r = b.getBoundingClientRect(), s = document.createElement("span"), d = Math.max(r.width, r.height);
  s.className = "ripple"; s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
  b.appendChild(s); setTimeout(() => s.remove(), 700);
});
const prod = n => A.products.find(p => p.product === n);
const featStats = n => A.category_by_product.filter(c => c.product === n);

// ---------- screens ----------
function show(id) { ["landing", "processing", "app"].forEach(s => $(s).classList.toggle("hidden", s !== id)); window.scrollTo(0, 0); }
function showLanding() { clearInterval(jobTimer); $("back-app").classList.toggle("hidden", !A); show("landing"); }
$("back-app").onclick = () => show("app");
$("new-ds").onclick = showLanding;
const drop = $("drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => pick(e.dataTransfer.files[0]));
$("file").onchange = e => pick(e.target.files[0]);
$("browse").onclick = e => { e.preventDefault(); $("file").click(); };
function pick(f) {
  $("up-error").classList.add("hidden");
  if (!f) return;
  chosenFile = f; $("chip").classList.remove("hidden"); $("chip").textContent = `${f.name} (${(f.size / 1024).toFixed(f.size > 1048576 ? 0 : 1)} KB)`; $("go").disabled = false;
}
$("go").onclick = async () => {
  if (!chosenFile) return;
  $("go").disabled = true; $("up-error").classList.add("hidden");
  const fd = new FormData(); fd.append("file", chosenFile);
  try {
    const r = await api("/api/upload", {method: "POST", body: fd});
    startProcessing(chosenFile.name, r.job_id, r.ingest);
  } catch (e) { $("up-error").textContent = e.message; $("up-error").classList.remove("hidden"); $("go").disabled = false; }
};
function renderStages(job) {
  $("stages").innerHTML = job.stages.map((s, i) => `<li class="${i < job.stage ? "done" : i === job.stage ? "on" : ""}"><i>${i < job.stage ? "&#10003;" : ""}</i>${s}</li>`).join("");
}
function startProcessing(name, jobId, ingest) {
  show("processing"); $("proc-file").textContent = name + (ingest ? ` - ${ingest.accepted.toLocaleString()} rows accepted` + (ingest.rejected ? `, ${ingest.rejected} rejected` : "") : "");
  $("proc-error").classList.add("hidden"); $("proc-retry").classList.add("hidden"); document.querySelector(".proc h2").textContent = "Analyzing your reviews";
  document.querySelector(".proc .ring").style.display = ""; document.querySelector(".bar-indet").style.display = "";
  renderStages({stages: ["Validating file", "Reading rows", "Cleaning text", "Analysing sentiment and features", "Aggregating products", "Finding keywords", "Building summaries"], stage: 1});
  clearInterval(jobTimer);
  jobTimer = setInterval(async () => {
    try {
      const j = await api("/api/jobs/" + jobId); renderStages(j);
      if (j.status === "done") { clearInterval(jobTimer); await loadAll(); show("app"); toast("Analysis complete", "good"); }
      if (j.status === "failed") {
        clearInterval(jobTimer); document.querySelector(".proc h2").textContent = "Analysis could not be completed";
        document.querySelector(".proc .ring").style.display = "none"; document.querySelector(".bar-indet").style.display = "none";
        $("proc-error").textContent = j.error + (j.reference ? " (Reference: " + j.reference + ")" : ""); $("proc-error").classList.remove("hidden"); $("proc-retry").classList.remove("hidden");
      }
    } catch (e) { clearInterval(jobTimer); $("proc-error").textContent = e.message; $("proc-error").classList.remove("hidden"); $("proc-retry").classList.remove("hidden"); }
  }, 700);
}
$("proc-retry").onclick = () => { $("go").disabled = !chosenFile; showLanding(); };

document.querySelectorAll("nav a").forEach(a => a.onclick = () => go(a.dataset.page));
function go(name) {
  document.querySelectorAll("nav a").forEach(x => x.classList.toggle("active", x.dataset.page === name));
  document.querySelectorAll(".page").forEach(x => x.classList.add("hidden")); $(name).classList.remove("hidden"); window.scrollTo(0, 0);
  ({dashboard: renderDashboard, insights: renderInsights, trends: renderTrends, verification: loadVerification, reports: renderReports}[name] || (() => {}))();
}

// ---------- dashboard ----------
function heatColor(v) { return `hsl(${Math.max(0, Math.min(1, v + .5)) * 120},60%,32%)`; }
function renderDashboard() {
  const o = A.overall, ing = A.ingest;
  $("hero-pills").innerHTML = [A.dataset.filename, `${o.total.toLocaleString()} reviews`].map(x => `<span class="pill">${esc(x)}</span>`).join("");
  const k = [["Reviews analysed", o.total, "&#9776;", "#38bdf8,#2563eb"], ["Products", o.products, "&#9638;", "#a78bfa,#6d28d9"], ["Positive reviews", o.positive, "&#9786;", "#34d399,#059669"], ["Negative reviews", o.negative, "&#9785;", "#fb7185,#e11d48"],
    ["Neutral reviews", o.neutral, "&#9644;", "#94a3b8,#475569"], ["Mixed reviews", o.mixed, "&#8646;", "#fbbf24,#d97706"], ["Most discussed feature", o.top_feature, "&#9733;", "#fbbf24,#f97316"], ["Overall sentiment", o.label + " (" + fmt(o.avg_score) + ")", "&#9829;", "#f472b6,#c026d3"]];
  $("kpis").innerHTML = k.map(x => `<div class="kpi glass"><div class="kicon" style="background:linear-gradient(135deg,${x[3]})">${x[2]}</div><div><small>${x[0]}</small><b ${typeof x[1] === "number" ? `data-count="${x[1]}"` : ""}>${typeof x[1] === "number" ? 0 : esc(x[1])}</b></div></div>`).join("");
  document.querySelectorAll("#kpis [data-count]").forEach(countUp);
  donut("c-sent", LABELS.map(l => o[l]));
  $("sent-center").innerHTML = `<b>${fmt(o.avg_score)}</b><small>average score</small>`;
  const cats = A.categories;
  if (cats.length) draw("c-cat", "bar", cats.map(c => c.category), [{data: cats.map(c => c.count), backgroundColor: PAL, borderRadius: 8}], Object.assign({indexAxis: "y"}, axes("Number of mentions", "Feature")), hbarH(cats.length));
  else emptyState("c-cat", "No product features were detected in the reviews.");
  const lb = A.leaderboard.slice(0, 10);
  $("leaderboard").innerHTML = lb.map((p, i) => `<div class="lb" data-p="${esc(p.product)}"><span class="rk">${i + 1}</span><div class="nm"><div>${esc(p.product)}</div><div class="track"><i data-w="${Math.max(3, (p.avg_score + 1) * 50)}"></i></div></div><div><b>${fmt(p.avg_score)}</b><br><small>${p.pos_pct}% positive</small></div></div>`).join("");
  setTimeout(() => document.querySelectorAll("#leaderboard i").forEach(i => i.style.width = i.dataset.w + "%"), 60);
  document.querySelectorAll(".lb").forEach(l => l.onclick = () => { $("ins-a").value = l.dataset.p; setMode("single"); go("insights"); });
  const F = [...new Set(A.category_by_product.map(c => c.category))], cell = {};
  A.category_by_product.forEach(c => cell[c.product + "|" + c.category] = c);
  $("heatmap").innerHTML = F.length ? `<div class="heat" style="grid-template-columns:170px repeat(${F.length},1fr)"><div class="hh"></div>${F.map(f => `<div class="hh">${f}</div>`).join("")}` +
    A.products.map(p => `<div class="hl" title="${esc(p.product)}">${esc(p.product)}</div>` + F.map(f => { const c = cell[p.product + "|" + f]; return c && c.count >= 3 ? `<div class="hc" style="background:${heatColor(c.avg_score)}" title="${c.count} mentions">${fmt(c.avg_score)}</div>` : `<div style="opacity:.3" title="Fewer than 3 mentions">-</div>`; }).join("")).join("") + "</div>" : '<div class="empty">No feature mentions found.</div>';
  $("heat-legend").innerHTML = F.length ? `<div class="grad-bar"></div><div class="ends"><span>-0.5 or lower: negative</span><span>0: neutral or mixed</span><span>+0.5 or higher: positive</span></div><div>Values are the average sentiment score (-1 to +1) of review sentences about that feature. "-" means fewer than 3 mentions.</div>` : "";
  const mx = A.keywords_global.length ? A.keywords_global[0].count : 1;
  $("cloud").innerHTML = A.keywords_global.length ? A.keywords_global.map((w, i) => `<span style="font-size:${13 + 24 * w.count / mx}px;color:${PAL[i % 8]}" title="${w.count} mentions">${esc(w.word)}</span>`).join("") : '<div class="empty">No words to show.</div>';
  const pr = A.products.slice().sort((a, b) => b.total - a.total);
  draw("c-prod", "bar", pr.map(p => p.product), LABELS.map(s => ({label: NICE[s], data: pr.map(p => p[s]), backgroundColor: SC[s], borderRadius: 4})),
    Object.assign({indexAxis: "y", plugins: {legend: {display: true, position: "bottom"}}}, axes("Number of reviews", "Product", {x: {stacked: true}, y: {stacked: true}})), hbarH(pr.length) + 30);
}

// ---------- insights ----------
function setMode(m) {
  mode = m; document.querySelectorAll("#mode button").forEach(b => b.classList.toggle("on", b.dataset.mode === m));
  $("single").classList.toggle("hidden", m !== "single"); $("compare").classList.toggle("hidden", m !== "compare"); $("lab-b").classList.toggle("hidden", m !== "compare");
}
document.querySelectorAll("#mode button").forEach(b => b.onclick = () => { if (b.dataset.mode === "compare" && A.products.length < 2) return toast("This dataset has only one product, so there is nothing to compare.", "err"); setMode(b.dataset.mode); renderInsights(); });
$("ins-a").onchange = $("ins-b").onchange = () => renderInsights();
function renderInsights() {
  if (!A.products.length) return;
  mode === "single" ? renderSingle() : renderCompare();
}
function quotes(arr, cls) { return arr && arr.length ? arr.map(x => `<div class="quote ${cls}">${esc(x.text)}<small>${esc(x.category)} - score ${fmt(x.score)}</small></div>`).join("") : '<div class="empty">No strong reviews of this kind.</div>'; }
function renderSingle() {
  const name = $("ins-a").value, q = prod(name); if (!q) return;
  const fs = featStats(name).filter(f => f.count >= 3).sort((a, b) => b.avg_score - a.avg_score);
  $("profile").innerHTML = `<div class="ringbox"><svg width="120" height="120"><defs><linearGradient id="rg"><stop offset="0" stop-color="#38bdf8"/><stop offset="1" stop-color="#f472b6"/></linearGradient></defs><circle class="ring-bg" cx="60" cy="60" r="52" fill="none" stroke-width="10"/><circle id="ringfg" class="ring-fg" cx="60" cy="60" r="52" fill="none" stroke-width="10" stroke-dasharray="327" stroke-dashoffset="327"/></svg><div class="rt"><b>${q.positive_pct}%</b><small>positive</small></div></div>
  <div><h3>${esc(name)}</h3><div class="stats"><div><small>Reviews</small><b>${q.total.toLocaleString()}</b></div><div><small>Average sentiment</small><b>${fmt(q.avg_score)}</b></div><div><small>Negative</small><b>${q.negative_pct}%</b></div>${q.avg_rating != null ? `<div><small>Average rating</small><b>${q.avg_rating}</b></div>` : ""}</div></div>`;
  setTimeout(() => { const r = $("ringfg"); if (r) r.style.strokeDashoffset = 327 * (1 - q.positive_pct / 100); }, 60);
  const s = A.summaries[name]; $("i-summary").textContent = s.text;
  $("i-chips").innerHTML = s.strengths.map(x => `<span class="tag p">Strength: ${esc(x)}</span>`).join("") + s.complaints.map(x => `<span class="tag n">Concern: ${esc(x)}</span>`).join("");
  donut("i-sent", LABELS.map(l => q[l]));
  if (fs.length) draw("i-feat", "bar", fs.map(f => f.category), [{data: fs.map(f => f.avg_score), backgroundColor: fs.map(f => f.avg_score >= 0.1 ? SC.positive : f.avg_score <= -0.1 ? SC.negative : SC.neutral), borderRadius: 8}], Object.assign({indexAxis: "y"}, axes("Average sentiment (-1 to +1)", "Feature", {x: {min: -1, max: 1}})), hbarH(fs.length));
  else { $("cv-i-feat").style.height = "120px"; emptyState("i-feat", "Not enough feature mentions for this product."); }
  const kw = A.keywords_by_product[name] || [];
  draw("i-kw", "bar", kw.map(k => k.word), [{data: kw.map(k => k.count), backgroundColor: grad("#a78bfa", "#f472b6"), borderRadius: 8}], Object.assign({indexAxis: "y"}, axes("Number of mentions", "Word")), hbarH(kw.length));
  const pc = A.pros_cons[name] || {}; $("i-pros").innerHTML = quotes(pc.pros, ""); $("i-cons").innerHTML = quotes(pc.cons, "c");
}
function renderCompare() {
  const a = $("ins-a").value, b = $("ins-b").value, pa = prod(a), pb = prod(b);
  if (!pa || !pb || a === b) { $("c-diff").innerHTML = '<div class="empty">Select two different products to compare.</div>'; return; }
  const fa = Object.fromEntries(featStats(a).map(f => [f.category, f])), fb = Object.fromEntries(featStats(b).map(f => [f.category, f]));
  const common = Object.keys(fa).filter(f => fb[f] && fa[f].count >= 3 && fb[f].count >= 3).map(f => ({f, d: fa[f].avg_score - fb[f].avg_score})).sort((x, y) => Math.abs(y.d) - Math.abs(x.d));
  const [hi, lo] = pa.avg_score >= pb.avg_score ? [pa, pb] : [pb, pa];
  let t = `<p><b>${esc(hi.product)}</b> has the higher average sentiment (${fmt(hi.avg_score)} compared with ${fmt(lo.avg_score)}); ${hi.positive_pct}% of its reviews are positive against ${lo.positive_pct}% for ${esc(lo.product)}.</p>`;
  if (common.length) t += "<p>" + common.slice(0, 3).map(c => `${c.d > 0 ? esc(a) : esc(b)} scores higher on <b>${c.f}</b> (${fmt(fa[c.f].avg_score)} vs ${fmt(fb[c.f].avg_score)})`).join("; ") + ".</p>";
  else t += "<p>The two products do not share enough feature mentions to compare features.</p>";
  t += `<p>${esc(a)} has ${pa.total.toLocaleString()} reviews and ${esc(b)} has ${pb.total.toLocaleString()}.${Math.min(pa.total, pb.total) < 30 ? " One product has few reviews, so treat differences with care." : ""}</p>`;
  $("c-diff").innerHTML = t;
  const row = (n, k, hiBetter, suffix = "") => { if (pa[k] == null) return ""; const w = pa[k] === pb[k] ? 0 : hiBetter === null ? 0 : ((pa[k] > pb[k]) === hiBetter ? 1 : 2); return `<tr><td>${n}</td><td class="${w === 1 ? "win" : ""}">${pa[k]}${suffix}</td><td class="${w === 2 ? "win" : ""}">${pb[k]}${suffix}</td></tr>`; };
  $("c-table").innerHTML = `<table><tr><th>Metric</th><th>${esc(a)}</th><th>${esc(b)}</th></tr>${row("Reviews", "total", null)}${row("Positive %", "positive_pct", true, "%")}${row("Negative %", "negative_pct", false, "%")}${row("Neutral %", "neutral_pct", null, "%")}${row("Mixed %", "mixed_pct", null, "%")}${row("Average sentiment (-1 to +1)", "avg_score", true)}${row("Average review length (characters)", "avg_length", null)}${row("Average rating", "avg_rating", true)}</table>`;
  draw("c-dist", "bar", LABELS.map(l => NICE[l] + " %"), [pa, pb].map((p, i) => ({label: p.product, data: LABELS.map(l => p[l + "_pct"]), backgroundColor: i ? "#f472b6" : "#38bdf8", borderRadius: 8})), Object.assign({plugins: {legend: {display: true, position: "bottom"}}}, axes("Sentiment group", "Share of reviews (%)", {y: {min: 0, max: 100}})), 280);
  const F = [...new Set([...Object.keys(fa), ...Object.keys(fb)])], v = (m, f) => m[f] && m[f].count >= 3 ? m[f].avg_score : 0;
  draw("c-radar", "radar", F, [[a, fa, "#38bdf8"], [b, fb, "#f472b6"]].map(([n, m, c]) => ({label: n, data: F.map(f => v(m, f)), borderColor: c, backgroundColor: c + "33"})), {plugins: {legend: {display: true, position: "bottom"}}, scales: {r: {suggestedMin: -.5, suggestedMax: .8, ticks: {display: false}, grid: {color: "rgba(255,255,255,.1)"}, angleLines: {color: "rgba(255,255,255,.1)"}, pointLabels: {color: "#cdd6ff"}}}}, 320);
  draw("c-ment", "bar", F, [[a, fa, "#38bdf8"], [b, fb, "#f472b6"]].map(([n, m, c]) => ({label: n, data: F.map(f => m[f] ? m[f].count : 0), backgroundColor: c, borderRadius: 6})), Object.assign({plugins: {legend: {display: true, position: "bottom"}}}, axes("Feature", "Number of mentions")), 320);
}

// ---------- analyzer ----------
$("an-find").onclick = findReviews; $("an-search").onkeydown = e => { if (e.key === "Enter") findReviews(); };
async function findReviews() {
  const q = $("an-search").value.trim(); if (q.length > 200) return toast("Search text is too long (max 200 characters).", "err");
  $("an-results").innerHTML = '<div class="empty">Searching...</div>';
  try {
    const r = await api(`/api/reviews?product=${encodeURIComponent($("an-product").value)}&q=${encodeURIComponent(q)}&limit=25`);
    $("an-count").textContent = r.matches ? `Showing ${r.shown} of ${r.matches.toLocaleString()} matching reviews (searching ${r.searchable_rows.toLocaleString()} of ${r.dataset_rows.toLocaleString()} analysed reviews).` : "";
    $("an-results").innerHTML = r.rows.length ? r.rows.map((x, i) => `<div class="res" data-i="${i}"><span class="badge ${x.sentiment}">${x.sentiment}</span><div>${esc(x.text.length > 170 ? x.text.slice(0, 170) + "..." : x.text)}<small>${esc(x.product)} - ${esc(x.category)}</small></div></div>`).join("") : '<div class="empty">No matching reviews found. Try a different word or product.</div>';
    document.querySelectorAll(".res").forEach(el => el.onclick = () => { document.querySelectorAll(".res").forEach(x => x.classList.remove("sel")); el.classList.add("sel"); analyze(r.rows[+el.dataset.i].text, r.rows[+el.dataset.i]); });
  } catch (e) { $("an-results").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
$("an-run").onclick = () => analyze($("an-text").value);
async function analyze(text, row) {
  try {
    const r = await post("/api/analyze", {text}), tags = (a, c) => a.map(t => `<span class="tag ${c || ""}">${esc(t)}</span>`).join("") || '<span class="muted">none</span>';
    $("an-result").innerHTML = `<div class="flow"><div class="fstep glass"><h4>1 Original review</h4>${esc(r.original)}</div><div class="fstep glass"><h4>2 Cleaned text</h4>${esc(r.cleaned)}</div><div class="fstep glass"><h4>3 Words (tokens)</h4>${tags(r.tokens)}</div><div class="fstep glass"><h4>4 Without stop-words</h4>${tags(r.tokens_without_stopwords)}</div></div>
    <div class="grid3"><div class="card glass"><h3>Sentiment</h3><p class="desc">Overall feeling of the review, from -1 (negative) to +1 (positive).</p><span class="badge ${r.sentiment}">${r.sentiment}</span> <b>${fmt(r.score)}</b><div class="meter"><i id="mi"></i></div></div>
    <div class="card glass"><h3>Feature and Keywords</h3><p class="desc">The main product feature mentioned and the most frequent words.</p><span class="tag" style="font-size:15px">${esc(r.category)}</span><div style="margin-top:8px">${tags(r.keywords)}</div></div>
    <div class="card glass"><h3>Opinion Words</h3><p class="desc">Words that carry feeling; green is positive, red is negative.</p>${r.opinion_words.map(w => `<span class="tag ${w.valence > 0 ? "p" : "n"}">${esc(w.word)} ${w.valence > 0 ? "+" : ""}${w.valence}</span>`).join("") || '<span class="muted">No opinion words found</span>'}</div></div>
    <div class="grid2"><div class="card glass"><h3>Clause Breakdown</h3><p class="desc">The review is split at punctuation and words like "but" so mixed opinions are seen separately.</p><div class="scroll"><table><tr><th>Part</th><th>Sentiment</th><th>Feature</th></tr>${r.clauses.map(c => `<tr><td>${esc(c.text)}</td><td><span class="badge ${c.label}">${c.label}</span> ${fmt(c.score)}</td><td>${esc(c.category)}</td></tr>`).join("")}</table></div></div>
    <div class="card glass"><h3>Short Summary</h3><p class="desc">A one-line reading of tone and the features praised or criticised.</p><p class="summary-text">${esc(r.summary)}</p></div></div>`;
    setTimeout(() => { const m = $("mi"); if (m) m.style.left = ((r.score + 1) / 2 * 100) + "%"; }, 60);
    $("an-result").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (e) { toast(e.message, "err"); }
}

// ---------- trends ----------
$("tr-product").onchange = () => renderTrends();
function renderTrends() {
  const p = $("tr-product").value, t = A.trends.filter(x => x.product === p), timed = A.time_based, xl = timed ? "Review month" : "Review group (file order, 5 equal parts)";
  $("tr-note").classList.toggle("hidden", timed); $("tr-note").textContent = "This dataset has no usable dates, so reviews are grouped into 5 equal parts in file order. This is not a real timeline.";
  $("d-t1").textContent = "Average sentiment score (-1 to +1) of reviews in each " + (timed ? "month." : "review group."); $("d-t2").textContent = "Number of reviews in each " + (timed ? "month." : "review group.");
  $("d-t3").textContent = "Counts of positive and negative reviews in each " + (timed ? "month." : "review group.");
  if (!t.length) { ["t-score", "t-vol", "t-pn"].forEach(id => { $("cv-" + id).style.height = "120px"; emptyState(id, "No valid dates available for time-based analysis."); }); }
  else {
    draw("t-score", "line", t.map(x => x.period), [{label: "Average sentiment", data: t.map(x => x.avg_score), borderColor: "#38bdf8", backgroundColor: "rgba(56,189,248,.18)", fill: true, tension: .35, pointRadius: 4, pointBackgroundColor: "#fff"}], axes(xl, "Average sentiment score (-1 to +1)", {y: {suggestedMin: -.5, suggestedMax: .8}}), 280);
    draw("t-vol", "bar", t.map(x => x.period), [{label: "Reviews", data: t.map(x => x.count), backgroundColor: grad("#a78bfa", "#f472b6"), borderRadius: 8}], axes(xl, "Number of reviews"), 280);
    draw("t-pn", "bar", t.map(x => x.period), [{label: "Positive", data: t.map(x => x.positive), backgroundColor: SC.positive, borderRadius: 5}, {label: "Negative", data: t.map(x => x.negative), backgroundColor: SC.negative, borderRadius: 5}], Object.assign({plugins: {legend: {display: true, position: "bottom"}}}, axes(xl, "Number of reviews")), 280);
  }
  const agg = {}; A.category_by_product.forEach(c => { const a = agg[c.category] = agg[c.category] || {n: 0, s: 0}; a.n += c.count; a.s += c.count * c.avg_score; });
  const f = Object.entries(agg).map(([k, v]) => [k, v.s / v.n]).sort((a, b) => b[1] - a[1]);
  draw("t-feat", "bar", f.map(x => x[0]), [{data: f.map(x => +x[1].toFixed(3)), backgroundColor: f.map(x => x[1] >= 0.1 ? SC.positive : x[1] <= -0.1 ? SC.negative : SC.neutral), borderRadius: 8}], Object.assign({indexAxis: "y"}, axes("Average sentiment (-1 to +1)", "Feature", {x: {min: -1, max: 1}})), hbarH(f.length));
}

// ---------- verification ----------
const short = h => h ? h.slice(0, 18) + "..." : "-";
function result(cls, title, body) { $("v-result").className = ""; $("v-result").innerHTML = `<div class="alert ${cls}"><b>${title}</b><br>${body}</div>`; }
function renderVerifyResult(r) {
  const cls = {verified: "ok", mismatch: "bad", not_registered: "warn", failed: "gray"}[r.status] || "gray";
  let body = esc(r.message);
  if (r.registered_root) body += `<div class="kv" style="margin-top:10px"><span>Registered fingerprint</span><span class="mono">${r.registered_root}</span><span>Current fingerprint</span><span class="mono">${r.current_root}</span><span>Rows</span><span>${r.registered_rows} registered, ${r.current_rows} now</span><span>Ledger block</span><span>#${r.block_index}</span></div>`;
  if (r.changes && r.changes.length) body += `<div class="scroll"><table style="margin-top:10px"><tr><th>Row</th><th>Review ID</th><th>Original text</th><th>Current text</th></tr>${r.changes.map(c => `<tr><td>${c.row}</td><td>${esc(c.review_id || "")}</td><td>${esc(c.original || "")}</td><td>${esc(c.modified || "(removed)")}</td></tr>`).join("")}</table></div>${r.total_changes > r.changes.length ? `<small>Showing ${r.changes.length} of ${r.total_changes} changes.</small>` : ""}`;
  if (r.ledger_valid === false) body += "<br><b>Warning:</b> the ledger itself failed its integrity check.";
  result(cls, r.title, body);
}
async function loadVerification() {
  try {
    const s = await api("/api/integrity/state"), c = s.current;
    $("ledger-state").innerHTML = `<span class="pill" style="color:${s.ledger_valid ? "#34d399" : "#fb7185"}">${s.ledger_valid ? "Ledger intact" : "Ledger damaged at block " + s.bad_block} - ${s.blocks} blocks</span>`;
    $("v-current").innerHTML = c ? `<div class="kv"><span>File</span><span>${esc(c.filename)}</span><span>Dataset ID</span><span class="mono">${c.dataset_id}</span><span>Rows</span><span>${c.rows.toLocaleString()}</span><span>Uploaded</span><span>${c.uploaded_at}</span><span>Status</span><span>${c.registered ? '<span class="badge positive">Registered</span> block #' + c.block_index : '<span class="badge mixed">Not registered</span>'}</span>${c.merkle_root ? `<span>Fingerprint</span><span class="mono">${c.merkle_root}</span>` : ""}${c.demo ? `<span>Demonstration</span><span class="badge negative">Working copy modified (row ${c.demo.row})</span>` : ""}</div>` : '<div class="empty">No dataset selected.</div>';
    if (c) { $("v-register").disabled = c.registered || !!c.demo; $("v-verify").disabled = false; $("v-sim").disabled = !c.registered || !!c.demo; $("v-reset").disabled = !c.demo; }
    $("v-history").innerHTML = s.history.length ? `<table><tr><th>File</th><th>Dataset ID</th><th>Rows</th><th>Fingerprint</th><th>Block</th><th>Registered</th><th></th></tr>${s.history.map(h => `<tr><td>${esc(h.filename)}${c && h.dataset_id === c.dataset_id ? ' <span class="badge neutral">current</span>' : ""}</td><td class="mono">${h.dataset_id}</td><td>${h.row_count}</td><td class="mono">${short(h.merkle_root)}</td><td>#${h.block_index}</td><td>${h.registered_at}</td><td><button class="ghost small" data-v="${h.dataset_id}">Verify</button></td></tr>`).join("")}</table>` : '<div class="empty">No registered datasets yet.</div>';
    document.querySelectorAll("[data-v]").forEach(b => b.onclick = async () => { try { renderVerifyResult(await post("/api/integrity/verify", {dataset_id: b.dataset.v})); } catch (e) { toast(e.message, "err"); } });
    const l = await api("/api/ledger");
    $("v-chain").innerHTML = l.blocks.slice().reverse().map(b => `<div class="blk"><b>Block #${b.index}${b.data.type === "GENESIS" ? " (start)" : ""}</b>${b.data.filename ? esc(b.data.filename) + "<br>Rows: " + b.data.row_count + "<br>" : ""}Fingerprint: <span class="mono">${short(b.data.merkle_root)}</span><br>Previous: <span class="mono">${short(b.prev_hash)}</span><br>Hash: <span class="mono">${short(b.hash)}</span></div>`).join("");
  } catch (e) { $("v-current").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
$("v-register").onclick = async () => { try { const r = await post("/api/integrity/register"); toast("Dataset registered", "good"); result("ok", "Dataset Registered", `Fingerprint saved for ${r.rows.toLocaleString()} rows in ledger block #${r.block_index}.<div class="kv" style="margin-top:10px"><span>Fingerprint</span><span class="mono">${r.merkle_root}</span><span>Block hash</span><span class="mono">${r.transaction}</span></div>`); loadVerification(); } catch (e) { toast(e.message, "err"); } };
$("v-verify").onclick = async () => { try { renderVerifyResult(await post("/api/integrity/verify")); } catch (e) { toast(e.message, "err"); } };
$("v-sim").onclick = async () => { try { const d = await post("/api/integrity/simulate"); result("warn", "Review Modified in Working Copy", `Row ${d.row} (${esc(d.product)}, ID ${esc(d.review_id)}) was changed. Your uploaded file was not touched. Click <b>Verify Dataset</b> to detect the change.<div class="kv" style="margin-top:10px"><span>Original</span><span>${esc(d.original)}</span><span>Modified</span><span>${esc(d.modified)}</span></div>`); loadVerification(); } catch (e) { toast(e.message, "err"); } };
$("v-reset").onclick = async () => { try { await post("/api/integrity/reset"); result("info", "Demonstration Reset", "The working copy now matches the original again. Verify to confirm."); loadVerification(); } catch (e) { toast(e.message, "err"); } };
$("sim-tamper").onclick = async () => { try { const r = await post("/api/ledger/simulate-tamper"); $("sim-out").innerHTML = `<div class="alert ${r.valid ? "ok" : "bad"}">A copy of the ledger was altered at block #1 (the real ledger is untouched). Result: <b>${r.valid ? "still valid" : "tampering detected at block " + r.bad_block}</b>.</div>`; } catch (e) { toast(e.message, "err"); } };

// ---------- reports ----------
function renderReports() {
  const i = A.ingest, s = A.spark;
  $("r-pills").innerHTML = [A.dataset.filename, `${A.overall.total.toLocaleString()} reviews`, A.dataset.uploaded_at].map(x => `<span class="pill">${esc(x)}</span>`).join("");
  const steps = [`Read ${i.rows_read.toLocaleString()} rows`, `Rejected ${i.rejected}`, `Removed ${s.too_short_removed} too short`, `Removed ${s.duplicates_removed} duplicates`, `Analysed ${s.analysed.toLocaleString()}`];
  $("r-flow").innerHTML = '<div class="flow-chips">' + steps.map((x, k) => `<span>${x}</span>${k < steps.length - 1 ? "<em>&rarr;</em>" : ""}`).join("") + "</div>";
  const why = Object.entries(i.reject_reasons).map(([k, v]) => `${v} ${k}`).join(", ");
  $("r-meta").innerHTML = `<div class="kv"><span>File</span><span>${esc(A.dataset.filename)}</span><span>Columns used</span><span>${Object.entries(i.columns_found).map(([k, v]) => k + " = " + esc(v)).join(", ")}</span><span>Rejected rows</span><span>${i.rejected}${why ? " (" + why + ")" : ""}</span><span>Dates</span><span>${A.time_based ? "Valid dates found" : "No usable dates - trends use review groups"}</span></div>`;
  $("r-board").innerHTML = `<table><tr><th>#</th><th>Product</th><th>Reviews</th><th>Avg sentiment</th><th>Positive %</th></tr>${A.leaderboard.map((p, k) => `<tr><td>${k + 1}</td><td>${esc(p.product)}</td><td>${p.n}</td><td>${fmt(p.avg_score)}</td><td>${p.pos_pct}</td></tr>`).join("")}</table>`;
  loadPreview();
}
$("r-n").onchange = loadPreview;
async function loadPreview() {
  try {
    const r = await api("/api/reviews?limit=" + $("r-n").value);
    $("r-preview").innerHTML = `<table><tr><th>ID</th><th>Product</th><th>Review</th><th>Sentiment</th><th>Feature</th></tr>${r.rows.map(x => `<tr><td>${esc(x.review_id)}</td><td>${esc(x.product)}</td><td>${esc(x.text)}</td><td><span class="badge ${x.sentiment}">${x.sentiment}</span></td><td>${esc(x.category)}</td></tr>`).join("")}</table>`;
    $("r-count").textContent = `Showing ${r.shown} of ${r.dataset_rows.toLocaleString()} analysed reviews.`;
  } catch (e) { $("r-preview").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

// ---------- start ----------
async function loadAll() {
  A = await api("/api/analytics"); Object.values(charts).forEach(c => c.destroy()); charts = {};
  const names = A.products.map(p => p.product);
  fillSelect($("ins-a"), names, "Upload a dataset to view products"); fillSelect($("tr-product"), names, "Upload a dataset to view products"); fillSelect($("an-product"), names, "Upload a dataset to view products", true);
  fillSelect($("ins-b"), names, "Only one product in this dataset"); if (names.length > 1) $("ins-b").value = names[1];
  $("side-ds").textContent = `${A.dataset.filename} - ${A.overall.total.toLocaleString()} reviews`;
  $("an-results").innerHTML = ""; $("an-count").textContent = ""; $("an-result").innerHTML = ""; $("an-search").value = ""; $("v-result").className = "muted"; $("v-result").textContent = "No action yet.";
  setMode("single"); go("dashboard");
}
(async function init() {
  try {
    const s = await api("/api/state");
    if (s.active) { await loadAll(); show("app"); } else showLanding();
  } catch (e) { showLanding(); $("up-error").textContent = e.message; $("up-error").classList.remove("hidden"); }
})();
