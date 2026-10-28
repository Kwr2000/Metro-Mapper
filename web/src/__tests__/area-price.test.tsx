import {cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {areaScore,FACTOR_IDS,FACTOR_LABELS,cleanScorePreferences,type AreaScore} from "../score";
import {comparePrices,priceClass,priceFeatures,priceList,pricePopup,validatePrice,PRICE_CLASSES,PRICE_COLOURS,type AreaPrice} from "../area-price";
import {AreasList,PriceLegend} from "../AreaPricePanel";
import {ScorePanel,scorePopup} from "../ScorePanel";
import {BatchPage} from "../batch/BatchPage";
import {homeData} from "../homes/data";
import {home,meta,hoods} from "./homes-fixtures";
import {readScorePreferences,writeScorePreferences} from "../store";
import {encodeView,readView} from "../view-state";

const ids=["484530001001","484530002001","484910001001","482090001001","482090002001"];
const weights=[5,0,0,0,0,0],schools=[0,5,0,0,0,0];
const scores:AreaScore={v:1,test_data:true,method:"Synthetic ranks",percentile_note:"Three counties",
 factors:FACTOR_IDS.map((id,i)=>({id,label:FACTOR_LABELS[i],source:"Allowed synthetic source",field:["allowed_measure"],raw_indices:[6+i],measure_labels:["Raw"],units:["points"],better:"higher",as_of:"2026-01-01",note:"Test fixture",test_data:true})),
 rows:Object.fromEntries(ids.map((id,i)=>[id,[...[i===4?null:i<2?90:10,i===4?null:i===1||i===2?90:10,...(i===4?[null,null,null,null]:[50,50,50,50])],1,2,3,4,5,6,7,8]]))};
const prices:AreaPrice={v:1,test_data:true,as_of:"2026-01-01 appraisals; FHFA 2026-06-30",method:"Synthetic single-family median; unplaced excluded",rows:Object.fromEntries(ids.map((id,i)=>[id,[10+i,i===4?1000:i%2?300:100]]))};
vi.mock("../use-area-data",()=>({useAreaData:()=>({score:scores,price:prices,scoreError:"",priceError:""}),useScoreWeights:()=>schools}));
afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear();});

it("splits on paired medians, puts ties on the higher side and ranks prices over all priced areas",()=>{
 const c=comparePrices(scores,prices,weights);expect(c.scoreMedian).toBe(50);expect(c.priceMedian).toBe(200);
 expect(c.rows.slice(0,4).map(r=>priceClass(r,c))).toEqual([0,1,2,3]);expect(priceClass(c.rows[4],c)).toBeNull();
 expect(c.rows.map(r=>r.percentile)).toEqual([20,60,20,60,90]);expect([c.min,c.max]).toEqual([100,1000]);
 const ties=comparePrices({...scores,rows:Object.fromEntries(ids.slice(0,4).map(id=>[id,[50,50,50,50,50,50,1,2,3,4,5,6,7,8]]))},{...prices,rows:Object.fromEntries(ids.slice(0,4).map(id=>[id,[10,200]]))},weights);
 expect(ties.rows.map(r=>priceClass(r,ties))).toEqual([1,1,1,1]);
 const none=comparePrices(scores,prices,[0,0,0,0,0,0]);expect(none.scoreMedian).toBeNull();expect(none.priceMedian).toBeNull();expect(priceList(none,1000)).toEqual([]);
});
it("filters inclusively and reorders list/colours with the owner's weights",()=>{
 const a=comparePrices(scores,prices,weights),b=comparePrices(scores,prices,schools);
 expect(priceList(a,100).map(r=>r.id)).toEqual([ids[0],ids[2]]);expect(priceList(b,100).map(r=>r.id)).toEqual([ids[2],ids[0]]);
 const features=ids.map(id=>({type:"Feature" as const,id,geometry:{type:"Point" as const,coordinates:[0,0]},properties:{geoid:id,get CANARY_PEOPLE(){throw new Error("Read People");}}}));
 const output=priceFeatures(features,a);expect(output.features.map(f=>f.properties?.score_colour)).toEqual([...PRICE_COLOURS,"#bdbdbd"]);
 expect(priceFeatures(features,b).features[0].properties?.score_colour).toBe(PRICE_COLOURS[2]);
 expect(Object.keys(output.features[0].properties!)).toEqual(["geoid","score","partial","score_colour"]);
});
it("uses data-derived slider limits, stable score ordering and working map links",()=>{
 const fly=vi.fn();const props={scores,prices,weights,names:{[ids[0]]:"Test area A",[ids[2]]:"Test area C"},links:{},onFly:fly};
 const {rerender}=render(<AreasList {...props}/>);const slider=screen.getByRole("slider");expect(slider.getAttribute("min")).toBe("100");expect(slider.getAttribute("max")).toBe("1000");
 fireEvent.change(slider,{target:{value:"100"}});expect(screen.getAllByRole("link").map(a=>a.textContent)).toEqual(["Test area A","Test area C"]);
 rerender(<AreasList {...props} weights={schools}/>);expect(screen.getAllByRole("link")[0].textContent).toBe("Test area C");fireEvent.click(screen.getAllByRole("link")[0]);expect(fly).toHaveBeenCalledWith(ids[2]);
});
it("keeps map modes exclusive and persists/shares the new mode with numeric weights only",()=>{
 const change=vi.fn();render(<ScorePanel data={scores} prices={prices} error="" preferences={{weights,colour:true}} onChange={change}/>);
 fireEvent.click(screen.getByRole("checkbox",{name:"Score vs price"}));const next=change.mock.calls[0][0];expect(next).toEqual({weights,colour:false,price:true});
 writeScorePreferences(next);expect(readScorePreferences()).toEqual(next);const view=readView(encodeView({camera:null,visible:[],variants:{},filters:{},compare:[],colour:{},score:next}));expect(view?.score).toEqual(next);
 expect(cleanScorePreferences({weights,colour:true,price:true})?.colour).toBe(false);
 fireEvent.click(screen.getByRole("tab",{name:"Areas list"}));expect(screen.getByRole("table")).toBeDefined();
});
it("adds a sourced popup line, rejects invalid publications and preserves zero",()=>{
 expect(pricePopup({...prices,rows:{[ids[0]]:[412,243]}},ids[0])).toContain("Median appraisal-based $ per sq ft: $243 (n = 412 single-family homes)");
 expect(scorePopup(scores,ids[0],weights,prices)).toContain("Median appraisal-based $ per sq ft");
 expect(pricePopup(null,ids[0])).toContain("Not available");expect(pricePopup({...prices,as_of:"<script>"},ids[0])).not.toContain("<script>");
 expect(validatePrice({...prices,rows:{[ids[0]]:[10,0]}}).rows[ids[0]][1]).toBe(0);
 for(const row of [[9,100],[10,null],[10,-1],[true,100]])expect(()=>validatePrice({...prices,rows:{[ids[0]]:row}})).toThrow();
});
it("renders and sorts both batch columns without changing its default sort",async()=>{
 vi.spyOn(homeData,"meta").mockResolvedValue(meta);vi.spyOn(homeData,"hoods").mockResolvedValue(hoods);
 vi.spyOn(homeData,"search").mockImplementation(async text=>[{...home,id:text.startsWith("100")?home.id:"48491:R124",number:text.startsWith("100")?"100":"200",block_group:text.startsWith("100")?ids[0]:ids[1]}]);
 render(<BatchPage registry={null}/>);fireEvent.change(screen.getByRole("textbox",{name:"Addresses and asking prices"}),{target:{value:"100 TEST ST #2 78664 $560000\n200 TEST ST #2 78664 $400000"}});fireEvent.click(screen.getByRole("button",{name:"Check pasted listings"}));
 await screen.findByRole("heading",{name:"Listing results"});expect((screen.getByRole("combobox",{name:"Sort by"}) as HTMLSelectElement).value).toBe("default");
 expect(screen.getByRole("columnheader",{name:"Area score"})).toBeDefined();expect(screen.getByRole("columnheader",{name:"Area $/sq ft percentile"})).toBeDefined();
 fireEvent.click(screen.getByRole("button",{name:"Sort by Area score"}));let rows=screen.getAllByRole("row").slice(1);expect(rows[0].getAttribute("data-listing-key")).toBe("0");expect(within(rows[0]).getAllByText("10").length).toBeGreaterThan(0);
 fireEvent.click(screen.getByRole("button",{name:"Sort by Area score"}));rows=screen.getAllByRole("row").slice(1);expect(rows[0].getAttribute("data-listing-key")).toBe("1");
 fireEvent.click(screen.getByRole("button",{name:"Sort by Area $/sq ft percentile"}));expect(screen.getAllByRole("row")[1].getAttribute("data-listing-key")).toBe("0");
});
it("isolates numerical code and list imports from People/layer/benchmark modules and extends the copy guard",()=>{
 for(const file of ["area-price.ts","AreaPricePanel.tsx"]){const text=readFileSync(resolve(__dirname,"..",file),"utf8"),imports=[...text.matchAll(/from\s+["']([^"']+)["']/g)].map(m=>m[1]);
  expect(imports.every(p=>["react","geojson","./score","./area-price"].includes(p))).toBe(true);expect(text).not.toMatch(/\.demographic\b|\.group\b|\.layers\b|\.benchmarks\b|\.filters\b/);
 }
 render(<><PriceLegend scores={scores} prices={prices} weights={weights}/><AreasList scores={scores} prices={prices} weights={weights} names={{}} links={{}} onFly={()=>{}}/></>);
 expect(document.body.textContent+scorePopup(scores,ids[0],weights,prices)).not.toMatch(/\b(fair value|good deal|bargain|undervalued|overpriced|worth|better|worse|cheap|expensive)\b/i);
 for(const label of PRICE_CLASSES)expect(screen.getByText(label)).toBeDefined();
});
