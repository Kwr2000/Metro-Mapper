import type {HomeMeta} from "../homes/data";
import {categoryLabel} from "../homes/HomeCard";
import {published,type BatchRow} from "./model";

/** Quoted CSV, with user-controlled text protected from spreadsheet formula evaluation. */
function cell(value:unknown):string {
  let text=value==null?"":String(value);
  if(typeof value==="string" && /^[\s]*[=+@-]/.test(text))text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
}
export function exportTable(rows:BatchRow[],meta:HomeMeta):string {
  const show=published(meta);
  const header=["Address","County","Category","Listing beds","Listing baths","Listing sq ft","Appraisal living sq ft","Appraisal year built","Asking price","Asking per appraisal sq ft",
    ...(show?["Range low","Range centre","Range high","Position percent of centre","Range width percent","Range flags"]:[]),
    "Approx neighbourhood percentile","Neighbourhood homes","Days on market","HOA per month","Home id","Listing URL","CAD source","Value as of","CAD export date","FHFA as of","Study year","Test data"];
  const lines=[header.map(cell).join(",")];
  for(const row of rows){if(!row.home||!row.metrics)continue;const h=row.home,m=row.metrics,l=row.listing,c=meta.counties[h.county];
    const values=[h.situs,h.county,categoryLabel(h.category),l.beds,l.baths,l.sqft,h.living_area,h.year_built,l.price,m.psf,
      ...(show?[m.low,m.mid,m.high,m.position,m.rangePct,m.flags]:[]),m.percentile,m.n,l.days,l.hoa,h.id,l.url,meta.sources[c?.source]??c?.source,c?.value_as_of?.join("; "),h.certified,
      meta.value_range?.hpi.as_of,meta.value_range?.study_year,m.testData?"Test data":""];
    lines.push(values.map(cell).join(","));
  }
  return "\uFEFF"+lines.join("\r\n")+"\r\n";
}
export function downloadCSV(text:string){
  const url=URL.createObjectURL(new Blob([text],{type:"text/csv;charset=utf-8"}));
  const a=document.createElement("a");a.href=url;a.download="metro-mapper-listings.csv";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),0);
}
