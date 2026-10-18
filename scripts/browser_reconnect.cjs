/* Run against a disposable offline demo server: simulates cable loss in Chromium. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const url = process.env.REFILL_URL || 'http://127.0.0.1:8096';

(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
    const context = await browser.newContext({viewport:{width:820,height:1180}});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let navigations = 0, streams = 0;
    await page.route('**/api/connection-status', route => route.fulfill({json:{
      client_ip:'192.168.50.2', ethernet:{carrier:1, state:'up', speed_mbps:1000,
        carrier_changes:4, rx_packets:123, tx_packets:456, rx_errors:0, tx_errors:0, rx_dropped:0},
    }}));
    page.on('framenavigated', frame => {if (frame === page.mainFrame()) navigations++;});
    // Use a decodable frame as a feed double to verify reconnection requests.
    const frame = Buffer.from(await (await fetch(`${url}/api/frame`)).arrayBuffer());
    await page.route('**/ready', async route => {
      const response = await route.fetch();
      const info = await response.json();
      info.video.mode = 'camera';
      await route.fulfill({response, json:info});
    });
    await page.route('**/api/video?*', async route => {
      streams++;
      await route.fulfill({contentType:'image/jpeg', body:frame});
    });
    await page.goto(url);
    const restored = async () => page.waitForFunction(() =>
      document.querySelector('#connectionLost').hidden &&
      document.querySelector('#connection').textContent.includes('Connected'));
    await restored();
    await page.waitForFunction(() => document.querySelector('#connectionHistory').textContent.includes('carrier=1'));
    await page.locator('#livePreview').evaluate(image => {image.parentElement.open = true;});
    await page.waitForFunction(() => document.querySelector('#livePreview').dataset.streaming);
    const initialStreams = streams;

    await context.setOffline(true);
    await page.locator('#connectionLost').waitFor({state:'visible', timeout:6000});
    assert.match(await page.locator('#connectionLost').innerText(), /bad cable connection/);
    assert.match(await page.locator('#connectionDiagnostics').innerText(), /192\.168\.50\.2/);
    assert.match(await page.locator('#connectionDiagnostics').innerText(), /carrier=1/);
    assert.match(await page.locator('#connectionDiagnostics').innerText(), /last success:/);
    assert.equal(await page.locator('#start').isDisabled(), true);
    // Change server state while the tablet cannot reach it: recovery must fetch
    // the current snapshot rather than repainting the tablet's old cached state.
    const response = await fetch(`${url}/api/demo-features`, {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({untrained_categories:true})});
    assert.equal(response.ok, true);
    await context.setOffline(false);
    await restored();
    await page.waitForFunction(() => document.querySelector('#untrainedCategories').checked);
    await page.waitForFunction(() => document.querySelector('#livePreview').naturalWidth > 0);
    assert.ok(streams > initialStreams, 'Live stream must restart after reconnection');

    // A blackholed Ethernet path may leave WebSocket OPEN for minutes. The HTTP
    // watchdog must detect the outage without waiting for a socket close event.
    await page.route('**/health', () => {}); // No response: exercise the real 2s deadline.
    await page.locator('#connectionLost').waitFor({state:'visible', timeout:6000});
    assert.match(await page.locator('#connectionDiagnostics').innerText(), /TIMEOUT: no response within 2s/);
    await page.unroute('**/health');
    await restored();
    assert.match(await page.locator('#connectionHistory').textContent(), /HTTP check failed: TIMEOUT/);
    await page.route('**/health', route => route.fulfill({status:503, body:'Unavailable'}));
    await page.locator('#connectionLost').waitFor({state:'visible', timeout:6000});
    assert.match(await page.locator('#connectionDiagnostics').innerText(), /HTTP 503/);
    await page.unroute('**/health');
    await restored();
    assert.equal(navigations, 1, 'Recovery must not reload or navigate the page');
    assert.deepEqual(errors, []);
    console.log('PASS: cable loss, stale open socket, automatic state/video recovery, no reload');
  } finally {
    await fetch(`${url}/api/demo-features`, {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify({untrained_categories:false})});
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
