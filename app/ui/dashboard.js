const $ = id => document.getElementById(id);
// The mock history is an evening bar in Los Angeles (scripts/make_mock_events.py), so hours
// and days are bucketed in the venue's time zone, not the viewing browser's.
const VENUE_TZ = 'America/Los_Angeles';
const DRINKS = ['water','coke','coffee','beer','cocktail','unknown'];
const COLORS = {water:'#4a8fb8', coke:'#a23b2a', coffee:'#6b4a2e', beer:'#d9a13b', cocktail:'#c45d8a', unknown:'#a9ab9f'};
const color = item => COLORS[item] || '#7f9a6a';
const NS = 'http://www.w3.org/2000/svg';
let events = [];
const levelChoice = {hourLevel: 'low', dayLevel: 'low'};

const parts = new Intl.DateTimeFormat('en-CA', {timeZone: VENUE_TZ, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', hourCycle:'h23'});
function venueTime(ts) {
  const p = Object.fromEntries(parts.formatToParts(new Date(ts)).map(x => [x.type, x.value]));
  const day = `${p.year}-${p.month}-${p.day}`;
  return {day, hour: Number(p.hour), weekday: new Date(`${day}T12:00:00Z`).getUTCDay()};
}
// Monday first, as a bar's week reads; values are Date.getUTCDay() numbers.
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 0];
const weekdayLabel = w => ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][w];
const hourLabel = h => `${h % 12 || 12}${h < 12 ? 'am' : 'pm'}`;
const dayLabel = d => new Date(`${d}T12:00:00Z`).toLocaleDateString('en-US', {timeZone:'UTC', weekday:'short', month:'numeric', day:'numeric'});
const dayLong = d => new Date(`${d}T12:00:00Z`).toLocaleDateString('en-US', {timeZone:'UTC', weekday:'long', month:'short', day:'numeric'});

function showError(message) { $('error').textContent = message; $('error').hidden = false; clearTimeout(showError.timer); showError.timer = setTimeout(() => $('error').hidden = true, 9000); }

// Contiguous axes so a quiet hour or day shows as a gap instead of disappearing.
function hourAxis(rows) {
  const hours = rows.map(r => r.hour);
  if (!hours.length) return [];
  const out = []; for (let h = Math.min(...hours); h <= Math.max(...hours); h++) out.push(h); return out;
}
function dayAxis(rows) {
  const days = [...new Set(rows.map(r => r.day))].sort();
  if (!days.length) return [];
  const out = [], end = new Date(`${days.at(-1)}T12:00:00Z`);
  for (let d = new Date(`${days[0]}T12:00:00Z`); d <= end; d.setUTCDate(d.getUTCDate() + 1)) out.push(d.toISOString().slice(0, 10));
  return out;
}
function countBy(rows, key) { const m = new Map(); for (const r of rows) m.set(r[key], (m.get(r[key]) || 0) + 1); return m; }
function drinksIn(rows) { const seen = new Set(rows.map(r => r.item)); return [...DRINKS.filter(d => seen.has(d)), ...[...seen].filter(d => !DRINKS.includes(d))]; }
function topOf(map) { let best = null; for (const [k, v] of map) if (!best || v > best[1]) best = [k, v]; return best; }

function niceMax(value, ticks = 4) {
  if (value <= 0) return {max: ticks, step: 1};
  const raw = value / ticks, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map(n => n * mag).find(s => s >= raw);
  return {max: Math.ceil(value / step) * step, step};
}

function el(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}
function frame(container, height = 380) {
  const width = Math.max(320, container.clientWidth);
  const svg = el('svg', {width, height, viewBox: `0 0 ${width} ${height}`, role: 'img'});
  container.replaceChildren(svg);
  return {svg, width, height, pad: {l: 56, r: 12, t: 36, b: 52}};
}
function axes(f, max, step) {
  const {svg, width, height, pad} = f, plotH = height - pad.t - pad.b;
  for (let v = 0; v <= max; v += step) {
    const y = pad.t + plotH - v / max * plotH;
    svg.append(el('line', {x1: pad.l, x2: width - pad.r, y1: y, y2: y, stroke: v ? '#e8eadf' : '#c9cbbf', 'stroke-width': v ? 1 : 2}));
    svg.append(el('text', {x: pad.l - 12, y: y + 6, 'text-anchor': 'end', 'font-size': 17}, v));
  }
  return y => pad.t + plotH - y / max * plotH;
}
function empty(f, message) { f.svg.append(el('text', {x: f.width / 2, y: f.height / 2, 'text-anchor': 'middle', class: 'empty'}, message)); }

function stackedBars(container, labels, series, emptyMessage) {
  const f = frame(container), {svg, width, pad} = f;
  const totals = labels.map((_, i) => series.reduce((s, x) => s + x.values[i], 0));
  if (!totals.some(Boolean)) return empty(f, emptyMessage);
  const {max, step} = niceMax(Math.max(...totals)), y = axes(f, max, step);
  const slot = (width - pad.l - pad.r) / labels.length, bar = Math.min(72, slot * 0.66);
  labels.forEach((label, i) => {
    const x = pad.l + slot * i + (slot - bar) / 2;
    let base = 0;
    for (const s of series) {
      const v = s.values[i]; if (!v) continue;
      const rect = el('rect', {x, width: bar, y: y(base + v), height: y(base) - y(base + v), fill: s.color, rx: 4});
      rect.append(el('title', {}, `${label} · ${s.name}: ${v}`)); svg.append(rect); base += v;
    }
    if (totals[i]) svg.append(el('text', {x: x + bar / 2, y: y(totals[i]) - 10, 'text-anchor': 'middle', 'font-size': 20, class: 'total'}, totals[i]));
    svg.append(el('text', {x: x + bar / 2, y: f.height - pad.b + 30, 'text-anchor': 'middle', 'font-size': 17}, label));
  });
}

function bars(container, labels, values, peak, emptyMessage) {
  const f = frame(container), {svg, width, pad} = f;
  if (!values.some(Boolean)) return empty(f, emptyMessage);
  const {max, step} = niceMax(Math.max(...values)), y = axes(f, max, step);
  const slot = (width - pad.l - pad.r) / labels.length, bar = Math.min(110, slot * 0.6);
  labels.forEach((label, i) => {
    const x = pad.l + slot * i + (slot - bar) / 2, isPeak = i === peak;
    if (values[i]) svg.append(el('rect', {x, width: bar, y: y(values[i]), height: y(0) - y(values[i]), rx: 6, fill: isPeak ? '#1e5140' : '#b9cc94'}));
    svg.append(el('text', {x: x + bar / 2, y: y(values[i]) - 10, 'text-anchor': 'middle', 'font-size': isPeak ? 26 : 20, class: isPeak ? 'peak' : 'total'}, values[i]));
    svg.append(el('text', {x: x + bar / 2, y: f.height - pad.b + 30, 'text-anchor': 'middle', 'font-size': 18, class: isPeak ? 'peak' : ''}, label));
  });
}

function line(container, labels, values, peak, emptyMessage) {
  const f = frame(container), {svg, width, pad} = f;
  if (!values.some(Boolean)) return empty(f, emptyMessage);
  const {max, step} = niceMax(Math.max(...values)), y = axes(f, max, step);
  const slot = (width - pad.l - pad.r) / labels.length, x = i => pad.l + slot * (i + 0.5);
  const points = values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  svg.append(el('polygon', {points: `${x(0)},${y(0)} ${points} ${x(values.length - 1)},${y(0)}`, fill: '#d9e9a766'}));
  svg.append(el('polyline', {points, fill: 'none', stroke: '#1e5140', 'stroke-width': 5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
  values.forEach((v, i) => {
    const isPeak = i === peak;
    svg.append(el('circle', {cx: x(i), cy: y(v), r: isPeak ? 11 : 7, fill: isPeak ? '#af593c' : '#fffefa', stroke: isPeak ? '#fffefa' : '#1e5140', 'stroke-width': 4}));
    svg.append(el('text', {x: x(i), y: y(v) - 18, 'text-anchor': 'middle', 'font-size': isPeak ? 26 : 19, class: isPeak ? 'peak' : 'total'}, v));
    svg.append(el('text', {x: x(i), y: f.height - pad.b + 30, 'text-anchor': 'middle', 'font-size': 17, class: isPeak ? 'peak' : ''}, labels[i]));
  });
}

function legend(card, drinks) {
  card.querySelector('[data-legend]').replaceChildren(...drinks.map(d => {
    const span = document.createElement('span'), dot = document.createElement('i');
    dot.style.background = color(d); span.append(dot, d); return span;
  }));
}

function ranking(rows) {
  const counts = [...countBy(rows, 'item')].sort((a, b) => b[1] - a[1]);
  const box = $('drinkRanking');
  if (!counts.length) { box.textContent = 'No requests yet.'; return; }
  const max = counts[0][1];
  box.replaceChildren(...counts.map(([item, n], i) => {
    const row = document.createElement('div'); row.className = 'rank-row';
    row.innerHTML = '<span class="rank-no"></span><span class="rank-name"></span><div class="rank-bar"><span></span></div><span class="rank-count"></span>';
    row.querySelector('.rank-no').textContent = i + 1;
    row.querySelector('.rank-name').textContent = item;
    Object.assign(row.querySelector('.rank-bar span').style, {width: `${n / max * 100}%`, background: color(item)});
    row.querySelector('.rank-count').textContent = n;
    return row;
  }));
}

const stamp = new Intl.DateTimeFormat('en-US', {timeZone: VENUE_TZ, weekday:'short', month:'short', day:'numeric', hour:'numeric', minute:'2-digit'});
function ago(ts) {
  const minutes = Math.round((Date.now() - new Date(ts)) / 60000);
  // Mock history runs to 10pm on the demo day, so it can sit in the future.
  if (minutes < 0) return '';
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / 60 / 24)} d ago`;
}
function recent(rows) {
  const box = $('recentLog');
  const latest = [...rows].sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 5);
  if (!latest.length) { box.textContent = 'No events yet.'; return; }
  box.replaceChildren(...latest.map(r => {
    const li = document.createElement('li'); li.className = `recent-row ${r.event}`;
    li.innerHTML = '<span class="recent-kind"></span><span class="recent-drink"><i></i><b></b></span><span class="recent-detail"></span><span class="recent-time"><b></b><small></small></span>';
    li.querySelector('.recent-kind').textContent = r.event === 'requested' ? 'Request' : 'Detect';
    li.querySelector('.recent-drink i').style.background = color(r.item);
    li.querySelector('.recent-drink b').textContent = r.item;
    const detail = li.querySelector('.recent-detail');
    if (r.event === 'detected') {
      const level = document.createElement('span'); level.className = `level-tag ${r.level}`;
      level.textContent = r.level === 'unknown' ? 'Fill ?' : r.level;
      detail.append(level);
      if (r.fill_ratio != null) detail.append(` ${Math.round(r.fill_ratio * 100)}% left`);
    } else {
      detail.textContent = r.transcript ? `\u201C${r.transcript}\u201D` : 'Refill requested';
    }
    li.querySelector('.recent-time b').textContent = stamp.format(new Date(r.ts));
    li.querySelector('.recent-time small').textContent = ago(r.ts);
    return li;
  }));
}

function render() {
  const rows = events
    .filter(e => e.ts && (e.event === 'detected' || e.event === 'requested'))
    .map(e => ({...e, item: e.item || 'unknown', ...venueTime(e.ts)}));
  const detected = rows.filter(r => r.event === 'detected'), requested = rows.filter(r => r.event === 'requested');
  const hours = hourAxis(rows), days = dayAxis(rows);

  // Detected drinks by hour / weekday, for the chosen fill level.
  for (const [id, axis, key, fmt] of [['hourLevel', hours, 'hour', hourLabel], ['dayLevel', WEEKDAYS, 'weekday', weekdayLabel]]) {
    const level = levelChoice[id], subset = detected.filter(r => r.level === level), drinks = drinksIn(subset);
    const series = drinks.map(d => ({name: d, color: color(d), values: axis.map(a => subset.filter(r => r.item === d && r[key] === a).length)}));
    stackedBars($(id), axis.map(fmt), series, `No ${level} cups detected`);
    legend($(id).closest('.chart-card'), drinks);
  }

  ranking(requested);
  recent(rows);

  const byHour = countBy(requested, 'hour'), byDay = countBy(requested, 'day');
  const hourValues = hours.map(h => byHour.get(h) || 0), dayValues = days.map(d => byDay.get(d) || 0);
  const peakHour = topOf(byHour), peakDay = topOf(byDay), topDrink = topOf(countBy(requested, 'item'));
  line($('hourRequests'), hours.map(hourLabel), hourValues, peakHour ? hours.indexOf(peakHour[0]) : -1, 'No requests yet');
  bars($('dayRequests'), days.map(dayLabel), dayValues, peakDay ? days.indexOf(peakDay[0]) : -1, 'No requests yet');

  const low = detected.filter(r => r.level === 'low').length;
  $('kpiDetected').textContent = detected.length;
  $('kpiDetectedSub').textContent = `${low} low · ${detected.length - low} high`;
  $('kpiRequests').textContent = requested.length;
  $('kpiRequestsSub').textContent = detected.length ? `${Math.round(requested.length / Math.max(low, 1) * 100)}% of low cups` : '';
  $('kpiTopDrink').textContent = topDrink ? topDrink[0] : '–';
  $('kpiTopDrinkSub').textContent = topDrink ? `${topDrink[1]} requests` : 'No requests yet';
  $('kpiTopDay').textContent = peakDay ? dayLabel(peakDay[0]) : '–';
  $('kpiTopDaySub').textContent = peakDay ? `${dayLong(peakDay[0])} · ${peakDay[1]} requests` : 'No requests yet';
  $('kpiTopHour').textContent = peakHour ? hourLabel(peakHour[0]) : '–';
  $('kpiTopHourSub').textContent = peakHour ? `${hourLabel(peakHour[0])}–${hourLabel((peakHour[0] + 1) % 24)} · ${peakHour[1]} requests` : 'No requests yet';

  $('rangeNote').textContent = days.length
    ? `${dayLong(days[0])} – ${dayLong(days.at(-1))} · ${hours.length ? `${hourLabel(hours[0])}–${hourLabel((hours.at(-1) + 1) % 24)}` : ''} · times in Los Angeles`
    : 'No events yet.';
}

async function load() {
  try {
    const response = await fetch('/api/events', {cache: 'no-store'});
    if (!response.ok) throw Error('The event history is unavailable.');
    events = (await response.json()).events;
    render();
  } catch (error) { showError(error.message || 'Could not reach the Controller.'); }
}

document.querySelectorAll('.segmented.level').forEach(group => group.onclick = event => {
  const button = event.target.closest('button'); if (!button) return;
  levelChoice[group.dataset.chart] = button.dataset.level;
  group.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === button));
  render();
});
let resizeTimer = null;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(render, 150); });
load();
// Live rows land in the log as the demo runs; keep the board current without a reload.
setInterval(load, 10000);
