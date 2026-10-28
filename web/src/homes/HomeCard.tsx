import { useEffect, useId, useRef, useState } from "react";
import type { Home, HomeMeta, HoodData, HoodStat } from "./data";
import { homeData, homeLink } from "./data";
import { valueRange } from "./range";
import { readAskingPrice, storageAvailable, writeAskingPrice } from "../store";

export const categoryLabel = (category:string) => ({single_family:"Single-family home",condo:"Condo",mobile_home:"Mobile home",two_to_four_units:"2–4 units",rural_home:"Rural home",builder_inventory:"Builder inventory (new construction)",other_residential:"Other residential home"} as Record<string,string>)[category] ?? "Residential home";
const currency=(n:number|null)=>n==null ? "Not available" : new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(n);
const number=(n:number|null)=>n==null ? "Not available" : n.toLocaleString("en-US",{maximumFractionDigits:4});
export function dateLabel(value?:string|null):string {
  if(!value || !/^\d{4}-\d{2}-\d{2}$/.test(value))return "Not available";
  return new Date(value+"T12:00:00Z").toLocaleDateString("en-US",{month:"long",day:"numeric",year:"numeric",timeZone:"UTC"});
}
export function percentilePosition(price:number,stat:HoodStat):number {
  const points:[number,number][]=[[stat.p10,10],[stat.p25,25],[stat.p50,50],[stat.p75,75],[stat.p90,90]];
  if(price<=points[0][0])return 10;
  for(let i=1;i<points.length;i++)if(price<=points[i][0]){
    const [lo,p]=points[i-1],[hi,q]=points[i];return hi===lo ? p : p+(price-lo)/(hi-lo)*(q-p);
  }
  return 90;
}
const flagLabels:Record<string,string>={new:"Built in the last two years or builder inventory",lot:"Lot over one acre",condo:"Condo",size:"Unusually large/small for its neighbourhood",type:"Not a single-family home"};
const reasons:Record<string,string>={no_building:"No building value on January 1, 2026",partial:"Partial-ownership record",no_value:"No 2026 market value"};
export function HomeCard({home,meta,areaName,onShowMap,onClose,loadHoods=()=>homeData.hoods()}: {
  home:Home;meta:HomeMeta;areaName?:string;onShowMap:(home:Home)=>void;onClose?:()=>void;loadHoods?:()=>Promise<HoodData>;
}) {
  const uid=useId();
  const heading=useRef<HTMLHeadingElement>(null);
  const [asking,setAsking]=useState(()=>readAskingPrice(home.id)),[persistent,setPersistent]=useState(storageAvailable);
  const [hoods,setHoods]=useState<HoodData|null>(null),[hoodError,setHoodError]=useState(false);
  const county=meta.counties[home.county],range=meta.value_range,fips=home.id.split(":")[0];
  const codes=(home.range_flags??"").split(",").filter(Boolean);
  const shown=range?.published===true;
  let result:{low:number|null;mid:number|null;high:number|null}={low:null,mid:null,high:null};
  if(shown && home.range_pct!=null)try{result=valueRange(home.market_value,fips,home.range_pct,range.hpi.factor,range.levels);}catch{ /* Fail closed on unavailable range inputs. */ }
  const price=asking!=="" && Number(asking)>0 && Number.isFinite(Number(asking)) ? Number(asking) : null;
  const psf=price!=null && home.living_area!=null && home.living_area>0 ? price/home.living_area : null;
  useEffect(()=>{heading.current?.focus();},[home.id]);
  useEffect(()=>{
    let cancelled=false;
    if(shown && result.mid!=null && psf!=null)loadHoods().then(data=>{if(!cancelled){setHoods(data);setHoodError(false);}},()=>{if(!cancelled)setHoodError(true);});
    return()=>{cancelled=true;};
  },[shown,result.mid,psf,home.id]); // loader is shared/cached; private price is never sent to it.
  const group=["single_family","condo"].includes(home.category)?home.category:"other";
  const stat=hoods?.rows.find(s=>s.county===home.county && s.hood_cd===home.hood_cd && s.category===group);
  const description=home.hood_cd && meta.hood_desc[home.county]?.[home.hood_cd];
  const source=meta.sources[county?.source] ?? `${home.county} appraisal district`;
  const test=meta.test_data || county?.test_data || home.test_data || shown && (range?.test_data || hoods?.test_data);
  const location=home.placed==="parcel" && home.lon!=null && home.lat!=null;
  return <article className="home-card" aria-label="Home details">
    {onClose && <button className="home-close" aria-label="Close home details" onClick={onClose}>×</button>}
    {test && <p className="badge home-test">Test data</p>}
    <h2 ref={heading} tabIndex={-1}>{home.situs || "Address not available"}</h2>
    <p className="home-category">{home.county} County · {categoryLabel(home.category)}</p>
    <section aria-labelledby={uid+"-home-facts"}><h3 id={uid+"-home-facts"}>Property facts</h3>
      <dl className="home-facts"><div><dt>Living area</dt><dd>{home.living_area==null ? "Not available" : `${number(home.living_area)} sq ft`}</dd></div>
        <div><dt>Year built</dt><dd>{home.year_built ?? "Not available"}</dd></div><div><dt>Lot size</dt><dd>{home.land_acres==null?"Not available":`${number(home.land_acres)} acres`}</dd></div>
        <div><dt>Floors</dt><dd>{number(home.floors)}</dd></div><div><dt>Appraisal neighbourhood</dt><dd>{home.hood_cd ? `${description ? description+" · " : ""}${home.hood_cd}` : "Not available"}</dd></div></dl>
      {home.land_acres==null && home.county==="Williamson" && <p className="small muted">Lots priced per lot often have no recorded acreage.</p>}
      <p className="home-source small">{source} · {home.value_year ?? "2026"} records · export {dateLabel(home.certified)}</p>
    </section>
    <section aria-labelledby={uid+"-home-appraisal"}><h3 id={uid+"-home-appraisal"}>{home.value_year ?? "2026"} appraisal</h3>
      <dl className="home-facts"><div><dt>Market value</dt><dd>{currency(home.market_value)}</dd></div><div><dt>Land</dt><dd>{currency(home.land_value)}</dd></div><div><dt>Improvements</dt><dd>{currency(home.improvement_value)}</dd></div></dl>
      <p className="home-source small">{source} · as of {dateLabel(county?.value_as_of?.[0] ?? "2026-01-01")} · export {dateLabel(home.certified)}</p>
    </section>
    <section aria-labelledby={uid+"-home-range"}><h3 id={uid+"-home-range"}>Appraisal-based value range</h3>
      {!shown ? <p>The value range is being validated and will appear here.</p> : home.range_pct==null ? <p>{reasons[codes[0]] ?? "A range is not available for this record."}</p> : result.mid==null ? <p>Range inputs are not available for this record.</p> : <>
        {range.test_data && <p className="badge">Test data · value range</p>}
        <p className="home-range-number">{currency(result.low)} – {currency(result.high)} <span>(centre {currency(result.mid)})</span></p>
        <p>±{home.range_pct}%{codes.length ? ` · ${codes.map(c=>flagLabels[c]??range.flags[c]??c).join("; ")}` : ""}</p>
        <details className="range-explanation"><summary>How this is worked out</summary>
          <ol><li>{home.value_year} appraisal: {currency(home.market_value)}, as of {dateLabel(county?.value_as_of?.[0] ?? "2026-01-01")}, from {source}.</li>
            <li>Divide by the county appraisal level {range.levels[fips]?.toFixed(2)}: {home.market_value!=null && range.levels[fips]>0 ? currency(home.market_value/range.levels[fips]) : "Not available"}. {range.study} ({range.study_year}).</li>
            <li>Multiply by FHFA factor {range.hpi.factor.toFixed(6)}: latest {range.hpi.latest_quarter} SA index {range.hpi.latest_index} ÷ base mean {range.hpi.base_index} ({range.hpi.base_quarters.join(" and ")}). FHFA purchase-only metro index, as of {dateLabel(range.hpi.as_of)}.</li>
            <li>Round the centre to $1,000: {currency(result.mid)}. Apply ±{home.range_pct}% and round endpoints to $1,000 using nearest-even rounding.</li></ol>
          <p>{range.method}</p><p>{range.year_over_year_note}</p>
          <p>{range.within_10pct[fips]!=null ? `${(range.within_10pct[fips]*100).toFixed(2)}% of single-family sales were within 10% of the appraisal in the ${range.study_year} study.` : "Study coverage is not available."}</p>
          {range.size_note && <p>{range.size_note}</p>}
        </details>
      </>}
    </section>
    <section aria-labelledby={uid+"-asking-heading"}><h3 id={uid+"-asking-heading"}>Your asking price</h3>
      <label className="asking-label">Asking price (optional)<input type="number" inputMode="decimal" min="0" step="1" value={asking} onChange={e=>{const v=e.target.value;if(/^\d*(?:\.\d{0,2})?$/.test(v)){setAsking(v);setPersistent(writeAskingPrice(home.id,v));}}} /></label>
      <p className="small muted">Kept only in this browser. Not included in shared links.{!persistent ? " Storage is blocked; this price lasts for this session only." : ""}</p>
      {shown && result.mid!=null && price!=null && result.low!=null && result.high!=null && <p className="asking-position">The asking price is {price<result.low ? "below" : price>result.high ? "above" : "inside"} the appraisal-based value range.</p>}
      {psf!=null && <p>Your asking price per sq ft: {currency(psf)} · based on {number(home.living_area)} sq ft in the {home.value_year} {source} records.</p>}
      {shown && result.mid!=null && psf!=null && (hoodError ? <p>Neighbourhood comparison could not load. Try reloading.</p> : !hoods ? <p>Loading neighbourhood comparison…</p> : !stat ? <p>No neighbourhood table is available for this category (at least 10 measured homes with a range are needed).</p> : <div className="hood-comparison">
        {hoods.test_data && <p className="badge">Test data · neighbourhood comparison</p>}
        <p>The asking price per sq ft is {psf<stat.p10 ? "lower than about 90%" : `higher than about ${Math.round(percentilePosition(psf,stat))}%`} of similar homes in this appraisal neighbourhood, by appraisal-based $ per sq ft.</p>
        <p className="small">Approximate position between published percentiles, capped at the 10th and 90th percentiles; {number(stat.n)} comparable homes. {categoryLabel(group)}{group==="other" ? " categories grouped together" : ""}.</p>
        <table><caption>Appraisal-based centres per sq ft</caption><thead><tr>{[10,25,50,75,90].map(p=><th key={p} scope="col">{p}th</th>)}</tr></thead><tbody><tr>{[stat.p10,stat.p25,stat.p50,stat.p75,stat.p90].map((n,i)=><td key={i}>{currency(n)}</td>)}</tr></tbody></table>
        <p className="home-source small">{source}, {home.value_year} appraisals · FHFA as of {dateLabel(range?.hpi.as_of)} · {range?.study_year} Comptroller study. {range?.hood_stats_note}</p>
      </div>)}
    </section>
    <section><h3>The area</h3><p>{home.block_group ? areaName || `Block group ${home.block_group}` : "Area name not available"}</p>
      {location ? <button onClick={()=>onShowMap(home)}>Show on map</button> : <p>No map location yet for this home (Travis condos are not yet placed)</p>}
    </section>
    <p className="home-source small">Sources: {source}, {home.value_year} appraisal, export {dateLabel(home.certified)}.{location ? ` StratMap (location), acquired ${dateLabel(county?.parcel_as_of?.[0])}.` : ""}{shown && result.mid!=null ? ` FHFA, ${dateLabel(range?.hpi.as_of)}; ${range?.study}, ${range?.study_year}.` : ""}</p>
    <a className="home-share" href={homeLink(home.id)}>Link to this home</a>
  </article>;
}
