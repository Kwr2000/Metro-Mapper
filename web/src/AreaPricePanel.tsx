import {useMemo,useState} from "react";
import type {AreaScore} from "./score";
import {comparePrices,priceList,PRICE_CLASSES,PRICE_COLOURS,PRICE_MEANING,PRICE_NOTE,type AreaPrice} from "./area-price";

const number=(n:number|null)=>n==null?"Not available":n.toLocaleString("en-US",{maximumFractionDigits:2});
export function PriceLegend({scores,prices,weights}:{scores:AreaScore|null;prices:AreaPrice|null;weights:number[]}){
 const comparison=useMemo(()=>comparePrices(scores,prices,weights),[scores,prices,weights]);
 return <div className="score-legend" aria-label="Score vs price legend"><p>Split at three-county medians: score {number(comparison.scoreMedian)}; price per sq ft {comparison.priceMedian==null?"Not available":"$"+number(comparison.priceMedian)}. Ties belong to the higher side. Only areas with both values set the splits.</p>
  <ul>{PRICE_CLASSES.map((label,i)=><li key={label}><span style={{background:PRICE_COLOURS[i]}}/>{label}</li>)}<li><span style={{background:"#bdbdbd"}}/>Not available</li></ul>
  <p>{PRICE_MEANING}</p><p>Lighter fill: partial score.</p>{prices&&<p className="small">{prices.as_of} · {prices.method}</p>}
  {(scores?.test_data||prices?.test_data)&&<p className="badge">Test data</p>}</div>;
}
export function AreasList({scores,prices,weights,names,links,onFly,maxPrice,onMaxChange}:{scores:AreaScore|null;prices:AreaPrice|null;weights:number[];names:Record<string,string>;links:Record<string,string>;onFly:(id:string)=>void;maxPrice?:number|null;onMaxChange?:(value:number)=>void}){
 const comparison=useMemo(()=>comparePrices(scores,prices,weights),[scores,prices,weights]);
 const [chosen,setChosen]=useState<number|null>(null);
 const desired=maxPrice===undefined?chosen:maxPrice;
 const max=comparison.max==null?null:Math.max(comparison.min!,Math.min(desired??comparison.max,comparison.max));
 const rows=useMemo(()=>priceList(comparison,max),[comparison,max]);
 return <section className="areas-price-list" aria-label="Areas list"><h3>Areas list</h3>
  <label>Max $ per sq ft <output>{max==null?"Not available":"$"+number(max)}</output><input aria-label="Max $ per sq ft" type="range" disabled={max==null||comparison.min===comparison.max} min={comparison.min??0} max={comparison.max??0} step="1" value={max??0} onChange={e=>{const n=Number(e.target.value);if(onMaxChange)onMaxChange(n);else setChosen(n);}}/></label>
  <p role="status">{rows.length.toLocaleString()} areas under the price limit with an available score.</p><p>{PRICE_NOTE}</p><p className="small">{PRICE_MEANING}</p>
  <table><caption>Areas by score, highest first</caption><thead><tr><th>Area</th><th>Score (your weights)</th><th>Median $ per sq ft</th><th>Homes</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><th><a href={links[r.id]??"#/"} onClick={e=>{e.preventDefault();onFly(r.id);}}>{names[r.id]??r.id}</a><small>{r.id}</small></th><td>{number(r.score)}{r.partial?" · Partial":""}</td><td>${number(r.price)}</td><td>{r.n.toLocaleString()}</td></tr>)}</tbody></table>
  {!rows.length&&<p>No areas meet these settings. Areas without a score or sufficient measured homes stay unavailable.</p>}
  {(scores?.test_data||prices?.test_data)&&<p className="badge">Test data</p>}{prices&&<p className="small">{prices.as_of} · {prices.method}</p>}
  {scores&&<details><summary>Score sources and dates</summary>{scores.factors.map(f=><p key={f.id}>{f.label}: {f.source} · {f.as_of}. {f.note}</p>)}</details>}
 </section>;
}
