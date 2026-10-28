// Browser-only conveniences (AGENTS.md: personal state lives only in the browser).
import { cleanScorePreferences, DEFAULT_SCORE, type ScorePreferences } from "./score";

import {blankListing,listingURL,type Listing} from "./batch/parse";
import {validHomeId} from "./homes/data";
// localStorage can be missing or throw (private windows, blocked storage); every
// read and write is guarded, and the site works without it.
const PREFIX = "metro-mapper:";
const session = new Map<string, unknown>();
const pending = new Set<string>();

export function readLocal<T>(key: string, fallback: T): T {
  if (pending.has(key)) return session.get(key) as T;
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return (session.has(key) ? session.get(key) : fallback) as T;
  }
}

export function writeLocal(key: string, value: unknown): boolean {
  session.set(key, value);
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
    pending.delete(key);
    return true;
  } catch { pending.add(key); return false; }
}

export function storageAvailable(): boolean {
  try { window.localStorage.setItem(PREFIX + "check", "1"); window.localStorage.removeItem(PREFIX + "check"); return true; }
  catch { return false; }
}
export type SavedArea = { id: string; name: string; note: string };
export function readShortlist(): SavedArea[] {
  const value = readLocal<unknown>("shortlist", []);
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is SavedArea => v && /^\d{12}$/.test(v.id) && typeof v.name === "string" && typeof v.note === "string");
}

/** Asking prices never enter view state, query strings, fetch URLs or shared links. */
export function readAskingPrice(id: string): string {
  const value=readLocal<unknown>("asking:"+id,"");
  return typeof value==="string" && /^\d*(?:\.\d{0,2})?$/.test(value) ? value : "";
}
export function writeAskingPrice(id: string, value: string): boolean {
  return writeLocal("asking:"+id,/^\d*(?:\.\d{0,2})?$/.test(value) ? value : "");
}

export function readScorePreferences():ScorePreferences {return cleanScorePreferences(readLocal("area-score",null)) ?? {...DEFAULT_SCORE,weights:[...DEFAULT_SCORE.weights]};}
export function writeScorePreferences(value:ScorePreferences):boolean {const saved=writeLocal("area-score",cleanScorePreferences(value) ?? DEFAULT_SCORE);window.dispatchEvent(new Event("metro-mapper:score-change"));return saved;}

export type SavedBatch={name:string;rows:Listing[]};
const BATCH="batch-list:";
function batchKeys():string[]{
  const keys=new Set([...session.keys()].filter(k=>k.startsWith(BATCH)));
  try {for(let i=0;i<window.localStorage.length;i++){const key=window.localStorage.key(i);if(key?.startsWith(PREFIX+BATCH))keys.add(key.slice(PREFIX.length));}}catch{/* Session fallback only. */}
  return [...keys];
}
function cleanBatch(value:unknown):SavedBatch|null {
  if(!value || typeof value!=="object")return null;const v=value as SavedBatch;
  if(typeof v.name!=="string" || !v.name.trim() || v.name.length>80 || !Array.isArray(v.rows) || !v.rows.length || v.rows.length>400)return null;
  const rows:Listing[]=[];
  for(let i=0;i<v.rows.length;i++){
    const source=v.rows[i];if(!source || typeof source.query!=="string" || source.query.length>2000)return null;
    const row=blankListing(source.query,String(i));
    for(const key of ["state","status","propertyType","issue"] as const)if(typeof source[key]==="string")row[key]=source[key].slice(0,500);
    for(const key of ["price","beds","baths","sqft","lot","year","days","hoa","lat","lon"] as const){const n=source[key];row[key]=typeof n==="number"&&Number.isFinite(n)?n:null;}
    row.url=typeof source.url==="string"?listingURL(source.url):null;
    if(typeof source.selectedId==="string" && validHomeId(source.selectedId))row.selectedId=source.selectedId;
    rows.push(row);
  }
  return {name:v.name.trim(),rows};
}
export function readBatchLists():SavedBatch[]{
  return batchKeys().map(key=>cleanBatch(readLocal(key,null))).filter((v):v is SavedBatch=>v!==null).sort((a,b)=>a.name.localeCompare(b.name)).slice(0,5);
}
export function saveBatchList(name:string,rows:Listing[]):boolean {
  name=name.trim();const value=cleanBatch({name,rows});if(!value)throw new Error("Use a list name of 1–80 characters and 1–400 listing rows.");
  const existing=readBatchLists();if(existing.length>=5 && !existing.some(l=>l.name===name))throw new Error("Five lists are already saved. Replace a named list or remove one first.");
  return writeLocal(BATCH+encodeURIComponent(name),value);
}
export function removeBatchList(name:string):boolean {
  const key=BATCH+encodeURIComponent(name);session.delete(key);pending.delete(key);
  try{window.localStorage.removeItem(PREFIX+key);return true;}catch{session.set(key,null);pending.add(key);return false;}
}
export function clearBatchLists():boolean {
  let persistent=true;for(const key of batchKeys()){
    session.delete(key);pending.delete(key);
    try{window.localStorage.removeItem(PREFIX+key);}catch{session.set(key,null);pending.add(key);persistent=false;}
  }return persistent;
}
