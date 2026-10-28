import {memo,useEffect,useMemo,useRef,useState} from "react";
import type {FeatureCollection} from "geojson";
import {areaLayer} from "../areas";
import {loadJSON,type Registry} from "../registry";
import {clearBatchLists,readBatchLists,removeBatchList,saveBatchList,type SavedBatch} from "../store";
import {categoryLabel,dateLabel} from "../homes/HomeCard";
import {homeLink,type HomeMeta} from "../homes/data";
import {MAX_FILE_BYTES,parseImport,type Listing} from "./parse";
import {chooseMatch,positionLabel,processListings,published,SORT_LABELS,tableRows,type BatchResult,type BatchRow,type SortKey} from "./model";
import {downloadCSV,exportTable} from "./export";

const amount=(n:number|null|undefined)=>n==null?"Not available":n.toLocaleString("en-US",{maximumFractionDigits:2});
const money=(n:number|null|undefined)=>n==null?"Not available":n.toLocaleString("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0});
type Column={label:string;sort?:SortKey;range?:boolean;render:(row:BatchRow)=>React.ReactNode};
export const columns:Column[]=[
  {label:"Address",render:r=><><strong>{r.home?.situs||r.listing.query}</strong><div className="batch-links"><a href={homeLink(r.home!.id)} target="_blank" rel="noopener noreferrer">Home card</a>{r.listing.url&&<a href={r.listing.url} target="_blank" rel="noopener noreferrer">Listing</a>}</div></>},
  {label:"County",render:r=>r.home?.county},{label:"Category",render:r=>categoryLabel(r.home!.category)},
  ...([['Beds','beds'],['Baths','baths'],['Listing sq ft','sqft']] as const).map(([label,sort])=>({label,sort,render:(r:BatchRow)=><>{amount(r.listing[sort])}{sort==='sqft'&&r.metrics?.areaWarning&&<strong className="batch-area-warning">⚠ More than 10% different from appraisal living area</strong>}</>})),
  {label:"Appraisal sq ft",sort:"living_area",render:r=>amount(r.home?.living_area)},
  {label:"Year built",sort:"year_built",render:r=>amount(r.home?.year_built)},
  {label:"Asking price",sort:"price",render:r=>money(r.listing.price)},
  {label:"Asking $ per sq ft",sort:"psf",render:r=>money(r.metrics?.psf)},
  {label:"Appraisal-based value range",sort:"low",range:true,render:r=>r.metrics?.mid==null?"Not available":<>{money(r.metrics.low)} – {money(r.metrics.high)}<small>Centre {money(r.metrics.mid)}</small></>},
  {label:"Position",sort:"position",range:true,render:r=>positionLabel(r.metrics?.position??null)},
  {label:"Range width / flags",sort:"rangePct",range:true,render:r=><>{r.metrics?.rangePct==null?"Not available":`±${r.metrics.rangePct}%`}{r.metrics?.flags&&<small>{r.metrics.flags}</small>}</>},
  {label:"Neighbourhood percentile",sort:"percentile",render:r=>r.metrics?.percentile==null?"Not available":`≈${Math.round(r.metrics.percentile)}th`},
  {label:"Neighbourhood homes (n)",sort:"n",render:r=>amount(r.metrics?.n)},
  {label:"Days on market",sort:"days",render:r=>amount(r.listing.days)},
  {label:"HOA per month",sort:"hoa",render:r=>money(r.listing.hoa)},
];
function readFile(file:File):Promise<string>{
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result??""));reader.onerror=()=>reject(new Error("The file could not be read."));reader.readAsText(file);});
}
function SourceDetails({row,meta}:{row:BatchRow;meta:HomeMeta}){
  const h=row.home!,c=meta.counties[h.county],range=meta.value_range;
  return <details className="batch-source"><summary>Sources and file details{row.metrics?.testData?" · Test data":""}</summary>
    <p>{meta.sources[c?.source]??c?.source} · appraisal as of {dateLabel(c?.value_as_of?.[0])} · export {dateLabel(h.certified)}.</p>
    <p>Asking price, beds/baths, listing area, days and HOA are supplied by your file.</p>
    <p>Listing year: {amount(row.listing.year)} · Lot: {amount(row.listing.lot)} (file units) · Status: {row.listing.status||"Not available"} · Property type: {row.listing.propertyType||"Not available"}.</p>
    {range&&<p>Neighbourhood appraisal-based $ per sq ft uses {range.study} ({range.study_year}) and FHFA as of {dateLabel(range.hpi.as_of)}. Approximate percentile position interpolates between published quantiles and is capped at the 10th and 90th percentiles.</p>}
  </details>;
}
const ResultRow=memo(function ResultRow({row,meta,showRange}:{row:BatchRow;meta:HomeMeta;showRange:boolean}){
  return <tr data-listing-key={row.listing.key}>{columns.filter(c=>showRange||!c.range).map(c=><td key={c.label}><span className="batch-mobile-label">{c.label}</span><div>{c.render(row)}</div></td>)}<td><SourceDetails row={row} meta={meta}/></td></tr>;
});
export function BatchPage({registry}:{registry:Registry|null}){
  const [paste,setPaste]=useState(""),[result,setResult]=useState<BatchResult|null>(null),[ignored,setIgnored]=useState<string[]>([]);
  const [busy,setBusy]=useState(false),[progress,setProgress]=useState([0,0]),[error,setError]=useState(""),[message,setMessage]=useState("");
  const [name,setName]=useState(""),[saved,setSaved]=useState<SavedBatch[]>(readBatchLists),[restoreName,setRestoreName]=useState("");
  const [filters,setFilters]=useState({county:"",category:"",hasRange:false}),[sort,setSort]=useState<{key:SortKey;descending:boolean}>({key:"default",descending:false});
  const [choices,setChoices]=useState<Record<string,string>>({}),[limit,setLimit]=useState(25);
  const ticket=useRef(0),focusedTicket=useRef(0),controller=useRef<AbortController>(),fileInput=useRef<HTMLInputElement>(null),heading=useRef<HTMLHeadingElement>(null);
  const bounds=useRef<Promise<FeatureCollection|null>>();
  useEffect(()=>()=>{ticket.current++;controller.current?.abort();},[]);
  useEffect(()=>{if(result&&focusedTicket.current!==ticket.current){heading.current?.focus();focusedTicket.current=ticket.current;}},[result]);
  const showRange=!!result&&published(result.meta);
  const matched=useMemo(()=>tableRows(result?.rows??[],filters,sort.key,sort.descending,showRange),[result,filters,sort,showRange]);
  const unresolved=result?.rows.filter(row=>!row.home)??[];
  useEffect(()=>{
    setLimit(25);let timer:ReturnType<typeof setTimeout>;let count=25;
    const more=()=>{count+=25;setLimit(count);if(count<matched.length)timer=setTimeout(more,0);};
    if(matched.length>25)timer=setTimeout(more,0);return()=>clearTimeout(timer);
  },[matched]);
  const loadBounds=()=>{
    const url=registry&&areaLayer(registry)?.data_url;
    if(!url||!/^data\/layers\/[a-z0-9_]+\.geojson$/.test(url))return Promise.resolve(null);
    bounds.current??=loadJSON<FeatureCollection>(url).catch(()=>null);return bounds.current;
  };
  const start=async(input:(signal:AbortSignal)=>Promise<{listings:Listing[];ignoredHeaders:string[]}>,restored="")=>{
    const current=++ticket.current;controller.current?.abort();const abort=new AbortController();controller.current=abort;
    setBusy(true);setError("");setMessage("");setResult(null);setIgnored([]);setChoices({});setProgress([0,0]);setName(restored);setFilters({county:"",category:"",hasRange:false});setSort({key:"default",descending:false});
    try{
      const parsed=await input(abort.signal);if(current!==ticket.current)return;setIgnored(parsed.ignoredHeaders);
      const next=await processListings(parsed.listings,{signal:abort.signal,loadBounds,onProgress:(done,total)=>{if(current===ticket.current)setProgress([done,total]);}});
      if(current!==ticket.current)return;setResult(next);heading.current?.focus();
    }catch(e){if(current===ticket.current && !abort.signal.aborted)setError(e instanceof Error?e.message:"The import could not be processed.");}
    finally{if(current===ticket.current)setBusy(false);}
  };
  const importFile=(file:File)=>{
    void start(async signal=>{if(file.size>MAX_FILE_BYTES)throw new Error("Choose a file under 5 MB.");const text=await readFile(file);return parseImport(text,"csv",signal);});
    if(fileInput.current)fileInput.current.value="";
  };
  const clear=()=>{
    ticket.current++;controller.current?.abort();setResult(null);setPaste("");setIgnored([]);setError("");setMessage(clearBatchLists()?"All listing imports and saved lists were cleared.":"Listings cleared for this session; browser storage could not be changed.");setSaved(readBatchLists());setRestoreName("");setName("");setBusy(false);setProgress([0,0]);setChoices({});if(fileInput.current)fileInput.current.value="";
  };
  const save=()=>{
    if(!result)return;try{const ok=saveBatchList(name,result.rows.map(r=>r.listing));setSaved(readBatchLists());setRestoreName(name.trim());setMessage(ok?"List saved in this browser.":"Storage is blocked or full; this saved list lasts only for this session.");setError("");}catch(e){setError((e as Error).message);}
  };
  const sortBy=(key:SortKey)=>setSort(old=>({key,descending:old.key===key?!old.descending:false}));
  return <main className="page batch-page"><h1>Check many listings</h1>
    <p>Your file stays in this browser. Nothing is uploaded or saved unless you choose Save.</p>
    <section className="batch-import" aria-label="Import listings" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(e.dataTransfer.files.length!==1)setError("Drop one CSV file at a time.");else importFile(e.dataTransfer.files[0]);}}>
      <label className="batch-file">Drop a Redfin CSV here or choose a file (up to 350 listings, 5 MB)<input ref={fileInput} type="file" accept=".csv,text/csv" aria-label="Choose Redfin CSV" onChange={e=>{const file=e.target.files?.[0];if(file)importFile(file);}}/></label>
      <label>Addresses and asking prices<textarea value={paste} onChange={e=>setPaste(e.target.value)} rows={3} placeholder="1008 S 8th St #2, Austin, TX 78704 — $725,000"/></label>
      <button disabled={!paste.trim()||busy} onClick={()=>void start(signal=>parseImport(paste,"paste",signal))}>Check pasted listings</button>
    </section>
    <div className="batch-saved"><label>Saved lists<select aria-label="Saved lists" value={restoreName} onChange={e=>setRestoreName(e.target.value)}><option value="">Choose a saved list</option>{saved.map(list=><option key={list.name} value={list.name}>{list.name} ({list.rows.length})</option>)}</select></label>
      <button disabled={!restoreName||busy} onClick={()=>{const list=saved.find(s=>s.name===restoreName);if(list)void start(async()=>({listings:list.rows,ignoredHeaders:[]}),list.name);}}>Restore list</button>
      <button disabled={!restoreName||busy} onClick={()=>{removeBatchList(restoreName);setSaved(readBatchLists());setRestoreName("");setMessage("Saved list removed.");}}>Remove saved list</button>
      <button onClick={clear}>Clear all listings</button>
    </div>
    {busy&&<p role="status">Checking listings… {progress[0]} of {progress[1]||"…"}</p>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {!!ignored.length&&<p className="small">Ignored column headers: {ignored.join(", ")}. Their values were discarded.</p>}
    {result&&<>
      <h2 ref={heading} tabIndex={-1}>Listing results</h2>
      {(result.meta.test_data || result.hoods?.test_data || showRange&&result.meta.value_range?.test_data)&&<p className="badge">Test data</p>}
      <p className="batch-sort-note">{showRange?"Listings priced furthest below their appraisal-based range come first. A low price often has a reason the appraisal can't see — condition, layout, noise. Check the home's card before deciding.":"The value range is being validated and will appear here. Listings are ordered by their neighbourhood appraisal-based $ per sq ft percentile."}</p>
      <p className="small">Listing figures come from your import. Sources and dates for the public records are available in every row. Percentile positions are approximate and bounded at the 10th and 90th percentiles.</p>
      {result.hoodError&&<p role="status">Neighbourhood comparisons could not load; those fields are Not available.</p>}
      <div className="batch-controls">
        <label>County<select aria-label="County" value={filters.county} onChange={e=>setFilters({...filters,county:e.target.value})}><option value="">All counties</option>{[...new Set(result.rows.flatMap(r=>r.home?[r.home.county]:[]))].sort().map(county=><option key={county}>{county}</option>)}</select></label>
        <label>Category<select aria-label="Category" value={filters.category} onChange={e=>setFilters({...filters,category:e.target.value})}><option value="">All categories</option>{[...new Set(result.rows.flatMap(r=>r.home?[r.home.category]:[]))].sort().map(category=><option key={category} value={category}>{categoryLabel(category)}</option>)}</select></label>
        {showRange&&<label><input type="checkbox" checked={filters.hasRange} onChange={e=>setFilters({...filters,hasRange:e.target.checked})}/>Has a range</label>}
        <label>Sort by<select aria-label="Sort by" value={sort.key} onChange={e=>setSort({key:e.target.value as SortKey,descending:false})}>{Object.entries(SORT_LABELS).filter(([key])=>showRange||!["low","high","position","rangePct"].includes(key)).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <button disabled={sort.key==="default"} onClick={()=>setSort({...sort,descending:!sort.descending})}>{sort.descending?"Descending":"Ascending"}</button>
      </div>
      <p role="status">{matched.length} matched listings shown · {unresolved.length} need attention</p>
      <div className="batch-actions"><label>List name<input value={name} maxLength={80} onChange={e=>setName(e.target.value)}/></label><button onClick={save} disabled={!name.trim()}>Save list</button><button disabled={!matched.length} onClick={()=>downloadCSV(exportTable(matched,result.meta))}>Export table CSV</button><span className="small">Export uses the filtered table in its current order. Clear removes this import and all saved listing lists.</span></div>
      <div className="batch-table-wrap"><table className="batch-table"><caption>Matched listings</caption><thead><tr>{columns.filter(c=>showRange||!c.range).map(c=><th key={c.label} scope="col" aria-sort={c.sort&&sort.key===c.sort?(sort.descending?"descending":"ascending"):undefined}>{c.sort?<button onClick={()=>sortBy(c.sort!)} aria-label={`Sort by ${c.label}`}>{c.label}</button>:c.label}</th>)}<th scope="col">Sources / file details</th></tr></thead>
        <tbody>{matched.slice(0,limit).map(row=><ResultRow key={row.listing.key} row={row} meta={result.meta} showRange={showRange}/>)}</tbody></table></div>
      {limit<matched.length&&<p role="status">Rendering more listings…</p>}
      {!!unresolved.length&&<section className="batch-unmatched" aria-label="Listings needing attention"><h2>Listings needing attention</h2><ul>{unresolved.map(row=><li key={row.listing.key}><h3>{row.listing.query||"Address not available"}</h3><p>{row.reason}</p><p className="small">Normalized search: {[row.normalized.number,row.normalized.street_key,row.normalized.unit?`Unit ${row.normalized.unit}`:"",row.normalized.zip].filter(Boolean).join(" ")||"No street address"}</p>
        {!!row.candidates.length&&<><label>Choose appraisal record<select aria-label={`Choose appraisal record for listing ${Number(row.listing.key)+1}`} value={choices[row.listing.key]??""} onChange={e=>setChoices({...choices,[row.listing.key]:e.target.value})}><option value="">Choose a record</option>{row.candidates.map(home=><option key={home.id} value={home.id}>{home.situs} · {home.county} · {categoryLabel(home.category)} · {amount(home.living_area)} sq ft</option>)}</select></label><button disabled={!choices[row.listing.key]} onClick={()=>setResult(old=>old?{...old,rows:old.rows.map(r=>r.listing.key===row.listing.key?chooseMatch(r,choices[row.listing.key],old.meta,old.hoods):r)}:old)}>Use this record</button></>}
      </li>)}</ul></section>}
    </>}
  </main>;
}
