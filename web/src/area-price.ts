/** Score/price calculations accept only the two dedicated publications. */
import type {FeatureCollection} from "geojson";
import {areaScore,type AreaScore} from "./score";

export type AreaPrice={v:1;test_data:boolean;as_of:string;method:string;rows:Record<string,[number,number]>};
export const PRICE_CLASSES=["Higher score, lower price per sq ft","Higher score, higher price per sq ft","Lower score, lower price per sq ft","Lower score, higher price per sq ft"];
export const PRICE_COLOURS=["#2166ac","#762a83","#b8860b","#d6604d"];
export const PRICE_NOTE="Prices are appraisal-based, not sale prices; a high score reflects only the factors and weights you chose.";
export const PRICE_MEANING="Price means the median appraisal-based centre per sq ft of single-family homes in the area. At least 10 located homes with a range and living area are required. Homes without a location are excluded.";
export function validatePrice(value:unknown):AreaPrice {
 const d=value as AreaPrice;
 if(!d||d.v!==1||typeof d.test_data!=="boolean"||typeof d.as_of!=="string"||typeof d.method!=="string"||!d.rows||typeof d.rows!=="object"||Array.isArray(d.rows))throw new Error("Invalid area price data");
 for(const [id,row] of Object.entries(d.rows))if(!/^\d{12}$/.test(id)||!Array.isArray(row)||row.length!==2||!Number.isInteger(row[0])||row[0]<10||!Number.isInteger(row[1])||row[1]<0)throw new Error("Invalid area price row");
 return d;
}
export const median=(values:number[])=>{const v=[...values].sort((a,b)=>a-b),n=v.length;return n?n%2?v[(n-1)/2]:(v[n/2-1]+v[n/2])/2:null;};
export type PriceRow={id:string;score:number|null;partial:boolean;price:number;n:number;percentile:number};
export type PriceComparison={rows:PriceRow[];byId:Map<string,PriceRow>;scoreMedian:number|null;priceMedian:number|null;min:number|null;max:number|null};
export function comparePrices(scores:AreaScore|null|undefined,prices:AreaPrice|null|undefined,weights:readonly number[]):PriceComparison {
 const groups=new Map<number,string[]>();
 for(const [id,[,price]] of Object.entries(prices?.rows??{})){const g=groups.get(price)??[];g.push(id);groups.set(price,g);}
 const percentiles=new Map<string,number>();let below=0;const n=Object.keys(prices?.rows??{}).length;
 for(const [price,ids] of [...groups].sort(([a],[b])=>a-b)){for(const id of ids)percentiles.set(id,100*(below+ids.length/2)/n);below+=ids.length;}
 const rows=Object.entries(prices?.rows??{}).map(([id,[n,price]])=>{const score=areaScore(scores?.rows[id],weights);return {id,score:score.value,partial:score.partial,price,n,percentile:percentiles.get(id)!};});
 const paired=rows.filter(r=>r.score!=null),values=rows.map(r=>r.price);
 return {rows,byId:new Map(rows.map(r=>[r.id,r])),scoreMedian:median(paired.map(r=>r.score!)),priceMedian:median(paired.map(r=>r.price)),min:values.length?Math.min(...values):null,max:values.length?Math.max(...values):null};
}
export function priceClass(row:PriceRow|undefined,comparison:PriceComparison):number|null {
 if(row?.score==null||comparison.scoreMedian==null||comparison.priceMedian==null)return null;
 return (row.score>=comparison.scoreMedian?0:2)+(row.price>=comparison.priceMedian?1:0);
}
export function priceList(comparison:PriceComparison,max:number|null):PriceRow[]{
 return comparison.rows.filter(r=>r.score!=null&&(max==null||r.price<=max)).sort((a,b)=>b.score!-a.score!||a.price-b.price||a.id.localeCompare(b.id));
}
export function priceFeatures(areas:FeatureCollection["features"],comparison:PriceComparison):FeatureCollection {
 return {type:"FeatureCollection",features:areas.map(f=>{const id=String(f.properties?.geoid??f.id??""),r=comparison.byId.get(id),c=priceClass(r,comparison);
  return {type:"Feature",id,geometry:f.geometry,properties:{geoid:id,score:c==null?null:r!.score,partial:r?.partial??false,score_colour:c==null?"#bdbdbd":PRICE_COLOURS[c]}};})};
}
const escape=(s:string)=>s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]!);
export function pricePopup(data:AreaPrice|null|undefined,id:string):string {
 const r=data?.rows[id];return `<p>Median appraisal-based $ per sq ft: ${r?`$${r[1].toLocaleString("en-US")} (n = ${r[0].toLocaleString("en-US")} single-family homes)`:"Not available"}</p>`+
  (data?`<small>${escape(data.as_of)} · ${escape(data.method)}${data.test_data?" · Test data":""}</small>`:"");
}
