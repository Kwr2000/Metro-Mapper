import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {blankListing,CSVParser,listingsFromCSV,parseCSV,parseImport,parsePaste,listingURL} from "../batch/parse";
import {analyse,chooseMatch,position,processListings,published,tableRows,type BatchRow} from "../batch/model";
import {exportTable} from "../batch/export";
import {BatchPage} from "../batch/BatchPage";
import {clearBatchLists,readBatchLists,readAskingPrice,removeBatchList,saveBatchList} from "../store";
import {HomeData,homeData} from "../homes/data";
import {home,meta,hoods,shard} from "./homes-fixtures";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";

const csv='\uFEFF address ,CITY,STATE,ZIP,LIST PRICE,BEDS,BATHS,SQUARE FEET,LOT SIZE,YEAR BUILT,DAYS ON MARKET,HOA/MONTH,STATUS,PROPERTY TYPE,URL (SEE DETAILS),LATITUDE,LONGITUDE,PRIVATE NOTES\r\n"100 Test St, #2",Round Rock,TX,78664,"$560,000",3,2.5,2201,8000,2000,0,,Active,Condo,https://example.invalid/home,30.3,-97.7,"CANARY_PRIVATE, \"\"quotes\"\"\r\nsecond line"\r\n,,,,,,,,,,,,,,,,,Publisher disclaimer\r\n';
const listing=()=>({...blankListing('100 TEST ST #2, Round Rock TX 78664','0'),price:560000,state:'TX'});
beforeEach(()=>{clearBatchLists();localStorage.clear();window.history.replaceState(null,'','#/home?tab=many');});
afterEach(()=>{cleanup();clearBatchLists();vi.restoreAllMocks();vi.unstubAllGlobals();});

it('parses native CSV aliases, BOM/CRLF, quoted commas, doubled quotes/newlines and drops private cells',async()=>{
 const parsed=listingsFromCSV(parseCSV(csv));expect(parsed.listings).toHaveLength(1);const l=parsed.listings[0];
 expect(l.query).toBe('100 Test St, #2, Round Rock, TX 78664');expect(l.price).toBe(560000);expect(l.beds).toBe(3);expect(l.baths).toBe(2.5);expect(l.days).toBe(0);expect(l.hoa).toBeNull();expect(l.lat).toBe(30.3);
 expect(parsed.ignoredHeaders).toEqual(['PRIVATE NOTES']);expect(JSON.stringify(l)).not.toContain('CANARY');
 const parser=new CSVParser();for(const c of csv)parser.feed(c);expect(parser.finish()).toEqual(parseCSV(csv));
 expect(await parseImport(csv,'csv')).toEqual(parsed);
 const headers='ADDRESS,STATE OR PROVINCE,ZIP OR POSTAL CODE,PRICE,URL\n100 Test St,TX,78664,500000,https://example.invalid/';expect(listingsFromCSV(parseCSV(headers)).listings[0].price).toBe(500000);
 for(const invalid of ['ADDRESS,PRICE\n"unclosed,5','ADDRESS,PRICE,price\n100 Test St,3,4','ADDRESS,BEDS\n100 Test St,3'])expect(()=>listingsFromCSV(parseCSV(invalid))).toThrow();
 expect(listingURL('javascript:alert(1)')).toBeNull();expect(listingURL('https://user:password@example.invalid/')).toBeNull();
});
it.each([
 ['100 S 8th St #2, Austin TX 78704 — $725,000',725000,'100 S 8th St #2, Austin TX 78704'],
 ['100 Test St\t725000',725000,'100 Test St'],['100 Test St,725,000',725000,'100 Test St'],
 ['100 Test St 725000',725000,'100 Test St'],['100 Test St, Austin TX 78704',null,'100 Test St, Austin TX 78704'],
])('parses pasted %s',(text,price,query)=>{const l=parsePaste(text).listings[0];expect(l.price).toBe(price);expect(l.query).toBe(query);});
it('reports shorthand, missing prices and import limits without silently truncating',()=>{
 expect(parsePaste('100 Test St — 725k').listings[0].issue).toMatch(/shorthand/);expect(parsePaste('100 Test St').listings[0].price).toBeNull();
 expect(()=>parsePaste(Array(351).fill('100 Test St $500000').join('\n'))).toThrow(/350/);
 expect(()=>listingsFromCSV(parseCSV('ADDRESS,PRICE\n'+Array(351).fill('100 Test St,500000').join('\n')))).toThrow(/350/);
});
it('computes the boundary-relative position and keeps area discrepancies strictly above 10%',()=>{
 const range={low:400000,mid:500000,high:600000};expect(position(350000,range)).toBe(-10);expect(position(650000,range)).toBe(10);
 for(const p of [400000,500000,600000])expect(position(p,range)).toBe(0);
 const l=listing();const m=analyse({...l,sqft:2200},home,meta,hoods);expect(m.percentile).toBe(70);expect(m.n).toBe(20);expect(m.psf).toBe(280);expect(m.areaWarning).toBe(false);
 expect(analyse({...l,sqft:2201},home,meta,hoods).areaWarning).toBe(true);
 expect(analyse(l,{...home,living_area:null},meta,hoods).psf).toBeNull();
 const hidden={...meta,value_range:{...meta.value_range!,published:false}};const h=analyse(l,home,hidden,hoods);
 expect(h.low).toBeNull();expect(h.position).toBeNull();expect(h.rangePct).toBeNull();expect(h.percentile).toBe(70);expect(published(hidden)).toBe(false);
});

function serve(){
 const documents:Record<string,unknown>={'meta.json':meta,'hoods.json':hoods,'addr/TE.json':shard([home,{...home,id:'48491:R124',unit:'3',situs:'100 TEST ST #3'}])};
 const urls:string[]=[];vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=new URL(String(input),window.location.href);expect(url.origin).toBe(window.location.origin);expect(url.pathname.startsWith('/data/')).toBe(true);expect(url.search).toBe('');expect(init?.body).toBeUndefined();expect(init?.method??'GET').toBe('GET');urls.push(url.pathname);
  const key=url.pathname.split('/data/homes/')[1],body=documents[key];return body?new Response(JSON.stringify(body)):new Response('',{status:404});
 }));return urls;
}
it('processes 350 file rows through the real loader with no requests outside own data/ and no storage writes',async()=>{
 const urls=serve();const writes=vi.spyOn(Storage.prototype,'setItem');const rows=Array.from({length:350},(_,i)=>({...listing(),key:String(i),url:'https://example.invalid/NEVER_FETCH_THIS'}));
 const progress=vi.fn();const result=await processListings(rows,{loader:new HomeData(),onProgress:progress});
 expect(result.rows).toHaveLength(350);expect(result.rows.every(r=>r.home?.id===home.id)).toBe(true);
 expect(urls.filter(u=>u.endsWith('/addr/TE.json'))).toHaveLength(1);expect(urls).toHaveLength(3);expect(progress).toHaveBeenLastCalledWith(350,350);expect(writes).not.toHaveBeenCalled();expect(readAskingPrice(home.id)).toBe('');
 for(const [input,init] of vi.mocked(fetch).mock.calls){const url=new URL(String(input),window.location.href);expect(url.origin).toBe(window.location.origin);expect(url.pathname.startsWith('/data/')).toBe(true);expect(url.search).toBe('');expect(init?.method??'GET').toBe('GET');expect(init?.body).toBeUndefined();}
 expect(JSON.stringify(urls)).not.toMatch(/NEVER_FETCH|560000|TEST/);
});
it('groups requests by shard so the 20-shard loader cache never causes repeat downloads',async()=>{
 const ids=Array.from({length:25},(_,i)=>`A${String.fromCharCode(65+i)}`);const names=ids.map(id=>id+'TEST ST');const sources={...meta,shards:Object.fromEntries(ids.map(id=>[id,[id]]))};
 const counts=new Map<string,number>();vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
  const url=String(input);if(url.endsWith('meta.json'))return new Response(JSON.stringify(sources));if(url.endsWith('hoods.json'))return new Response(JSON.stringify(hoods));
  const id=url.match(/addr\/([A-Z]{2})\.json$/)![1];counts.set(id,(counts.get(id)??0)+1);return new Response(JSON.stringify(shard([{...home,id:'48491:R'+id,street_key:id+'TEST ST'}])));
 }));
 const listings=Array.from({length:100},(_,i)=>({...listing(),key:String(i),query:`100 ${names[i%25]} #2 78664`}));
 const data=new HomeData();const result=await processListings(listings,{loader:data});expect(result.rows.every(r=>r.home)).toBe(true);expect(counts.size).toBe(25);expect([...counts.values()].every(n=>n===1)).toBe(true);expect(data.cacheSizes.shards).toBeLessThanOrEqual(20);
});
it('separates no-price/outside/not-found/ambiguous rows, allows explicit unit choice and cancels imports',async()=>{
 serve();const rows=[{...listing(),query:'100 TEST ST 78664'},{...listing(),key:'1',price:null},{...listing(),key:'2',state:'CA'}, {...listing(),key:'3',query:'999 Unknown St',lat:0,lon:0}];
 const result=await processListings(rows,{loader:new HomeData(),loadBounds:async()=>({type:'FeatureCollection',features:[]})});expect(result.rows.map(r=>r.reason)).toEqual(['Several matches — pick one','No asking price','Outside the three counties (state is not Texas)','Outside the three counties (listing coordinates)']);
 const chosen=chooseMatch(result.rows[0],home.id,meta,hoods);expect(chosen.home?.id).toBe(home.id);expect(chosen.listing.selectedId).toBe(home.id);expect(chosen.reason).toBeNull();
 const abort=new AbortController();abort.abort();await expect(processListings([listing()],{loader:new HomeData(),signal:abort.signal})).rejects.toThrow(/Cancelled/);
});
it('sorts numeric fields with missing last, applies filters, and defaults to percentile while unpublished',()=>{
 const row=(key:string,county:string,price:number,position:number|null,percentile:number|null):BatchRow=>({listing:{...listing(),key,price},home:{...home,county},normalized:{number:'100',street_key:'TEST ST',unit:'2',zip:'78664'},candidates:[],reason:null,metrics:{...analyse(listing(),home,meta,hoods),position,percentile}});
 const rows=[row('0','Travis',500000,5,60),row('1','Williamson',400000,-5,80),row('2','Williamson',300000,null,20)];const filters={county:'',category:'',hasRange:false};
 expect(tableRows(rows,filters).map(r=>r.listing.key)).toEqual(['1','0','2']);expect(tableRows(rows,filters,'default',false,false).map(r=>r.listing.key)).toEqual(['2','0','1']);
 expect(tableRows(rows,{...filters,county:'Williamson'},'price',true).map(r=>r.listing.key)).toEqual(['1','2']);expect(tableRows(rows,{...filters,category:'single_family'})).toHaveLength(0);
});
it('saves only on request, restores choices, enforces 5 lists/400 rows, and clears only batch data',()=>{
 const row={...listing(),selectedId:home.id};expect(readBatchLists()).toEqual([]);
 for(let i=0;i<5;i++)expect(saveBatchList('List '+i,[row])).toBe(true);expect(readBatchLists()).toHaveLength(5);expect(readBatchLists()[0].rows[0].selectedId).toBe(home.id);
 expect(()=>saveBatchList('Sixth',[row])).toThrow(/Five/);expect(saveBatchList('List 0',Array(400).fill(row))).toBe(true);expect(()=>saveBatchList('List 0',Array(401).fill(row))).toThrow(/400/);
 expect(removeBatchList('List 0')).toBe(true);expect(readBatchLists()).toHaveLength(4);localStorage.setItem('metro-mapper:shortlist','[]');expect(clearBatchLists()).toBe(true);expect(readBatchLists()).toEqual([]);expect(localStorage.getItem('metro-mapper:shortlist')).toBe('[]');
});
it('exports the shown rows/columns locally, includes provenance, and protects formula text',async()=>{
 serve();const result=await processListings([listing()],{loader:new HomeData()});const text=exportTable(result.rows,meta);
 expect(text).toContain('560000');expect(text).toContain('Range low');expect(text).toContain(home.id);expect(text).toContain(home.certified);
 const hidden=exportTable(result.rows,{...meta,value_range:{...meta.value_range!,published:false}});expect(hidden).not.toContain('Range low');expect(hidden).not.toContain('Position percent');
 result.rows[0].home={...home,situs:'=HYPERLINK("bad")'};expect(exportTable(result.rows,meta)).toContain("'=HYPERLINK");
});
it('renders a local paste import, hides unpublished range columns, and saves/restores/clears explicitly',async()=>{
 vi.spyOn(homeData,'meta').mockResolvedValue({...meta,value_range:{...meta.value_range!,published:false}});vi.spyOn(homeData,'hoods').mockResolvedValue(hoods);vi.spyOn(homeData,'search').mockResolvedValue([home]);
 render(<BatchPage registry={null}/>);fireEvent.change(screen.getByRole('textbox',{name:'Addresses and asking prices'}),{target:{value:'100 TEST ST #2 78664 — $560,000'}});fireEvent.click(screen.getByRole('button',{name:'Check pasted listings'}));
 await screen.findByRole('heading',{name:'Listing results'});await waitFor(()=>expect(screen.getByRole('heading',{name:'Listing results'})).toBe(document.activeElement));
 expect(screen.queryByRole('columnheader',{name:'Position'})).toBeNull();expect(screen.queryByRole('columnheader',{name:'Appraisal-based value range'})).toBeNull();expect(screen.getByText('≈70th')).toBeDefined();expect(readBatchLists()).toEqual([]);
 fireEvent.change(screen.getByRole('textbox',{name:'List name'}),{target:{value:'Private list'}});fireEvent.click(screen.getByRole('button',{name:'Save list'}));expect(readBatchLists()).toHaveLength(1);
 fireEvent.click(screen.getByRole('button',{name:'Clear all listings'}));expect(readBatchLists()).toEqual([]);expect(screen.queryByRole('table')).toBeNull();expect(window.location.hash).toBe('#/home?tab=many');
});
it('checks the extended prohibited wording guard in built-copy configuration and rendered batch copy',()=>{
 const config=readFileSync(resolve(__dirname,'../../vite.config.ts'),'utf8');expect(config).toContain('bargain|undervalued');
 render(<BatchPage registry={null}/>);expect(document.body.textContent).not.toMatch(/\b(fair value|good deal|overpriced|worth|bargain|undervalued|bad|avoid|deal)\b/i);
});
