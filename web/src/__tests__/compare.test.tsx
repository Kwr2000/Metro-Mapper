import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CompareTable } from "../ComparePanel";
import { polygonFeatures } from "../map-polygons";
import { collection, ids, layer, registry } from "./workspace-fixtures";

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function(this: HTMLDialogElement) { this.setAttribute("open", ""); });
  HTMLDialogElement.prototype.close = vi.fn();
});
afterEach(cleanup);

it("comparison reuses popup uncertainty, annotations, dates, safe links and context grouping", () => {
  const estimate = layer("estimate", { demographic: true, group: "People", popup: [{ ...layer("x").popup[0], moe_field: "moe", reliability_field: "reliability", annotation_field: "annotation", display_field: "display" }] });
  const other = layer("other");
  const jurisdiction = layer("district", { join: "jurisdiction", popup: [
    { ...layer("x").popup[0], field: "name", label: "Name", format: "text" },
    { ...layer("x").popup[0], field: "link", label: "Finder", format: "link" }] });
  const census = structuredClone(collection);
  census.features[0].properties = { ...census.features[0].properties, measure: 100, moe: 35, reliability: "low reliability", annotation: "Census note", display: "100 or more" };
  const districtData = structuredClone(collection);
  districtData.features[0].properties = { name: "<script>District</script>", link: "https://district.example.test" };
  const { container } = render(<CompareTable registry={registry([estimate, other, jurisdiction])} areas={polygonFeatures(collection)} ids={[ids[0],ids[1]]}
    data={{ [estimate.data_url!]: census, [other.data_url!]: collection, [jurisdiction.data_url!]: districtData }} errors={{}} onClose={() => {}} />);
  expect(screen.getByText("100 or more")).toBeDefined();
  expect(screen.getByText(/± 35 \(90% MOE\)/)).toBeDefined();
  expect(screen.getByText("low reliability")).toBeDefined();
  expect(screen.getByText("Census note")).toBeDefined();
  expect(screen.getAllByText(/Source: Synthetic source · as of 2026-01-01 · Test data/)).toHaveLength(3);
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("<script>District</script>")).toBeDefined();
  expect(screen.getByRole("link", { name: "Open source page" }).getAttribute("href")).toBe("https://district.example.test/");
  const groups = container.querySelectorAll(".comparison-group > h3");
  expect([...groups].map((g) => g.textContent)).toEqual(["Environment", "People (context only)"]);
  expect(screen.queryAllByRole("button", { name: /sort|rank/i })).toHaveLength(0);
});
