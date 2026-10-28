import { afterEach,beforeEach,expect,it,vi } from "vitest";
import { HomeData, neighbourCells,nearest,cellId,homeLink } from "../homes/data";
import { idBucket } from "../homes/id";
import { home,meta,shard } from "./homes-fixtures";
beforeEach(()=>{localStorage.clear();});afterEach(()=>vi.unstubAllGlobals());
function serve(overrides:Record<string,unknown>={}){
 const files:Record<string,unknown>={"meta.json":meta,"addr/TE.json":shard(),...overrides};
 const mock=vi.fn(async(url:unknown)=>{const key=String(url).split("data/homes/")[1];return key in files?new Response(JSON.stringify(files[key]),{status:200}):new Response("",{status:404});});vi.stubGlobal("fetch",mock);return mock;
}
it("loads meta once and one exact shard for an address, with retry-safe missing files",async()=>{
 const fetcher=serve();const data=new HomeData();expect(await data.search("100 Test Street #2, Round Rock TX 78664")).toHaveLength(1);
 await data.search("100 Test St");expect(fetcher.mock.calls.filter(([url])=>String(url).endsWith("meta.json"))).toHaveLength(1);expect(fetcher.mock.calls.filter(([url])=>String(url).includes("addr/"))).toHaveLength(1);
 expect(await data.search("100 Unknown Ln")).toEqual([]);
 serve({"addr/TE.json":undefined});const empty=new HomeData();vi.stubGlobal("fetch",vi.fn(async(url:unknown)=>String(url).endsWith("meta.json")?new Response(JSON.stringify(meta)):new Response("",{status:404})));expect(await empty.search("100 Test St")).toEqual([]);
});
it("resolves split shards and a fresh id-only link without sharing private state",async()=>{
 const fetcher=serve({"meta.json":{...meta,shards:{TE:["TE-S","TE-N"]}},"addr/TE-S.json":shard(),"addr/TE-N.json":shard([]),[`ids/${idBucket(home.id)}.json`]:{v:1,rows:{[home.id]:"TE-S"}}});
 const data=new HomeData();expect((await data.search("100 Test St #2"))[0].id).toBe(home.id);
 expect(fetcher.mock.calls.filter(([url])=>String(url).includes("addr/"))).toHaveLength(1);
 const newer=new HomeData();expect((await newer.byId(home.id))?.id).toBe(home.id);expect(homeLink(home.id)).toBe("#/home?id=48491%3AR123");
 localStorage.clear();const fresh=new HomeData();expect((await fresh.byId(home.id))?.id).toBe(home.id);
 expect(await fresh.byId("../../secret")).toBeNull();
});
it("bounds caches to 20 shards and 50 cells even while requests are in flight",async()=>{
 const names=Array.from({length:25},(_,i)=>`A${String.fromCharCode(65+i)}`),cells=Array.from({length:55},(_,i)=>`${i}_3000`);
 const fetcher=serve({"meta.json":{...meta,shards:Object.fromEntries(names.map(n=>[n,[n]])),cells}});
 fetcher.mockImplementation(async(url:unknown)=>new Response(JSON.stringify(String(url).endsWith("meta.json")?{...meta,shards:Object.fromEntries(names.map(n=>[n,[n]])),cells}:String(url).includes("addr/")?shard():{rows:[]})));
 const data=new HomeData();await Promise.all(names.map(n=>data.shard(n)));await Promise.all(cells.map(c=>data.cell(c)));expect(data.cacheSizes).toEqual({shards:20,cells:50});
 await data.shard(names[0]);expect(data.cacheSizes.shards).toBe(20);
});
it("loads at most nine neighbour cells then the chosen shard, including a cell edge",async()=>{
 const point:[number,number]=[-97.700001,30.300001],near:[string,number,number,string]=[home.id,-97.699999,30.299999,"TE"];
 const cells=neighbourCells(...point),files:Record<string,unknown>={"meta.json":{...meta,cells}};
 for(const cell of cells)files[`grid/${cell}.json`]={rows:cell===cellId(near[1],near[2])?[near]:[]};const fetcher=serve(files);
 const found=await new HomeData().atPoint(...point);expect(found?.id).toBe(home.id);
 expect(fetcher.mock.calls.filter(([url])=>String(url).includes("grid/"))).toHaveLength(9);expect(fetcher.mock.calls.filter(([url])=>String(url).includes("addr/"))).toHaveLength(1);
 expect(nearest([[home.id,-97.69,30.3,"TE"]],...point)).toBeNull();
});
it("cancels an id lookup when the user starts another lookup",async()=>{
 serve();const controller=new AbortController();controller.abort();await expect(new HomeData().byId(home.id,controller.signal)).rejects.toThrow(/cancelled/);
});
