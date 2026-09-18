/** Real Chromium interaction check against the built, running local app.
 * Needs frontend devDependencies installed and an installed Chrome/Edge browser.
 * Example: node scripts/browser_check.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const app=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(app,'frontend','package.json'));
const {chromium}=require('playwright');
const base=process.env.DOORLENS_URL || 'http://127.0.0.1:8000';
const browserPath=process.env.DOORLENS_BROWSER || [
 'C:/Program Files/Google/Chrome/Application/chrome.exe',
 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find(existsSync);
const artifacts=path.join(app,'artifacts');
const temp=path.join(app,'.local','browser-downloads');
await mkdir(artifacts,{recursive:true});await mkdir(temp,{recursive:true});
const browser=await chromium.launch({headless:true,...(browserPath?{executablePath:browserPath}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
const page=await context.newPage();
const requests=[],external=[],errors=[];
page.on('request',request=>requests.push(request.url()));
page.on('pageerror',error=>errors.push(error.message));
page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
// Block attempted external resources and record them. Loopback remains available.
// This tests local-only operation; it does not disconnect the laptop itself.
await context.route('**/*',route=>{
 const url=new URL(route.request().url());
 if(url.origin===new URL(base).origin || ['data:','blob:'].includes(url.protocol))return route.continue();
 external.push(url.href);return route.abort('blockedbyclient');
});
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const responseFor=fragment=>page.waitForResponse(r=>r.url().includes(fragment)&&r.request().method()==='POST'&&r.status()===200);
async function download(label,name){
 const waiting=page.waitForEvent('download');
 await page.getByRole('link',{name:label,exact:true}).click();
 const item=await waiting; const target=path.join(temp,name);await item.saveAs(target);
 return readFile(target);
}
async function settlePlots(){
 await page.evaluate(()=>document.fonts.ready);
 if(await page.locator('.js-plotly-plot').count()){
  await page.waitForFunction(()=>[...document.querySelectorAll('.js-plotly-plot')].every(plot=>
   plot._fullLayout && plot._fullLayout.width<=plot.getBoundingClientRect().width+1 &&
   plot.getBoundingClientRect().right<=innerWidth+1),undefined,{timeout:10000});
 }
}
async function screenshot(name){await settlePlots();await page.screenshot({path:path.join(artifacts,name),fullPage:true});}
let report;
try{
 await page.goto(base,{waitUntil:'networkidle'});
 await page.getByText('Local engine ready',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Analyse recording',exact:true}).isDisabled(),true);
 await screenshot('browser-empty-1440.png');
 await page.getByLabel('Choose door recording CSV').setInputFiles(path.join(app,'..','02_Datasets','Door','Test.csv'));
 const uploadResponse=responseFor('/api/analyze');
 await page.getByRole('button',{name:'Analyse recording',exact:true}).click();
 const uploaded=await (await uploadResponse).json();
 assert.equal(uploaded.summary.cycle_count,38);
 await page.getByRole('heading',{name:'Test.csv',exact:true}).waitFor();
 await page.getByRole('heading',{name:'Recorded signals',exact:true}).waitFor();
 await page.locator('.js-plotly-plot').first().waitFor();
 await page.waitForFunction(()=>document.querySelectorAll('.js-plotly-plot').length>=3);
 const testZip=await download('Download ZIP','test-predictions.zip');
 const testCsv=await download('Original CSV','test-door_predictions.csv');
 assert.equal(hash(testCsv),uploaded.csv_sha256);
 const apiZip=await (await context.request.get(`${base}/api/analyses/${uploaded.id}/predictions.zip`)).body();
 assert.deepEqual(testZip,apiZip);
 const official=path.join(artifacts,'predictions.zip');
 if(existsSync(official))assert.deepEqual(testZip,await readFile(official));
 await screenshot('browser-recording-1440.png');

 // Deliberately delay a challenge response, then switch cycles. The late response
 // must never attach to the newly selected cycle (even with rapid clicks).
 let observed,release;
 const started=new Promise(resolve=>{observed=resolve;});
 const held=new Promise(resolve=>{release=resolve;});
 const delayed=`**/api/analyses/${uploaded.id}/cycles/0/challenge`;
 await page.route(delayed,async route=>{
   const result=await route.fetch();observed();await held;
   try{await route.fulfill({response:result});}catch{/* Browser may have aborted it. */}
 });
 await page.getByRole('button',{name:'Challenge this result',exact:true}).click();
 await started;
 await page.getByRole('button',{name:/cycle_002/}).click();
 await page.getByRole('button',{name:/cycle_003/}).click();
 release();
 await page.getByRole('heading',{name:'cycle_003',exact:true}).waitFor();
 await page.getByRole('heading',{name:'Recorded signals',exact:true}).waitFor();
 await page.waitForLoadState('networkidle');
 assert.equal(await page.getByText('Label changed',{exact:true}).count(),0);
 assert.equal(await page.getByText('Label unchanged',{exact:true}).count(),0);
 await page.unroute(delayed);

 const demoResponse=responseFor('/api/demo');
 await page.getByRole('button',{name:'Development example',exact:true}).click();
 const demo=await (await demoResponse).json();
 assert.notEqual(demo.model_id,uploaded.model_id);
 await page.getByRole('heading',{name:'train_seg_017',exact:true}).waitFor();
 await page.getByRole('heading',{name:'Recorded signals',exact:true}).waitFor();
 const before=await download('Original CSV','demo-before.csv');
 await page.getByLabel('Assumed recording change',{exact:true}).selectOption('current_minus_5pct');
 const challengeResponse=responseFor('/challenge');
 await page.getByRole('button',{name:'Challenge this result',exact:true}).click();
 const challenge=await (await challengeResponse).json();
 assert.equal(challenge.synthetic,true);
 assert.equal(challenge.label_changed,true);
 assert.equal(challenge.model_id,demo.model_id);
 await page.getByText('Label changed',{exact:true}).waitFor();
 await page.getByText('0.3600',{exact:true}).waitFor();
 await settlePlots();
 const plottedStart=await page.evaluate(()=>[...document.querySelectorAll('.js-plotly-plot')]
  .find(plot=>plot.data?.some(trace=>trace.name==='Original current'))?.data[0].x[0]);
 assert.equal(plottedStart,'2023-07-05T00:09:11.186','Plot shifted the recorded timestamp into the browser timezone');
 const after=await download('Original CSV','demo-after.csv');
 assert.deepEqual(before,after);
 await screenshot('browser-signature-1440.png');

 // The second channel probe must also execute dynamically, with changed voltage
 // values visible in its trace payload, rather than a scripted score.
 await page.getByLabel('Assumed recording change',{exact:true}).selectOption('voltage_minus_5pct');
 const voltageResponse=responseFor('/challenge');
 await page.getByRole('button',{name:'Challenge this result',exact:true}).click();
 const voltage=await (await voltageResponse).json();
 assert.equal(voltage.probe_id,'voltage_minus_5pct');
 assert.equal(voltage.label_changed,true);
 await page.getByText('0.2115',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Method & evidence',exact:true}).click();
 await page.getByRole('heading',{name:'Classifier comparison',exact:true}).waitFor();
 assert.equal(await page.getByText('22 correct',{exact:true}).count(),2);
 await screenshot('browser-methodology-1440.png');
 await page.getByRole('button',{name:'Close method and evidence',exact:true}).click();

 await page.setViewportSize({width:1280,height:800});
 await page.getByRole('button',{name:'Challenge this result',exact:true}).scrollIntoViewIfNeeded();
 await screenshot('browser-signature-1280.png');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Laptop document overflows horizontally');
 await page.setViewportSize({width:760,height:900});
 await screenshot('browser-responsive-760.png');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Small document overflows horizontally');
 await page.setViewportSize({width:1440,height:1000});

 // A malformed CSV should produce an actionable error, preserving the clearly
 // identified prior result instead of inventing a successful new analysis.
 await page.getByText('Analyse another CSV',{exact:true}).click();
 await page.getByLabel('Choose door recording CSV').setInputFiles({name:'invalid.csv',mimeType:'text/csv',buffer:Buffer.from('a,b\n1,2\n')});
 const invalidResponse=page.waitForResponse(r=>r.url().endsWith('/api/analyze')&&r.status()===422);
 await page.getByRole('button',{name:'Analyse recording',exact:true}).click();
 await invalidResponse;
 await page.getByRole('alert').filter({hasText:'Missing required columns'}).waitFor();
 await page.getByText('Analyse another CSV',{exact:true}).click();
 // Simulate the server's already-tested expiry response at the browser boundary.
 // A download error must be shown, never saved as a counterfeit CSV/ZIP file.
 let unexpectedDownload=false;
 page.on('download',()=>{unexpectedDownload=true;});
 await page.route(`**/api/analyses/${demo.id}/predictions.zip`,route=>route.fulfill({
  status:410,contentType:'application/json',body:JSON.stringify({detail:{code:'analysis_expired',message:'This analysis expired. Upload the recording again.'}})
 }));
 await page.getByRole('link',{name:'Download ZIP',exact:true}).click();
 await page.getByText(/Run expired · (analyse the file again|reopen Development example)/).waitFor();
 assert.equal(unexpectedDownload,false,'An expiry error was downloaded as a prediction file');
 // Chromium reports an expected 422 as a console error; distinguish it from
 // JavaScript failures or failed assets. No other errors are accepted.
 const unexpectedErrors=errors.filter(e=>!e.includes('422 (Unprocessable Entity)')&&!e.includes('422 (Unprocessable Content)')&&!e.includes('410 (Gone)'));
 assert.deepEqual(external,[],'Core page attempted an external service or asset');
 assert.deepEqual(unexpectedErrors,[],'Unexpected browser errors');
 report={verified_at:new Date().toISOString(),browser:await browser.version(),
  base_url:base,viewports:[{width:1440,height:1000},{width:1280,height:800},{width:760,height:900}],
  checks:{real_test_upload:true,test_cycles:uploaded.summary.cycle_count,ui_download_matches_api:true,
   ui_download_matches_saved_artifact:existsSync(official),delayed_probe_did_not_attach_to_new_cycle:true,
   correct_development_model:true,real_current_and_voltage_probes:true,recorded_timestamp_axis_preserved:true,original_csv_unchanged:true,
   malformed_csv_error:true,expired_download_error_does_not_create_file:true,responsive_no_document_overflow:true},
  demo_current_probe:{original:challenge.original,altered:challenge.altered},
  external_requests:external,unexpected_browser_errors:unexpectedErrors,
  network_test:'External origins actively blocked during the browser session; local HTTP allowed. The laptop network was not disconnected.',
  requested_local_paths:[...new Set(requests.filter(x=>x.startsWith(base)).map(x=>new URL(x).pathname))],
  test_csv_sha256:hash(testCsv),test_zip_sha256:hash(testZip)};
 await writeFile(path.join(artifacts,'browser-verification.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({checks:report.checks,external_requests:external,unexpected_browser_errors:unexpectedErrors},null,2));
}catch(error){
 await page.screenshot({path:path.join(artifacts,'browser-failure.png'),fullPage:true}).catch(()=>{});
 await writeFile(path.join(artifacts,'browser-failure.json'),JSON.stringify({error:String(error),errors,external,url:page.url()},null,2));
 throw error;
}finally{await browser.close();}
