/* Real Chromium UI check. Fake browser microphone tests transport, NOT STT accuracy. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8080';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  fs.mkdirSync('tmp/browser-qa', {recursive:true});
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined,
    args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
  try {
  const context = await browser.newContext({viewport:{width:1440,height:1150},permissions:['microphone']});
  const page = await context.newPage();
  const errors = []; page.on('pageerror',e=>errors.push(e.message));
  const requests = []; page.on('request',r=>requests.push(r.url()));
  // Force REST response to arrive AFTER newer WebSocket state (fast fixture regression).
  await page.route('**/api/observe',async route=>{const response=await route.fetch();await delay(180);await route.fulfill({response});},{times:1});
  await page.goto(url); await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('Connected'));
  await page.locator('#start').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
  await delay(300);
  assert.equal(await page.locator('#phase').textContent(),'OFFERED');
  assert.equal(await page.locator('.bbox').count(),3);
  const geometry = await page.evaluate(()=>{
    const image = document.querySelector('#sceneImage').getBoundingClientRect();
    const boxes = [...document.querySelectorAll('.bbox')].map(e=>{const r=e.getBoundingClientRect();return {x:(r.x-image.x)/image.width,y:(r.y-image.y)/image.height,w:r.width/image.width,h:r.height/image.height};});
    return {width:image.width,height:image.height,boxes};
  });
  assert(Math.abs(geometry.width/geometry.height-1.5)<.01);
  assert(Math.abs(geometry.boxes[0].x-.09)<.005);
  assert(Math.abs(geometry.boxes[2].x-.716)<.005);
  await page.waitForFunction(()=>document.querySelector('#audioToggle').getAttribute('aria-pressed')==='true');
  assert(requests.some(r=>r.includes('/ui/audio/')));
  await page.locator('#record').click(); await delay(900); await page.locator('#record').click();
  await page.waitForFunction(()=>!document.querySelector('#transcript').hidden);
  assert.match(await page.locator('#transcript').innerText(),/FIXTURE STT/);
  assert.equal(await page.locator('#utterance').inputValue(),'A little water, please');
  await page.locator('#send').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CARD');
  assert.match(await page.locator('#cardDrink').innerText(),/water/i);
  const frozen = await page.locator('#sceneImage').getAttribute('src');
  await page.locator('#utterance').fill('A regular coffee instead, please'); await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CARD' && document.querySelector('#cardDrink').textContent==='coffee');
  assert.equal(await page.locator('#sceneImage').getAttribute('src'),frozen);
  assert.equal(await page.locator('#audioToggle').getAttribute('aria-pressed'),'true');
  assert.equal(await page.evaluate(()=>audioContext.state),'running');
  assert(await page.evaluate(()=>audioBuffers.get('review')?.duration > 0));
  await page.screenshot({path:'tmp/browser-qa/desktop.png',fullPage:true});
  for (const width of [820,768,390]) {
    await page.setViewportSize({width,height:1180});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow at ${width}`);
    await page.screenshot({path:`tmp/browser-qa/width-${width}.png`,fullPage:true});
  }
  await page.locator('#confirm').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='DONE');
  await page.locator('#start').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
  await page.locator('[data-say="No thanks"]').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='DECLINED');
  await page.locator('#start').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
  await page.locator('#cancel').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
  await page.locator('.input-options > summary').click();
  await page.locator('.input-options details > summary').click();
  await page.waitForFunction(()=>document.querySelector('#livePreview').naturalWidth > 0);
  await page.locator('.input-options details > summary').click();
  await page.locator('#imageFile').setInputFiles('docs/assets/cups-example.jpg');
  await page.locator('#start').click();
  await page.waitForFunction(()=>document.querySelector('#phase').textContent==='OFFERED');
  await page.locator('#cancel').click(); await page.waitForFunction(()=>document.querySelector('#phase').textContent==='CANCELLED');
  await context.setOffline(true); await delay(2200);
  await context.setOffline(false); await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('Connected'),{timeout:20000});
  assert.deepEqual(errors,[]);
  fs.writeFileSync('tmp/browser-qa/result.json',JSON.stringify({passed:true,errors,geometry,viewports:[1440,820,768,390],
    checks:['text/edit/confirm/done','browser microphone -> fixture STT -> review','fixed audio decode and running Web Audio context','frozen target','bbox geometry','MJPEG live preview','image upload','decline/cancel','offline/reconnect'],
    scope:'Real Chromium, fake microphone input. Physical tablet permissions/speaker audibility unverified.'},null,2));
  } finally { await browser.close(); }
  console.log('Browser checks passed');
})().catch(error=>{console.error(error);process.exit(1)});
