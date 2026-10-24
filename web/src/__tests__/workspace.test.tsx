import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MapViewProps } from "../MapView";
vi.mock("../MapView", () => ({ MapView: (props: MapViewProps) => <button onClick={() => props.onSelectArea(props.areas[0] ? String(props.areas[0].properties?.geoid) : null)}>Inspect area</button> }));
import { Workspace } from "../Workspace";
import { readView } from "../view-state";
import { collection, ids, layer, registry } from "./workspace-fixtures";

const base = layer("boundaries", { group: "Areas", default_visible: true, popup: [{ ...layer("x").popup[0], field: "name", label: "Name", format: "text" }] });
const measure = layer("measure");
const context = layer("context", { group: "People", demographic: true, default_visible: true });
beforeEach(() => {
  window.history.replaceState(null,"","#/"); localStorage.clear();
  vi.stubGlobal("fetch",vi.fn(async () => new Response(JSON.stringify(collection),{status:200})));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("loads each bundle once, starts People off and keeps notes out of the view URL", async () => {
  render(<Workspace registry={registry([base,measure,context])} active />);
  await screen.findByText("5 of 5 areas match");
  expect(readView(window.location.hash)?.visible).toEqual([base.id]);
  fireEvent.click(screen.getByRole("button",{name:"Inspect area"}));
  fireEvent.click(screen.getByRole("button",{name:"Save area"}));
  fireEvent.click(screen.getByRole("button",{name:"Add to compare"}));
  fireEvent.click(screen.getByRole("button",{name:"Shortlist"}));
  fireEvent.change(screen.getByRole("textbox",{name:/Private note/}),{target:{value:"PRIVATE WORKSPACE NOTE"}});
  expect(localStorage.getItem("metro-mapper:shortlist")).toContain("PRIVATE WORKSPACE NOTE");
  expect(decodeURIComponent(window.location.hash)).not.toContain("PRIVATE");
  expect(readView(window.location.hash)?.compare).toEqual([ids[0]]);
  fireEvent.click(screen.getByRole("button",{name:"Filters"}));
  const row = document.querySelector(`[data-filter-id="${measure.id}"]`)!;
  fireEvent.click(row.querySelector("input[type=checkbox]")!);
  await waitFor(() => expect(document.querySelectorAll("input[type=number]").length).toBe(2));
  expect(vi.mocked(fetch).mock.calls.filter(([url]) => url === measure.data_url)).toHaveLength(1);
  fireEvent.click(screen.getByRole("button",{name:"Clear filters"}));
  expect(readView(window.location.hash)?.filters).toEqual({});
});

it("states the storage limitation while retaining a usable session shortlist", async () => {
  vi.spyOn(Storage.prototype,"getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype,"setItem").mockImplementation(() => { throw new Error("blocked"); });
  render(<Workspace registry={registry([base])} active />);
  await screen.findByText("5 of 5 areas match");
  fireEvent.click(screen.getByRole("button",{name:"Inspect area"}));
  fireEvent.click(screen.getByRole("button",{name:"Save area"}));
  fireEvent.click(screen.getByRole("button",{name:"Shortlist"}));
  expect(screen.getByText(/won't be kept/)).toBeDefined();
  expect(screen.getByRole("textbox",{name:/Private note/})).toBeDefined();
});
