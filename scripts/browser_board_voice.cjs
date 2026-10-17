/* Board audio fixture only: the browser must never open a microphone. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8090';
(async()=>{
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
    const page = await browser.newPage({viewport:{width:820,height:1180}});
    await page.addInitScript(()=>{
      window.voiceChecks = {micCalls:0,ended:0,listens:[],phases:[]};
      if(navigator.mediaDevices) navigator.mediaDevices.getUserMedia=()=>{
        window.voiceChecks.micCalls++; throw Error('Tablet microphone must not be used');
      };
      const make = AudioContext.prototype.createBufferSource;
      AudioContext.prototype.createBufferSource=function(){
        const source=make.call(this);
        source.addEventListener('ended',()=>window.voiceChecks.ended=performance.now());
        return source;
      };
      const request = window.fetch;
      window.fetch=function(path,options){
        if(path==='/api/voice/listen') window.voiceChecks.listens.push({at:performance.now(),ended:window.voiceChecks.ended});
        return request.call(this,path,options);
      };
    });
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    page.on('websocket',ws=>ws.on('framereceived',({payload})=>{
      const event=JSON.parse(payload);
      if(event.type==='state') page.evaluate(phase=>window.voiceChecks.phases.push(phase),event.state.phase).catch(()=>{});
    }));
    await page.goto(url);
    // Server image observation triggers the offer: no Start demo click.
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
    assert.equal(await page.locator('#record').innerText(),'Retry board recording');
    await page.locator('#audioToggle').click(); // one initial speaker activation gesture
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CARD',null,{timeout:30000});
    assert.match(await page.locator('#transcript').innerText(),/FIXTURE STT/);
    const result=await page.evaluate(()=>window.voiceChecks);
    assert.equal(result.micCalls,0);
    assert.equal(result.listens.length,1);
    assert(result.listens[0].ended>0 && result.listens[0].at>=result.listens[0].ended);
    assert(result.phases.includes('listening') && result.phases.includes('transcribing'));
    assert.equal(await page.locator('#confirm').isEnabled(),true);
    // No automatic hardware confirmation.
    const hardware=await (await page.request.get(url+'/api/hardware')).json();
    assert.equal(hardware.phase,'idle');
    fs.mkdirSync('tmp/browser-qa',{recursive:true});
    await page.screenshot({path:'tmp/browser-qa/board-voice-tablet.png',fullPage:true});
    assert.deepEqual(errors,[]);
    fs.writeFileSync('tmp/browser-qa/board-voice.json',JSON.stringify({passed:true,...result,errors},null,2));
    console.log('Automatic observation -> tablet audio ended -> board fixture capture -> STT -> card passed');
    await page.locator('#cancel').click();
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
    await page.request.post(url+'/api/observe');
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
    await page.waitForFunction(()=>playingSource && audioContext.state==='running');
    await page.locator('#cancel').click();
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
    await page.waitForTimeout(200);
    assert.equal(await page.evaluate(()=>window.voiceChecks.listens.length),1);
    console.log('Cancelling during the offer does not acknowledge playback or start capture');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
