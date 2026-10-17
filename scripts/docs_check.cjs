/* Standalone architecture explainer: all steps, placements and responsive image loading. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || undefined});
  try {
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.resolve('docs/architecture.html')).href);
  for(const width of [1440,820,390]){
    await page.setViewportSize({width,height:1100});
    for(let step=0;step<7;step++){
      await page.locator(`[data-step="${step}"]`).click();
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow at ${width}, step ${step}`);
      assert(await page.evaluate(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0)));
    }
    await page.locator('[data-mode="board"]').click();
    assert.match(await page.locator('#deployment').textContent(),/STT :8002/);
    await page.locator('[data-mode="dev"]').click();
  }
  fs.mkdirSync('tmp/browser-qa',{recursive:true});
  await page.screenshot({path:'tmp/browser-qa/architecture-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
  console.log('Architecture HTML checks passed');
})().catch(error=>{console.error(error);process.exit(1)});
