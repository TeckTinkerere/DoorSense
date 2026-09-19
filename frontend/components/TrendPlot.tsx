"use client";
import { useMemo } from "react";
import type { Data } from "plotly.js";
import { ResponsivePlot, base, amber } from "./SignalPlot";

export function TrendPlot({labels,series,ranked}:{labels:string[];series:Record<string,(number|null)[]>;ranked:string[]}) {
 const data = useMemo(() => ranked.filter(car=>series[car]).map((car,i):Data => ({
  x:labels, y:series[car], name:`Car ${car}`, type:"scatter", mode:"lines", connectgaps:false,
  line:{color:i===0?amber:"#9db1bb",width:i===0?2.6:1.2}, hovertemplate:`Car ${car}: %{y:.2f} °C<extra></extra>`
 } as Data)),[labels,series,ranked]);
 return <ResponsivePlot data={data} layout={{...base,height:280,showlegend:true,legend:{orientation:"h",y:-0.25},margin:{l:58,r:18,t:8,b:74},xaxis:{...base.xaxis,type:"category",nticks:6,title:{text:"Recorded time"}},yaxis:{...base.yaxis,title:{text:"Indoor − setpoint · °C"}}}} />;
}
