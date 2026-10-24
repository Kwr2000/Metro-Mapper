import { useEffect, useState } from "react";
import { asOfLabel, freshnessLabel, loadJSON, type HealthReport, type Registry } from "./registry";
import { contextGroups, PEOPLE, PEOPLE_NOTE } from "./areas";

const REPO = "https://github.com/Kwr2000/metro-mapper";
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-US", { timeZone: "America/Chicago" }) : "—");

export function SourcesPage({ registry, error }: { registry: Registry | null; error: string | null }) {
  if (error) return <main className="page"><p className="error">Registry unavailable: {error}</p></main>;
  if (!registry) return <main className="page"><p className="muted">Loading…</p></main>;
  return (
    <main className="page" data-testid="sources-page">
      <h1>Data sources and terms</h1>
      <p>Every map layer shows its source and the date its data describes. Layers marked
        <span className="badge badge-fixture_only">Test data</span> show made-up sample data, not real data.</p>
      <p className="small muted">Full source notes, licenses and how each was checked:{" "}
        <a href={`${REPO}/blob/main/docs/SOURCES.md`} target="_blank" rel="noopener noreferrer">docs/SOURCES.md</a>.
        Registry compiled {when(registry.compiled_at)}.</p>
      <table className="grid" data-testid="sources-table">
        <thead><tr><th>Layer</th><th>Source</th><th>License / terms</th><th>Refresh</th><th>Data</th></tr></thead>
        {contextGroups(registry).map(([group, layers]) => <tbody key={group}>
          <tr><th colSpan={5} scope="rowgroup">{group}{group === PEOPLE && <p className="small muted">{PEOPLE_NOTE}</p>}</th></tr>
          {layers.map((l) => (
            <tr key={l.id}>
              <th scope="row" data-label="Layer">{l.title}<div className="small muted">{l.group}</div></th>
              <td data-label="Source">{l.attribution}{l.disclaimer && <div className="small muted">{l.disclaimer}</div>}</td>
              <td data-label="License / terms">{l.license || "No license stated"}</td>
              <td data-label="Refresh">{l.refresh.replace("_", " ")}</td>
              <td data-label="Data"><span className={`badge badge-${l.freshness}`}>{freshnessLabel(l)}</span> <span className="small">{asOfLabel(l)}</span></td>
            </tr>
          ))}
        </tbody>)}
      </table>
      <p className="small muted">Basemap: {registry.basemap.attribution}.</p>
    </main>
  );
}

export function HealthPage() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadJSON<HealthReport>("health.json").then(setReport, (e) => setError(String(e))); }, []);
  if (error) return <main className="page"><p className="error">Health report unavailable: {error}</p></main>;
  if (!report) return <main className="page"><p className="muted">Loading…</p></main>;
  return (
    <main className="page">
      <h1>Source health</h1>
      <p className="muted">Generated {when(report.generated_at)}. Only live runs count as current data.</p>
      <table className="grid" data-testid="health-adapters">
        <thead><tr><th>Source</th><th>Status</th><th>Last run</th><th>Last success</th><th>Calls today</th><th>Calls this month</th></tr></thead>
        <tbody>
          {report.adapters.map((a) => (
            <tr key={a.adapter}>
              <td data-label="Source"><code>{a.adapter}</code><div className="muted small">{a.cadence}</div></td>
              <td data-label="Status"><span className={`badge badge-${a.freshness}`}>{a.freshness.replace("_", " ")}</span>
                {a.last_errors.length > 0 && <div className="error small">{a.last_errors[0]}</div>}</td>
              <td data-label="Last run">{when(a.last_run)}<div className="muted small">{a.last_status ?? ""}</div></td>
              <td data-label="Last success">{when(a.last_success)}</td>
              <td data-label="Calls today">{a.budget_per_day ? `${a.calls_today} / ${a.budget_per_day}` : a.calls_today}</td>
              <td data-label="Calls this month">{a.budget_per_month ? `${a.calls_this_month} / ${a.budget_per_month}` : a.calls_this_month}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}

export function AboutPage() {
  return (
    <main className="page prose">
      <h1>About Metro Mapper</h1>
      <p>A map of the Austin metro (Travis, Williamson and Hays counties) for understanding the housing
        market and comparing small areas. It does not list homes for sale.</p>
      <h2>How the numbers work</h2>
      <ul>
        <li><strong>Sourced and dated.</strong> Every number shows where it comes from and the date it describes.
          Estimates are shown as ranges, with what drives them.</li>
        <li><strong>No sale prices.</strong> Texas does not disclose home sale prices. Home values on this site
          will be <em>appraisal-based value ranges</em>, not market prices or judgments of a good deal.</li>
        <li><strong>No invented detail.</strong> Where data doesn't exist for a small area, the site says
          “Not available” or shows a larger area, clearly labeled. Missing data is never shown as zero.</li>
        <li><strong>Demographics are context only.</strong> Census demographics, including race and ethnicity,
          are map layers and filters. They are never used in any score, ranking or value estimate.</li>
        <li><strong>Nothing about people.</strong> Owner names, mailing addresses and exemption details are
          removed before anything is published.</li>
      </ul>
      <p>Read the <a href="#/methodology">methodology</a> for units, coverage and uncertainty. Source terms and licenses: see{" "}
        <a href="#/sources">Data sources and terms</a>.</p>
      <p className="small muted">Code: <a href={REPO} target="_blank" rel="noopener noreferrer">{REPO.replace("https://", "")}</a> (MIT).
        Map data © OpenStreetMap contributors (ODbL).</p>
    </main>
  );
}

export function Footer() {
  return (
    <footer className="footer small muted">
      <a href="#/sources">Data sources and terms</a> · <a href="#/methodology">Methodology</a> · Map data © OpenStreetMap contributors ·{" "}
      Values are sourced and dated; Texas home sale prices are not public.
    </footer>
  );
}
