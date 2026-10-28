import { loadJSON } from "../registry";
import {validateCalibration,type Calibration} from "./range";
import { idBucket } from "./id";
import { matches, normalizeQuery, shardId, shardThird } from "./address";

export type Home = { id:string; number:string|null; street_key:string|null; unit:string|null; zip:string|null; situs:string|null; city:string|null; county:string; category:string;
  lon:number|null; lat:number|null; block_group:string|null; hood_cd:string|null; living_area:number|null; year_built:number|null; land_acres:number|null; floors:number|null;
  market_value:number|null; land_value:number|null; improvement_value:number|null; value_year:number|null; certified:string|null; placed:string|null; range_pct:number|null; range_flags:string|null; test_data?:boolean };
export type RangeMeta = { published:boolean; test_data:boolean; label:string; method:string; study:string; study_year:number; levels:Record<string,number>; within_10pct:Record<string,number>;
  hpi:{factor:number;base_quarters:string[];base_index:number;latest_quarter:string;latest_index:number;as_of:string;source:string};
  calibration?:{used:boolean;fit_year:number;test_year:number;test_data:boolean;method:string};
  flags:Record<string,string>; year_over_year_note:string; size_note?:string; hood_stats_note?:string };
export type HomeMeta = { v:number; test_data:boolean; counties:Record<string,{source:string;test_data:boolean;value_as_of:string[];certified:string[];parcel_as_of:string[]}>;
  sources:Record<string,string>; hood_desc:Record<string,Record<string,string>>; shards:Record<string,string[]>; cells:string[]; value_range?:RangeMeta };
export type HoodStat = {county:string;hood_cd:string;category:string;n:number;p10:number;p25:number;p50:number;p75:number;p90:number};
export type HoodData = {test_data:boolean;rows:HoodStat[]};
export type GridRow = [string,number,number,string];
export const validHomeId = (id: string) => /^(48453|48491|48209):[A-Za-z0-9]+$/.test(id);
export const homeLink = (id: string) => "#/home?id="+encodeURIComponent(id);
const validShard = (id:string) => /^[A-Z0-9]{2}(?:-[A-Z0-9])?$/.test(id);
const validCell = (id:string) => /^-?\d+_-?\d+$/.test(id);

/** Bounded LRU, including in-flight requests; errors are retryable. */
class Cache<T> {
  private values = new Map<string,Promise<T>>();
  constructor(readonly limit:number) {}
  load(key:string,fetcher:()=>Promise<T>):Promise<T> {
    const previous=this.values.get(key); if (previous) { this.values.delete(key);this.values.set(key,previous);return previous; }
    const pending=fetcher().catch(error => { if (this.values.get(key)===pending) this.values.delete(key);throw error; });
    this.values.set(key,pending);while(this.values.size>this.limit)this.values.delete(this.values.keys().next().value!);return pending;
  }
  get size(){return this.values.size;}
}
export function cellId(lon:number,lat:number){return `${Math.floor(lon/.01)}_${Math.floor(lat/.01)}`;}
export function neighbourCells(lon:number,lat:number):string[]{
  const x=Math.floor(lon/.01),y=Math.floor(lat/.01);return [-1,0,1].flatMap(dx=>[-1,0,1].map(dy=>`${x+dx}_${y+dy}`));
}
export function nearest(rows:GridRow[],lon:number,lat:number,maxMetres=30):GridRow|null {
  const rad=(n:number)=>n*Math.PI/180;
  return rows.map(row=>({row,d:6371008.8*Math.hypot(rad(row[1]-lon)*Math.cos(rad((row[2]+lat)/2)),rad(row[2]-lat))}))
    .filter(x=>x.d<=maxMetres).sort((a,b)=>a.d-b.d || a.row[0].localeCompare(b.row[0]))[0]?.row ?? null;
}
export class HomeData {
  private metaRequest?:Promise<HomeMeta>;
  private hoodRequest?:Promise<HoodData>;
  private calibrationRequest?:Promise<Calibration>;
  private shards=new Cache<Home[]>(20);
  private cells=new Cache<GridRow[]>(50);
  private locators=new Cache<Record<string,string>>(8);
  private hints=new Map<string,string>();
  get cacheSizes(){return {shards:this.shards.size,cells:this.cells.size};}
  meta():Promise<HomeMeta>{
    if(!this.metaRequest)this.metaRequest=loadJSON<HomeMeta>("data/homes/meta.json").then(meta=>{
      if(meta.v!==1 || !meta.shards || !meta.counties || !Array.isArray(meta.cells))throw new Error("Home data is unavailable");
      return meta;
    }).catch(e=>{this.metaRequest=undefined;throw e;});
    return this.metaRequest;
  }
  hoods():Promise<HoodData>{
    if(!this.hoodRequest)this.hoodRequest=loadJSON<HoodData>("data/homes/hoods.json").then(data=>{
      if(!Array.isArray(data.rows))throw new Error("Neighbourhood table is unavailable");return data;
    }).catch(e=>{this.hoodRequest=undefined;throw e;});return this.hoodRequest;
  }
  calibration():Promise<Calibration>{
    if(!this.calibrationRequest)this.calibrationRequest=loadJSON<unknown>("data/homes/calibration.json").then(validateCalibration).catch(e=>{this.calibrationRequest=undefined;throw e;});
    return this.calibrationRequest;
  }
  remember(home:Home,shard:string){
    if(!validHomeId(home.id)||!validShard(shard))return;
    this.hints.delete(home.id);this.hints.set(home.id,shard);
    while(this.hints.size>200)this.hints.delete(this.hints.keys().next().value!);
  }

  async shard(id:string):Promise<Home[]>{
    const meta=await this.meta();if(!validShard(id)||!Object.values(meta.shards).some(files=>files.includes(id)))return [];
    return this.shards.load(id,async()=>{
      let response:Response;
      response=await fetch(import.meta.env.BASE_URL+`data/homes/addr/${id}.json`);
      if(response.status===404)return [];if(!response.ok)throw new Error("Address records could not load. Try again.");
      const doc=await response.json() as {v:number;fields:string[];rows:unknown[][];test_data:boolean};
      if(doc.v!==1||!Array.isArray(doc.fields)||!Array.isArray(doc.rows)||!doc.fields.includes("id"))throw new Error("Invalid address records");
      return doc.rows.map(row=>({...Object.fromEntries(doc.fields.map((field,i)=>[field,row[i] ?? null])),test_data:doc.test_data}) as Home)
        .filter(home=>typeof home.id==="string"&&validHomeId(home.id));
    });
  }
  async search(text:string):Promise<Home[]>{
    const query=normalizeQuery(text),base=shardId(query.street_key),meta=await this.meta();
    const files=meta.shards[base]??[],file=files.length===1 && files[0]===base ? base : base+"-"+shardThird(query.street_key);
    if(!query.number || !files.includes(file))return [];
    return (await this.shard(file)).filter(home=>matches(home,query)).map(home=>{this.remember(home,file);return home;});
  }
  async byId(id:string,signal?:AbortSignal):Promise<Home|null>{
    if(!validHomeId(id))return null;
    const meta=await this.meta(),files=Object.values(meta.shards).flat().filter(validShard);
    if(signal?.aborted)throw new DOMException("Search cancelled","AbortError");
    let file=this.hints.get(id);
    if(!file){
      const bucket=idBucket(id);
      const locator=await this.locators.load(bucket,async()=>{
        const response=await fetch(import.meta.env.BASE_URL+`data/homes/ids/${bucket}.json`);
        if(response.status===404)return {};if(!response.ok)throw new Error("Home link could not load");
        const doc=await response.json() as {v:number;rows:Record<string,string>};
        if(doc.v!==1 || !doc.rows || typeof doc.rows!=="object" || Array.isArray(doc.rows))throw new Error("Invalid home locator");return doc.rows;
      });
      file=locator[id];
    }
    if(signal?.aborted)throw new DOMException("Search cancelled","AbortError");
    if(typeof file!=="string" || !files.includes(file))return null;
    const home=(await this.shard(file)).find(home=>home.id===id)??null;
    if(signal?.aborted)throw new DOMException("Search cancelled","AbortError");
    if(home)this.remember(home,file);return home;
  }

  async cell(id:string):Promise<GridRow[]>{
    const meta=await this.meta();if(!validCell(id)||!meta.cells.includes(id))return [];
    return this.cells.load(id,async()=>{
      const response=await fetch(import.meta.env.BASE_URL+`data/homes/grid/${id}.json`);
      if(response.status===404)return [];if(!response.ok)throw new Error("Map locations could not load");
      const doc=await response.json() as {rows:GridRow[]};if(!Array.isArray(doc.rows))throw new Error("Invalid map grid");
      return doc.rows.filter(row=>validHomeId(row[0])&&Number.isFinite(row[1])&&Number.isFinite(row[2])&&validShard(row[3]));
    });
  }
  async atPoint(lon:number,lat:number):Promise<Home|null>{
    const rows=(await Promise.all(neighbourCells(lon,lat).map(cell=>this.cell(cell)))).flat(),hit=nearest(rows,lon,lat);
    if(!hit)return null;const home=(await this.shard(hit[3])).find(home=>home.id===hit[0])??null;if(home)this.remember(home,hit[3]);return home;
  }
}
export const homeData = new HomeData();
