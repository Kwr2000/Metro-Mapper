import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { bindPopupClose, popupContent, popupFieldHtml, popupValueHtml, shownFields } from "../popup";

describe("popups", () => {
  it("leaves out empty optional notes but keeps empty data as Not available", () => {
    const base = { format: "text", moe_field: null, reliability_field: null, annotation_field: null, display_field: null } as const;
    const fields = [{ ...base, field: "rate", label: "Rate", hide_if_empty: false },
                    { ...base, field: "note", label: "Note", hide_if_empty: true }];
    expect(shownFields(fields, { rate: null, note: null }).map((f) => f.field)).toEqual(["rate"]);
    expect(shownFields(fields, { rate: 1, note: "Few residents" }).map((f) => f.field)).toEqual(["rate", "note"]);
    expect(popupFieldHtml(fields[0], { rate: null })).toBe("Not available");
  });

  it("renders a source link without allowing HTML injection", () => {
    const html = popupValueHtml('https://example.gov/case?id=1&label="hello"', "link");
    expect(html).toContain('href="https://example.gov/case?id=1&amp;label=%22hello%22"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("escapes text and rejects executable, relative and credential URLs", () => {
    for (const value of ["javascript:alert(1)", "data:text/html,<script>", "/case/1", "https://user:pass@example.gov/"]) {
      expect(popupValueHtml(value, "link")).not.toContain("<a ");
    }
    expect(popupValueHtml('<img onerror="alert(1)">', "text")).toBe("&lt;img onerror=&quot;alert(1)&quot;&gt;");
    expect(popupValueHtml(null, "link")).toBe("Not available");
  });

  it("keeps the close button outside the scroll body and cleans up listeners", () => {
    const element = document.createElement("div");
    element.innerHTML = popupContent("<p>Long content</p>"); document.body.append(element);
    const close = vi.fn(), dispose = bindPopupClose(element, close);
    const button = element.querySelector<HTMLButtonElement>('[aria-label="Close popup"]')!;
    expect(element.querySelector(".popup-scroll")?.contains(button)).toBe(false);
    fireEvent.click(button); expect(close).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" }); expect(close).toHaveBeenCalledTimes(2);
    dispose(); fireEvent.keyDown(document, { key: "Escape" }); expect(close).toHaveBeenCalledTimes(2);
    element.remove();
  });

  it("shows margins of error and flags unreliable estimates", () => {
    const field = { field: "share", label: "Share estimate", format: "percent" as const, moe_field: "moe",
      reliability_field: "reliability", annotation_field: "annotation", display_field: null, hide_if_empty: false };
    const html = popupFieldHtml(field, { share: 0.25, moe: 0.1, reliability: "low reliability", annotation: "<script>" });
    expect(html).toContain("25.0%"); expect(html).toContain("10.0 pp");
    expect(html).toContain('class="reliability-low"'); expect(html).toContain("&lt;script&gt;");
    const missing = popupFieldHtml(field, { share: null, moe: null, reliability: "estimate unavailable" });
    expect(missing).toContain("MOE unavailable"); expect(missing).toContain("Not available"); expect(missing).not.toContain("0.0%");
  });

  it("shows a Census range in place of a capped median", () => {
    const field = { field: "income", label: "Income estimate", format: "currency" as const, moe_field: "moe",
      reliability_field: null, annotation_field: null, display_field: "income_display", hide_if_empty: false };
    const html = popupFieldHtml(field, { income: 250001, moe: null, income_display: "$250,000 or more" });
    expect(html).toContain("$250,000 or more"); expect(html).not.toContain("250,001");
    expect(popupFieldHtml(field, { income: 90000, moe: 5000 })).toContain("$90,000");
  });
});
