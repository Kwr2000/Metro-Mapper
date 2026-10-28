/** Local-only, dependency-free CSV/paste parsing. Unknown column values are discarded. */
export type Listing = { key:string;query:string;state:string;price:number|null;beds:number|null;baths:number|null;sqft:number|null;
  lot:number|null;year:number|null;days:number|null;hoa:number|null;status:string;propertyType:string;url:string|null;
  lat:number|null;lon:number|null;issue:string;selectedId?:string };
export type ParsedListings = {listings:Listing[];ignoredHeaders:string[]};
export const MAX_IMPORT_ROWS=350;
export const MAX_FILE_BYTES=5_000_000;
export const pause=()=>new Promise<void>(resolve=>setTimeout(resolve,0));

export class CSVParser {
  private state:"start"|"plain"|"quoted"|"after"="start";
  private cell="";private row:string[]=[];private rows:string[][]=[];private skipLF=false;private first=true;
  feed(text:string){
    for(const c of text){
      if(this.first){this.first=false;if(c==="\uFEFF")continue;}
      if(this.skipLF){this.skipLF=false;if(c==="\n")continue;}
      if(this.state==="quoted") {if(c==='"')this.state="after";else this.cell+=c;continue;}
      if(this.state==="after" && c==='"'){this.cell+='"';this.state="quoted";continue;}
      if(c==="," || c==="\r" || c==="\n"){
        this.row.push(this.cell);this.cell="";
        if(c!==","){if(this.row.some(v=>v.trim()))this.rows.push(this.row);this.row=[];this.skipLF=c==="\r";}
        this.state="start";continue;
      }
      if(this.state==="after" || c==='"' && this.state!=="start")throw new Error("CSV quotes are incomplete or misplaced.");
      if(c==='"')this.state="quoted";else {this.cell+=c;this.state="plain";}
    }
  }
  finish():string[][] {
    if(this.state==="quoted")throw new Error("CSV has an unclosed quoted field.");
    if(this.row.length || this.cell || this.state!=="start"){
      this.row.push(this.cell);if(this.row.some(v=>v.trim()))this.rows.push(this.row);
    }
    return this.rows;
  }
}
export function parseCSV(text:string):string[][] {const p=new CSVParser();p.feed(text);return p.finish();}
export async function parseCSVChunked(text:string,signal?:AbortSignal):Promise<string[][]>{
  const p=new CSVParser();for(let i=0;i<text.length;i+=32768){if(signal?.aborted)throw new DOMException("Cancelled","AbortError");p.feed(text.slice(i,i+32768));await pause();}return p.finish();
}
const ALIASES:Record<string,string[]>={address:["ADDRESS"],city:["CITY"],state:["STATE OR PROVINCE","STATE"],zip:["ZIP OR POSTAL CODE","ZIP"],
 price:["PRICE","LIST PRICE"],beds:["BEDS"],baths:["BATHS"],sqft:["SQUARE FEET"],lot:["LOT SIZE"],year:["YEAR BUILT"],days:["DAYS ON MARKET"],hoa:["HOA/MONTH"],
 status:["STATUS"],propertyType:["PROPERTY TYPE"],lat:["LATITUDE"],lon:["LONGITUDE"]};
const normalHeader=(s:string)=>s.trim().toUpperCase();
export function numberCell(text:string):number|null {
  const value=text.trim().replace(/^\$/,""),valid=/^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(value);
  if(!valid)return null;const n=Number(value.replaceAll(",",""));return Number.isFinite(n)?n:null;
}
const measure=(text:string)=>{const n=numberCell(text);return n!=null && n>=0?n:null;};
export function listingURL(text:string):string|null {
  try {const u=new URL(text.trim());return ["https:","http:"].includes(u.protocol) && !u.username && !u.password ? u.href:null;}catch{return null;}
}
export function blankListing(query:string,key:string):Listing {
  return {key,query,state:"",price:null,beds:null,baths:null,sqft:null,lot:null,year:null,days:null,hoa:null,status:"",propertyType:"",url:null,lat:null,lon:null,issue:""};
}
export function listingsFromCSV(rows:string[][],limit=MAX_IMPORT_ROWS):ParsedListings {
  if(!rows.length)throw new Error("The CSV is empty.");
  const original=rows[0],headers=original.map(normalHeader);
  if(new Set(headers.filter(Boolean)).size!==headers.filter(Boolean).length)throw new Error("CSV contains duplicate column headers.");
  if(!headers.includes("ADDRESS") || !ALIASES.price.some(h=>headers.includes(h)))throw new Error("CSV needs ADDRESS and PRICE or LIST PRICE columns.");
  const known=new Set(Object.values(ALIASES).flat());
  const ignoredHeaders=original.filter((h,i)=>h.trim()&&!known.has(headers[i])&&!headers[i].startsWith("URL")).map(h=>h.trim());
  const column=(row:string[],field:string)=>{
    const choices=field==="url"?headers.map((h,i)=>h.startsWith("URL")?i:-1).filter(i=>i>=0):ALIASES[field].map(h=>headers.indexOf(h)).filter(i=>i>=0);
    return choices.map(i=>(row[i]??"").trim()).find(Boolean)??"";
  };
  const listings:Listing[]=[];
  for(const row of rows.slice(1)){
    const address=column(row,"address"),priceText=column(row,"price");
    if(!address && !priceText)continue; // Trailing disclaimers carry neither field.
    if(row.length>headers.length)throw new Error("A CSV row has more fields than the header.");
    if(listings.length>=limit)throw new Error(`Choose no more than ${limit} listings at once.`);
    const city=column(row,"city"),state=column(row,"state"),zip=column(row,"zip");
    const query=[address,city,[state,zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
    const listing=blankListing(query,String(listings.length));listing.state=state;
    listing.price=measure(priceText);
    for(const key of ["beds","baths","sqft","lot","year","days","hoa"] as const)listing[key]=measure(column(row,key));
    listing.lat=numberCell(column(row,"lat"));listing.lon=numberCell(column(row,"lon"));
    if(listing.lat!=null && Math.abs(listing.lat)>90)listing.lat=null;
    if(listing.lon!=null && Math.abs(listing.lon)>180)listing.lon=null;
    listing.status=column(row,"status");listing.propertyType=column(row,"propertyType");listing.url=listingURL(column(row,"url"));
    if(/\d\s*[km]\b/i.test(priceText))listing.issue="Use a full asking price such as 725000; shorthand prices are not supported.";
    listings.push(listing);
  }
  if(!listings.length)throw new Error("No listing addresses were found in the CSV.");
  return {listings,ignoredHeaders};
}
export function parsePaste(text:string,limit=MAX_IMPORT_ROWS):ParsedListings {
  const listings:Listing[]=[];
  for(const line of text.split(/\r?\n/).map(v=>v.trim()).filter(Boolean)){
    if(listings.length>=limit)throw new Error(`Choose no more than ${limit} listings at once.`);
    const listing=blankListing(line,String(listings.length));
    if(/\d[\d,.]*\s*[km]\s*$/i.test(line))listing.issue="Use a full asking price such as 725000; shorthand prices are not supported.";
    else {
      const dollars=[...line.matchAll(/\$\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/g)];
      const plain=line.match(/(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*$/);
      const match=dollars.at(-1)??plain;
      if(match && match.index!=null){
        const price=measure(match[0]);const before=line.slice(0,match.index);
        const isZIP=!dollars.length && /\b(?:TX|TEXAS)\s*$/i.test(before) && /^\d{5}\s*$/.test(match[0]);
        if(price!=null && (dollars.length>0 || price>=10000) && !isZIP){
          listing.price=price;listing.query=(before+line.slice(match.index+match[0].length)).replace(/[\s,;\t|—–-]+$/g,"").trim();
        }
      }
    }
    listing.state=listing.query.match(/\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\s*$/i)?.[1]??"";
    listings.push(listing);
  }
  if(!listings.length)throw new Error("Paste at least one address and asking price.");
  return {listings,ignoredHeaders:[]};
}
export async function parseImport(text:string,kind:"csv"|"paste",signal?:AbortSignal):Promise<ParsedListings>{
  if(new Blob([text]).size>MAX_FILE_BYTES)throw new Error("Choose a file under 5 MB.");
  return kind==="csv"?listingsFromCSV(await parseCSVChunked(text,signal)):parsePaste(text);
}
