/** Port of mm/homes.py. Shared JSON vectors are read by tests, never duplicated. */
export type Address = { number: string; street_key: string; unit: string; zip: string };
const directions: Record<string,string> = Object.fromEntries("NORTH SOUTH EAST WEST NORTHEAST NORTHWEST SOUTHEAST SOUTHWEST".split(" ").map((v,i) => [v,"N S E W NE NW SE SW".split(" ")[i]]));
const dirs = new Set([...Object.keys(directions), ...Object.values(directions)]);
const suffixes: Record<string,string> = {};
for (const forms of [
  "AVE AVENUE AV AVEN AVENU AVN AVNUE", "BLVD BOULEVARD BOUL BOULV", "CIR CIRCLE CIRC CIRCL CRCL CRCLE",
  "CT COURT", "CV COVE", "XING CROSSING CRSSNG", "DR DRIVE DRIV DRV", "EXPY EXPRESSWAY EXP EXPW EXPRESS",
  "FWY FREEWAY FREEWY FRWAY FRWY", "HWY HIGHWAY HIGHWY HIWAY HIWY HWAY", "LN LANE", "LOOP LOOPS",
  "PKWY PARKWAY PARKWY PKWAY PKY", "PASS", "PATH PATHS", "PL PLACE", "PLZ PLAZA PLAZ", "PT POINT",
  "RD ROAD", "RUN", "SQ SQUARE SQR SQRE SQU", "ST STREET STR STRT", "TER TERRACE TERR", "TRCE TRACE TRACES",
  "TRL TRAIL TRAILS TR TRLS", "VW VIEW", "WAY", "ALY ALLEY", "BND BEND", "CRES CRESCENT", "HL HILL",
  "HLS HILLS", "HTS HEIGHTS", "HOLW HOLLOW", "RDG RIDGE", "RTE ROUTE", "WALK", "BCH BEACH", "GRV GROVE",
  "GLN GLEN", "LNDG LANDING", "MDW MEADOW", "PASSAGE PSGE", "RAMP", "VLY VALLEY", "VIS VISTA", "ROW",
]) { const words = forms.split(" "); for (const word of words) suffixes[word] = words[0]; }
const suffixForms = new Set(Object.values(suffixes));
const ordinals = Object.fromEntries("FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH THIRTEENTH FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH NINETEENTH TWENTIETH".split(" ")
  .map((word,i) => [word, ["1ST","2ND","3RD", ...Array.from({length:17},(_,n) => `${n+4}TH`)][i]]));
const units = new Set(["APT","APARTMENT","UNIT","STE","SUITE","BLDG"]);
const cities = ["AUSTIN","ROUND ROCK","GEORGETOWN","LEANDER","KYLE","CEDAR PARK","PFLUGERVILLE","HUTTO","SAN MARCOS","BUDA","LIBERTY HILL","DRIPPING SPRINGS","JARRELL","TAYLOR","WIMBERLEY","MANOR",
  "LAGO VISTA","DEL VALLE","LAKEWAY","DRIFTWOOD","SPICEWOOD","FLORENCE","MAXWELL","ELGIN","MANCHACA","GRANGER","THRALL","THE HILLS","JONESTOWN","WEST LAKE HILLS","BEE CAVE","UHLAND",
  "COUPLAND","BARTLETT","NIEDERWALD","MOUNTAIN CITY","WEBBERVILLE","SUNSET VALLEY","POINT VENTURE","MARBLE FALLS","BRIARCLIFF","VOLENTE","THORNDALE","CEDAR CREEK","CREEDMOOR","ROLLINGWOOD","WEIR",
  "NEW BRAUNFELS","WESTLAKE HILLS","BEE CAVES","FISCHER","HENLY","DRIPPING SPGS","DRIPPING SPRIGNS","DRIPPIING SPRINGS","AUSITN","AUSTN","PLUGERVILLE","NEIDERWALD","WIMBERELY","ROUND MOUNTAIN","WOODCREEK","BLANCO","SCHWERTNER","BERTRAM"]
  .map(c => c.split(" ")).sort((a,b) => b.length-a.length || a.join(" ").localeCompare(b.join(" ")));
const highways: [string,string][] = [
  ["(?:F M|FM|FARM TO MARKET)(?: ROAD| RD)?","FM"], ["(?:RANCH ROAD|RANCH RD|RR|RM|R M)","RR"],
  ["(?:STATE HIGHWAY|STATE HWY|SH|HWY|HIGHWAY)","SH"], ["(?:US HIGHWAY|US HWY|US|U S HIGHWAY|U S HWY|U S)","US"],
  ["(?:COUNTY ROAD|COUNTY RD|CR)","CR"], ["(?:INTERSTATE|IH|I H|I)","IH"],
];
const clean = (s?: string | null) => (s ?? "").toUpperCase().replace(/[.,#]/g," ").trim().replace(/\s+/g," ");
const unpad = (s: string) => s.replace(/(?<![A-Z0-9])0+(?=[0-9])/g,"");
const unit = (s: string) => unpad(clean(s).split(" ").filter(w => !units.has(w)).join(" "));

export function normalizeStreet(prefix?: string | null, name?: string | null, suffix?: string | null): string {
  const words = clean([prefix,name,suffix].filter(Boolean).join(" ")).split(" ").filter(Boolean).map(w => ordinals[w] ?? w);
  if (words.length && dirs.has(words[0])) words[0] = directions[words[0]] ?? words[0];
  if (words.length > 1 && dirs.has(words.at(-1)!)) words[words.length-1] = directions[words.at(-1)!] ?? words.at(-1)!;
  const end = words.length > 1 && dirs.has(words.at(-1)!) ? words.length-1 : words.length;
  if (end) words[end-1] = suffixes[words[end-1]] ?? words[end-1];
  const start = words.length > 2 && Object.values(directions).includes(words[0]) ? 1 : 0;
  if (end && end-1 === start+1 && /^[0-9]+$/.test(words[start]) && suffixForms.has(words[end-1])) {
    const n = Number(words[start]), last = n%100;
    words[start] = `${n}${last >= 10 && last <= 20 ? "TH" : ({1:"ST",2:"ND",3:"RD"} as Record<number,string>)[n%10] ?? "TH"}`;
  }
  let text = words.join(" ");
  for (const [pattern,replacement] of highways) {
    const re = new RegExp("^(?:(N|S|E|W|NE|NW|SE|SW) )?"+pattern+" (\\d+)\\b");
    if (re.test(text)) { text = text.replace(re,(_all,dir,n) => (dir ? dir+" " : "")+replacement+" "+Number(n)); break; }
  }
  return text;
}

export function normalizeQuery(text: string): Address {
  const original = (text ?? "").toUpperCase(); let normalized = clean(original);
  let zipMatch = /\b(\d{5})(?:-\d{4})?\s*$/.exec(normalized);
  if (zipMatch && (/\b(?:APT|APARTMENT|UNIT|STE|SUITE|BLDG)\s*$/.test(normalized.slice(0,zipMatch.index)) || /#\s*\d{5}\s*$/.test(original))) zipMatch = null;
  const zip = zipMatch?.[1] ?? "";
  if (zipMatch) normalized = normalized.slice(0,zipMatch.index).trim();
  normalized = normalized.replace(/\s+(?:TX|TEXAS)$/, "");
  if (original.includes(",")) {
    const chunks = original.split(","); let address = chunks[0];
    for (const chunk of chunks.slice(1)) { if (/^\s*(?:#|APT\b|APARTMENT\b|UNIT\b|STE\b|SUITE\b|BLDG\b)/.test(chunk)) address += " "+chunk; else break; }
    normalized = clean(address);
    if (zip) normalized = normalized.replace(new RegExp("\\s+"+zip+"(?:-\\d{4})?$"),"");
  }
  let words = normalized.split(" ").filter(Boolean), number = "";
  if (words.length && /^\d+[A-Z]?(?:[-/](?:\d+[A-Z]?|[A-Z]))*$/.test(words[0])) {
    number = unpad(words.shift()!);
    if (words.length && /^\d+\/\d+$/.test(words[0])) number += " "+words.shift();
    else if (words.length > 1 && !dirs.has(words[0]) && !suffixes[words[1]] && !highways.some(([p]) => new RegExp("^"+p+" \\d+\\b").test(words.join(" "))) && /^(?:[A-Z](?:[0-9]+|[/&-][A-Z])?|[0-9]+)$/.test(words[0])) number += " "+unpad(words.shift()!);
  }
  for (const city of cities) { if (words.length > city.length && words.slice(-city.length).join(" ") === city.join(" ")) { words = words.slice(0,-city.length); break; } }
  let foundUnit = ""; const marker = words.findIndex(w => units.has(w));
  if (marker >= 0) { foundUnit = unit(words.slice(marker+1).join(" ")); words = words.slice(0,marker); }
  else if (original.includes("#")) {
    const candidate = clean(original.split("#")[1].split(",")[0]).split(" ").filter(Boolean);
    if (candidate.length) { foundUnit = unit(candidate[0]); if (foundUnit && words.length && unit(words.at(-1)!) === foundUnit) words.pop(); }
  }
  words = normalizeStreet(null,words.join(" "),null).split(" ").filter(Boolean);
  if (!foundUnit) {
    const suffixPositions = words.map((w,i) => suffixes[w] && i > 0 ? i : -1).filter(i => i >= 0);
    if (suffixPositions.length) {
      let end = suffixPositions.at(-1)!+1; if (end < words.length && dirs.has(words[end])) end++;
      if (words.length === end+1 && /^[A-Z0-9][A-Z0-9/&-]*$/.test(words.at(-1)!)) { foundUnit = unit(words.at(-1)!); words = words.slice(0,end); }
    }
  }
  return { number, street_key: normalizeStreet(null,words.join(" "),null), unit:foundUnit, zip };
}
function streetName(key: string): string {
  const words = clean(key).split(" ").filter(Boolean);
  if (words.length > 1 && dirs.has(words[0])) words.shift();
  if (words.length > 1 && dirs.has(words.at(-1)!)) words.pop();
  if (words.length > 1 && suffixes[words.at(-1)!]) words.pop();
  return words.join(" ").replace(/[^A-Z0-9]/g,"");
}
export const shardId = (key: string) => (streetName(key)+"00").slice(0,2);
export const shardThird = (key: string) => (streetName(key)+"000")[2];
export function matches(row: Pick<Address,"number"|"street_key"|"unit"|"zip"> | Record<string,unknown>, query: Address): boolean {
  return (row.number ?? "") === query.number && (row.street_key ?? "") === query.street_key && (!query.unit || row.unit === query.unit) && (!query.zip || row.zip === query.zip);
}
