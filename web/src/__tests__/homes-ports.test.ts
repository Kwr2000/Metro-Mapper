import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect,it } from "vitest";
import type { Address } from "../homes/address";
import { matches, normalizeQuery, normalizeStreet, shardId, shardThird } from "../homes/address";
import { valueRange } from "../homes/range";
type AddressCase={id:string;query:string;expected:Address;cad?:{situs_prefix?:string|null;situs_street?:string|null;situs_suffix?:string|null}};
type RangeCase={id:string;home:{county:string;market_value:number|null};factor:number;expected:{range_pct:number|null;low:number|null;mid:number|null;high:number|null}};
const cases=<T,>(file:string):T[]=>JSON.parse(readFileSync(join(__dirname,"../../../pipeline/mm/data",file),"utf8")).cases;
const addresses=cases<AddressCase>("address_cases.json"), ranges=cases<RangeCase>("value_range_cases.json");
it.each(addresses)("shared address $id",c=>{
 const query=normalizeQuery(c.query);expect(query).toEqual(c.expected);expect(matches(c.expected,query)).toBe(true);
 if(c.cad)expect(normalizeStreet(c.cad.situs_prefix,c.cad.situs_street,c.cad.situs_suffix)).toBe(c.expected.street_key);
 expect(matches({...c.expected,number:"different"},query)).toBe(false);
});
it.each(ranges)("shared range $id",c=>{
 const fips=({Travis:"48453",Williamson:"48491",Hays:"48209"} as Record<string,string>)[c.home.county];
 const result=valueRange(c.home.market_value,fips,c.expected.range_pct,c.factor,{"48453":1,"48491":.96,"48209":1});
 expect(result).toEqual({low:c.expected.low,mid:c.expected.mid,high:c.expected.high});
});
it("reads every shared vector and uses the exact shard and optional match contracts",()=>{
 expect(addresses.length).toBeGreaterThanOrEqual(60);expect(ranges.length).toBeGreaterThanOrEqual(30);
 expect(shardId("N LAMAR BLVD")).toBe("LA");expect(shardId("FM 1626")).toBe("FM");expect(shardId("S A ST E")).toBe("A0");expect(shardId("")).toBe("00");expect(shardThird("N LAMAR BLVD")).toBe("M");
 const row={number:"100",street_key:"TEST ST",unit:"2",zip:"78664"};
 expect(matches(row,{...row,unit:"",zip:""})).toBe(true);expect(matches(row,{...row,unit:"3"})).toBe(false);
 expect(()=>valueRange(100,"48453",15,1,{"48453":1})).toThrow();
});
