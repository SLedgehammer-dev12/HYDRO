import { describe, expect, it } from "vitest";
import {
  decisionLabel,
  fixed,
  fmt,
  formatInput,
  num,
  parseNumber,
  statusTone,
} from "./format";

describe("parseNumber", () => {
  it("parses Turkish and US decimal formats accurately", () => {
    expect(parseNumber("12,5")).toBe(12.5);
    expect(parseNumber("1.234,56")).toBe(1234.56);
    expect(parseNumber("1,234.56")).toBe(1234.56);
    expect(parseNumber("1234.56")).toBe(1234.56);
    expect(parseNumber("-0,75")).toBe(-0.75);
  });

  it("returns null for empty or sign-only inputs and NaN for unparseable text", () => {
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("   ")).toBeNull();
    expect(parseNumber("+")).toBeNull();
    expect(parseNumber("-")).toBeNull();
    expect(Number.isNaN(parseNumber("12-3"))).toBe(true);
  });
});

describe("number formatting helpers", () => {
  it("formats numbers in tr-TR locale and handles invalid inputs", () => {
    expect(num(1234.5, 2)).toBe("1.234,5");
    expect(fixed(12.3, 3)).toBe("12,300");
    expect(formatInput(1234.5, 4)).toBe("1234,5");
    expect(num(null)).toBe("—");
    expect(num(Number.NaN)).toBe("—");
    expect(fmt.bar(75.5)).toBe("75,5 bar");
    expect(fmt.bytes(1536)).toBe("1,5 KB");
  });

  it("maps decision status labels and UI tones", () => {
    expect(decisionLabel(null)).toBe("Bekliyor");
    expect(decisionLabel("BASARILI")).toBe("Başarılı");
    expect(decisionLabel("BASARISIZ")).toBe("Başarısız");
    expect(statusTone("BASARILI")).toBe("pass");
    expect(statusTone("BASARISIZ")).toBe("fail");
    expect(statusTone("KATSAYI GUNCELLENMELI")).toBe("warning");
    expect(statusTone("BEKLIYOR")).toBe("pending");
  });
});
