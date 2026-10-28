/** Same bucket function in the web build and browser. Public IDs only, never prices. */
export function idBucket(id:string):string {
  let hash=2166136261;for(let i=0;i<id.length;i++)hash=Math.imul(hash^id.charCodeAt(i),16777619)>>>0;
  return (hash%256).toString(16).padStart(2,"0");
}
