import {cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {ThingsToCheck,checkItems,decodeChecks} from "../homes/Checks";
import {HomeCard} from "../homes/HomeCard";
import type {ChecksMeta} from "../homes/data";
import {homeData} from "../homes/data";
import {BatchPage} from "../batch/BatchPage";
import {home,meta,hoods} from "./homes-fixtures";

const fixture=JSON.parse(readFileSync(resolve(__dirname,"../../../pipeline/tests/fixtures/home_checks.json"),"utf8")) as {meta:ChecksMeta;cases:{encoded:string;contains:string}[]};
const checks=fixture.meta as ChecksMeta,model={...meta,checks},all=fixture.cases.map(c=>c.encoded).filter(c=>!["flood02","pre1978"].includes(c)).join(",");
afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear();});
it.each(fixture.cases)("shows the sourced fact for $encoded",(c:{encoded:string;contains:string})=>{
 render(<ThingsToCheck home={{...home,year_built:c.encoded==="pre1978"?1970:1985,checks:c.encoded}} meta={model} rangeFlags="Condo"/>);
 expect(screen.getByText(c.contains,{exact:false})).toBeDefined();expect(screen.getByText(/2026-10-/)).toBeDefined();
 if(/^(flood|highway|major_road|rail)/.test(c.encoded))expect(screen.getByText(/Test data · location checks/)).toBeDefined();
});
it("round trips encoded delimiters, escapes road names, and ignores malformed/unknown cells",()=>{
 const code="highway:90:Test%2C road%3A %C3%A9";expect(decodeChecks(code)).toEqual([{code:"highway",distance:90,label:"Test, road: é"}]);
 expect(decodeChecks("unknown,highway:NaN:a,rail:-1:a,highway:90:%xx,pre1978:extra")).toEqual([]);
 const source={...home,checks:"highway:90:%3Cscript%3E"};render(<ThingsToCheck home={source} meta={model}/>);
 expect(document.querySelector("script")).toBeNull();expect(screen.getByText(/<script>/)).toBeDefined();
});
it("withholds location facts without a point or the new stored geometry and handles old publications",()=>{
 render(<ThingsToCheck home={{...home,year_built:1985,placed:null,lon:null,lat:null,checks:all}} meta={model} rangeFlags="Condo"/>);
 expect(screen.getByText("Location checks not available (no map point)")).toBeDefined();expect(screen.queryByText(/Traffic noise/)).toBeNull();expect(screen.getByText(/Built in 1985/)).toBeDefined();
 cleanup();render(<ThingsToCheck home={{...home,checks:all}} meta={{...model,checks:{...checks,sources:{...checks.sources,fema:{...checks.sources.fema,available:false},osm:{...checks.sources.osm,available:false}}}}}/>);
 expect(screen.getByText("FEMA location checks not available from the stored maps.")).toBeDefined();expect(screen.queryByText(/Traffic noise/)).toBeNull();
 cleanup();render(<ThingsToCheck home={home} meta={meta}/>);expect(screen.getByText(/not available from this publication/)).toBeDefined();
});
it("renders the card section and batch facts disclosure, retaining the listing-size warning",async()=>{
 const h={...home,checks:all};render(<HomeCard home={h} meta={model} onShowMap={()=>{}}/>);
 expect(screen.getByRole("region",{name:"Things to check"})).toBeDefined();cleanup();
 vi.spyOn(homeData,"meta").mockResolvedValue(model);vi.spyOn(homeData,"hoods").mockResolvedValue(hoods);vi.spyOn(homeData,"search").mockResolvedValue([h]);
 render(<BatchPage registry={null}/>);fireEvent.change(screen.getByRole("textbox",{name:"Addresses and asking prices"}),{target:{value:"100 TEST ST #2 78664 $560000"}});fireEvent.click(screen.getByRole("button",{name:"Check pasted listings"}));
 await screen.findByRole("heading",{name:"Listing results"});expect(screen.getByRole("columnheader",{name:"Things to check"})).toBeDefined();
 const disclosure=document.querySelector(".batch-checks")!;fireEvent.click(disclosure.querySelector("summary")!);expect(within(disclosure as HTMLElement).getByText(/About 90 m/)).toBeDefined();
});
it("extends the prohibited-copy check to the new facts, with no People or election data access",()=>{
 const h={...home,checks:all};render(<ThingsToCheck home={h} meta={model} rangeFlags="Condo"/>);
 expect(document.body.textContent).not.toMatch(/\b(fair value|good deal|overpriced|worth|bargain|undervalued|bad|avoid|deal)\b/i);
 const code=readFileSync(resolve(__dirname,"../homes/Checks.tsx"),"utf8");expect([...code.matchAll(/from ["']([^"']+)["']/g)].map(m=>m[1])).toEqual(["./data"]);
 expect(code).not.toMatch(/\.demographic\b|\.group\b|\.layers\b|\.benchmarks\b/);
 expect(readFileSync(resolve(__dirname,"../../vite.config.ts"),"utf8")).toContain("bad|avoid|deal");
 expect(checkItems({...h,year_built:1985},model,"Condo")).toHaveLength(7);
 const calibrated={...model,value_range:{...model.value_range!,calibration:{used:true,fit_year:2025,test_year:2024,test_data:false,method:"Held-out adjustment"}}};
 expect(checkItems({...h,checks:"range_flags",range_flags:"cal"},calibrated)[0].source).toContain("FFIEC HMDA fitting year 2025, held-out year 2024");
});
