/** Isolated score arithmetic. Reads only its dedicated publication, never layer values. */
import type { FeatureCollection } from "geojson";

export const FACTOR_IDS = ["safety","schools","flood","daily","grocery_parks","transit"] as const;
export const FACTOR_LABELS = ["Safety","Schools","Flood","Walk/bike to daily needs","Grocery and parks","Transit"];
export const DEFAULT_WEIGHTS = [3,3,3,2,2,1];
export type ScorePreferences = { weights:number[]; colour:boolean };
export const DEFAULT_SCORE:ScorePreferences = {weights:DEFAULT_WEIGHTS,colour:false};
export type ScoreFactor = { id:string;label:string;source:string;field:string[];raw_indices:number[];measure_labels:string[];units:string[];
  better:string;as_of:string;note:string;test_data:boolean };
export type AreaScore = {v:number;test_data:boolean;factors:ScoreFactor[];rows:Record<string,(number|null)[]>;percentile_note:string;method:string};
export const SCORE_NOTE = "Built only from safety, schools, flood, and access layers. Census demographics and election results are never used.";
export const SCORE_COLOURS = ["#d73027","#fc8d59","#fee08b","#a6d96a","#1a9850"];
export const SCORE_CLASSES = ["0–19","20–39","40–59","60–79","80–100"];
export function cleanScorePreferences(value:unknown):ScorePreferences|null {
  if(!value || typeof value!=="object")return null;
  const v=value as Record<string,unknown>;
  if(!Array.isArray(v.weights) || v.weights.length!==6 || !v.weights.every(w=>typeof w==="number" && Number.isInteger(w) && w>=0 && w<=5))return null;
  return {weights:[...v.weights],colour:v.colour===true};
}
export function validateScore(value:unknown):AreaScore {
  const d=value as AreaScore;
  if(!d || d.v!==1 || typeof d.test_data!=="boolean" || !Array.isArray(d.factors) || d.factors.length!==6 ||
    !d.rows || typeof d.rows!=="object" || Array.isArray(d.rows))throw new Error("Invalid area score data");
  for(let i=0;i<6;i++){
    const f=d.factors[i];
    if(f.id!==FACTOR_IDS[i] || ![f.label,f.source,f.as_of,f.note].every(s=>typeof s==="string") ||
      !Array.isArray(f.raw_indices) || !f.raw_indices.length || !f.raw_indices.every(n=>Number.isInteger(n)&&n>=6&&n<14) ||
      !Array.isArray(f.measure_labels) || !Array.isArray(f.units) || f.measure_labels.length!==f.raw_indices.length || f.units.length!==f.raw_indices.length ||
      ![...f.measure_labels,...f.units].every(s=>typeof s==="string"))throw new Error("Invalid score factor");
  }
  for(const [id,row] of Object.entries(d.rows))if(!/^\d{12}$/.test(id) || !Array.isArray(row) || row.length!==14 ||
    !row.every(v=>v===null || typeof v==="number"&&Number.isFinite(v)) || row.slice(0,6).some(v=>v!==null && (v<0 || v>100)))throw new Error("Invalid score row");
  return d;
}
export function areaScore(row:readonly (number|null)[]|undefined,weights:readonly number[]) {
  const total=weights.reduce((a,b)=>a+b,0);let present=0,sum=0;
  for(let i=0;i<6;i++)if(row?.[i]!=null){present+=weights[i];sum+=weights[i]*row[i]!;}
  const available=total>0 && present>0 && present*2>=total;
  return {value:available?sum/present:null,partial:present<total,present,total};
}
export function scoreColour(value:number|null):string {return value==null?"#bdbdbd":SCORE_COLOURS[Math.min(4,Math.floor(Math.round(value)/20))];}
export function scoreFeatures(areas:FeatureCollection["features"],data:AreaScore|null|undefined,weights:number[]):FeatureCollection {
  return {type:"FeatureCollection",features:areas.map(f=>{
    const id=String(f.properties?.geoid ?? f.id ?? ""),s=areaScore(data?.rows[id],weights);
    return {type:"Feature",id,geometry:f.geometry,properties:{geoid:id,score:s.value,partial:s.partial,score_colour:scoreColour(s.value)}};
  })};
}
