import {useState} from "react";
import {AreasList,PriceLegend} from "./AreaPricePanel";
import {pricePopup,type AreaPrice} from "./area-price";
import { areaScore, DEFAULT_WEIGHTS, FACTOR_LABELS, SCORE_CLASSES, SCORE_COLOURS, SCORE_NOTE, type AreaScore, type ScorePreferences } from "./score";
import { escapeHtml as esc } from "./popup";

export function ScoreLegend(){return <div className="score-legend" aria-label="Score legend"><p>Higher/lower score under your weights · 0–100</p>
  <ul>{SCORE_CLASSES.map((label,i)=><li key={label}><span style={{background:SCORE_COLOURS[i]}}/>{label}</li>)}<li><span style={{background:"#bdbdbd"}}/>Not available</li></ul>
  <p><span className="score-partial-swatch"/>Lighter fill: partial — some weighted factors are missing.</p></div>;}
export function ScorePanel({data,error,preferences,onChange,prices=null,priceError="",names={},links={},onFly=()=>{}}:{data:AreaScore|null;error:string;preferences:ScorePreferences;onChange:(next:ScorePreferences)=>void;prices?:AreaPrice|null;priceError?:string;names?:Record<string,string>;links?:Record<string,string>;onFly?:(id:string)=>void}){
  const [tab,setTab]=useState("Weights"),[priceLimit,setPriceLimit]=useState<number|null>(null);
  return <section className="score-panel" aria-label="Good place to live"><h2>Good place to live</h2><p className="small">Your priorities, relative to block groups in the three counties. Percentiles describe direction, not absolute quality.</p>
    {data?.test_data && <p className="badge">Test data</p>}
    <label className="score-mode"><input type="checkbox" checked={preferences.colour} onChange={e=>onChange({...preferences,colour:e.target.checked,price:false})}/>Colour by score</label>
    <label className="score-mode"><input type="checkbox" checked={preferences.price===true} onChange={e=>onChange({...preferences,price:e.target.checked,colour:false})}/>Score vs price</label>
    <div role="tablist" aria-label="Score panel tabs">{["Weights","Areas list"].map(name=><button key={name} role="tab" aria-selected={tab===name} onClick={()=>setTab(name)}>{name}</button>)}</div>
    {priceError&&<p role="status">{priceError}</p>}
    {tab==="Areas list"&&error&&<p role="status">{error}</p>}
    {tab==="Areas list"?<AreasList scores={data} prices={prices} weights={preferences.weights} names={names} links={links} onFly={onFly} maxPrice={priceLimit} onMaxChange={setPriceLimit}/>:<>
    {FACTOR_LABELS.map((label,i)=><label className="score-weight" key={label}>{label}<output>{preferences.weights[i]}</output><input aria-label={label} type="range" min="0" max="5" step="1" value={preferences.weights[i]} onChange={e=>onChange({...preferences,weights:preferences.weights.map((w,j)=>i===j?Number(e.target.value):w)})}/></label>)}
    <button onClick={()=>onChange({...preferences,weights:[...DEFAULT_WEIGHTS]})}>Reset weights</button>
    {!preferences.weights.some(w=>w>0) && <p role="status">Set at least one weight above zero to get a score.</p>}
    <p className="small">Weights stay in this browser and shared view links. Missing factors are left out; at least half your total weight must be present.</p>
    {error?<p role="status">{error}</p>:!data?<p role="status">Loading score data…</p>:<details><summary>Factor sources and dates</summary>{data.factors.map(f=><p key={f.id}><strong>{f.label}</strong>: {f.source} · {f.as_of}. {f.note}{f.test_data?" Test data.":""}</p>)}</details>}
    {preferences.price?<PriceLegend scores={data} prices={prices} weights={preferences.weights}/>:<ScoreLegend/>}<p className="small">Other polygon fills are hidden while score or score vs price colouring is on. Point markers and filters still work.</p></>}
    <p className="small score-note">{SCORE_NOTE}</p>
  </section>;
}
const rawValue=(value:number|null|undefined,unit:string)=>value==null?"Not available":unit==="minutes"&&value===-1?"More than 60 minutes":unit==="share"?`${(value*100).toFixed(1)}%`:`${value.toLocaleString("en-US",{maximumFractionDigits:2})} ${unit}`;
export function scorePopup(data:AreaScore|null|undefined,id:string,weights:number[],prices?:AreaPrice|null):string {
  const row=data?.rows[id],score=areaScore(row,weights);
  let html=`<section class="score-popup"><h3>Good place to live: ${score.value==null?"Not available":Math.round(score.value)+" / 100 (your weights)"}</h3>`;
  html+=pricePopup(prices,id);
  if(data?.test_data)html+='<p class="badge">Test data</p>';
  if(score.partial)html+='<p>Partial: some weighted factors are missing.</p>';
  if(score.value==null)html+='<p>At least half the total weight must have measured factors, and some weight must be above zero.</p>';
  if(data)html+='<details><summary>Score breakdown</summary><p>Percentiles relative to block groups in Travis, Williamson and Hays counties; higher percentiles increase the score when their weight is positive.</p><table>'+data.factors.map((f,i)=>
    `<tr><th>${esc(f.label)}</th><td>Percentile: ${row?.[i]==null?"Not available":row[i]+" / 100"} · Weight ${weights[i]}<br/>`+
    f.raw_indices.map((index,j)=>`${esc(f.measure_labels[j])}: ${esc(rawValue(row?.[index],f.units[j]))}`).join("<br/>")+`<small>Source: ${esc(f.source)} · ${esc(f.as_of)}${f.test_data?" · Test data":""}</small><small>${esc(f.note)}</small></td></tr>`).join("")+"</table></details>";
  return html+`<p class="small">${esc(SCORE_NOTE)}</p></section>`;
}
