/* STT accuracy check. Records on the board, transcribes, scores against the phrase
   you were asked to read. Separate from the demo: no controller state is touched. */
const $ = id => document.getElementById(id);

// Drink wording the demo actually has to survive, plus the ways people decline.
const DEFAULT_PHRASES = [
  'A little water, please',
  'Can I get a refill of coke',
  'Coffee instead, please',
  'Just a half portion of water',
  'No thanks, I am fine',
  'Could you top up the coffee',
  'More coke please',
  'Actually make it water',
];

let phrases = load();
let index = 0;
let results = [];

// Takes live on the board, not in this tab: a reload, a second device or a
// restarted browser must not lose a measurement that took real speaking to get.
async function loadResults() {
  try {
    const response = await fetch('/api/stt/results');
    const body = await response.json();
    results = body.takes || [];
    summarise(results.at(-1)?.source);
  } catch {
    showError('Saved takes could not be loaded.');
  }
}

async function saveTake(take) {
  const response = await fetch('/api/stt/results', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(take),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || 'Could not save this take');
  results = body.takes;
}

async function dropTake(index) {
  const query = index === null ? '' : `?index=${index}`;
  const response = await fetch(`/api/stt/results${query}`, {method: 'DELETE'});
  const body = await response.json();
  results = body.takes || [];
  summarise();
}

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem('sttPhrases') || 'null');
    if (Array.isArray(saved) && saved.length) return saved;
  } catch { /* fall through to defaults */ }
  return DEFAULT_PHRASES.slice();
}

// Comparison ignores case, punctuation and spacing: the model is being judged on
// words heard, not on how the text happens to be formatted.
function words(text) {
  return text.toLowerCase().replace(/[^a-z0-9\s']/g, ' ').split(/\s+/).filter(Boolean);
}

// Levenshtein over words. Word error rate is the standard STT measure; exact match
// alone hides whether a miss was one word or the whole sentence.
function distance(a, b) {
  const rows = Array.from({length: a.length + 1}, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) rows[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      rows[i][j] = a[i - 1] === b[j - 1]
        ? rows[i - 1][j - 1]
        : 1 + Math.min(rows[i - 1][j - 1], rows[i][j - 1], rows[i - 1][j]);
  return rows[a.length][b.length];
}

function wer(expected, heard) {
  const a = words(expected), b = words(heard);
  if (!a.length) return b.length ? 1 : 0;
  return distance(a, b) / a.length;
}

function renderDiff(expected, heard) {
  const a = words(expected), b = words(heard);
  const seen = new Set(b);
  const node = $('sttDiff');
  node.replaceChildren();
  for (const word of a) {
    const tag = document.createElement(seen.has(word) ? 'ins' : 'del');
    tag.textContent = word;
    node.append(tag, ' ');
  }
  node.hidden = false;
}

// Suggestions only fill the box; whatever is typed there is what gets scored, so
// an unplanned sentence can be checked without editing the list first.
function showPhrase() {
  $('sttTarget').value = phrases[index % phrases.length] || '';
}

function renderSuggestions() {
  const box = $('sttSuggest');
  box.replaceChildren();
  for (const phrase of phrases) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = phrase;
    button.onclick = () => { $('sttTarget').value = phrase; $('sttTarget').focus(); };
    box.append(button);
  }
}

function summarise(source) {
  $('sttCount').textContent = results.length;
  const exact = results.filter(r => r.wer === 0).length;
  $('sttExact').textContent = results.length ? `${Math.round(exact / results.length * 100)}%` : '—';
  const mean = results.reduce((total, r) => total + r.wer, 0) / (results.length || 1);
  $('sttWer').textContent = results.length ? `${Math.round(mean * 100)}%` : '—';
  if (source) $('sttSource').textContent = source;

  const rows = $('sttRows');
  rows.replaceChildren();
  results.forEach((r, i) => {
    const row = document.createElement('tr');
    for (const value of [i + 1, r.expected, r.heard, `${Math.round(r.wer * 100)}%`]) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    }
    // A fumbled take says nothing about the model, so single rows can go.
    const cell = document.createElement('td');
    const drop = document.createElement('button');
    drop.type = 'button';
    drop.className = 'secondary';
    drop.textContent = '✕';
    drop.title = 'Discard this take';
    drop.onclick = () => dropTake(i).catch(() => showError('Could not discard that take.'));
    cell.append(drop);
    row.append(cell);
    rows.prepend(row);
  });
}

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = false;
  setTimeout(() => { $('error').hidden = true; }, 6000);
}

$('sttRecord').onclick = async () => {
  const expected = $('sttTarget').value.trim();
  if (!expected) return showError('Type the sentence you are about to say.');
  $('sttRecord').disabled = true;
  $('sttSkip').disabled = true;
  $('sttDiff').hidden = true;
  $('sttHeard').textContent = '';
  $('sttStatus').textContent = `Listening for ${$('sttSeconds').value}s…`;
  try {
    const seconds = $('sttSeconds').value;
    const response = await fetch(`/api/stt/check?seconds=${seconds}`, {method: 'POST'});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error?.message || 'Transcription failed');
    const score = wer(expected, body.text);
    await saveTake({
      expected, heard: body.text, wer: Number(score.toFixed(4)),
      seconds: body.seconds, source: body.source, at: new Date().toISOString(),
    });
    $('sttHeard').textContent = `“${body.text}”`;
    const verdict = document.createElement('span');
    verdict.className = `verdict ${score === 0 ? 'hit' : 'miss'}`;
    verdict.textContent = score === 0 ? 'EXACT' : `WER ${Math.round(score * 100)}%`;
    $('sttHeard').append(verdict);
    renderDiff(expected, body.text);
    summarise(body.source);
    // The sentence stays put: the same wording usually needs several takes before
    // its accuracy means anything. Use Next suggestion to move on.
  } catch (error) {
    showError(error.message);
  } finally {
    $('sttStatus').textContent = '';
    $('sttRecord').disabled = false;
    $('sttSkip').disabled = false;
  }
};

$('sttSkip').onclick = () => {
  index++;
  showPhrase();
  $('sttHeard').textContent = '';
  $('sttDiff').hidden = true;
};

$('sttSave').onclick = () => {
  const list = $('sttPhrases').value.split('\n').map(line => line.trim()).filter(Boolean);
  if (!list.length) return showError('Add at least one phrase.');
  phrases = list;
  localStorage.setItem('sttPhrases', JSON.stringify(list));
  index = 0;
  renderSuggestions();
  showPhrase();
};

$('sttReset').onclick = () => {
  localStorage.removeItem('sttPhrases');
  phrases = DEFAULT_PHRASES.slice();
  $('sttPhrases').value = phrases.join('\n');
  index = 0;
  renderSuggestions();
  showPhrase();
};

$('sttClear').onclick = () => {
  if (results.length && !confirm(`Discard all ${results.length} takes?`)) return;
  dropTake(null).catch(() => showError('Could not clear the saved takes.'));
};

$('sttCopy').onclick = async () => {
  const csv = ['expected,heard,wer']
    .concat(results.map(r => `"${r.expected}","${r.heard.replace(/"/g, '""')}",${r.wer.toFixed(3)}`))
    .join('\n');
  try {
    await navigator.clipboard.writeText(csv);
    $('sttStatus').textContent = 'Copied.';
    setTimeout(() => { $('sttStatus').textContent = ''; }, 2000);
  } catch {
    showError('Clipboard unavailable. Select the table instead.');
  }
};

$('sttCopyTop').onclick = () => $('sttCopy').click();

$('sttPhrases').value = phrases.join('\n');
renderSuggestions();
showPhrase();
summarise();
loadResults();
