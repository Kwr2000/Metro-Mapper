import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,readdirSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {expect,it} from "vitest";
import {buildHomeLocators} from "../../scripts/home-index";
import {idBucket} from "../homes/id";
it("builds deterministic small public ID locators without copying addresses or private fields",()=>{
 const root=mkdtempSync(join(tmpdir(),"mm-home-index-"));try{
 const dir=join(root,"data/homes");mkdirSync(join(dir,"addr"),{recursive:true});writeFileSync(join(dir,"meta.json"),"{}");
 writeFileSync(join(dir,"addr/TE.json"),JSON.stringify({fields:["id","situs","asking_price"],rows:[["48491:R123","TEST ADDRESS","PRIVATE PRICE"],["48209:456","OTHER ADDRESS","ANOTHER PRICE"]]}));
 expect(buildHomeLocators(root)).toBe(2);
 const file=join(dir,"ids",idBucket("48491:R123")+".json"),before=readFileSync(file,"utf8");expect(JSON.parse(before).rows["48491:R123"]).toBe("TE");
 for(const name of readdirSync(join(dir,"ids")))expect(readFileSync(join(dir,"ids",name),"utf8")).not.toMatch(/ADDRESS|PRICE|situs|asking/);
 buildHomeLocators(root);expect(readFileSync(file,"utf8")).toBe(before);
 writeFileSync(join(dir,"addr/AB.json"),JSON.stringify({fields:["id"],rows:[["48491:R123"]]}));expect(()=>buildHomeLocators(root)).toThrow(/duplicate/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
