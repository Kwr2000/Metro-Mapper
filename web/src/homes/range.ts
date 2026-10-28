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
export function valueRange(marketValue: number | null, countyFips: string, rangePct: number | null, factor: number, levels: Record<string,number>): {low:number|null;mid:number|null;high:number|null} {
  if (rangePct === null || marketValue === null || marketValue === 0) return {low:null,mid:null,high:null};
  const level = levels[countyFips];
  if (![10,20].includes(rangePct) || marketValue < 0 || !(factor > 0) || !(level > 0)) throw new Error("Invalid appraisal-based range inputs");
  const v = decimal(marketValue), l = decimal(level), f = decimal(factor);
  const mid = thousand(v.n*l.d*f.n,v.d*l.n*f.d);
  return {low:thousand(BigInt(mid)*BigInt(100-rangePct),100n),mid,high:thousand(BigInt(mid)*BigInt(100+rangePct),100n)};
}
