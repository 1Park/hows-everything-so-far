const $ = id => document.getElementById(id);
let state = null, connected = false, sound = false, recorder = null, recordingStream = null;
let displayedSession = '', lastPhase = '', retryTimer = null;
let audioContext = null, playingSource = null;
let draftVersion = 0, transcriptionVersion = 0, micVersion = 0;
let micPending = false, transcribing = false, pendingAction = null;
let audioVersion = 0;
const audioBuffers = new Map();
const editablePhases = ['offered','card','clarify','error'];
function canEdit() { return connected && !!state?.target && editablePhases.includes(state.phase); }
function stopRecording(discard = false) {
  micVersion++;
  if (recorder?.state === 'recording') {
    recorder.discard ||= discard;
    recorder.stop();
  }
}
function setSound(enabled) {
  sound = enabled;
  $('audioToggle').textContent = sound ? 'Sound on' : 'Enable sound';
  $('audioToggle').setAttribute('aria-pressed', String(sound));
}

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
  if (!sound || !audioContext) return false;
  const version = ++audioVersion;
  try {
    if (!audioBuffers.has(name)) {
      const response = await fetch(`/ui/audio/${name}.wav`);
      if (!response.ok) throw Error('Audio file unavailable');
      audioBuffers.set(name, await audioContext.decodeAudioData(await response.arrayBuffer()));
    }
    if (!sound || version !== audioVersion || audioContext.state !== 'running') return false;
    playingSource?.stop();
    playingSource = audioContext.createBufferSource();
    playingSource.buffer = audioBuffers.get(name);
    playingSource.connect(audioContext.destination);
    const source = playingSource;
    return await new Promise(resolve => {
      source.onended = () => resolve(sound && version === audioVersion);
      source.start();
    });
  } catch {
    if (version !== audioVersion) return;
    setSound(false);
    showError('Sound could not start. Tap Enable sound and check your browser audio permissions.');
    return false;
  }
}
async function announceOffer() {
  const prompt = state;
  if (!prompt || prompt.phase !== 'offered' || !connected) return;
  const finished = await playPrompt('offer');
  if (!finished || state?.session_id !== prompt.session_id || state.sequence !== prompt.sequence || !connected) return;
  if (state.audio_input === 'disabled') return;
  try {
    const response = await fetch('/api/voice/listen', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:prompt.session_id,scene_id:prompt.scene.scene_id,
        object_id:prompt.target.object_id,sequence:prompt.sequence})});
    const body = await response.json();
    if (response.ok) render(body);
    else if (response.status !== 409) showError(body.error?.message || 'Board recording could not start.');
  } catch {showError('Could not reach the board microphone. Please retry.');}
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
    sources.append(modePill('Hardware', info.hardware, info.hardware_ready)); sources.append(modePill('Location', info.location));
    $('videoMode').textContent = state?.snapshot_url ? 'Analyzed frame · frozen' : info.video.mode === 'fixture-image' ? 'Sample image' : 'Live source';
    $('imageCredit').textContent = info.video.mode === 'fixture-image' ? 'AI-generated sample · illustrative fixture' : 'Captured by the server · single video owner';
    $('liveStatus').textContent = info.video.error || 'Server capture · camera is opened once · 5 fps preview';
    $('liveRibbon').hidden = info.video.mode === 'fixture-image';
    if (info.video.mode !== 'fixture-image' && !$('liveFeed').getAttribute('src')) $('liveFeed').src='/api/video';
  } catch { $('sources').textContent = 'Cannot reach the Controller. Reconnecting…'; }
}
function render(next, authoritative = false) {
  if (state && state.instance_id === next.instance_id && next.sequence < state.sequence) return;
  if (state && state.instance_id !== next.instance_id && !authoritative) return;
  if (!state || state.session_id !== next.session_id || state.instance_id !== next.instance_id) {
    stopRecording(true); transcriptionVersion++; draftVersion++;
    $('utterance').value = ''; $('transcript').hidden = true;
    $('recordStatus').textContent = ''; $('error').hidden = true;
    $('audioFile').value = '';
    displayedSession = ''; lastPhase = '';
  }
  state = next;
  $('replayVoice').disabled = ['listening','transcribing'].includes(state.phase);
  if ($('replayVoice').disabled) $('voicePreview').pause();
  const boardAudio = state.audio_input && state.audio_input !== 'disabled';
  $('phase').textContent = state.phase.toUpperCase(); $('message').textContent = state.message;
  const editable = canEdit() && !pendingAction;
  $('utterance').disabled = !editable; $('send').disabled = !editable;
  $('record').disabled = !editable || micPending || transcribing || (boardAudio && !['offered','clarify','error'].includes(state.phase));
  $('audioFile').disabled = !editable || micPending || transcribing || recorder?.state === 'recording';
  if (!canEdit() || pendingAction) stopRecording(true);
  $('audioFile').parentElement.hidden = boardAudio;
  if (boardAudio) {
    $('record').textContent = 'Retry board recording';
    $('mediaSupport').textContent = `Microphone: ${state.audio_input === 'fixture' ? 'FIXTURE audio, not a real microphone' : 'board'} · Speaker: this tablet · Recording starts after the offer`;
    $('recordStatus').textContent = state.phase === 'listening' ? 'Listening on the board…' : state.phase === 'transcribing' ? 'Transcribing…' : '';
  }
  if (state.transcript) {
    $('transcript').textContent = `${state.stt_source.toUpperCase()} STT: “${state.transcript}” — interpreted automatically; review the card before confirming.`;
    $('transcript').hidden = false;
  }
  document.querySelectorAll('[data-say]').forEach(b => b.disabled = !editable);
  $('confirm').disabled = !connected || !!pendingAction || state.phase !== 'card';
  $('cancel').disabled = !connected || pendingAction === 'cancel' || ['idle','done','cancelled','declined','skipped','expired'].includes(state.phase);
  $('start').disabled = !connected || !!pendingAction || ['observing','listening','transcribing','loading','returning'].includes(state.phase);
  $('start').innerHTML = (state.phase === 'idle' ? 'Start demo' : 'Inspect again') + ' <span>↗</span>';
  if (state.snapshot_url && displayedSession !== state.session_id) {
    $('boxes').hidden = true;
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
  $('requestCard').hidden = !state.card || !['card','interpreting','clarify','error','loading','returning','done'].includes(state.phase);
  if (state.card) {
    $('cardDrink').textContent = state.card.item; $('cardPortion').textContent = `${state.card.portion} refill`;
    $('revision').textContent = `v${state.card.revision}`;
    $('targetId').textContent = `Target ${state.card.object_id} · Frozen at proposal · ${state.qwen_source || 'pending'} Qwen`;
    // CSS presentation of the frozen target. Never supplied as model crop/preprocessing.
    const b = state.target.bbox, width = b.x2-b.x1, height = b.y2-b.y1;
    $('targetImage').style.backgroundImage = `url("${state.snapshot_url}")`;
    $('targetImage').style.backgroundSize = `${100/width}% ${100/height}%`;
    $('targetImage').style.backgroundPosition = `${width === 1 ? 0 : b.x1/(1-width)*100}% ${height === 1 ? 0 : b.y1/(1-height)*100}%`;
  }
  const step = ['observing','skipped'].includes(state.phase) ? 0 : ['offered','listening','transcribing','interpreting','clarify','error'].includes(state.phase) ? 1 : state.phase === 'card' ? 2 : ['loading','returning','done'].includes(state.phase) ? 3 : -1;
  document.querySelectorAll('[data-step]').forEach(e => e.classList.toggle('active', Number(e.dataset.step) <= step));
  if (lastPhase !== state.phase) {
    if (lastPhase === 'offered') {audioVersion++; playingSource?.stop();}
    if (state.phase === 'offered') announceOffer();
    if (state.phase === 'card') playPrompt('review');
    if (state.phase === 'done') playPrompt('done');
    if (state.phase === 'cancelled') playPrompt('cancelled');
    lastPhase = state.phase;
  }
}
$('sceneImage').onload = () => {
  if ($('sceneImage').getAttribute('src') === state?.snapshot_url) $('boxes').hidden = false;
};
$('sceneImage').onerror = () => {
  $('boxes').hidden = true;
  showError('The scene image could not load. Inspect the scene again to retry.');
};
function connect() {
  clearTimeout(retryTimer);
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => {connected=true; lastPhase=''; $('connection').textContent='● Connected'; $('connection').classList.add('online'); checkConnection();};
  ws.onmessage = event => {const data=JSON.parse(event.data); if(data.type==='state') render(data.state, true);};
  ws.onclose = () => {connected=false; audioVersion++; playingSource?.stop(); $('connection').textContent='Reconnecting…'; $('connection').classList.remove('online'); if(state) render(state); retryTimer=setTimeout(connect,1500);};
  ws.onerror = () => ws.close();
}
async function observe() {
  const form = new FormData(); form.append('scenario', $('scenario').value);
  if ($('imageFile').files[0]) form.append('file', $('imageFile').files[0]);
  $('transcript').hidden = true;
  await action('observe', () => api('/api/observe', {method:'POST', body:form}));
}
async function action(name, operation) {
  if (pendingAction && name !== 'cancel') return;
  pendingAction = name;
  transcriptionVersion++; stopRecording(true);
  if (state) render(state);
  try { render(await operation()); }
  finally {
    if (pendingAction === name) pendingAction = null;
    if (state) render(state);
  }
}
$('start').onclick = () => { if(!sound) {$('audioToggle').click();} observe().catch(()=>{}); };
async function send(utterance) {
  if(!canEdit() || pendingAction) return;
  const input = {scene_id:state.scene.scene_id, object_id:state.target.object_id, utterance};
  await action('send', () => post('/api/utterance', input));
}
$('requestForm').onsubmit = event => {event.preventDefault(); const value=$('utterance').value.trim(); if(value) send(value).catch(()=>{});};
document.querySelectorAll('[data-say]').forEach(b => b.onclick = () => {$('utterance').value=b.dataset.say; send(b.dataset.say).catch(()=>{});});
// Confirmation only sends the contract identity fields (not presentation/model fields).
$('confirm').onclick = async () => {const c=state?.card; if(!c || pendingAction || state.phase !== 'card') return; try {await action('confirm', () => post('/api/confirm', {scene_id:c.scene_id,object_id:c.object_id,request_id:c.request_id,revision:c.revision}));} catch {api('/api/state').then(render).catch(()=>{});}};
$('cancel').onclick = () => {if(state && pendingAction !== 'cancel') action('cancel', () => post('/api/cancel',{session_id:state.session_id})).catch(()=>{});};
$('refresh').onclick = checkConnection;
$('replayVoice').onclick = () => {
  const preview = $('voicePreview');
  preview.currentTime = 0;
  preview.play().catch(() => showError('Voice playback failed. Check your tablet volume and audio output.'));
};
$('audioToggle').onclick = () => {
  audioVersion++;
  setSound(!sound);
  if(sound) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {setSound(false); showError('This browser does not support audio playback.'); return;}
    audioContext ||= new AudioContextClass();
    audioContext.resume().then(()=>state?.phase === 'offered' ? announceOffer() : playPrompt('welcome')).catch(()=>showError('Tap Enable sound to activate audio.'));
  } else {playingSource?.stop(); playingSource=null;}
};
$('livePreview').parentElement.addEventListener('toggle', event => {if(event.target.open) $('livePreview').src='/api/video'; else $('livePreview').removeAttribute('src');});
async function transcribe(blob) {
  if (!canEdit() || pendingAction) return;
  const session = state.session_id, sequence = state.sequence, draft = draftVersion;
  const version = ++transcriptionVersion;
  transcribing = true; render(state);
  $('recordStatus').textContent='Transcribing…'; const form=new FormData(); form.append('file',blob,'request');
  try {
    const result=await api('/api/transcribe',{method:'POST',body:form});
    if(version !== transcriptionVersion || session !== state?.session_id || sequence !== state.sequence || draft !== draftVersion || !canEdit() || pendingAction) return;
    $('utterance').value=result.text; $('transcript').textContent=`${result.source.toUpperCase()} STT: “${result.text}” — review and send the text.`; $('transcript').hidden=false;
  } finally { transcribing = false; $('recordStatus').textContent=''; if(state) render(state); }
}
$('utterance').addEventListener('input', () => {draftVersion++; $('transcript').hidden = true;});
$('audioFile').onchange = () => {if($('audioFile').files[0]) transcribe($('audioFile').files[0]).catch(()=>{});};
$('record').onclick = async () => {
  if (state?.audio_input && state.audio_input !== 'disabled') {
    if (canEdit() && !pendingAction) {
      const current = state;
      await action('listen', () => post('/api/voice/listen', {session_id:current.session_id,
        scene_id:current.scene.scene_id,object_id:current.target.object_id,sequence:current.sequence})).catch(()=>{});
    }
    return;
  }
  if(recorder?.state==='recording') {recorder.stop(); return;}
  if (!canEdit() || pendingAction || micPending || transcribing) return;
  const version = ++micVersion, session = state.session_id, sequence = state.sequence;
  micPending = true; render(state);
  try {
    if(!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw Error('Microphone recording requires localhost or HTTPS. Upload an audio file instead.');
    recordingStream=await navigator.mediaDevices.getUserMedia({audio:true});
    if (version !== micVersion || session !== state?.session_id || sequence !== state.sequence || !canEdit() || pendingAction) {
      recordingStream.getTracks().forEach(t=>t.stop()); return;
    }
    const mime=['audio/webm','audio/mp4','audio/ogg'].find(t=>MediaRecorder.isTypeSupported(t));
    recorder=new MediaRecorder(recordingStream,mime?{mimeType:mime}:{});
    const active = recorder, stream = recordingStream, parts = [];
    active.ondataavailable=e=>{if(e.data.size) parts.push(e.data);};
    active.onstop=()=>{clearTimeout(active.timer); stream.getTracks().forEach(t=>t.stop()); $('record').textContent='◉ Record request'; $('recordStatus').textContent=''; if(recorder===active) recorder=null; if(!active.discard && session===state?.session_id && sequence===state.sequence) transcribe(new Blob(parts,{type:active.mimeType})).catch(()=>{}); if(state) render(state);};
    recorder.start(); $('record').textContent='■ Stop recording'; $('recordStatus').textContent='Recording · max 15 seconds';
    active.timer=setTimeout(()=>{if(active.state==='recording') active.stop();},15000);
  } catch(error) {if(version===micVersion) showError(error.message); recordingStream?.getTracks().forEach(t=>t.stop());}
  finally {micPending=false; if(state) render(state);}
};
window.addEventListener('beforeunload',()=>recordingStream?.getTracks().forEach(t=>t.stop()));
connect();
$('mediaSupport').textContent = window.isSecureContext && navigator.mediaDevices?.getUserMedia
  ? 'Microphone & speaker: this browser · permission requested when recording'
  : 'For tablet microphone access, open the HTTPS demo URL.';
