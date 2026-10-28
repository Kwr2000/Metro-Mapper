/** Exact decimal-rational port of mm/values.py; ties round to the nearest even $1,000. */
type Rational = { n: bigint; d: bigint };
function decimal(value: number): Rational {
  if (!Number.isFinite(value)) throw new Error("Invalid numeric input");
  const [mantissa,exp="0"] = String(value).toLowerCase().split("e"), [whole,fraction=""] = mantissa.split(".");
  const exponent = Number(exp)-fraction.length;
  const n = BigInt(whole+fraction);
  return exponent >= 0 ? {n:n*10n**BigInt(exponent),d:1n} : {n,d:10n**BigInt(-exponent)};
}
function thousand(n: bigint,d: bigint): number {
  const divisor = d*1000n, q = n/divisor, remainder = n%divisor;
  return Number((q+(remainder*2n > divisor || remainder*2n === divisor && q%2n !== 0n ? 1n : 0n))*1000n);
}
export function valueRange(marketValue: number | null, countyFips: string, rangePct: number | null, factor: number, levels: Record<string,number>, k=1): {low:number|null;mid:number|null;high:number|null} {
  if (rangePct === null || marketValue === null || marketValue === 0) return {low:null,mid:null,high:null};
  const level = levels[countyFips];
  if (![10,20].includes(rangePct) || marketValue < 0 || !(factor > 0) || !(level > 0) || !(k > 0)) throw new Error("Invalid appraisal-based range inputs");
  const v = decimal(marketValue), l = decimal(level), f = decimal(factor), c = decimal(k);
  const mid = thousand(v.n*l.d*f.n*c.n,v.d*l.n*f.d*c.d);
  return {low:thousand(BigInt(mid)*BigInt(100-rangePct),100n),mid,high:thousand(BigInt(mid)*BigInt(100+rangePct),100n)};
}

export type Calibration={v:1;fit_year:number;test_year:number;county:Record<string,number>;tract:Record<string,number>;test_data?:boolean};
export function validateCalibration(value:unknown):Calibration {
  const c=value as Calibration;
  const counties=["48453","48491","48209"];
  if(!c || c.v!==1 || !Number.isInteger(c.fit_year) || c.test_year!==c.fit_year-1 || !c.county || !c.tract || typeof c.tract!=="object" || Array.isArray(c.tract) ||
    Object.keys(c.county).length!==3 || !counties.every(f=>Number.isFinite(c.county[f])&&c.county[f]>0) ||
    Object.entries(c.tract).some(([t,k])=>!/^\d{11}$/.test(t)||!counties.includes(t.slice(0,5))||!Number.isFinite(k)||k<.8||k>1.25))throw new Error("Neighbourhood adjustments are unavailable");
  return c;
}
export function calibrationFactor(home:{id:string;block_group:string|null},cal:Calibration|null|undefined):number {
  if(!cal)return 1;
  const county=home.id.split(":")[0],tract=home.block_group?.slice(0,11);
  return tract?.startsWith(county)&&cal.tract[tract]!=null?cal.tract[tract]:cal.county[county]??1;
}
export function adjustmentText(k:number,year:number):string {
  const change=(k-1)*100;
  return `Neighbourhood adjustment of ${change>=0?"+":""}${change.toFixed(0)}% from ${year} home-purchase loans`;
}
