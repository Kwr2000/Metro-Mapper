import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {areaScore,cleanScorePreferences,DEFAULT_SCORE,DEFAULT_WEIGHTS,FACTOR_IDS,FACTOR_LABELS,scoreColour,scoreFeatures,SCORE_COLOURS,validateScore,type AreaScore} from "../score";
import {ScorePanel,scorePopup} from "../ScorePanel";
import {readScorePreferences,writeScorePreferences} from "../store";
import {encodeView,readView} from "../view-state";
import {collection,ids} from "./workspace-fixtures";

export const scoreData:AreaScore={v:1,test_data:true,percentile_note:"Relative to the three counties",method:"Synthetic mid-ranks",
 factors:FACTOR_IDS.map((id,i)=>({id,label:FACTOR_LABELS[i],source:"Synthetic allowed source",field:["allowed_measure"],raw_indices:[6+i],measure_labels:["Measured value"],units:["minutes"],better:"higher",as_of:"2026-01-01",note:"Synthetic factor",test_data:true})),
 rows:Object.fromEntries(ids.map((id,i)=>[id,[10+i*10,30,40,50,60,i?null:0,1,2,3,4,5,6,7,0]]))};
afterEach(()=>{cleanup();localStorage.clear();vi.restoreAllMocks();});

it("computes the weighted mean, missing weights, exactly half, all-zero and partial",()=>{
 expect(areaScore([100,0,50,50,50,50],[3,1,0,0,0,0])).toEqual({value:75,partial:false,present:4,total:4});
 expect(areaScore([100,null,null,null,null,null],[3,3,0,0,0,0]).value).toBe(100);
 expect(areaScore([100,null,null,null,null,null],[2,3,0,0,0,0]).value).toBeNull();
 expect(areaScore([100,null,null,null,null,null],[3,3,0,0,0,0]).partial).toBe(true);
 expect(areaScore([100,null,null,null,null,null],[3,0,0,0,0,0]).partial).toBe(false);
 expect(areaScore([0,0,0,0,0,0],DEFAULT_WEIGHTS).value).toBe(0);
 expect(areaScore(undefined,DEFAULT_WEIGHTS).value).toBeNull();
 expect(areaScore([100,100,100,100,100,100],[0,0,0,0,0,0]).value).toBeNull();
});
it("has five increasing classes, grey missing, and map-only properties without People data",()=>{
 expect([0,20,40,60,80,100].map(scoreColour)).toEqual([...SCORE_COLOURS,SCORE_COLOURS[4]]);
 expect(scoreColour(null)).toBe("#bdbdbd");expect(scoreColour(19.5)).toBe(SCORE_COLOURS[1]);
 Object.defineProperty(collection.features[0].properties!,"CANARY_PEOPLE",{get(){throw new Error("Read People data");},configurable:true});
 const result=scoreFeatures(collection.features,scoreData,DEFAULT_WEIGHTS);
 expect(Object.keys(result.features[0].properties!)).toEqual(["geoid","score","partial","score_colour"]);
 expect(result.features[1].properties?.partial).toBe(true);
 delete collection.features[0].properties!.CANARY_PEOPLE;
});
it("uses default sliders, edits numeric weights, resets and shows the partial legend and note",()=>{
 const change=vi.fn();render(<ScorePanel data={scoreData} error="" preferences={DEFAULT_SCORE} onChange={change}/>);
 expect(screen.getAllByRole("slider").map(n=>(n as HTMLInputElement).value)).toEqual(["3","3","3","2","2","1"]);
 fireEvent.change(screen.getByRole("slider",{name:"Safety"}),{target:{value:"5"}});expect(change.mock.calls[0][0].weights).toEqual([5,3,3,2,2,1]);
 fireEvent.click(screen.getByRole("checkbox",{name:"Colour by score"}));expect(change.mock.calls[1][0].colour).toBe(true);
 fireEvent.click(screen.getByRole("button",{name:"Reset weights"}));expect(change.mock.calls[2][0].weights).toEqual(DEFAULT_WEIGHTS);
 expect(screen.getByText(/Lighter fill: partial/)).toBeDefined();expect(screen.getByText(/election results are never used/)).toBeDefined();
 expect(screen.getByText("Test data")).toBeDefined();
});
it("persists weights per browser and round-trips numeric-only view settings",()=>{
 const score={weights:[5,4,3,2,1,0],colour:true};writeScorePreferences(score);expect(readScorePreferences()).toEqual(score);
 const raw={camera:null,visible:[],variants:{},filters:{},compare:[],colour:{},score:{...score,note:"PRIVATE",people:{race:100}}};
 const link=encodeView(raw);expect(readView(link)?.score).toEqual(score);expect(decodeURIComponent(link)).not.toMatch(/PRIVATE|people|race|note/);
 for(const weights of [[1],[1,2,3,4,5,6],[-1,2,3,4,5,0],[.5,2,3,4,5,0],[NaN,2,3,4,5,0]])expect(cleanScorePreferences({weights,colour:true})).toBeNull();
 vi.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw new Error("blocked");});writeScorePreferences(score);expect(readScorePreferences()).toEqual(score);
});
it("renders percentile, raw value, weight, source/date and missing breakdown safely",()=>{
 const html=scorePopup(scoreData,ids[1],DEFAULT_WEIGHTS);expect(html).toContain("Good place to live:");expect(html).toContain("your weights");expect(html).toContain("Partial:");
 expect(html).toContain("Percentile: 20 / 100 · Weight 3");expect(html).toContain("Measured value: 1 minutes");expect(html).toContain("Synthetic allowed source");expect(html).toContain("2026-01-01");expect(html).toContain("Not available");
 const escaped=structuredClone(scoreData);escaped.factors[0].source="<script>CANARY</script>";expect(scorePopup(escaped,ids[0],DEFAULT_WEIGHTS)).not.toContain("<script>");
});
it("rejects foreign factor payloads and invalid percentile/raw cells",()=>{
 expect(validateScore(scoreData)).toBe(scoreData);
 const data=structuredClone(scoreData);data.factors[0].id="People";expect(()=>validateScore(data)).toThrow();
 data.factors[0].id="safety";data.rows[ids[0]][0]=101;expect(()=>validateScore(data)).toThrow();
});
it("score modules import no People-group, ACS, election, layer-data or benchmark code",()=>{
 for(const file of ["score.ts","ScorePanel.tsx"]){
  const text=readFileSync(resolve(__dirname,"..",file),"utf8");
  const imports=[...text.matchAll(/from\s+["']([^"']+)["']/g)].map(m=>m[1]);
  expect(imports.every(name=>["react","geojson","./score","./popup","./AreaPricePanel","./area-price"].includes(name))).toBe(true);
  expect(text).not.toMatch(/\.demographic\b|\.group\b|\.layers\b|\.benchmarks\b|\.filters\b|\.compare\b/);
 }
});
