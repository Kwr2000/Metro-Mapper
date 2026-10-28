import type {FeatureCollection} from "geojson";
import {polygonContains,polygonFeatures} from "../map-polygons";
import {matches,normalizeQuery,shardId,shardThird,type Address} from "../homes/address";
import {homeData,type Home,type HomeMeta,type HoodData} from "../homes/data";
import {valueRange,calibrationFactor,adjustmentText,type Calibration} from "../homes/range";
import {percentilePosition,flagLabels,reasons} from "../homes/HomeCard";
import {pause,type Listing} from "./parse";

export type Metrics={low:number|null;mid:number|null;high:number|null;position:number|null;psf:number|null;percentile:number|null;n:number|null;rangePct:number|null;flags:string;areaWarning:boolean;testData:boolean};
export type BatchRow={listing:Listing;normalized:Address;home:Home|null;candidates:Home[];reason:string|null;metrics:Metrics|null};
export type BatchResult={rows:BatchRow[];meta:HomeMeta;hoods:HoodData|null;hoodError:boolean;calibration?:Calibration|null};
export const published=(meta:HomeMeta)=>meta.value_range?.published===true;
export function position(price:number,range:{low:number;mid:number;high:number}):number {
  return (price<range.low?price-range.low:price>range.high?price-range.high:0)/range.mid*100;
}
export function positionLabel(value:number|null):string {
  if(value==null)return "Not available";if(value===0)return "Inside the range";
  const n=Math.abs(value);return `${n<.1?"<0.1":n.toFixed(1)}% ${value<0?"below":"above"} the range`;
}
export function analyse(listing:Listing,home:Home,meta:HomeMeta,hoods:HoodData|null,calibration:Calibration|null=null):Metrics {
  let endpoints:{low:number|null;mid:number|null;high:number|null}={low:null,mid:null,high:null};
  const range=meta.value_range,k=range?.calibration?.used?calibrationFactor(home,calibration):1;
  if(published(meta) && range && (!range.calibration?.used||calibration) && home.range_pct!=null)try{endpoints=valueRange(home.market_value,home.id.split(":")[0],home.range_pct,range.hpi.factor,range.levels,k);}catch{/* Unusable inputs never expose a range. */}
  const psf=listing.price!=null && home.living_area!=null && home.living_area>0?listing.price/home.living_area:null;
  const category=["single_family","condo"].includes(home.category)?home.category:"other";
  const stat=hoods?.rows.find(s=>s.county===home.county && s.hood_cd===home.hood_cd && s.category===category);
  const flags=(home.range_flags??"").split(",").filter(Boolean).map(code=>code==="cal"&&calibration?adjustmentText(k,calibration.fit_year):flagLabels[code]??reasons[code]??range?.flags[code]??code).join("; ");
  return {...endpoints,position:listing.price!=null && endpoints.low!=null && endpoints.mid!=null && endpoints.mid>0 && endpoints.high!=null?position(listing.price,{low:endpoints.low,mid:endpoints.mid,high:endpoints.high}):null,
    psf,percentile:psf!=null && stat?percentilePosition(psf,stat):null,n:psf!=null && stat?stat.n:null,
    rangePct:published(meta)?home.range_pct:null,flags:published(meta)?flags:"",areaWarning:listing.sqft!=null && home.living_area!=null && home.living_area>0 && Math.abs(listing.sqft-home.living_area)*10>home.living_area,
    testData:!!(meta.test_data || meta.counties[home.county]?.test_data || home.test_data || hoods?.test_data || published(meta)&&(range?.test_data||calibration?.test_data))};
}
export function chooseMatch(row:BatchRow,id:string,meta:HomeMeta,hoods:HoodData|null,calibration:Calibration|null=null):BatchRow {
  const home=row.candidates.find(h=>h.id===id && matches(h,row.normalized));if(!home)return row;
  const listing={...row.listing,selectedId:id};return {...row,listing,home,reason:null,metrics:analyse(listing,home,meta,hoods,calibration)};
}
const aborted=(signal?:AbortSignal)=>{if(signal?.aborted)throw new DOMException("Cancelled","AbortError");};
type Loader=Pick<typeof homeData,"meta"|"search"|"hoods"|"calibration">;
export async function processListings(listings:Listing[],options:{loader?:Loader;signal?:AbortSignal;onProgress?:(done:number,total:number)=>void;loadBounds?:()=>Promise<FeatureCollection|null>}={}):Promise<BatchResult>{
  const loader=options.loader??homeData;aborted(options.signal);
  const [meta,hoods]=await Promise.all([loader.meta(),loader.hoods().catch(()=>null)]);aborted(options.signal);
  const calibration=published(meta)&&meta.value_range?.calibration?.used?await loader.calibration():null;aborted(options.signal);
  const rows:BatchRow[]=listings.map(listing=>({listing,normalized:normalizeQuery(listing.query),home:null,candidates:[],reason:null,metrics:null}));
  const groups=new Map<string,BatchRow[]>();let done=0;let bounds:Promise<FeatureCollection|null>|undefined;
  for(const row of rows){
    const base=shardId(row.normalized.street_key),files=meta.shards[base]??[],key=files.length===1&&files[0]===base?base:base+"-"+shardThird(row.normalized.street_key);
    const group=groups.get(key)??[];group.push(row);groups.set(key,group);
  }
  const queue=[...groups.values()];
  async function worker(){
    while(queue.length){
      const group=queue.shift()!;
      for(const row of group){
        aborted(options.signal);const l=row.listing;
        if(l.issue)row.reason=l.issue;
        else if(l.price==null || l.price<=0)row.reason="No asking price";
        else if(l.state && !["TX","TEXAS"].includes(l.state.trim().toUpperCase()))row.reason="Outside the three counties (state is not Texas)";
        else if(!row.normalized.number || !row.normalized.street_key)row.reason="Not found: enter a street address with a house number";
        else {
          try {
            row.candidates=(await loader.search(l.query)).filter(h=>matches(h,row.normalized));aborted(options.signal);
            const selected=row.candidates.find(h=>h.id===l.selectedId);
            row.home=selected??(row.candidates.length===1?row.candidates[0]:null);
            if(row.home){row.metrics=analyse(l,row.home,meta,hoods,calibration);}
            else if(row.candidates.length>1)row.reason="Several matches — pick one";
            else {
              row.reason="Not found in the 2026 appraisal records";
              if(l.lat!=null && l.lon!=null && options.loadBounds){
                bounds??=options.loadBounds().catch(()=>null);const doc=await bounds;aborted(options.signal);
                if(doc && !polygonFeatures(doc).some(f=>polygonContains([l.lon!,l.lat!],f.geometry)))row.reason="Outside the three counties (listing coordinates)";
              }
            }
          }catch(error){if(options.signal?.aborted)throw error;row.reason="Home records could not load. Try this import again.";}
        }
        done++;options.onProgress?.(done,listings.length);await pause();
      }
    }
  }
  await Promise.all(Array.from({length:Math.min(4,queue.length)},worker));aborted(options.signal);
  return {rows,meta,hoods,hoodError:hoods===null,calibration};
}

export type SortKey="default"|"beds"|"baths"|"sqft"|"living_area"|"year_built"|"price"|"psf"|"low"|"high"|"position"|"rangePct"|"percentile"|"n"|"days"|"hoa";
export const SORT_LABELS:Record<SortKey,string>={default:"Default order",beds:"Beds",baths:"Baths",sqft:"Listing sq ft",living_area:"Appraisal sq ft",year_built:"Year built",price:"Asking price",psf:"Asking $ per sq ft",low:"Range low",high:"Range high",position:"Position",rangePct:"Range width",percentile:"Neighbourhood percentile",n:"Neighbourhood homes",days:"Days on market",hoa:"HOA per month"};
export function numericValue(row:BatchRow,key:SortKey):number|null {
  if(["beds","baths","sqft","price","days","hoa"].includes(key))return row.listing[key as "beds"];
  if(key==="living_area"||key==="year_built")return row.home?.[key]??null;
  return row.metrics?.[key as keyof Metrics] as number|null ?? null;
}
export function tableRows(rows:BatchRow[],filters:{county:string;category:string;hasRange:boolean},sort:SortKey="default",descending=false,showRange=true):BatchRow[]{
  const selected=rows.filter(r=>r.home && (!filters.county||r.home.county===filters.county) && (!filters.category||r.home.category===filters.category) && (!filters.hasRange||!showRange||r.metrics?.mid!=null));
  const compare=(a:number|null,b:number|null,reverse=false)=>a==null?(b==null?0:1):b==null?-1:(a-b)*(reverse?-1:1);
  const key=!showRange && ["low","high","position","rangePct"].includes(sort)?"percentile":sort;
  return selected.sort((a,b)=>key==="default"?(showRange?compare(a.metrics?.position??null,b.metrics?.position??null):0)||compare(a.metrics?.percentile??null,b.metrics?.percentile??null)||Number(a.listing.key)-Number(b.listing.key):compare(numericValue(a,key),numericValue(b,key),descending)||Number(a.listing.key)-Number(b.listing.key));
}
