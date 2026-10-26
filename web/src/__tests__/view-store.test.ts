import { afterEach, describe, expect, it, vi } from "vitest";
import { encodeView, readView, registryView, type ViewState } from "../view-state";
import { readLocal, readShortlist, storageAvailable, writeLocal } from "../store";
import { ids, layer, registry } from "./workspace-fixtures";

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });
const view: ViewState = { camera: { center: [-97.7,30.3], zoom: 10 }, visible: ["example"], variants: { Environment: "bg" },
  filters: { example: { min: 0, max: 5 } }, colour: {}, compare: ids.slice(0,2) };
describe("share links", () => {
  it("round trips view state while preserving page routes", () => {
    const hash = encodeView(view);
    expect(hash.startsWith("#/?v=")).toBe(true);
    expect(readView(hash)).toEqual(view);
    expect(readView(hash.replace("#/", "#/sources"))).toEqual(view);
    expect(readView("#/methodology")).toBeNull();
  });
  it("never serializes notes, shortlist or nested extra fields", () => {
    const untrusted = { ...view, notes: "PRIVATE NOTE", shortlist: [{ id: ids[2], name: "PRIVATE NAME" }],
      camera: { ...view.camera!, note: "PRIVATE CAMERA" }, filters: { example: { min: 0, max: 5, notes: "PRIVATE RANGE" } } };
    const encoded = decodeURIComponent(encodeView(untrusted));
    expect(encoded).not.toMatch(/PRIVATE|notes|shortlist/);
    expect(readView(encodeView(untrusted))).toEqual(view);
  });
  it("handles damaged links, caps comparison and removes unknown registry entries", () => {
    for (const hash of ["#/?v=%", "#/?v=null", "#/?v=[]", '#/?v={"version":99}']) expect(readView(hash)).toBeNull();
    const many = readView(encodeView({ ...view, compare: ids }))!;
    expect(many.compare).toHaveLength(4);
    const reg = registry([layer("example", { variant: { family: "f", key: "bg", label: "BG" } })]);
    expect(registryView({ ...view, visible: ["unknown", "example"], filters: { unknown: { min: 0,max: 10 } } },reg)).toEqual({ ...view, visible: ["example"], filters: {} });
  });
});
describe("browser-only shortlist", () => {
  it("keeps notes in local storage, separately from view links", () => {
    expect(writeLocal("shortlist", [{ id: ids[0],name: "Area",note: "Private thought" }])).toBe(true);
    expect(readShortlist()[0].note).toBe("Private thought");
    expect(encodeView(view)).not.toContain("Private");
  });
  it("keeps a usable session fallback when local storage throws", () => {
    vi.spyOn(Storage.prototype,"getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype,"setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(storageAvailable()).toBe(false);
    const saved = [{ id: ids[0],name: "Area",note: "Session only" }];
    expect(writeLocal("shortlist", saved)).toBe(false);
    expect(readShortlist()).toEqual(saved);
    expect(readLocal("absent", 42)).toBe(42);
  });
  it("ignores malformed saved state", () => {
    writeLocal("shortlist", []);
    localStorage.setItem("metro-mapper:shortlist", '{"bad":true}'); expect(readShortlist()).toEqual([]);
    localStorage.setItem("metro-mapper:shortlist", '[{"id":"bad","name":"x","note":"x"}]'); expect(readShortlist()).toEqual([]);
  });
  it("uses new session notes when reads work but writes exceed quota", () => {
    writeLocal("shortlist", []);
    vi.spyOn(Storage.prototype,"setItem").mockImplementation(() => { throw new Error("quota"); });
    const next = [{ id: ids[0], name: "Area", note: "Newer than storage" }];
    expect(writeLocal("shortlist", next)).toBe(false);
    expect(readShortlist()).toEqual(next);
  });
});
