/* Real Chromium + offline Controller; mocked WAV transport, no physical audio/STT claims. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8094';
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
    const page = await browser.newPage();
    await page.addInitScript(() => {
      window.audioStarts = [];
      const start = AudioBufferSourceNode.prototype.start;
      AudioBufferSourceNode.prototype.start = function (...args) {
        window.audioStarts.push({session:state?.session_id,phase:state?.phase});
        return start.apply(this,args);
      };
    });
    await page.route('**/api/speech/**', route => route.fulfill({
      contentType:'audio/wav',body:fs.readFileSync('app/ui/audio/offer.wav')}));
    await page.route('**/api/speech-preview', route => route.fulfill({
      contentType:'audio/wav',body:fs.readFileSync('app/ui/audio/welcome.wav')}));
    await page.goto(url);
    await page.waitForFunction(() => connected && state);
    const ready = await (await page.request.get(`${url}/ready`)).json();
    assert(Object.values(ready.dependencies).every(d => d.source==='fixture'));
    assert.equal(await page.evaluate(() => state.audio_input),'fixture');
    assert.equal(await page.evaluate(() => state.tts_backend),'http');
    assert.equal(await page.evaluate(() => state.requires_confirmation),false);
    await page.request.post(`${url}/api/capture`,{data:{mode:'manual'}});
    const existing = await (await page.request.get(`${url}/api/state`)).json();
    if (!['idle','done','cancelled','declined','skipped','expired','error'].includes(existing.phase)) {
      await page.request.post(`${url}/api/cancel`,{data:{session_id:existing.session_id}});
    }
    await page.request.post(`${url}/api/capture/restart-timer`,{data:{enabled:true,seconds:1}});
    await page.waitForFunction(() => captureState.mode==='manual');
    await page.locator('.dev-tools').evaluate(e => e.open=true);
    await page.locator('#captureMode').selectOption('auto');
    await page.waitForFunction(() => state.phase === 'done',null,{timeout:15000});
    await page.request.post(`${url}/api/capture/restart-timer`,{data:{enabled:false,seconds:1}});
    const first = await page.evaluate(() => state.session_id);
    await page.evaluate(() => audioContext.suspend());
    assert.equal(await page.evaluate(() => sound),true);
    await page.locator('#start').click();
    await page.waitForFunction(old => state.session_id!==old && state.phase==='offered',first);
    const second = await page.evaluate(() => state.session_id);
    await page.waitForFunction(session => audioStarts.some(a => a.session===session && a.phase==='offered'),
      second,{timeout:4000});
    await page.waitForFunction(() => state.phase==='done',null,{timeout:10000});
    // Automatic rearm must recover the same suspended context without another click.
    await page.request.post(`${url}/api/capture/restart-timer`,{data:{enabled:true,seconds:1}});
    await page.evaluate(() => audioContext.suspend());
    await page.waitForFunction(old => state.session_id!==old && state.phase==='offered',second);
    const third = await page.evaluate(() => state.session_id);
    await page.waitForFunction(session => audioStarts.some(a => a.session===session && a.phase==='offered'),
      third,{timeout:4000});
    await page.waitForFunction(() => state.phase==='done',null,{timeout:10000});
    await page.locator('#captureMode').selectOption('manual');
    console.log('Manual and timer rearm replay TTS after suspended audio; playback ACK resumes voice capture.');
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exit(1);});
