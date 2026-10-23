import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// MapLibre needs WebGL, which jsdom lacks; the map itself is covered by browser checks.
vi.mock("../MapView", () => ({ MapView: () => <div data-testid="map" /> }));
import { App } from "../App";

const pub = (name: string) => readFileSync(join(__dirname, "../../public", name), "utf8");

describe("app shell", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const name = String(url).replace(/^\.?\//, "");
      try { return new Response(pub(name), { status: 200 }); } catch { return new Response("", { status: 404 }); }
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); window.location.hash = ""; });

  it("loads the registry, lists layers and labels test data", async () => {
    render(<App />);
    expect((await screen.findByTestId("test-banner")).textContent).toMatch(/Test data/);
    expect(screen.getAllByText("Test data").length).toBeGreaterThan(0);
    expect(screen.getByRole("contentinfo").textContent).toMatch(/Data sources and terms/);
  });

  it("sources page shows each layer's source and as-of", async () => {
    window.location.hash = "#/sources";
    render(<App />);
    const table = await screen.findByTestId("sources-table");
    expect(table.textContent).toMatch(/as of \d{4}-\d{2}-\d{2}/);
  });
});
