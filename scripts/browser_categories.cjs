/* Offline fixture UI check; does not measure model accuracy. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8088';
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('Connected'));
    await page.locator('.dev-tools').evaluate(e => e.open = true);
    await page.waitForFunction(() => document.querySelector('#categoryMapping').textContent.includes('coke + coffee → coke'));
    assert.equal(await page.locator('#categoryMapping input, #categoryMapping select, #categoryMapping button').count(), 0);
    await page.locator('#start').click();
    await page.waitForFunction(() => document.querySelector('#phase').textContent === 'OFFERED');
    assert.equal(await page.locator('#drinkChoices, .drink-choice').count(), 0);
    await page.locator('#utterance').fill('Coffee please');
    await page.locator('#send').click();
    await page.waitForFunction(() => document.querySelector('#phase').textContent === 'CARD');
    assert.equal(await page.locator('#cardDrink').textContent(), 'coffee');
    assert.equal((await (await page.request.get(`${url}/api/state`)).json()).hardware_source, 'mock');
    assert.equal(await page.locator('#untrainedCategories').isChecked(), false);
    await page.locator('#untrainedCategories').check();
    await page.waitForFunction(() => document.querySelector('#untrainedCategories').checked && document.querySelector('#phase').textContent === 'OFFERED');
    assert.deepEqual((await (await page.request.get(`${url}/api/state`)).json()).allowed_items,
      ['water','sparkling_water','soda','coke','coke_zero','coffee']);
    assert.equal(await page.locator('#requestCard').isVisible(), false);
    await page.reload();
    await page.locator('.dev-tools').evaluate(e => e.open = true);
    await page.waitForFunction(() => document.querySelector('#untrainedCategories').checked);
    await page.locator('#utterance').fill('Sparkling water please');
    await page.locator('#send').click();
    await page.waitForFunction(() => document.querySelector('#phase').textContent === 'CARD');
    assert.equal(await page.locator('#cardDrink').textContent(), 'sparkling water');
    await page.locator('#untrainedCategories').uncheck();
    await page.waitForFunction(() => !document.querySelector('#untrainedCategories').checked && document.querySelector('#phase').textContent === 'OFFERED');
    assert.equal(await page.locator('#requestCard').isVisible(), false);
    for (const width of [390,1440]) {
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    }
    await page.locator('#cancel').click();
    assert.deepEqual(errors, []);
    console.log('Passed: read-only mapping, no drink badges, typed request card, demo toggle, reload persistence, expanded request, stale card invalidation, responsive layout.');
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
