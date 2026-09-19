"use client";
import { useRef, useState } from "react";
import { apiUrl, errorMessage, request } from "@/lib/api";
import { TrendPlot } from "./TrendPlot";
import s from "./Acv.module.css";

interface CarRow { car:string; rank:number; leak_score:number|null; valid_samples:number; gap_mean_c:number|null; gap_median_c:number|null; gap_p90_c:number|null; }
interface AcvResult { id:string; filename:string; model_id:string; ranked_cars:string[]; cars:CarRow[]; top_margin:number; confidence:"clear"|"moderate"|"low"; n_rows:number; n_cars:number; unscored_cars:string[]; trend:{labels:string[];series:Record<string,(number|null)[]>}; elapsed_ms:number; warnings:string[]; csv_sha256:string; }
const MAX = 64*1024*1024;
const LEAD = { clear:"Large lead over the runner-up", moderate:"Moderate lead over the runner-up", low:"Small lead: check the top 2–3 cars" } as const;

export default function AcvPanel() {
 const [file,setFile]=useState<File|null>(null); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
 const [result,setResult]=useState<AcvResult|null>(null); const [drag,setDrag]=useState(false);
 const input=useRef<HTMLInputElement>(null);
 function pick(f?:File){ if(!f)return; if(f.size>MAX){setError("This file exceeds the 64 MiB limit.");return;} if(!/\.(xlsx|csv)$/i.test(f.name)){setError("Choose an ACV telemetry workbook (.xlsx) or .csv.");return;} setFile(f);setError(""); }
 async function run(){ if(!file)return; setBusy(true);setError(""); try{ const body=new FormData(); body.append("file",file); setResult(await request<AcvResult>("/api/acv/analyze",{method:"POST",body})); }catch(e){setError(errorMessage(e));}finally{setBusy(false);} }
 async function download(kind:"csv"|"zip"){ if(!result)return; try{
  const url=kind==="csv"?`/api/acv/${result.id}/predictions.csv`:`/api/submission.zip?acv_id=${encodeURIComponent(result.id)}`;
  const r=await fetch(apiUrl(url),{cache:"no-store"}); if(!r.ok){const b=await r.json().catch(()=>null); throw new Error(b?.detail?.message??"Download failed.");}
  const blob=await r.blob(); const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download=kind==="csv"?"acv_predictions.csv":"predictions.zip"; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);
 }catch(e){setError(errorMessage(e));} }
 const maxScore=Math.max(0.01,...(result?.cars.map(c=>Math.abs(c.leak_score??0))??[0]));
 return <main className={s.wrap} id="workspace">
  <section className={s.intro}><h1>Which car is leaking refrigerant?</h1><p>Upload one train&apos;s ACV telemetry (8 cars, one reading every 30 s). DoorLens compares every car with its peers and ranks them from most to least likely to be the leaking one.</p></section>
  <section className={`${s.drop} ${drag?s.dragging:""}`} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);pick(e.dataTransfer.files?.[0]);}}>
   <div className={s.row}>
    <input ref={input} type="file" hidden accept=".xlsx,.csv" aria-label="Choose ACV telemetry file" onChange={e=>pick(e.target.files?.[0])}/>
    <button className={s.btn2} onClick={()=>input.current?.click()}>Choose ACV file</button>
    <button className={s.btn} disabled={!file||busy} onClick={run}>{busy?"Ranking cars…":"Rank the cars"}</button>
    <span className={s.note}>{file?`${file.name} · ${(file.size/1048576).toFixed(1)} MiB`:"or drag an .xlsx / .csv here"}</span>
   </div>
   <p className={s.note}>Large workbooks (30 MiB+) can take up to a minute. Files are processed in memory and cleared after 30 minutes. Assumes the train contains exactly one leaking car.</p>
  </section>
  {error&&<div className={s.err} role="alert">{error}</div>}
  {result&&<>
   <section className={s.hero} aria-label="ACV result">
    <div className={s.answer}><small>Most likely leaking car</small><div className={s.big}>Car {result.ranked_cars[0]}</div>
     <span className={`${s.conf} ${s[result.confidence]}`}>{LEAD[result.confidence]}</span>
     <p className={s.note} style={{marginTop:14}}>Full ranking: <b>{result.ranked_cars.join(" › ")}</b></p>
     <div className={s.row} style={{marginTop:16}}><button className={s.btn} onClick={()=>download("csv")}>acv_predictions.csv</button><button className={s.btn2} onClick={()=>download("zip")}>predictions.zip</button></div>
     <p className={s.note} style={{marginTop:10}}>{result.n_rows.toLocaleString()} readings · {result.n_cars} cars · {result.elapsed_ms.toLocaleString()} ms</p>
    </div>
    <div className={s.panel}><h2>Cabin temperature above its own setpoint, over time</h2><TrendPlot labels={result.trend.labels} series={result.trend.series} ranked={result.ranked_cars}/>
     <p className={s.note}>A car whose cabin runs warmer than its target more than its peers do is cooling poorly, which is the signature of an undercharged (leaking) system. The top-ranked car is highlighted.</p></div>
   </section>
   <section className={s.panel} style={{marginTop:24}}><h2>Car-by-car evidence</h2><div className={s.scroll}><table className={s.table}><thead><tr><th>Rank</th><th>Car</th><th>Leak score</th><th>Mean gap °C</th><th>Median °C</th><th>90th pct °C</th><th>Valid readings</th></tr></thead><tbody>
    {result.cars.map(c=><tr key={c.car} className={c.rank===1?s.top:""}><td>{c.rank}</td><td>{c.car}</td><td>{c.leak_score===null?"no valid data":<><span className={s.bar} style={{width:`${Math.max(4,Math.round(60*Math.max(0,c.leak_score)/maxScore))}px`}}/>{c.leak_score.toFixed(2)}</>}</td><td>{c.gap_mean_c??"—"}</td><td>{c.gap_median_c??"—"}</td><td>{c.gap_p90_c??"—"}</td><td>{c.valid_samples.toLocaleString()}</td></tr>)}
   </tbody></table></div>
    {result.unscored_cars.length>0&&<p className={s.foot}>Cars {result.unscored_cars.join(", ")} have no usable temperature data in this file, so they are ranked last.</p>}
    <p className={s.foot}>{result.warnings.join(" ")}</p></section>
  </>}
 </main>;
}
