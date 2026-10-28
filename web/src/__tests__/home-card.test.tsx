import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {HomeCard,categoryLabel} from "../homes/HomeCard";
import {home,meta,hoods} from "./homes-fixtures";
import {readAskingPrice,writeAskingPrice} from "../store";
import {encodeView} from "../view-state";
beforeEach(()=>{localStorage.clear();writeAskingPrice(home.id,"");window.history.replaceState(null,"","#/home?id=48491%3AR123");});afterEach(()=>{cleanup();vi.restoreAllMocks();});
const show=(h=home,m=meta)=>render(<HomeCard home={h} meta={m} onShowMap={vi.fn()} areaName="Test area" loadHoods={async()=>hoods}/>);
it.each(["single_family","condo","mobile_home","two_to_four_units","rural_home","builder_inventory","other_residential"])("shows %s facts and sources without demographic context",category=>{
 show({...home,category});expect(screen.getAllByText(new RegExp(categoryLabel(category).replace(/[()]/g,"\\$&"))).length).toBeGreaterThan(0);
 expect(screen.getByText("Test neighbourhood · TEST")).toBeDefined();expect(screen.getByRole("heading",{name:home.situs!})).toBe(document.activeElement);
 expect(document.body.textContent).toContain("January 1, 2026");expect(document.body.textContent).toContain("October 21, 2026");expect(document.body.textContent).not.toContain("People (context only)");
});
it("keeps null facts unavailable and explains unplaced homes",()=>{
 show({...home,lon:null,lat:null,placed:null,block_group:null,living_area:null,year_built:null,land_acres:null,floors:null});
 expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(4);expect(screen.getByText(/No map location yet/)).toBeDefined();expect(screen.queryByRole("button",{name:"Show on map"})).toBeNull();
});
it("hides every calculated range and disclosure while unpublished",()=>{
 show(home,{...meta,value_range:{...meta.value_range!,published:false}});expect(screen.getByText(/being validated/)).toBeDefined();expect(screen.queryByText("$400,000")).toBeNull();expect(screen.queryByText("How this is worked out")).toBeNull();
});
it.each([["no_value","No 2026 market value"],["no_building","No building value on January 1, 2026"],["partial","Partial-ownership record"]])("explains %s without inventing endpoints",(reason,label)=>{
 show({...home,range_pct:null,range_flags:reason});expect(screen.getByText(label)).toBeDefined();expect(screen.queryByText("How this is worked out")).toBeNull();
});
it("shows the actual method, flag descriptions and Test data labels",()=>{
 show({...home,range_flags:"new,lot,condo,size,type"},{...meta,value_range:{...meta.value_range!,test_data:true}});
 for(const label of [/Built in the last two years/,/Lot over one acre/,/Unusually large\/small/,/Not a single-family home/])expect(screen.getByText(label)).toBeDefined();
 expect(screen.getAllByText(/Test data/).length).toBeGreaterThan(0);fireEvent.click(screen.getByText("How this is worked out"));expect(document.querySelector("details")?.open).toBe(true);
 expect(document.body.textContent).toContain("668.665");expect(document.body.textContent).toContain("75.59%");expect(document.body.textContent).toContain("June 30, 2026");
});
it("stores the asking price per id only in this browser, compares PPSF and never shares it",async()=>{
 show();fireEvent.change(screen.getByRole("spinbutton",{name:"Asking price (optional)"}),{target:{value:"560000"}});
 expect(readAskingPrice(home.id)).toBe("560000");expect(readAskingPrice("48491:R999")).toBe("");
 expect(await screen.findByText(/higher than about 70%/)).toBeDefined();expect(screen.getByText(/inside the appraisal-based/)).toBeDefined();
 expect(window.location.href).not.toContain("560000");expect(screen.getByRole("link",{name:"Link to this home"}).getAttribute("href")).not.toContain("560000");
 expect(encodeView({camera:null,visible:[],variants:{},filters:{},compare:[],colour:{}})).not.toContain("560000");
 cleanup();show();expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("560000");
 await waitFor(()=>expect(screen.getByText(/20 comparable homes/)).toBeDefined());
});
it.each([[300000,"below"],[700000,"above"]])("compares an asking price of %s",(price,position)=>{
 show();fireEvent.change(screen.getByRole("spinbutton"),{target:{value:String(price)}});expect(screen.getByText(new RegExp(`${position} the appraisal-based value range`))).toBeDefined();
});
it("keeps a session price when persistent storage is blocked",()=>{
 vi.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw new Error("blocked");});show();fireEvent.change(screen.getByRole("spinbutton"),{target:{value:"570000"}});expect(screen.getByText(/Storage is blocked/)).toBeDefined();expect(readAskingPrice(home.id)).toBe("570000");
});
it("contains no prohibited wording in rendered page text",()=>{
 show();expect(document.body.textContent).not.toMatch(/\b(fair value|good deal|overpriced|worth)\b/i);
});

it("keeps the published four-decimal lot precision",()=>{
 show({...home,land_acres:.0001});expect(screen.getByText("0.0001 acres")).toBeDefined();
});
