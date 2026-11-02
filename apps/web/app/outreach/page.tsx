"use client";
import {useEffect,useState} from "react";
import {request} from "@/lib/api";
type Draft={id:string;channel:string;state:string;version:number};
export default function Outreach(){
  const [items,setItems]=useState<Draft[]>([]),[message,setMessage]=useState("");
  const load=()=>request<Draft[]>("/outreach/drafts").then(setItems).catch(e=>setMessage(e.message));
  useEffect(()=>{void load()},[]);
  async function action(id:string,kind:string){try{await request(`/outreach/drafts/${id}/${kind}`,{method:"POST"});setMessage(`${kind} completed`);void load()}catch(e){setMessage((e as Error).message)}}
  return <><h1>Outreach Studio</h1><p className="sub">Approval and sending are separate. LinkedIn remains human-operated.</p>{message&&<div className={message.includes("completed")?"success":"error"}>{message}</div>}<div className="card"><table><thead><tr><th>Draft</th><th>Channel</th><th>State</th><th>Actions</th></tr></thead><tbody>{items.map(d=><tr key={d.id}><td>{d.id.slice(0,8)}</td><td>{d.channel}</td><td><span className="pill">{d.state}</span></td><td className="toolbar"><button className="secondary" onClick={()=>action(d.id,"approve")}>Approve</button><button className="danger" onClick={()=>action(d.id,"reject")}>Reject</button><button disabled={d.state!=="APPROVED"||d.channel!=="EMAIL"} onClick={()=>action(d.id,"send")}>Send</button></td></tr>)}</tbody></table></div></>
}
