/* Venue display: shows what the board just did. Read-only — it never posts, so a
   stray touch on the projector cannot disturb a run.

   It reads the Controller's own websocket rather than keeping state of its own, so
   it can join or reconnect mid-demo and immediately show the current step. The
   Controller is on another port, so its origin is taken from ?controller= or
   assumed to be this host on 8080. */
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const CONTROLLER = (params.get('controller') || `${location.hostname}:8080`).replace(/\/+$/, '');
const HTTP = `${location.protocol}//${CONTROLLER}`;
const WS = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${CONTROLLER}/ws`;

const STEPS = ['look', 'offer', 'listen', 'hear', 'understand', 'act'];
// How far each phase has carried the demo. Anything not listed leaves the rail alone.
const REACHED = {
  idle: -1, observing: 0, skipped: 0,
  offered: 1, not_understood: 1,
  listening: 2, transcribing: 3,
  interpreting: 4, card: 4, declined: 4, cancelled: 4,
  loading: 5, returning: 5, done: 5,
};
const FAILED = new Set(['skipped', 'declined', 'cancelled', 'expired', 'error']);

let state = null;
let policy = {low_fill_threshold: 0.35, min_confidence: 0.6};
// The conversation builds up here: the room should be able to read what was said
// a moment ago, not just the current line.
let chat = [];
let chatSession = null;
// The last line recorded from each side. A transcript stays in the state after it
// is read, so without this it was re-added as soon as the assistant replied.
// Cleared when a new recording starts, so a customer who repeats a sentence after
// "say that again" is shown twice, which is what the room saw happen.
let said = {assistant: null, customer: null};
let lastPhase = null;
let shownSnapshot = null;
let streaming = false;
let retry = null;

function paintRuntime(ready) {
  const chips = [];
  const add = (label, value, kind) => chips.push({label, value, kind});
  if (ready) {
    add('Vision', ready.dependencies?.vision?.source === 'external' ? 'DINOv2 · NPU' : 'fixture',
        ready.dependencies?.vision?.source === 'external' ? 'npu' : '');
    add('Speech', ready.dependencies?.stt?.source === 'external' ? 'whisper · CPU' : 'fixture',
        ready.dependencies?.stt?.source === 'external' ? 'cpu' : '');
    add('Language', ready.dependencies?.qwen?.model || '—',
        ready.dependencies?.qwen?.ready ? 'npu' : '');
    if (ready.tts?.ready) add('Voice', `Piper · ${(ready.tts.decoder || '').toUpperCase()}`, 'npu');
    add('Board', ready.hardware === 'bridge' ? 'MCU over Bridge' : 'mock', '');
  }
  const box = $('runtime');
  box.replaceChildren();
  for (const chip of chips) {
    const node = document.createElement('span');
    node.className = `chip ${chip.kind}`;
    const name = document.createElement('b');
    name.textContent = chip.label;
    node.append(name, ` ${chip.value}`);
    box.append(node);
  }
}

async function loadRuntime() {
  // Same-origin: this server relays the Controller's /ready, which a cross-origin
  // fetch could not read.
  try {
    const ready = await (await fetch('/runtime')).json();
    // The same thresholds the Controller marks a refill with, so both screens
    // call the same cup low.
    if (ready.policy) policy = ready.policy;
    paintRuntime(ready);
  } catch {
    paintRuntime(null);
  }
}

function needsRefill(object) {
  return object.fill_ratio !== null && object.confidence !== null
    && object.fill_ratio <= policy.low_fill_threshold
    && object.confidence >= policy.min_confidence;
}

function paintSteps(phase) {
  const reached = REACHED[phase];
  if (reached === undefined) return;
  STEPS.forEach((name, index) => {
    const node = document.querySelector(`[data-step="${name}"]`);
    node.classList.toggle('done', index < reached);
    node.classList.toggle('active', index === reached && !FAILED.has(phase));
    node.classList.toggle('failed', index === reached && FAILED.has(phase));
  });
}

function paintImage() {
  const snapshot = state?.snapshot_url;
  if (snapshot) {
    if (shownSnapshot !== snapshot) {
      shownSnapshot = snapshot;
      streaming = false;
      $('sceneImage').src = HTTP + snapshot;
      $('frameLabel').textContent = 'Analyzed frame';
    }
    return;
  }
  shownSnapshot = null;
  if (streaming) return;
  streaming = true;
  $('frameLabel').textContent = 'Live view';
  const image = $('sceneImage');
  image.src = `${HTTP}/api/video?t=${Date.now()}`;
  image.onerror = () => {
    streaming = false;
    setTimeout(paintImage, 1500);  // the feed drops; the display should not stay blank
  };
}

function paintBoxes() {
  const boxes = $('boxes');
  boxes.replaceChildren();
  // Boxes belong to the analyzed frame only: on the live view they would point at
  // cups that have since been moved.
  if (!state?.snapshot_url) return;
  for (const object of state.scene?.objects || []) {
    const node = document.createElement('div');
    const selected = object.object_id === state.target?.object_id;
    const refill = needsRefill(object);
    node.className = `bbox${selected ? ' selected' : ''}${refill ? ' refill' : ''}`;
    const b = object.bbox;
    Object.assign(node.style, {
      left: `${b.x1 * 100}%`, top: `${b.y1 * 100}%`,
      width: `${(b.x2 - b.x1) * 100}%`, height: `${(b.y2 - b.y1) * 100}%`,
    });
    const label = document.createElement('span');
    label.className = 'box-label';
    const item = object.item.replace(/_/g, ' ');
    const fill = object.fill_ratio === null
      ? 'fill ?' : `${Math.round(object.fill_ratio * 100)}% left`;
    label.textContent = `${object.object_id} · ${item}${refill ? ' · REFILL' : ''}\n`
      + `${fill} · conf ${Math.round((object.confidence ?? 0) * 100)}%`;
    node.append(label);
    boxes.append(node);
  }
}

function paintObjects() {
  const list = $('objects');
  list.replaceChildren();
  const objects = state?.scene?.objects || [];
  if (!objects.length) {
    const empty = document.createElement('p');
    empty.className = 'source';
    empty.textContent = state?.phase === 'idle' ? 'Waiting for a table.' : 'Nothing recognised yet.';
    list.append(empty);
    return;
  }
  for (const object of objects) {
    const isTarget = object.object_id === state.target?.object_id;
    const fill = object.fill_ratio;
    const refill = needsRefill(object);
    const node = document.createElement('div');
    node.className = `object${isTarget ? ' target' : ''}${refill ? ' refill' : ''}`;

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = object.item.replace(/_/g, ' ');
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = [
      fill === null ? null : `fill ${Math.round(fill * 100)}%`,
      object.confidence === null ? null : `conf ${object.confidence.toFixed(2)}`,
    ].filter(Boolean).join(' · ');
    const bar = document.createElement('div');
    bar.className = 'bar';
    const level = document.createElement('i');
    level.style.width = `${Math.round((fill ?? 0) * 100)}%`;
    bar.append(level);

    node.append(name, meta, bar);
    list.append(node);
  }
}

// The room cannot hear the tablet, so both sides of the exchange are written out
// and kept: an assistant line when it is spoken, a customer line when it is heard.
function recordTurns() {
  if (!state) return;
  if (chatSession !== state.session_id) {
    chatSession = state.session_id;
    chat = [];
    said = {assistant: null, customer: null};
  }
  if (state.phase === 'listening' && lastPhase !== 'listening') {
    said = {assistant: null, customer: null};  // a new take may repeat the last one
  }
  lastPhase = state.phase;
  const add = (who, text, note) => {
    if (!text || said[who] === text) return;
    said[who] = text;
    chat.push({who, text, note});
  };
  add('assistant', state.speech);
  add('customer', state.transcript,
      state.stt_source ? `${state.stt_source.toUpperCase()} speech recognition` : null);
}

function paintChat() {
  const box = $('chat');
  box.replaceChildren();
  for (const turn of chat) {
    const node = document.createElement('div');
    node.className = `turn ${turn.who}`;
    node.append(document.createTextNode(
      turn.who === 'customer' ? `“${turn.text}”` : turn.text));
    if (turn.note) {
      const note = document.createElement('small');
      note.textContent = turn.note;
      node.append(note);
    }
    box.append(node);
  }
  box.scrollTop = box.scrollHeight;
}

function paintText() {
  $('phaseTag').textContent = (state?.phase || 'idle').replace(/_/g, ' ').toUpperCase();
  recordTurns();
  paintChat();

  const card = state?.card;
  $('requestPanel').hidden = !card;
  if (card) {
    $('request').replaceChildren(
      document.createTextNode(card.item.replace(/_/g, ' ')));
    const source = document.createElement('span');
    source.className = 'source';
    source.textContent = `interpreted by ${state.qwen_source || 'the language model'}`
      + (state.phase === 'done' ? ' · sequence complete' : '');
    $('request').append(source);
  }
}

function render(next) {
  state = next;
  paintSteps(next.phase);
  paintImage();
  paintBoxes();
  paintObjects();
  paintText();
}

function connect() {
  clearTimeout(retry);
  const socket = new WebSocket(WS);
  socket.onopen = () => {
    $('link').textContent = `connected · ${CONTROLLER}`;
    $('link').classList.remove('down');
    loadRuntime();
  };
  socket.onmessage = event => {
    const payload = JSON.parse(event.data);
    if (payload.type === 'state') render(payload.state);
  };
  socket.onclose = () => {
    $('link').textContent = 'reconnecting…';
    $('link').classList.add('down');
    retry = setTimeout(connect, 1500);
  };
  socket.onerror = () => socket.close();
}

connect();
setInterval(loadRuntime, 30000);
