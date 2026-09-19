"use client";
import { useEffect, useState } from "react";
import Workbench from "./Workbench";
import AcvPanel from "./AcvPanel";
import s from "./Suite.module.css";

type Tab = "door" | "acv";
export default function Suite() {
 const [tab,setTab] = useState<Tab>("door");
 useEffect(()=>{ try { if (new URLSearchParams(window.location.search).get("subsystem")==="acv") setTab("acv"); } catch {} },[]);
 function pick(next:Tab) { setTab(next); try { history.replaceState(null,"",next==="acv"?"?subsystem=acv":window.location.pathname); } catch {} }
 return <>
  <nav className={s.bar} aria-label="Subsystem">
   <div className={s.tabs} role="group" aria-label="Choose subsystem">
    <button aria-pressed={tab==="door"} onClick={()=>pick("door")}><b>Door</b><span>Find and classify open/close cycles</span></button>
    <button aria-pressed={tab==="acv"} onClick={()=>pick("acv")}><b>ACV</b><span>Locate the leaking air-conditioning car</span></button>
   </div>
   <a className={s.how} href="/how-it-works/">How this works →</a>
  </nav>
  <div hidden={tab!=="door"}><Workbench /></div>
  {tab==="acv"&&<AcvPanel />}
 </>;
}
