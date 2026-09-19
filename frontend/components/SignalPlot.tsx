"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import type { Trace, CycleDetail, Challenge } from "@/lib/types";
import styles from "./Workbench.module.css";
const Plot = dynamic(() => import("react-plotly.js"), { ssr:false, loading:() => <div className={styles.plotLoading}>Preparing the signal view…</div> });
export const navy = "#244b65", amber = "#af6b20", green = "#397451";
const config = { responsive:true, displaylogo:false, scrollZoom:false, modeBarButtonsToRemove:["lasso2d","select2d","autoScale2d"] as ("lasso2d"|"select2d"|"autoScale2d")[], toImageButtonOptions:{format:"png" as const,filename:"doorlens-recorded-evidence",scale:2} };
export const base:Partial<Layout> = { autosize:true, paper_bgcolor:"transparent", plot_bgcolor:"#fff", font:{family:"Manrope Variable, sans-serif",size:11,color:"#5d6a71"}, hovermode:"x unified", margin:{l:58,r:25,t:12,b:47}, showlegend:false, hoverlabel:{bgcolor:"#fff",bordercolor:"#d8ddd9",font:{color:"#172d40"}}, xaxis:{gridcolor:"#eef0ed",zeroline:false}, yaxis:{gridcolor:"#eef0ed",zeroline:false}, dragmode:"zoom" };
function trace(x:(number|string|null)[], y:(number|null)[], name:string, color:string, extra:Record<string,unknown> = {}):Data {
 return { x, y, name, type:"scatter", mode:"lines", line:{color,width:1.7}, connectgaps:false, ...extra } as Data;
}
// Plotly interprets numeric date coordinates through the host timezone. These
// timezone-free ISO coordinates preserve the recording's original wall clock.
function recordedTimes(data:Trace):(string|null)[] {
 return data.time_ms.map(value=>value===null?null:new Date(value).toISOString().slice(0,-1));
}
export function ResponsivePlot({data,layout}:{data:Data[];layout:Partial<Layout>}) {
 const container=useRef<HTMLDivElement>(null);
 const [width,setWidth]=useState(0);
 useEffect(()=>{
  const element=container.current;
  if(!element)return;
  const measure=()=>setWidth(Math.max(1,Math.floor(element.getBoundingClientRect().width)));
  measure();
  const observer=new ResizeObserver(measure);
  observer.observe(element);
  return ()=>observer.disconnect();
 },[]);
 return <div ref={container} className={styles.plotFrame} style={{minHeight:layout.height}}>
  {width>0?<Plot data={data} layout={{...layout,width,autosize:false}} config={config} style={{width:"100%",maxWidth:"100%"}}/>:<div className={styles.plotLoading}>Preparing the signal view…</div>}
 </div>;
}
export function OverviewPlot({data,runId}:{data:Trace;runId:string}) {
 const traces = useMemo(() => [trace(recordedTimes(data),data.current_a,"Recorded current",navy,{customdata:data.timestamps,hovertemplate:"%{customdata}<br>%{y:.3f} A<extra></extra>"})],[data]);
 return <ResponsivePlot data={traces} layout={{...base,height:166,uirevision:runId,margin:{l:55,r:18,t:6,b:38},xaxis:{...base.xaxis,type:"date",tickformat:"%H:%M:%S",title:{text:"Recorded time"}},yaxis:{...base.yaxis,title:{text:"Current · A"}}}} />;
}
export function TimePlot({detail,challenge,channel}:{detail:CycleDetail;challenge:Challenge|null;channel:"current"|"voltage"}) {
 const data = useMemo(() => {
 const voltage=channel==="voltage",unit=voltage?"V":"A"; const traces:Data[] = [trace(recordedTimes(detail.trace),voltage?detail.trace.voltage_v:detail.trace.current_a,`Original ${channel}`,navy,{customdata:detail.trace.timestamps,hovertemplate:`%{customdata}<br>Original %{y:.4f} ${unit}<extra></extra>`}),trace(recordedTimes(detail.trace),detail.trace.position,"Original position",navy,{yaxis:"y2",xaxis:"x2",hovertemplate:"%{y:.1f} counts<extra>Original position</extra>"})];
 if (challenge) {
 traces.push(trace(recordedTimes(challenge.trace),voltage?challenge.trace.voltage_v:challenge.trace.current_a,`Changed ${channel}`,amber,{line:{color:amber,width:1.7,dash:"dot"},hovertemplate:`Changed %{y:.4f} ${unit}<extra></extra>`}));
 traces.push(trace(recordedTimes(challenge.trace),challenge.trace.position,"Changed position",amber,{xaxis:"x2",yaxis:"y2",line:{color:amber,width:1.7,dash:"dot"},hovertemplate:"%{y:.1f} counts<extra>Changed position</extra>"}));
 }
 return traces;
 },[detail,challenge,channel]);
 return <ResponsivePlot data={data} layout={{...base,height:342,uirevision:`${detail.analysis_id}-${detail.index}-${channel}`,margin:{l:67,r:25,t:10,b:43},xaxis:{...base.xaxis,type:"date",domain:[0,1],anchor:"y",showticklabels:false},xaxis2:{...base.xaxis,type:"date",domain:[0,1],anchor:"y2",matches:"x",tickformat:"%H:%M:%S.%L",title:{text:"Recorded time · original coordinates"}},yaxis:{...base.yaxis,domain:[.43,1],title:{text:channel==="voltage"?"Voltage · V":"Current · A"}},yaxis2:{...base.yaxis,domain:[0,.3],title:{text:"Position · counts"}}}} />;
}
export function ReferencePlot({detail,challenge}:{detail:CycleDetail;challenge:Challenge|null}) {
 const data = useMemo(() => {
 const r=detail.reference;
 const rows:Data[] = [trace(r.progress,r.current_lower_a,"Normal lower",green,{line:{width:0},hoverinfo:"skip"}),trace(r.progress,r.current_upper_a,"Normal reference · 10th–90th percentile",green,{line:{width:0},fill:"tonexty",fillcolor:"rgba(57,116,81,.12)",hoverinfo:"skip"}),trace(r.progress,r.current_median_a,"Training-normal median",green,{line:{color:green,width:1.4,dash:"dash"},hovertemplate:"Median %{y:.3f} A<extra></extra>"}),trace(detail.trace.progress,detail.trace.current_a.map(v=>v===null?null:Math.abs(v)),"Original",navy,{hovertemplate:"Original %{y:.3f} A<extra></extra>"})];
 if(challenge) rows.push(trace(challenge.trace.progress,challenge.trace.current_a.map(v=>v===null?null:Math.abs(v)),"Assumed change",amber,{line:{color:amber,width:1.5,dash:"dot"},hovertemplate:"Changed %{y:.3f} A<extra></extra>"}));
 return rows;
 },[detail,challenge]);
 return <ResponsivePlot data={data} layout={{...base,height:230,uirevision:`reference-${detail.analysis_id}-${detail.index}`,xaxis:{...base.xaxis,title:{text:"Relative door travel"},tickformat:".0%",range:[0,1]},yaxis:{...base.yaxis,title:{text:"Absolute current · A"}}}} />;
}


