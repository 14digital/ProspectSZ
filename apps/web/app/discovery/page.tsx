"use client";
import {FormEvent,useEffect,useState} from "react";
import {request} from "@/lib/api";
type Run={id:string;state:string;source:string;target_count:number;discovered_count:number;qualified_count:number;error?:string};
export default function Discovery(){
  const [runs,setRuns]=useState<Run[]>([]),[selected,setSelected]=useState(""),[message,setMessage]=useState("");
  const load=()=>request<Run[]>("/discovery-runs").then(setRuns).catch(e=>setMessage(e.message));
  useEffect(()=>{void load()},[]);
  async function create(){const run=await request<Run>("/discovery-runs",{method:"POST",body:JSON.stringify({source:"CQC_CSV",target_count:20})});setSelected(run.id);void load()}
  async function upload(e:FormEvent<HTMLFormElement>){e.preventDefault();if(!selected)return setMessage("Create or select a discovery run first");try{const result=await request<{job_id:string}>(`/discovery-runs/${selected}/upload`,{method:"POST",body:new FormData(e.currentTarget)});setMessage(`Import queued. Job ${result.job_id||"already exists"}`);void load()}catch(err){setMessage((err as Error).message)}}
  return <><h1>Prospect Discovery</h1><p className="sub">CQC CSV is the dependable source. Imports preserve provider and location identifiers and run asynchronously.</p><div className="toolbar"><button onClick={create}>Run Discovery</button><label>Discovery run<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select…</option>{runs.map(r=><option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.state}</option>)}</select></label></div><form className="card toolbar" onSubmit={upload}><label>CQC provider/location CSV<input type="file" name="file" accept=".csv,text/csv" required/></label><label>Source URL<input name="source_url" type="url" placeholder="https://www.cqc.org.uk/about-us/transparency/using-cqc-data"/></label><button>Queue import</button></form>{message&&<p className={message.includes("queued")?"success":"error"}>{message}</p>}<div className="card"><table><thead><tr><th>Run</th><th>State</th><th>Source</th><th>Discovered</th><th>Qualified</th><th>Error</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td>{r.id.slice(0,8)}</td><td><span className="pill">{r.state}</span></td><td>{r.source}</td><td>{r.discovered_count}</td><td>{r.qualified_count}</td><td>{r.error}</td></tr>)}</tbody></table></div></>
}
