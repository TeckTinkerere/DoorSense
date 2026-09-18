"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Analysis, CycleDetail, Challenge, Methodology, Prediction } from "@/lib/types";
import { ApiError, apiUrl, errorMessage, request } from "@/lib/api";
import { OverviewPlot, TimePlot, ReferencePlot } from "./SignalPlot";
import s from "./Workbench.module.css";

function Icon({name,size=18}:{name:"upload"|"arrow"|"download"|"check"|"cross"|"beaker";size?:number}) {
 const paths = {upload:"M12 16V4m-4 4 4-4 4 4M4 15v5h16v-5",arrow:"M5 12h14m-5-5 5 5-5 5",download:"M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4",check:"m5 12 4 4L19 6",cross:"m6 6 12 12M6 18 18 6",beaker:"M9 3h6m-5 0v7L4 20h16l-6-10V3M8 14h8"};
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}
function Label({prediction}:{prediction:Prediction}) { return <span className={`${s.label} ${prediction==="Normal"?s.normal:s.abnormal}`}><span aria-hidden="true"/>{prediction}</span>; }
function score(value:number) { return Number.isFinite(value)?value.toFixed(4):"Unavailable"; }
function time(value:string) { return value.includes(" ")?value.split(" ").slice(1).join(" "):value; }
function isAbort(error:unknown) { return error instanceof DOMException && error.name==="AbortError"; }

export default function Workbench() {
 const [upload,setUpload] = useState<Analysis|null>(null);
 const [demo,setDemo] = useState<Analysis|null>(null);
 const [active,setActive] = useState<"upload"|"development-demo">("upload");
 const [file,setFile] = useState<File|null>(null);
 const [busy,setBusy] = useState<"upload"|"demo"|null>(null);
 const [error,setError] = useState("");
 const [dragging,setDragging] = useState(false);
 const [selected,setSelected] = useState<number|null>(null);
 const [filter,setFilter] = useState("All movements");
 const [detail,setDetail] = useState<CycleDetail|null>(null);
 const [detailLoading,setDetailLoading] = useState(false);
 const [detailError,setDetailError] = useState("");
 const [challenge,setChallenge] = useState<Challenge|null>(null);
 const [probeId,setProbeId] = useState("current_minus_5pct");
 const [challenging,setChallenging] = useState(false); const [channel,setChannel] = useState<"current"|"voltage">("current"); const [downloading,setDownloading] = useState(false);
 const [challengeError,setChallengeError] = useState("");
 const [methodology,setMethodology] = useState<Methodology|null>(null);
 const [methodError,setMethodError] = useState("");
 const [showMethod,setShowMethod] = useState(false);
 const [health,setHealth] = useState<"checking"|"ready"|"unavailable">("checking");
 const [expired,setExpired] = useState<Set<string>>(new Set());
 const inputRef=useRef<HTMLInputElement>(null); const newUploadRef=useRef<HTMLDetailsElement>(null);
 const uploadController=useRef<AbortController|null>(null);
 const selectionController=useRef<AbortController|null>(null);
 const challengeController=useRef<AbortController|null>(null);
 const runSequence=useRef(0), detailSequence=useRef(0), challengeSequence=useRef(0);
 const currentKey=useRef("");
 const analysis=active==="upload"?upload:demo;
 const runKey=analysis?.id ?? "";
 currentKey.current=`${runKey}:${selected}`;
 const selectedCycle=analysis?.cycles.find(c=>c.index===selected);
 const expiredRun=!!analysis && expired.has(analysis.id);
 const markExpiry=useCallback((err:unknown,id:string)=>{ if(err instanceof ApiError && err.status===410) setExpired(previous=>new Set([...previous,id])); },[]);

 useEffect(()=>{
  const ctrl=new AbortController();
  request<{status:string}>("/api/health",{signal:ctrl.signal}).then(()=>setHealth("ready")).catch(e=>{if(!isAbort(e))setHealth("unavailable");});
  request<Methodology>("/api/methodology",{signal:ctrl.signal}).then(setMethodology).catch(e=>{if(!isAbort(e))setMethodError(errorMessage(e));});
  return ()=>ctrl.abort();
 },[]);
 useEffect(()=>()=>{uploadController.current?.abort();selectionController.current?.abort();challengeController.current?.abort();},[]);

 useEffect(()=>{
  selectionController.current?.abort();challengeController.current?.abort();
  ++challengeSequence.current;
  setDetail(null);setDetailError("");setChannel("current");setChallenge(null);setChallengeError("");setChallenging(false);
  if(!analysis || selected===null) {setDetailLoading(false);return;}
  const ctrl=new AbortController();selectionController.current=ctrl;
  const seq=++detailSequence.current, id=analysis.id, index=selected, model=analysis.model_id;
  setDetailLoading(true);
  request<CycleDetail>(`/api/analyses/${id}/cycles/${index}`,{signal:ctrl.signal}).then(value=>{
   if(ctrl.signal.aborted || seq!==detailSequence.current || currentKey.current!==`${id}:${index}`)return;
   if(value.analysis_id!==id || value.index!==index || value.model_id!==model || value.context!==analysis.context)throw new Error("The cycle response did not match the selected recording. Please select it again.");
   setDetail(value);
  }).catch(e=>{if(!isAbort(e)&&seq===detailSequence.current){setDetailError(errorMessage(e));markExpiry(e,id);}}).finally(()=>{if(seq===detailSequence.current&&!ctrl.signal.aborted)setDetailLoading(false);});
  return ()=>ctrl.abort();
 },[analysis,selected,markExpiry]);

 function pickFile(next:File|undefined) {
  if(!next)return;
  if(next.size>20*1024*1024){setError("This file exceeds the 20 MiB limit. Choose a smaller recording.");return;}
  if(!next.name.toLowerCase().endsWith(".csv")){setError("Choose a CSV recording (.csv).");return;}
  setFile(next);setError("");
 }
 async function start(kind:"upload"|"demo") {
  if(kind==="upload"&&!file)return;
  uploadController.current?.abort();
  const ctrl=new AbortController();uploadController.current=ctrl;const seq=++runSequence.current;
  setBusy(kind);setError("");
  try {
   const body=new FormData();if(file)body.append("file",file);
   const value=await request<Analysis>(kind==="demo"?"/api/demo":"/api/analyze",{method:"POST",...(kind==="upload"?{body}:{}),signal:ctrl.signal});
   if(ctrl.signal.aborted||seq!==runSequence.current)return;
   if(value.context!==(kind==="upload"?"upload":"development-demo"))throw new Error("The service returned an unexpected model context.");
   if(kind==="upload"){setUpload(value);if(newUploadRef.current)newUploadRef.current.open=false;}else setDemo(value);
   setActive(value.context);setSelected(value.cycles[0]?.index??null);setFilter("All movements");setHealth("ready");
  } catch(e) {if(!isAbort(e)&&seq===runSequence.current)setError(errorMessage(e));}
  finally {if(seq===runSequence.current&&!ctrl.signal.aborted)setBusy(null);}
 }
 function switchRun(context:Analysis["context"]) {
  const target=context==="upload"?upload:demo;
  setActive(context);setSelected(target?.cycles[0]?.index??null);setFilter("All movements");
 }
 function selectCycle(index:number) {if(index===selected)return;setSelected(index);}
 async function runChallenge() {
  if(!analysis || !detail || selected===null)return;
  challengeController.current?.abort();
  const ctrl=new AbortController();challengeController.current=ctrl;
  const seq=++challengeSequence.current, id=analysis.id,index=selected,model=analysis.model_id,probe=probeId;
  setChallenging(true);setChallengeError("");setChallenge(null);
  try {
   const value=await request<Challenge>(`/api/analyses/${id}/cycles/${index}/challenge`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({probe_id:probe}),signal:ctrl.signal});
   if(ctrl.signal.aborted||seq!==challengeSequence.current||currentKey.current!==`${id}:${index}`)return;
   if(value.analysis_id!==id||value.index!==index||value.model_id!==model||value.probe_id!==probe||value.original_csv_sha256!==analysis.csv_sha256||value.synthetic!==true)throw new Error("The comparison did not match this original cycle. Please retry.");
   setChallenge(value);setChannel(probe.startsWith("voltage_")?"voltage":"current");
  }catch(e){if(!isAbort(e)&&seq===challengeSequence.current&&currentKey.current===`${id}:${index}`){setChallengeError(errorMessage(e));markExpiry(e,id);}}
  finally{if(seq===challengeSequence.current&&!ctrl.signal.aborted)setChallenging(false);}
 }
 function changeProbe(value:string){challengeController.current?.abort();++challengeSequence.current;setChallenging(false);setChallenge(null);setChallengeError("");setProbeId(value);}
 async function downloadOriginal(kind:"csv"|"zip") {
  if(!analysis || downloading)return;
  const id=analysis.id;
  setDownloading(true);setError("");
  try {
   const response=await fetch(apiUrl(`/api/analyses/${id}/predictions.${kind}`),{cache:"no-store"});
   if(!response.ok){const body=await response.json().catch(()=>null);throw new ApiError(body?.detail?.message??"The original export could not be downloaded.",response.status,body?.detail?.code??"download_failed");}
   const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=url;anchor.download=kind==="csv"?"door_predictions.csv":"predictions.zip";document.body.appendChild(anchor);anchor.click();anchor.remove();window.setTimeout(()=>URL.revokeObjectURL(url),10000);
  } catch(e){setError(errorMessage(e));markExpiry(e,id);} finally{setDownloading(false);}
 }
 const visible=analysis?.cycles.filter(c=>filter==="All movements"||(filter==="Abnormal resistance"?c.prediction==="Abnormal resistance":c.prediction==="Normal"))??[];
 const uploadControl=<div className={s.fileControls}><input ref={inputRef} id="recording-file" type="file" accept=".csv,text/csv" aria-label="Choose door recording CSV" onChange={e=>pickFile(e.target.files?.[0])}/><button className={s.secondary} onClick={()=>inputRef.current?.click()} disabled={!!busy}><Icon name="upload"/>{file?"Change CSV":"Choose CSV"}</button>{file&&<span className={s.fileName} title={file.name}>{file.name} <small>{(file.size/1024).toFixed(0)} KiB</small></span>}<button className={s.primary} disabled={!file||!!busy} onClick={()=>start("upload")}>{busy==="upload"?"Analysing recording…":"Analyse recording"}<Icon name="arrow"/></button></div>;

 return <div className={s.shell}>
  <a href="#workspace" className={s.skip}>Skip to workspace</a>
  <header className={s.masthead}>
   <a className={s.brand} href="#workspace" aria-label="DoorLens workspace"><svg width="29" height="34" viewBox="0 0 29 34" aria-hidden="true"><path d="M2 31V3h25v28M14.5 3v28M7 10h3v13H7zm12 0h3v13h-3z" fill="none" stroke="currentColor" strokeWidth="1.6"/></svg>DoorLens<span>Recorded door analysis</span></a>
   <div className={s.nav}><span className={`${s.service} ${health==="unavailable"?s.serviceDown:""}`}><i/>{health==="ready"?"Local engine ready":health==="checking"?"Connecting to local engine":"Local engine unavailable"}</span><button className={s.textButton} aria-expanded={showMethod} onClick={()=>setShowMethod(!showMethod)}>Method & evidence</button></div>
  </header>
  <main id="workspace" className={s.main}>
   {showMethod&&<section className={s.method} aria-label="Method and saved evaluation"><div className={s.sectionHeading}><h2>Method & evidence</h2><button className={s.iconButton} aria-label="Close method and evidence" onClick={()=>setShowMethod(false)}><Icon name="cross"/></button></div><p className={s.muted}>Saved experiment · reproduced at packaging. These results are separate from the current recording.</p>{methodError&&<p role="alert" className={s.error}>{methodError}</p>}{!methodology&&!methodError&&<p>Loading saved evidence…</p>}{methodology&&<>
    <p className={s.methodDescription}>{methodology.model_description}</p><p>{methodology.scope}</p>
    <div className={s.methodGrid}><div><h3>Classifier comparison</h3><div className={s.tableScroll}><table className={s.evidenceTable}><thead><tr><th>Saved evaluation</th><th>Current baseline</th><th>Phase model</th></tr></thead><tbody><tr><td>Development · {methodology.development.n} cycles</td><td>{methodology.development.current_correct} correct</td><td>{methodology.development.phase_correct} correct</td></tr><tr><td>Reserve · {methodology.reserve.n} cycles</td><td>{methodology.reserve.current_correct} correct</td><td>{methodology.reserve.phase_correct} correct</td></tr></tbody></table></div><p className={s.note}>{methodology.metric}</p><p className={s.note}>The baseline ties on the reserve. Development was used for model selection; the reserve is already examined. Neither is independent field validation.</p></div><div><h3>Synthetic sensitivity · {methodology.sensitivity.n} development cycles</h3><div className={s.tableScroll}><table className={s.evidenceTable}><thead><tr><th>Assumed change</th><th>Baseline changes</th><th>Phase changes</th></tr></thead><tbody>{methodology.sensitivity.probes.map(p=><tr key={p.id}><td>{p.label}</td><td>{p.current_changes}</td><td>{p.phase_changes}</td></tr>)}</tbody></table></div><p className={s.note}>At least one changed label: {methodology.sensitivity.current_affected} baseline cycles; {methodology.sensitivity.phase_affected} phase cycles. Probe counts overlap.</p></div></div>
    <details className={s.disclosure}><summary>Limitations, provenance & source files</summary><ul>{methodology.limitations.map((x,i)=><li key={i}>{x}</li>)}</ul><p>Signature reproduced: {methodology.verification.signature_reproduced?"yes":"no"} · checked {methodology.verification.verified_at}</p><p>Maximum reproduced model-score difference: {methodology.verification.parity_max_abs_error.toExponential(2)}</p><ul>{methodology.sources.map(source=><li key={source.path}>{source.label} <code>{source.path}</code></li>)}</ul></details>
   </>}</section>}
   {error&&<div className={s.error} role="alert"><strong>The local request could not finish.</strong> {error}<button aria-label="Dismiss error" className={s.iconButton} onClick={()=>setError("")}><Icon name="cross"/></button></div>}
   {!analysis?<section className={s.empty}>
    <div className={s.emptyIntro}><h1>A closer look at<br/>every door movement.</h1><p>Classify a recorded movement. Inspect its signals. Explore whether an assumed recording change alters the result.</p><div className={s.emptyFlow}><span>01 <b>Upload</b></span><span>02 <b>Inspect</b></span><span>03 <b>Challenge</b></span><span>04 <b>Export</b></span></div></div>
    <div className={`${s.uploadPanel} ${dragging?s.dragging:""}`} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);pickFile(e.dataTransfer.files[0]);}}><div className={s.uploadSymbol}><Icon name="upload" size={28}/></div><h2>Start with a door recording</h2><p>Drop your CSV here, or choose a file.</p>{uploadControl}<p className={s.note}>Up to 20 MiB · 300,000 rows · supplied door schema<br/>Processed by the local engine. Uploaded data does not train the model.</p></div>
    <aside className={s.exampleIntro}><div><Icon name="beaker" size={24}/><h2>See a result change.</h2><p>Open a recorded development example and apply a synthetic recording assumption. The original prediction stays intact.</p></div><button className={s.secondary} onClick={()=>start("demo")} disabled={!!busy}>{busy==="demo"?"Opening example…":"Open development example"}<Icon name="arrow"/></button><small>Separate fold-trained model · previously examined example</small></aside>
   </section>:<>
    <div className={s.contextBar}><div className={s.contextTabs} role="group" aria-label="Analysis context"><button aria-pressed={active==="upload"} disabled={!upload} onClick={()=>switchRun("upload")}>Your recording</button><button aria-pressed={active==="development-demo"} onClick={()=>demo&&!expired.has(demo.id)?switchRun("development-demo"):start("demo")} disabled={!!busy}>{busy==="demo"?"Opening example…":"Development example"}</button></div><details ref={newUploadRef} className={s.newUpload}><summary>Analyse another CSV</summary><div>{uploadControl}</div></details></div>
    <section className={s.runHeader} aria-label="Original analysis">
     <div><div className={s.runTitle}><h1>{analysis.filename}</h1><span className={active==="development-demo"?s.demoBadge:s.recordingBadge}>{active==="development-demo"?"Recorded development example":"Original recording"}</span></div><p className={s.muted}>{analysis.model_label} · {analysis.model_id}</p></div>
     <div className={s.downloads}>{expiredRun?<span className={s.errorText}>{active==="development-demo"?"Run expired · reopen Development example":"Run expired · analyse the file again"}</span>:<><a className={s.secondary} href={apiUrl(`/api/analyses/${analysis.id}/predictions.csv`)} download="door_predictions.csv" aria-disabled={downloading} onClick={e=>{e.preventDefault();void downloadOriginal("csv");}}><Icon name="download"/>Original CSV</a><a className={s.primary} href={apiUrl(`/api/analyses/${analysis.id}/predictions.zip`)} download="predictions.zip" aria-disabled={downloading} onClick={e=>{e.preventDefault();void downloadOriginal("zip");}}><Icon name="download"/>Download ZIP</a></>}<span>Original predictions · unchanged by challenges</span></div>
    </section>
    {active==="development-demo"&&<div className={s.demoNotice}><Icon name="beaker"/><p><strong>Development example, separate model.</strong> This previously examined cycle uses its frozen fold-trained model. It is not a prediction on your uploaded file or a fresh validation result.</p></div>}
    {analysis.warnings.length>0&&<details className={s.sessionLimits}><summary>Assumptions & session limits</summary><ul>{analysis.warnings.map((warning,i)=><li key={i}>{warning}</li>)}</ul></details>}
    <section className={s.overview} aria-label="Recording overview"><div className={s.overviewHeading}><h2>Recording overview</h2><div className={s.counts}><span><b>{analysis.summary.cycle_count}</b> movements</span><span className={s.greenText}><b>{analysis.summary.normal_count}</b> normal</span><span className={s.amberText}><b>{analysis.summary.abnormal_count}</b> abnormal resistance</span></div></div><OverviewPlot data={analysis.overview} runId={analysis.id}/><div className={s.overviewFooter}><span>Gaps preserved · overview may be reduced for display</span><span>Analysis {(analysis.elapsed_ms/1000).toFixed(2)} s</span></div></section>
    <div className={s.workspaceGrid}>
     <section className={s.movementPanel} aria-label="Movement selection"><div className={s.listHeading}><h2>Movements</h2><label className={s.srOnly} htmlFor="cycle-filter">Filter movements</label><select id="cycle-filter" value={filter} onChange={e=>setFilter(e.target.value)}><option>All movements</option><option>Abnormal resistance</option><option>Normal</option></select></div><div className={s.cycleList}>{visible.length===0?<p className={s.listEmpty}>No movements match this filter.</p>:visible.map(c=><button key={`${analysis.id}-${c.index}`} className={`${s.cycleRow} ${selected===c.index?s.selectedRow:""}`} aria-pressed={selected===c.index} onClick={()=>selectCycle(c.index)}><span className={s.cycleRowTop}><strong>{c.cycle_id}</strong><span>{c.direction}<Icon name="arrow" size={13}/></span></span><span className={s.cycleTime}>{time(c.start_time)} · {c.duration_s.toFixed(2)} s</span><Label prediction={c.prediction}/></button>)}</div><p className={s.listFoot}>{visible.length} shown · select a movement to inspect</p></section>
     <section className={s.detailPanel} aria-label="Selected movement evidence" aria-busy={detailLoading}>
      {selectedCycle&&<div className={s.cycleHeader}><div><h2>{selectedCycle.cycle_id}</h2><p className={s.muted}>{selectedCycle.direction} movement · {selectedCycle.sample_count} samples · {selectedCycle.duration_s.toFixed(2)} seconds</p></div><div className={s.originalScore}><Label prediction={selectedCycle.prediction}/><span>Uncalibrated model score <strong>{score(selectedCycle.score)}</strong></span></div></div>}
      {detailLoading&&<div className={s.loading} role="status">Loading this movement’s recorded signals…</div>}
      {detailError&&<p role="alert" className={s.error}>{detailError}</p>}
      {!selectedCycle&&<p className={s.loading}>Select a movement to inspect its recorded evidence.</p>}
      {detail&&detail.analysis_id===analysis.id&&detail.index===selected&&<>
       <div className={s.chartHeading}><h3>Recorded signals</h3><div className={s.legend}><span><i className={s.originalLine}/>Original</span>{challenge&&<span><i className={s.changedLine}/>Assumed change</span>}</div></div><div className={s.channelTabs} role="group" aria-label="Recorded signal channel"><button aria-pressed={channel==="current"} onClick={()=>setChannel("current")}>Current · A</button><button aria-pressed={channel==="voltage"} onClick={()=>setChannel("voltage")}>Voltage · V</button></div><TimePlot detail={detail} challenge={challenge} channel={channel}/>
       <p className={s.chartNote}>Full-resolution cycle · hover for values, drag to zoom, double-click to reset. Position is in recorded counts.</p>
       <section className={s.challengePanel} aria-labelledby="challenge-title"><div className={s.challengeHeading}><Icon name="beaker"/><div><h3 id="challenge-title">Challenge this result</h3><p>Synthetic sensitivity check · same frozen model</p></div></div><p className={s.challengeDescription}>Does an explicit recording assumption change this classification? Choose one change and recompute the selected cycle.</p><div className={s.probeControls}><div><label htmlFor="probe">Assumed recording change</label><select id="probe" value={probeId} onChange={e=>changeProbe(e.target.value)}>{analysis.probe_definitions.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></div><button className={s.primary} onClick={runChallenge} disabled={challenging||expiredRun}>{challenging?"Computing comparison…":"Challenge this result"}<Icon name="arrow"/></button></div><p className={s.note}>{analysis.probe_definitions.find(p=>p.id===probeId)?.description}</p>
       {challengeError&&<p className={s.error} role="alert">{challengeError}</p>}
       {challenge&&<div className={s.comparison} aria-live="polite"><div className={`${s.comparisonVerdict} ${challenge.label_changed?s.changedVerdict:""}`}><Icon name={challenge.label_changed?"beaker":"check"}/><strong>{challenge.label_changed?"Label changed":"Label unchanged"}</strong><span>under this assumed recording change</span></div><div className={s.comparisonGrid}><div><span>Original · unchanged</span><Label prediction={challenge.original.prediction}/><p>Uncalibrated model score <b>{score(challenge.original.score)}</b></p><small>{detail.cycle.sample_count} samples</small></div><div><span>{challenge.probe_label}</span><Label prediction={challenge.altered.prediction}/><p>Uncalibrated model score <b>{score(challenge.altered.score)}</b></p><small>{challenge.sample_count} samples</small></div></div><p className={s.comparisonAction}>{challenge.label_changed?"Review the named recording assumption before interpreting this result as maintenance evidence.":"This label is stable under this one probe. Stability does not establish correctness."}</p><p className={s.note}>{challenge.caveat}</p><button className={s.textButton} onClick={()=>setChallenge(null)}>Clear comparison · keep original</button></div>}
       <p className={s.scopeNote}>The changes are assumptions, not verified sensor tolerances or physical faults. Probes run after segmentation. Scores are uncalibrated; they are not confidence percentages. Original CSV and ZIP stay unchanged.</p></section>
       <div className={s.chartHeading}><h3>Absolute current across door travel</h3><span className={s.referenceLegend}>Training-normal reference</span></div><ReferencePlot detail={detail} challenge={challenge}/><p className={s.chartNote}>Same-direction training reference: median and 10th–90th percentile range, from {detail.reference.sample_count} normal cycles. This is a descriptive range, not a confidence interval or component diagnosis.</p><details className={s.disclosure}><summary>Cycle & reference provenance</summary><dl className={s.provenance}><dt>Start</dt><dd>{detail.cycle.start_time}</dd><dt>End</dt><dd>{detail.cycle.end_time}</dd><dt>Reference</dt><dd>{detail.reference.provenance}</dd><dt>Model</dt><dd>{detail.model_id}</dd></dl></details>
      </>}
     </section>
    </div>
    <details className={s.runProvenance}><summary>Original recording & export provenance</summary><dl className={s.provenance}><dt>Analysis ID</dt><dd>{analysis.id}</dd><dt>Context</dt><dd>{analysis.context}</dd><dt>Input SHA-256</dt><dd><code>{analysis.input_sha256}</code></dd><dt>Original CSV SHA-256</dt><dd><code>{analysis.csv_sha256}</code></dd><dt>Created</dt><dd>{analysis.created_at}</dd><dt>Expires</dt><dd>{analysis.expires_at}</dd></dl></details>
   </>}
  </main>
  <footer className={s.footer}><span>DoorLens <b>·</b> Local recorded-data analysis</span><span>Retrospective classification. No departure or safety authorisation.</span></footer>
 </div>;
}



