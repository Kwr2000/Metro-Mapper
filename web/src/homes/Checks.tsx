import type {Home,HomeMeta} from "./data";

const labels:Record<string,string>={flood1:"Flood (1%)",flood02:"Flood (0.2%)",highway:"Highway",major_road:"Major road",rail:"Rail",pre1978:"Before 1978",old_systems:"Year built",small_lot:"Lot size",range_flags:"Range notes"};
export function decodeChecks(value:string|null|undefined):{code:string;distance?:number;label?:string;zone?:string}[]{
 const result=[];
 for(const entry of (value??"").split(",").filter(Boolean)){
  const [code,a,b,...extra]=entry.split(":");if(!labels[code]||extra.length)continue;
  try{
   if(code==="flood1"){if(a===undefined||b!==undefined)continue;result.push({code,zone:decodeURIComponent(a)});}
   else if(["highway","major_road","rail"].includes(code)){
    if(!/^\d+$/.test(a??"")||b===undefined)continue;result.push({code,distance:Number(a),label:decodeURIComponent(b)});
   }else if(a===undefined)result.push({code});
  }catch{/* Malformed cells stay unavailable; never turn them into a measurement. */}
 }
 return result;
}
export function checkItems(home:Home,meta:HomeMeta,rangeFlags?:string){
 const model=meta.checks;if(!model)return [];
 const county=meta.counties[home.county],cad=`${meta.sources[county?.source]??home.county+" appraisal district"} · ${home.value_year??"Not available"} records · export ${home.certified??"Not available"}`;
 return decodeChecks(home.checks).flatMap(item=>{
  if(item.code==="pre1978"&&!(home.year_built!=null&&home.year_built>0&&home.year_built<1978))return [];
  if(item.code==="old_systems"&&!(home.year_built!=null&&home.year_built>=1978&&home.year_built<1990))return [];
  const spatial=["flood1","flood02","highway","major_road","rail"].includes(item.code);
  if(spatial&&(home.placed!=="parcel"||home.lon==null||home.lat==null))return [];
  const fema=item.code.startsWith("flood"),source=model.sources[fema?"fema":"osm"];
  if(spatial&&!source?.available)return [];
  const text=item.code==="range_flags"?rangeFlags||(home.range_flags??"").split(",").map(c=>meta.value_range?.flags[c]??"Range note not available").join("; "):
   model.texts[item.code]?.replace("{distance}",String(item.distance)).replace("{label}",item.label?` (${item.label})`:"").replace("{zone}",item.zone?`stored zone labels: ${item.zone.split("/").join(", ")}`:"zone label not available").replace("{year}",String(home.year_built));
  if(!text)return [];
  const calibration=meta.value_range?.calibration;
  const rangeSource=item.code==="range_flags"?` · ${meta.value_range?.study??""} ${meta.value_range?.study_year??""} · FHFA ${meta.value_range?.hpi.as_of??"Not available"}`+
   ((home.range_flags??"").split(",").includes("cal")&&calibration?` · FFIEC HMDA fitting year ${calibration.fit_year}, held-out year ${calibration.test_year}`:""):"";
  const provenance=spatial?`${source.source} · ${fema?"retrieved":"extract"} ${source.dates.join(", ")||"Not available"}${fema?` · NFHL versions: ${source.versions?.join(", ")||"Not available"}. ${model.zone_note}`:`. ${model.distance_note}`}`:cad+(item.code==="small_lot"?`. ${model.lot_note}`:"")+rangeSource;
  return [{code:item.code,label:labels[item.code],text,source:provenance,test:spatial&&source.test_data}];
 });
}
export function ThingsToCheck({home,meta,compact=false,rangeFlags}:{home:Home;meta:HomeMeta;compact?:boolean;rangeFlags?:string}){
 const items=checkItems(home,meta,rangeFlags),model=meta.checks,located=home.placed==="parcel"&&home.lon!=null&&home.lat!=null;
 const content=<><p>{model?.header??"Things that often go with a lower price. None of them is a verdict; check the home."}</p>
  {!model||home.checks===undefined?<p>Property checks are not available from this publication.</p>:<>
   {!located&&<p>Location checks not available (no map point)</p>}
   {located&&["fema","osm"].map(key=>!model.sources[key]?.available&&<p key={key}>{key==="fema"?"FEMA":"OpenStreetMap"} location checks not available from the stored maps.</p>)}
   {!items.length&&<p>No listed facts met these thresholds in the available records. This is not a complete inspection.</p>}
   <ul className="home-checks-list">{items.map(item=><li key={item.code}><p>{item.text}</p><small>{item.source}{item.test?" · Test data":""}</small></li>)}</ul>
   {items.some(i=>i.test)&&<p className="badge">Test data · location checks</p>}
  </>}
 </>;
 return compact?<details className="home-checks batch-checks"><summary title={items.map(i=>i.text).join(" ")}>⚑ {items.length?items.map(i=>i.label).join(" · "):"Things to check"}</summary>{content}</details>:<section className="home-checks" aria-label="Things to check"><h3>Things to check</h3>{content}</section>;
}
