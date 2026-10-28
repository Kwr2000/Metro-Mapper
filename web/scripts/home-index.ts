import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { idBucket } from "../src/homes/id";

/** A web-build asset derived solely from the site's existing address publications. */
export function buildHomeLocators(publicDir="public"):number {
  const folder=join(publicDir,"data/homes"),addr=join(folder,"addr");
  if(!existsSync(addr) || !existsSync(join(folder,"meta.json")))return 0;
  const buckets=new Map<string,Record<string,string>>(),seen=new Set<string>();
  for(const file of readdirSync(addr).sort()){
    if(!/^[A-Z0-9]{2}(?:-[A-Z0-9])?\.json$/.test(file))continue;
    const doc=JSON.parse(readFileSync(join(addr,file),"utf8")),index=doc.fields.indexOf("id");
    if(index<0)throw new Error("Home publication has no ID column");
    for(const row of doc.rows){
      const id=row[index];if(typeof id!=="string" || !/^(48453|48491|48209):[A-Za-z0-9]+$/.test(id) || seen.has(id))throw new Error("Invalid or duplicate home ID");
      seen.add(id);const key=idBucket(id),bucket=buckets.get(key)??{};bucket[id]=file.slice(0,-5);buckets.set(key,bucket);
    }
  }
  const target=join(folder,"ids");rmSync(target,{recursive:true,force:true});mkdirSync(target,{recursive:true});
  for(const [key,rows] of buckets){
    const text=JSON.stringify({v:1,rows:Object.fromEntries(Object.entries(rows).sort(([a],[b])=>a.localeCompare(b)))})+"\n";
    if(Buffer.byteLength(text)>2_000_000)throw new Error("Home locator bucket exceeds its size limit");
    writeFileSync(join(target,key+".json"),text);
  }
  return seen.size;
}
