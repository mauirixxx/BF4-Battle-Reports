(() => {
  'use strict';
  const table = document.getElementById('history');
  if (!table) return;
  const keys = [...table.tHead.rows[0].cells].map(c => c.dataset.key);
  const ki = keys.indexOf('kills'), di = keys.indexOf('deaths');
  if (ki < 0 || di < 0) return;
  const popup = document.createElement('aside');
  popup.className = 'bf4cr-trend-popup';
  popup.setAttribute('role', 'tooltip');
  popup.innerHTML = '<div class="bf4cr-trend-title">Recent match performance <span class="bf4cr-trend-count"></span></div><div class="bf4cr-trend-stats"></div><div class="bf4cr-trend-graphs"></div><div class="bf4cr-trend-foot">Left → right: reverse of current table order · up to 200 visible reports</div>';
  document.body.append(popup);
  const countEl = popup.querySelector('.bf4cr-trend-count');
  const statsEl = popup.querySelector('.bf4cr-trend-stats');
  const graphsEl = popup.querySelector('.bf4cr-trend-graphs');
  const escape = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const numeric = text => Number(String(text).replace(/,/g, '').trim());
  function graph(label, values, color, scaleMax = null, combined = false) {
    const width = 720, height = 148, pad = 12;
    const ceiling = scaleMax ?? Math.max(1, ...values);
    const pts = values.map((v, i) => {
      const x = pad + (values.length === 1 ? (width - 2 * pad) / 2 : i * (width - 2 * pad) / (values.length - 1));
      const y = height - pad - (v / ceiling) * (height - 2 * pad);
      return [x, y];
    });
    // Shape-preserving cubic interpolation: curves never exceed the adjacent values.
    const slopes = pts.slice(1).map((p, i) => (p[1] - pts[i][1]) / (p[0] - pts[i][0]));
    const tangent = pts.map((p, i) => {
      if (i === 0) return slopes[0] || 0;
      if (i === pts.length - 1) return slopes[slopes.length - 1] || 0;
      const a = slopes[i - 1], b = slopes[i];
      return a * b <= 0 ? 0 : 2 * a * b / (a + b);
    });
    let path = pts.length ? `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}` : '';
    for (let i = 0; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
      const dx = x1 - x0;
      path += ` C${(x0 + dx / 3).toFixed(1)},${(y0 + tangent[i] * dx / 3).toFixed(1)} ${(x1 - dx / 3).toFixed(1)},${(y1 - tangent[i + 1] * dx / 3).toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
    }
    if (combined) return path;
    const dots = pts.length === 1 ? `<circle cx="${pts[0][0]}" cy="${pts[0][1]}" r="3" fill="${color}"/>` : '';
    return `<div class="bf4cr-trend-label"><span style="color:${color}">${escape(label)}</span><span>Max ${ceiling}</span></div><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="${escape(label)} over ${values.length} matches" role="img"><path d="M7 ${height-pad}H${width-pad}" stroke="#344a61" stroke-width="1"/><path d="${path}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>${dots}</svg>`;
  }
  function combinedGraph(kills, deaths) {
    const width = 720, height = 148, pad = 12;
    const ceiling = Math.max(1, ...kills, ...deaths);
    const orange = graph('Kills', kills, '#f6a34b', ceiling, true);
    const blue = graph('Deaths', deaths, '#66c7ff', ceiling, true);
    return `<div class="bf4cr-trend-label"><span><span style="color:#f6a34b">● Kills</span> &nbsp; <span style="color:#66c7ff">● Deaths</span></span><span>Shared scale · Max ${ceiling}</span></div><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Kills and deaths together over ${kills.length} matches"><path d="M7 ${height-pad}H${width-pad}" stroke="#344a61" stroke-width="1"/><path d="${orange}" fill="none" stroke="#f6a34b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/><path d="${blue}" fill="none" stroke="#66c7ff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function refresh() {
    const rows = [...table.tBodies[0].rows].filter(r => r.getClientRects().length).slice(0, 200);
    const kills = rows.map(r => numeric(r.cells[ki].textContent));
    const deaths = rows.map(r => numeric(r.cells[di].textContent));
    const pairs = kills.map((k, i) => [k, deaths[i]]).filter(([k, d]) => Number.isFinite(k) && Number.isFinite(d));
    if (!pairs.length) return false;
    const ks = pairs.map(p => p[0]).reverse(), ds = pairs.map(p => p[1]).reverse();
    const totalK = ks.reduce((a, b) => a + b, 0), totalD = ds.reduce((a, b) => a + b, 0);
    const kd = totalD ? (totalK / totalD).toFixed(2) : (totalK ? '∞' : '0.00');
    countEl.textContent = `${pairs.length} reports`;
    statsEl.innerHTML = `<span>Total kills <b>${totalK.toLocaleString()}</b></span><span>Total deaths <b>${totalD.toLocaleString()}</b></span><span>Average K/D <b>${kd}</b></span>`;
    graphsEl.innerHTML = graph('Kills', ks, '#f6a34b') + graph('Deaths', ds, '#66c7ff') + combinedGraph(ks, ds);
    return true;
  }
  function position(x, y) {
    const margin = 12, rect = popup.getBoundingClientRect();
    const left = Math.min(Math.max(margin, x + 16), Math.max(margin, innerWidth - rect.width - margin));
    const top = Math.min(Math.max(margin, y + 16), Math.max(margin, innerHeight - rect.height - margin));
    popup.style.left = `${left}px`;
    popup.style.top = `${top}px`;
  }
  const target = el => el?.closest?.('[data-key="kills"], [data-key="deaths"], [data-key="kd"]');
  let active = false;
  table.addEventListener('pointerover', e => {
    if (e.pointerType === 'touch' || !target(e.target)) return;
    if (refresh()) { active = true; popup.classList.add('visible'); position(e.clientX, e.clientY); }
  });
  table.addEventListener('pointermove', e => {
    if (active && target(e.target)) position(e.clientX, e.clientY);
    else if (active) { active = false; popup.classList.remove('visible'); }
  });
  table.addEventListener('pointerleave', () => { active = false; popup.classList.remove('visible'); });
  table.addEventListener('focusin', e => { if (target(e.target) && refresh()) { popup.classList.add('visible'); position(innerWidth / 2, 100); } });
  table.addEventListener('focusout', () => popup.classList.remove('visible'));
})();