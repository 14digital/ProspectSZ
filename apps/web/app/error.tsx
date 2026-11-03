"use client";
import {useEffect} from "react";

export default function ErrorPage({error,reset}:{error:Error&{digest?:string};reset:()=>void}){
  useEffect(()=>{console.error(error)},[error]);
  return <div className="card stack"><h1>Prospect page could not load</h1><p className="error">{error.message||"A browser error occurred while reading this prospect."}</p><button onClick={reset}>Try again</button><a href="/prospects">Return to prospect list</a></div>
}
