/* Local offline/fixture UI check. Does not validate real Vision accuracy. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8088';
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('Connected'));
    await page.locator('.dev-tools').evaluate(e => e.open = true);
    assert.equal(await page.locator('#captureMode').inputValue(), 'manual');
    const started = Date.now();
    await page.locator('#captureMode').selectOption('auto');
    await page.waitForFunction(() => document.querySelector('#captureStatus').textContent.includes('Stable types'));
    assert.equal(await page.locator('#phase').textContent(), 'IDLE');
    assert.match(await page.locator('#videoMode').textContent(), /scanning/);
    await page.reload(); // mode/window belongs to the server, not this browser.
    await page.waitForFunction(() => document.querySelector('#captureMode').value === 'auto');
    await page.waitForFunction(() => document.querySelector('#phase').textContent === 'OFFERED', null, {timeout:15000});
    assert(Date.now()-started >= 2800, 'Must observe for three seconds, not freeze immediately');
    await page.waitForFunction(() => !document.querySelector('#boxes').hidden);
    const state = await (await page.request.get(`${url}/api/state`)).json();
    assert.equal(state.scene.source, 'fixture');
    assert.equal(await page.locator('.bbox').count(), state.scene.objects.length);
    assert.equal(await page.locator('#sceneImage').getAttribute('src'), state.snapshot_url);
    assert.match(await page.locator('#videoMode').textContent(), /frozen/);
    const boxes = await page.evaluate(() => Array.from(document.querySelectorAll('.bbox')).map(b=>({
      left:parseFloat(b.style.left)/100, top:parseFloat(b.style.top)/100,
      width:parseFloat(b.style.width)/100, height:parseFloat(b.style.height)/100
    })));
    boxes.forEach((box,i)=>{
      assert(Math.abs(box.left-state.scene.objects[i].bbox.x1)<1e-8);
      assert(Math.abs(box.width-(state.scene.objects[i].bbox.x2-state.scene.objects[i].bbox.x1))<1e-8);
    });
    // Mode switches do not revoke or replace the active proposal.
    await page.locator('.dev-tools').evaluate(e => e.open = true);
    await page.locator('#captureMode').selectOption('manual');
    await page.waitForFunction(() => document.querySelector('#captureStatus').textContent.includes('Manual capture'));
    assert.equal((await (await page.request.get(`${url}/api/state`)).json()).session_id, state.session_id);
    await page.locator('#cancel').click();
    await page.waitForFunction(() => document.querySelector('#phase').textContent === 'CANCELLED');
    // Returning to auto clears the old window and cannot instantly reuse it.
    await page.locator('#captureMode').selectOption('auto');
    await page.waitForTimeout(700);
    assert.equal(await page.locator('#phase').textContent(), 'CANCELLED');
    await page.locator('#captureMode').selectOption('manual');
    for (const width of [1440,390]) {
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1));
      fs.mkdirSync('tmp/browser-qa',{recursive:true});
      await page.screenshot({path:`tmp/browser-qa/auto-capture-${width}.png`,fullPage:true});
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({passed:true,checks:['three-second automatic start','mode survives reload',
      'frozen frame/bbox alignment','mode change preserves active session','rearm resets window','desktop/mobile layout']}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
