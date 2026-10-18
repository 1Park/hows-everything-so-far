/* Offline fixture check: countdown, shared settings, rearm and cancellation. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8088';
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(url);
    await page.waitForFunction(() => connected && captureState);
    const ready = await (await page.request.get(`${url}/ready`)).json();
    assert(Object.values(ready.dependencies).every(d => d.source === 'fixture'), 'Run against --mode offline');
    const getState = async () => (await page.request.get(`${url}/api/state`)).json();
    const finish = async (utterance) => {
      const state = await getState();
      const response = await page.request.post(`${url}/api/utterance`, {data:{
        scene_id:state.scene.scene_id, object_id:state.target.object_id, utterance}});
      assert.equal(response.status(),202);
      await page.waitForFunction(() => captureState?.status === 'cooldown');
      return (await getState()).session_id;
    };
    await page.locator('.dev-tools').evaluate(e => e.open = true);
    assert.equal(await page.locator('#autoRestartEnabled').isChecked(),true);
    assert.equal(await page.locator('#autoRestartSeconds').inputValue(),'10');
    await page.locator('#captureMode').selectOption('auto');
    await page.waitForFunction(() => state.phase === 'offered');
    assert.equal(await page.locator('#captureRestartTimer').isVisible(),false);
    const firstSession = await finish('Water please');
    assert.match(await page.locator('#captureRestartTimer').textContent(),/Restart in \d+s/);
    const before = await page.locator('#captureRestartTimer').textContent();
    await page.waitForTimeout(1100);
    assert.notEqual(await page.locator('#captureRestartTimer').textContent(), before);
    await page.locator('#autoRestartSeconds').fill('2');
    await page.locator('#autoRestartSeconds').press('Tab');
    await page.waitForFunction(() => captureState.restart_seconds === 2);
    const other = await browser.newPage();
    await other.goto(url);
    await other.waitForFunction(() => captureState?.restart_seconds === 2);
    await other.reload();
    await other.waitForFunction(() => captureState?.restart_seconds === 2);
    await page.waitForFunction(old => state.phase === 'offered' && state.session_id !== old,
      firstSession,{timeout:12000});
    assert.equal((await getState()).card,null);
    await page.locator('#autoRestartEnabled').uncheck();
    await page.waitForFunction(() => captureState.restart_enabled === false);
    await other.waitForFunction(() => captureState.restart_enabled === false);
    const declinedSession = await getState();
    await page.request.post(`${url}/api/utterance`,{data:{
      scene_id:declinedSession.scene.scene_id,object_id:declinedSession.target.object_id,utterance:'No thanks'}});
    await page.waitForFunction(() => state.phase === 'declined');
    await page.waitForTimeout(2600);
    assert.equal((await getState()).session_id,declinedSession.session_id);
    assert.equal((await getState()).phase,'declined');
    assert.equal(await page.locator('#captureRestartTimer').isVisible(),false);
    await page.locator('#autoRestartEnabled').check();
    await page.waitForFunction(() => captureState.status === 'cooldown');
    await page.locator('#captureMode').selectOption('manual');
    assert.equal(await page.locator('#captureRestartTimer').isVisible(),false);
    await page.waitForTimeout(2400);
    assert.equal((await getState()).session_id,declinedSession.session_id);
    await page.locator('#captureMode').selectOption('auto');
    await page.waitForFunction(() => state.phase === 'offered');
    const cancelled = await getState();
    await page.request.post(`${url}/api/cancel`,{data:{session_id:cancelled.session_id}});
    await page.waitForFunction(() => captureState.status === 'cooldown');
    await page.locator('#start').click();
    await page.waitForFunction(() => state.phase === 'idle' && captureState.status !== 'cooldown');
    await page.waitForFunction(() => state.phase === 'offered');
    fs.mkdirSync('tmp/browser-qa',{recursive:true});
    for (const width of [1440,390]) {
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({path:`tmp/browser-qa/auto-restart-${width}.png`,fullPage:true});
    }
    assert.deepEqual(errors,[]);
    await page.locator('#captureMode').selectOption('manual');
    console.log('Auto restart: countdown, shared/reloaded settings, same-scene rearm, disable, manual and button checks passed.');
    await other.close();
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exit(1);});
