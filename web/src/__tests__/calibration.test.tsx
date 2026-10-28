import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {HomeCard} from "../homes/HomeCard";
import {HomeData,type HomeMeta} from "../homes/data";
import {calibrationFactor,validateCalibration,type Calibration} from "../homes/range";
import {analyse,chooseMatch,processListings} from "../batch/model";
import {blankListing} from "../batch/parse";
import {home,meta,hoods} from "./homes-fixtures";

const cal:Calibration={v:1,fit_year:2025,test_year:2024,county:{"48453":1.1,"48491":1.05,"48209":1},tract:{"48491000100":1.2},test_data:true};
const calibratedHome={...home,block_group:"484910001001",range_flags:"condo,cal"};
const calibratedMeta:HomeMeta={...meta,value_range:{...meta.value_range!,calibration:{used:true,fit_year:2025,test_year:2024,test_data:true,method:"Fit on 2025, test on 2024"}}};
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();localStorage.clear();});

it("uses only the home's county or tract, with an unplaced county fallback",()=>{
 expect(calibrationFactor(calibratedHome,cal)).toBe(1.2);
 expect(calibrationFactor({...home,block_group:null},cal)).toBe(1.05);
 expect(calibrationFactor(home,cal)).toBe(1.05); // foreign block-group prefix cannot borrow a factor
 expect(calibrationFactor(calibratedHome,null)).toBe(1);
 for(const invalid of [{...cal,tract:[]},{...cal,tract:{"48491000100":.79}},{...cal,county:{"48453":1}},{...cal,test_year:2025}])expect(()=>validateCalibration(invalid)).toThrow();
});
it("loads only the static calibration file, caches it, and retries a failed load",async()=>{
 const fetcher=vi.fn(async(url:RequestInfo|URL)=>{expect(String(url)).toBe("data/homes/calibration.json");return new Response(JSON.stringify(cal));});vi.stubGlobal("fetch",fetcher);
 const data=new HomeData();const results=await Promise.all([data.calibration(),data.calibration()]);expect(results).toEqual([cal,cal]);expect(fetcher).toHaveBeenCalledTimes(1);
 const retry=new HomeData();fetcher.mockRejectedValueOnce(new Error("unavailable"));await expect(retry.calibration()).rejects.toThrow();expect(await retry.calibration()).toEqual(cal);
});
it("shows the same calibrated result on the card, with fitting/testing years and its adjustment flag",async()=>{
 localStorage.clear();render(<HomeCard home={calibratedHome} meta={calibratedMeta} onShowMap={vi.fn()} loadHoods={async()=>hoods} loadCalibration={async()=>cal}/>);
 expect(screen.getByText("Loading neighbourhood adjustment…")).toBeDefined();
 await screen.findByText("$480,000 – $720,000");expect(screen.getByText(/Neighbourhood adjustment of \+20% from 2025 home-purchase loans/)).toBeDefined();
 fireEvent.click(screen.getByText("How this is worked out"));expect(screen.getByText(/tract factor.*fitted on 2025.*checked on 2024/)).toBeDefined();
 expect(document.body.textContent).not.toMatch(/\b(fair value|good deal|bargain|undervalued|overpriced|worth)\b/i);
});
it("never substitutes an uncalibrated card result when the accepted calibration file fails to load",async()=>{
 render(<HomeCard home={calibratedHome} meta={calibratedMeta} onShowMap={vi.fn()} loadCalibration={async()=>{throw new Error("failed");}}/>);
 await screen.findByText("Neighbourhood adjustment could not load. Reload to retry.");expect(document.querySelector('.home-range-number')).toBeNull();
});
it("uses the factor in batch results and explicit matches, and omits it when calibration is off",async()=>{
 const listing={...blankListing("100 Test St #2 78664","0"),price:600000};const loader={meta:async()=>calibratedMeta,hoods:async()=>hoods,search:async()=>[calibratedHome],calibration:vi.fn(async()=>cal)};
 const result=await processListings([listing],{loader});expect(result.rows[0].metrics?.mid).toBe(600000);expect(result.rows[0].metrics?.flags).toContain("+20%");expect(loader.calibration).toHaveBeenCalledTimes(1);
 const selected=chooseMatch({...result.rows[0],home:null},calibratedHome.id,result.meta,result.hoods,result.calibration);expect(selected.metrics?.mid).toBe(600000);
 expect(analyse(listing,calibratedHome,calibratedMeta,hoods).mid).toBeNull();
 const off={...calibratedMeta,value_range:{...calibratedMeta.value_range!,calibration:{...calibratedMeta.value_range!.calibration!,used:false}}};
 expect(analyse(listing,calibratedHome,off,hoods,cal).mid).toBe(500000);
 const base=await processListings([listing],{loader:{...loader,meta:async()=>off}});expect(base.rows[0].metrics?.mid).toBe(500000);expect(loader.calibration).toHaveBeenCalledTimes(1);
});
