"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import CompleteDetails from "@/components/ipo/CompleteDetails";
import { ErrorState, Skeleton } from "@/components/ui/primitives";

type State={kind:"loading"}|{kind:"ready";data:Record<string,unknown>}|{kind:"error";title:string;detail:string};
export default function DetailsPage({params}:{params:Promise<{isin:string}>}){
 const {isin}=use(params); const [state,setState]=useState<State>({kind:"loading"});
 useEffect(()=>{const controller=new AbortController(); fetch(`/api/ipo/details/${encodeURIComponent(isin)}`,{signal:controller.signal}).then(async r=>{const body=await r.json().catch(()=>null);if(!r.ok)throw new Error(`${r.status}: ${body?.error||"Malformed details response"}`);if(body?.schema_version!=="ipo-details-v1")throw new Error("Malformed details snapshot contract");setState({kind:"ready",data:body});}).catch(e=>{if(e.name!=="AbortError")setState({kind:"error",title:String(e.message).startsWith("404")?"IPO details not found":String(e.message).startsWith("503")?"KV unavailable":"Details unavailable",detail:String(e.message)});});return()=>controller.abort()},[isin]);
 return <div style={{maxWidth:1100,margin:"0 auto",padding:"16px",overflowX:"clip"}}><Link href="/dashboard/ipo2">← IPO Command Center</Link>{state.kind==="loading"?<div style={{marginTop:16}} aria-label="Loading IPO details"><Skeleton h={120} n={4}/></div>:state.kind==="error"?<ErrorState title={state.title} detail={state.detail}/>:<CompleteDetails details={state.data}/>}</div>
}
