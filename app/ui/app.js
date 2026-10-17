const $ = id => document.getElementById(id);
let state = null, connected = false, sound = false, recorder = null, chunks = [], recordingStream = null;
let displayedSession = '', lastPhase = '', retryTimer = null;
let audioContext = null, playingSource = null;
const audioBuffers = new Map();

function showError(message) { $('error').textContent = message; $('error').hidden = false; clearTimeout(showError.timer); showError.timer = setTimeout(() => $('error').hidden = true, 9000); }
async function api(path, options = {}) {
  try {
    const response = await fetch(path, options);
    const body = await response.json();
    if (!response.ok) throw Error(body.error?.message || 'The service is unavailable. Please retry.');
    return body;
  } catch (error) { showError(error.message); throw error; }
}
function post(path, data) { return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); }
async function playPrompt(name) {
  if (!sound || !audioContext) return;
  try {
    if (!audioBuffers.has(name)) {
      const response = await fetch(`/ui/audio/${name}.wav`);
      if (!response.ok) throw Error('Audio file unavailable');
      audioBuffers.set(name, await audioContext.decodeAudioData(await response.arrayBuffer()));
    }
    if (!sound) return;
    playingSource?.stop();
    playingSource = audioContext.createBufferSource();
    playingSource.buffer = audioBuffers.get(name);
    playingSource.connect(audioContext.destination);
    playingSource.start();
  } catch {
    sound = false; $('audioToggle').textContent = 'Enable sound';
    $('audioToggle').setAttribute('aria-pressed','false');
    showError('Sound could not start. Tap Enable sound and check your browser audio permissions.');
  }
}
function modePill(label, source, ready = true) {
  const el = document.createElement('span'); el.className = 'source' + (ready ? '' : ' bad');
  el.textContent = `${label}: ${source}${ready ? '' : ' · unavailable'}`; return el;
}
async function checkConnection() {
  try {
    const response = await fetch('/ready'); const info = await response.json();
    const sources = $('sources'); sources.replaceChildren();
    for (const [name, data] of Object.entries(info.dependencies)) sources.append(modePill(name.toUpperCase(), data.source, data.ready));
    sources.append(modePill('Hardware', info.hardware)); sources.append(modePill('Location', info.location));
    $('videoMode').textContent = info.video.mode === 'fixture-image' ? 'Sample image' : 'Live source';
    $('imageCredit').textContent = info.video.mode === 'fixture-image' ? 'AI-generated sample · illustrative fixture' : 'Captured by the server · single video owner';
    $('liveStatus').textContent = info.video.error || 'Server capture · camera is opened once · 5 fps preview';
    $('liveRibbon').hidden = info.video.mode === 'fixture-image';
    if (info.video.mode !== 'fixture-image' && !$('liveFeed').getAttribute('src')) $('liveFeed').src='/api/video';
  } catch { $('sources').textContent = 'Cannot reach the Controller. Reconnecting…'; }
}
function render(next, authoritative = false) {
  if (state && state.instance_id === next.instance_id && next.sequence < state.sequence) return;
  if (state && state.instance_id !== next.instance_id && !authoritative) return;
  state = next;
  $('phase').textContent = state.phase.toUpperCase(); $('message').textContent = state.message;
  const editable = connected && ['offered','card','clarify','error'].includes(state.phase) && !!state.target;
  $('utterance').disabled = !editable; $('send').disabled = !editable;
  $('record').disabled = !editable; $('audioFile').disabled = !editable;
  if (!editable && recorder?.state === 'recording') recorder.stop();
  document.querySelectorAll('[data-say]').forEach(b => b.disabled = !editable);
  $('confirm').disabled = !connected || state.phase !== 'card';
  $('cancel').disabled = !connected || ['idle','done','cancelled','declined','skipped','expired'].includes(state.phase);
  $('start').disabled = !connected || ['observing','loading','returning'].includes(state.phase);
  $('start').innerHTML = (state.phase === 'idle' ? 'Start demo' : 'Inspect again') + ' <span>↗</span>';
  if (state.snapshot_url && displayedSession !== state.session_id) {
    $('sceneImage').src = state.snapshot_url; displayedSession = state.session_id;
    $('videoMode').textContent = 'Analyzed frame · frozen';
  }
  const boxes = $('boxes'); boxes.replaceChildren(); const objects = $('objects'); objects.replaceChildren();
  for (const obj of state.scene?.objects || []) {
    const selected = obj.object_id === state.target?.object_id;
    const box = document.createElement('div'); box.className = 'bbox' + (selected ? ' selected' : '');
    const b = obj.bbox; Object.assign(box.style, {left:`${b.x1*100}%`, top:`${b.y1*100}%`, width:`${(b.x2-b.x1)*100}%`, height:`${(b.y2-b.y1)*100}%`});
    const label = document.createElement('span'); label.className = 'box-label'; label.textContent = `${obj.object_id} · ${obj.item}`; box.append(label); boxes.append(box);
    const card = document.createElement('div'); card.className = 'object' + (selected ? ' target' : '');
    const title = document.createElement('strong'); title.textContent = obj.item; card.append(title);
    const small = document.createElement('small'); small.textContent = obj.object_id; card.append(small);
    const bar = document.createElement('div'); bar.className='fill'; const fill = document.createElement('span'); fill.style.width=`${(obj.fill_ratio || 0)*100}%`; bar.append(fill); card.append(bar);
    const details = document.createElement('span'); details.textContent = `${obj.fill_ratio === null ? 'Unknown fill' : Math.round(obj.fill_ratio*100)+'% left'} · ${Math.round(obj.confidence*100)}% confidence`; card.append(details); objects.append(card);
  }
  $('sceneTitle').textContent = state.scene ? `${state.scene.objects.length} cups observed` : 'Ready when you are';
  $('sceneSubtitle').textContent = state.scene ? `${state.scene.source === 'fixture' ? 'FIXTURE · Predetermined labels and scores' : 'EXTERNAL · Model team observations'}` : 'Inspect a scene to see the cups and their fill levels.';
  $('requestCard').hidden = !state.card;
  if (state.card) {
    $('cardDrink').textContent = state.card.item; $('cardPortion').textContent = `${state.card.portion} refill`;
    $('revision').textContent = `v${state.card.revision}`;
    $('targetId').textContent = `Target ${state.card.object_id} · Frozen at proposal · ${state.qwen_source || 'pending'} Qwen`;
    // CSS presentation of the frozen target. Never supplied as model crop/preprocessing.
    const b = state.target.bbox, width = b.x2-b.x1, height = b.y2-b.y1;
    $('targetImage').style.backgroundImage = `url("${state.snapshot_url}")`;
    $('targetImage').style.backgroundSize = `${100/width}% ${100/height}%`;
    $('targetImage').style.backgroundPosition = `${b.x1/(1-width)*100}% ${b.y1/(1-height)*100}%`;
  }
  const step = ['observing','skipped'].includes(state.phase) ? 0 : ['offered','interpreting','clarify','error'].includes(state.phase) ? 1 : state.phase === 'card' ? 2 : ['loading','returning','done'].includes(state.phase) ? 3 : -1;
  document.querySelectorAll('[data-step]').forEach(e => e.classList.toggle('active', Number(e.dataset.step) <= step));
  if (lastPhase !== state.phase) {
    if (state.phase === 'offered') playPrompt('offer');
    if (state.phase === 'card') playPrompt('review');
    if (state.phase === 'done') playPrompt('done');
    if (state.phase === 'cancelled') playPrompt('cancelled');
    lastPhase = state.phase;
  }
}
function connect() {
  clearTimeout(retryTimer);
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => {connected=true; $('connection').textContent='● Connected'; $('connection').classList.add('online'); checkConnection();};
  ws.onmessage = event => {const data=JSON.parse(event.data); if(data.type==='state') render(data.state, true);};
  ws.onclose = () => {connected=false; $('connection').textContent='Reconnecting…'; $('connection').classList.remove('online'); if(state) render(state); retryTimer=setTimeout(connect,1500);};
  ws.onerror = () => ws.close();
}
async function observe() {
  if (recorder?.state === 'recording') recorder.stop();
  const form = new FormData(); form.append('scenario', $('scenario').value);
  if ($('imageFile').files[0]) form.append('file', $('imageFile').files[0]);
  $('transcript').hidden = true;
  render(await api('/api/observe', {method:'POST', body:form}));
}
$('start').onclick = () => { if(!sound) {$('audioToggle').click();} observe().catch(()=>{}); };
async function send(utterance) {
  if(!state?.target) return;
  render(await post('/api/utterance', {scene_id:state.scene.scene_id, object_id:state.target.object_id, utterance}));
}
$('requestForm').onsubmit = event => {event.preventDefault(); const value=$('utterance').value.trim(); if(value) send(value).catch(()=>{});};
document.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {$('utterance').value=b.dataset.say; send(b.dataset.say).catch(()=>{});});
// Confirmation only sends the contract identity fields (not presentation/model fields).
$('confirm').onclick = async () => {const c=state?.card; if(!c) return; $('confirm').disabled=true; try {render(await post('/api/confirm', {scene_id:c.scene_id,object_id:c.object_id,request_id:c.request_id,revision:c.revision}));} catch {api('/api/state').then(render).catch(()=>{});}};
$('cancel').onclick = () => post('/api/cancel',{session_id:state.session_id}).then(render).catch(()=>{});
$('refresh').onclick = checkConnection;
$('audioToggle').onclick = () => {
  sound=!sound;
  $('audioToggle').textContent=sound?'Sound on':'Enable sound';
  $('audioToggle').setAttribute('aria-pressed',String(sound));
  if(sound) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {sound=false; showError('This browser does not support audio playback.'); return;}
    audioContext ||= new AudioContextClass();
    audioContext.resume().then(()=>playPrompt('welcome')).catch(()=>showError('Tap Enable sound to activate audio.'));
  } else {playingSource?.stop(); playingSource=null;}
};
$('livePreview').parentElement.addEventListener('toggle', event => {if(event.target.open) $('livePreview').src='/api/video'; else $('livePreview').removeAttribute('src');});
async function transcribe(blob) {
  if (!state || !['offered','card','clarify','error'].includes(state.phase)) return;
  const session = state?.session_id;
  $('recordStatus').textContent='Transcribing…'; const form=new FormData(); form.append('file',blob,'request');
  try {
    const result=await api('/api/transcribe',{method:'POST',body:form});
    if(session !== state?.session_id || !['offered','card','clarify','error'].includes(state.phase)) return;
    $('utterance').value=result.text; $('transcript').textContent=`${result.source.toUpperCase()} STT: “${result.text}” — review and send the text.`; $('transcript').hidden=false;
  } finally { $('recordStatus').textContent=''; }
}
$('audioFile').onchange = () => {if($('audioFile').files[0]) transcribe($('audioFile').files[0]).catch(()=>{});};
$('record').onclick = async () => {
  if(recorder?.state==='recording') {recorder.stop(); return;}
  try {
    if(!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw Error('Microphone recording requires localhost or HTTPS. Upload an audio file instead.');
    recordingStream=await navigator.mediaDevices.getUserMedia({audio:true});
    const mime=['audio/webm','audio/mp4','audio/ogg'].find(t=>MediaRecorder.isTypeSupported(t));
    recorder=new MediaRecorder(recordingStream,mime?{mimeType:mime}:{}); chunks=[];
    recorder.ondataavailable=e=>{if(e.data.size) chunks.push(e.data);};
    recorder.onstop=()=>{clearTimeout(recorder.timer); recordingStream.getTracks().forEach(t=>t.stop()); $('record').textContent='◉ Record request'; transcribe(new Blob(chunks,{type:recorder.mimeType})).catch(()=>{});};
    recorder.start(); $('record').textContent='■ Stop recording'; $('recordStatus').textContent='Recording · max 15 seconds';
    recorder.timer=setTimeout(()=>{if(recorder.state==='recording') recorder.stop();},15000);
  } catch(error) {showError(error.message); recordingStream?.getTracks().forEach(t=>t.stop());}
};
window.addEventListener('beforeunload',()=>recordingStream?.getTracks().forEach(t=>t.stop()));
connect();
$('mediaSupport').textContent = window.isSecureContext && navigator.mediaDevices?.getUserMedia
  ? 'Microphone & speaker: this browser · permission requested when recording'
  : 'For tablet microphone access, open the HTTPS demo URL.';
