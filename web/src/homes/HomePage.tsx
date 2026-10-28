import { useEffect, useRef, useState } from "react";
import type { Registry } from "../registry";
import { loadJSON } from "../registry";
import { areaLayer, areaName as labelArea, featureId } from "../areas";
import type { FeatureCollection } from "geojson";
import type { PolygonFeature } from "../map-polygons";
import { HomeCard, categoryLabel } from "./HomeCard";
import { homeData, homeLink, validHomeId, type Home, type HomeMeta } from "./data";
import { normalizeQuery } from "./address";
import { BatchPage } from "../batch/BatchPage";

const areaRequests=new Map<string,Promise<FeatureCollection>>();
export function useHomeArea(registry:Registry|null,home:Home|null):string|undefined {
  const [name,setName]=useState<string>();
  useEffect(()=>{
    let cancelled=false;setName(undefined);
    const base=registry && areaLayer(registry),url=base?.data_url;
    if(home?.block_group && url && /^data\/layers\/[a-z0-9_]+\.geojson$/.test(url)){
      if(!areaRequests.has(url))areaRequests.set(url,loadJSON<FeatureCollection>(url).catch(e=>{areaRequests.delete(url);throw e;}));
      areaRequests.get(url)!.then(doc=>{const area=doc.features.find(f=>featureId(f as PolygonFeature)===home.block_group);if(!cancelled && area)setName(labelArea(area as PolygonFeature));},()=>{});
    }
    return()=>{cancelled=true;};
  },[registry,home?.block_group]);return name;
}
type HomePageProps={hash:string;registry:Registry|null;onShowMap:(home:Home)=>void};
export function HomePage(props:HomePageProps){
  const many=new URLSearchParams(props.hash.split("?")[1]??"").get("tab")==="many";
  return <><nav className="home-tabs" aria-label="Home checks"><a href="#/home" aria-current={!many?"page":undefined}>Check a home</a><a href="#/home?tab=many" aria-current={many?"page":undefined}>Check many listings</a></nav>
    {many?<BatchPage registry={props.registry}/>:<SingleHomePage {...props}/>}</>;
}
function SingleHomePage({hash,registry,onShowMap}:HomePageProps) {
  const [meta,setMeta]=useState<HomeMeta|null>(null),[text,setText]=useState(""),[selected,setSelected]=useState<Home|null>(null);
  const [matches,setMatches]=useState<Home[]|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[searched,setSearched]=useState("");
  const sequence=useRef(0),controller=useRef<AbortController>();
  const list=useRef<HTMLUListElement>(null),name=useHomeArea(registry,selected);
  useEffect(()=>{let cancelled=false;homeData.meta().then(m=>{if(!cancelled)setMeta(m);},()=>{if(!cancelled)setError("Home records could not load. Please reload to retry.");});return()=>{cancelled=true;};},[]);
  useEffect(()=>()=>{sequence.current++;controller.current?.abort();},[]);
  const id=new URLSearchParams(hash.split("?")[1]??"").get("id");
  useEffect(()=>{window.history.replaceState(null,"",id && validHomeId(id) ? homeLink(id) : "#/home");},[id]);
  useEffect(()=>{
    const ticket=++sequence.current;controller.current?.abort();setError("");setMatches(null);setSelected(null);
    if(id){
      if(!validHomeId(id)){setBusy(false);setError("This home link is not valid.");return;}
      setBusy(true);const abort=new AbortController();controller.current=abort;
      homeData.byId(id,abort.signal)
        .then(home=>{if(ticket===sequence.current){setSelected(home);if(!home)setError("This home was not found in the published appraisal records.");}},e=>{if(ticket===sequence.current && e.name!=="AbortError")setError("The home could not load. Please try again.");})
        .finally(()=>{if(ticket===sequence.current)setBusy(false);});
    }else setBusy(false);
    return()=>{controller.current?.abort();};
  },[id]);
  const choose=(home:Home)=>{setSelected(home);setMatches(null);window.location.hash=homeLink(home.id);};
  const search=async()=>{
    window.history.replaceState(null,"","#/home");
    const ticket=++sequence.current;controller.current?.abort();setBusy(true);setError("");setSelected(null);setMatches(null);setSearched(text);
    try{const [found,m]=await Promise.all([homeData.search(text),homeData.meta()]);if(ticket!==sequence.current)return;setMeta(m);if(found.length===1)choose(found[0]);else setMatches(found);}
    catch{if(ticket===sequence.current)setError("Address records could not load. Please try again.");}
    finally{if(ticket===sequence.current)setBusy(false);}
  };
  useEffect(()=>{if(matches && matches.length>1)list.current?.querySelector<HTMLButtonElement>("button")?.focus();},[matches]);
  const query=normalizeQuery(searched);
  return <main className="page home-page"><div className="home-intro"><h1>Check a home</h1><p>Public property facts and an appraisal-based value range for Travis, Williamson and Hays counties.</p></div>
    <form className="home-search" onSubmit={e=>{e.preventDefault();void search();}}><label htmlFor="home-address">Paste an address from Zillow or similar</label>
      <div><input id="home-address" type="search" autoComplete="street-address" value={text} onChange={e=>setText(e.target.value)} placeholder="1008 S 8th St #2, Austin, TX 78704" required/><button disabled={busy || !text.trim()}>Find home</button></div>
      <p className="small muted">Search by street address. Owner names are not included.</p>
    </form>
    {busy && <p role="status">Loading home records…</p>}
    {error && <p role="alert">{error}</p>}
    {matches?.length===0 && <section role="status"><p>Not found in the 2026 appraisal records for Travis, Williamson and Hays counties</p><p>Normalized search: {[query.number,query.street_key,query.unit?`Unit ${query.unit}`:"",query.zip].filter(Boolean).join(" ") || "No street address entered"}</p><p>Try without the unit or ZIP.</p></section>}
    {matches && matches.length>1 && <section aria-label="Matching homes"><h2>Choose a home ({matches.length})</h2><p>Several appraisal records match this address. Use the arrow keys to move, then Enter to choose.</p>
      <ul ref={list} className="home-matches" onKeyDown={e=>{if(!["ArrowDown","ArrowUp","Home","End"].includes(e.key))return;const buttons=[...list.current!.querySelectorAll<HTMLButtonElement>("button")];const index=buttons.indexOf(document.activeElement as HTMLButtonElement);const next=e.key==="Home"?0:e.key==="End"?buttons.length-1:(index+(e.key==="ArrowDown"?1:-1)+buttons.length)%buttons.length;e.preventDefault();buttons[next]?.focus();}}>
        {matches.map(home=><li key={home.id}><button onClick={()=>choose(home)}>{home.situs || "Address not available"}<span>{home.county} County · {categoryLabel(home.category)} · {home.living_area==null?"Living area not available":`${home.living_area.toLocaleString()} sq ft`}</span></button></li>)}
      </ul></section>}
    {selected && meta && <HomeCard key={selected.id} home={selected} meta={meta} areaName={name} onShowMap={onShowMap}/>}
  </main>;
}
