import content from "./content/methodology.md?raw";

/** Tiny text-only Markdown subset: headings and paragraphs, never HTML. */
export function MethodologyPage() {
  return <main className="page prose">{content.split(/\n\s*\n/).map((block, i) => {
    if (block.trim().startsWith("<!--")) return null;
    if (block.startsWith("# ")) return <h1 key={i}>{block.slice(2)}</h1>;
    if (block.startsWith("## ")) return <h2 key={i}>{block.slice(3)}</h2>;
    return <p key={i}>{block.replace(/\n/g, " ")}</p>;
  })}</main>;
}
