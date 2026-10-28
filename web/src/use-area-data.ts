/** Dedicated static publications, shared by map and batch. No layer/People data access. */
import {useEffect,useState} from "react";
import {validateScore,type AreaScore} from "./score";
import {validatePrice,type AreaPrice} from "./area-price";
import {readScorePreferences} from "./store";

let scoreRequest:Promise<AreaScore>|undefined,priceRequest:Promise<AreaPrice>|undefined;
async function read(path:string){const r=await fetch(import.meta.env.BASE_URL+path,{cache:"no-store"});if(!r.ok)throw new Error("Publication unavailable");return r.json();}
function score(){return scoreRequest??=(read("data/area_score.json").then(validateScore).catch(e=>{scoreRequest=undefined;throw e;}));}
function price(){return priceRequest??=(read("data/area_price.json").then(validatePrice).catch(e=>{priceRequest=undefined;throw e;}));}
export function useAreaData(){
 const [data,setData]=useState<{score:AreaScore|null;price:AreaPrice|null;scoreError:string;priceError:string}>({score:null,price:null,scoreError:"",priceError:""});
 useEffect(()=>{let cancelled=false;
  score().then(s=>{if(!cancelled)setData(d=>({...d,score:s}));},()=>{if(!cancelled)setData(d=>({...d,scoreError:"Score data is unavailable. Reload to retry."}));});
  price().then(p=>{if(!cancelled)setData(d=>({...d,price:p}));},()=>{if(!cancelled)setData(d=>({...d,priceError:"Area prices are unavailable. Reload to retry."}));});
  return()=>{cancelled=true;};
 },[]);return data;
}
export function useScoreWeights(){
 const [weights,setWeights]=useState(()=>readScorePreferences().weights);
 useEffect(()=>{const update=()=>setWeights(readScorePreferences().weights);window.addEventListener("metro-mapper:score-change",update);window.addEventListener("storage",update);return()=>{window.removeEventListener("metro-mapper:score-change",update);window.removeEventListener("storage",update);};},[]);
 return weights;
}
