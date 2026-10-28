import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {HomePage} from "../homes/HomePage";
import {homeData} from "../homes/data";
import {home,meta} from "./homes-fixtures";
beforeEach(()=>{window.history.replaceState(null,"","#/home");vi.spyOn(homeData,"meta").mockResolvedValue({...meta,value_range:{...meta.value_range!,published:false}});});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it("handles no match with the normalized form and a retry hint",async()=>{
 vi.spyOn(homeData,"search").mockResolvedValue([]);render(<HomePage hash="#/home" registry={null} onShowMap={vi.fn()}/>);
 fireEvent.change(screen.getByRole("searchbox"),{target:{value:"100 North Test Street #2, Austin TX 78704"}});fireEvent.submit(screen.getByRole("searchbox").closest("form")!);
 expect(await screen.findByText(/Not found in the 2026/)).toBeDefined();expect(screen.getByText(/Normalized search: 100 N TEST ST Unit 2 78704/)).toBeDefined();expect(screen.getByText(/Try without the unit/)).toBeDefined();
});
it("moves through ambiguous matches by keyboard, focuses the chosen card and links only its id",async()=>{
 vi.spyOn(homeData,"search").mockResolvedValue([home,{...home,id:"48491:R124",unit:"3",situs:"100 TEST ST #3"}]);
 render(<HomePage hash="#/home" registry={null} onShowMap={vi.fn()}/>);fireEvent.change(screen.getByRole("searchbox"),{target:{value:"100 Test St"}});fireEvent.submit(screen.getByRole("searchbox").closest("form")!);
 const region=await screen.findByRole("region",{name:"Matching homes"}),buttons=region.querySelectorAll("button");await waitFor(()=>expect(document.activeElement).toBe(buttons[0]));fireEvent.keyDown(buttons[0],{key:"ArrowDown"});expect(document.activeElement).toBe(buttons[1]);fireEvent.click(buttons[1]);
 await waitFor(()=>expect(document.activeElement).toBe(screen.getByRole("heading",{name:"100 TEST ST #3"})));expect(new URLSearchParams(window.location.hash.split("?")[1]).get("id")).toBe("48491:R124");expect(window.location.hash).not.toContain("TEST");
});
it("loads a fresh id link and cancels late searches on unmount",async()=>{
 vi.spyOn(homeData,"byId").mockResolvedValue(home);const first=render(<HomePage hash="#/home?id=48491%3AR123" registry={null} onShowMap={vi.fn()}/>);expect(await screen.findByRole("heading",{name:home.situs!})).toBeDefined();first.unmount();
 let resolve!:(v:typeof home[])=>void;vi.spyOn(homeData,"search").mockReturnValue(new Promise(r=>{resolve=r;}));window.history.replaceState(null,"","#/home");
 const later=render(<HomePage hash="#/home" registry={null} onShowMap={vi.fn()}/>);fireEvent.change(screen.getByRole("searchbox"),{target:{value:"100 TEST ST"}});fireEvent.submit(screen.getByRole("searchbox").closest("form")!);later.unmount();window.history.replaceState(null,"","#/methodology");resolve([home]);await new Promise(r=>setTimeout(r,0));expect(window.location.hash).toBe("#/methodology");
});

it("strips unsolicited parameters from a home link without accepting a price",async()=>{
 localStorage.clear();vi.spyOn(homeData,"byId").mockResolvedValue(home);
 window.history.replaceState(null,"","#/home?id=48491%3AR123&asking=987654");
 render(<HomePage hash="#/home?id=48491%3AR123&asking=987654" registry={null} onShowMap={vi.fn()}/>);
 expect(await screen.findByRole("heading",{name:home.situs!})).toBeDefined();
 expect(window.location.hash).toBe("#/home?id=48491%3AR123");expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("");
});
