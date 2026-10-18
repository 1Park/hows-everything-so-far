/* UI race regressions. Offline model fixtures and fake browser audio only. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8080';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined,
    args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
  const failures = [], passed = [];
  try {
    const page = await browser.newPage({viewport:{width:820,height:1180}});
    const errors = []; page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);
    await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('Connected'));
    await page.locator('.dev-tools').evaluate(e=>e.open=true);
    const offered = async () => {
      await page.locator('#start').click();
      await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
    };
    const check = async (name, test) => {
      try {await test(); passed.push(name);} catch(e) {failures.push({name,error:e.message});}
    };
    await offered();
    await page.locator('#utterance').fill('A regular coffee instead, please');
    await page.locator('#send').click();
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CARD');
    await page.locator('#refresh').click(); await pause(300);
    await check('Readiness refresh keeps frozen-frame label',async()=>{
      assert.match(await page.locator('#videoMode').innerText(),/frozen/);
    });
    await page.locator('#cancel').click();
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
    await check('Cancel hides obsolete request card',async()=>{
      assert.equal(await page.locator('#requestCard').isVisible(),false);
    });
    await offered();
    await check('New scene clears previous customer text',async()=>{
      assert.equal(await page.locator('#utterance').inputValue(),'');
    });
    let release;
    const gate = new Promise(resolve=>{release=resolve;});
    await page.route('**/api/transcribe',async route=>{
      await gate;
      await route.fulfill({json:{text:'A little water, please',source:'fixture',language:'en'}});
    });
    await page.evaluate(()=>{window.pendingTranscript=transcribe(new Blob(['test'],{type:'audio/wav'}));});
    await page.locator('#utterance').fill('Coffee instead, please');
    release(); await page.evaluate(()=>window.pendingTranscript);
    await check('Late STT preserves manually edited text',async()=>{
      assert.equal(await page.locator('#utterance').inputValue(),'Coffee instead, please');
    });
    await page.unroute('**/api/transcribe');
    await page.evaluate(()=>{
      window.micStopped=0;
      navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{
        window.releaseMic=()=>resolve({getTracks:()=>[{stop:()=>window.micStopped++}]});
      });
    });
    await page.locator('#record').click();
    await page.waitForFunction(()=>typeof window.releaseMic==='function');
    await page.locator('#cancel').click();
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
    await page.evaluate(()=>window.releaseMic()); await pause(100);
    await check('Late microphone permission is discarded without recorder error',async()=>{
      assert.equal(await page.locator('#error').isVisible(),false);
      assert.equal(await page.evaluate(()=>window.micStopped),1);
    });
    // Reload restores the real fake-device getUserMedia after the delayed permission double.
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('Connected'));
    await offered();
    let submissions = 0;
    await page.route('**/api/utterance',async route=>{
      submissions++; await pause(200); await route.continue();
    });
    await page.locator('#utterance').fill('A little water, please');
    await page.evaluate(()=>{
      document.querySelector('#requestForm').requestSubmit();
      document.querySelector('#requestForm').requestSubmit();
    });
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CARD');
    await check('Rapid double submit sends one request',async()=>assert.equal(submissions,1));
    await page.unroute('**/api/utterance');
    let transcriptions = 0;
    page.on('request',request=>{if(request.url().endsWith('/api/transcribe')) transcriptions++;});
    await page.locator('#record').click();
    await page.waitForFunction(()=>document.querySelector('#record').textContent.includes('Stop recording'));
    await pause(350);
    await page.locator('#cancel').click();
    await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
    await pause(200);
    await check('Cancel discards recording without uploading audio',async()=>{
      assert.equal(transcriptions,0);
      assert.equal(await page.locator('#recordStatus').textContent(),'');
    });
    await check('No uncaught browser errors',async()=>assert.deepEqual(errors,[]));
    fs.mkdirSync('tmp/browser-qa',{recursive:true});
    await page.screenshot({path:'tmp/browser-qa/regressions-tablet.png',fullPage:true});
    fs.writeFileSync('tmp/browser-qa/regressions.json',JSON.stringify({passed,failures},null,2));
    console.log(JSON.stringify({passed,failures},null,2));
    assert.equal(failures.length,0,'UI regression failures');
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1);});
