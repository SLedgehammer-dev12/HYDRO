import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionCard } from "./DecisionCard";
import type { Decision } from "../../lib/types";

describe("DecisionCard", () => {
  it("renders full long safety warnings in compact mode without ellipsis truncation", () => {
    const decision: Decision = {
      status: "BASARISIZ",
      title: "Basınçlandırma izleme red",
      summary:
        "Azami artis hizi = 0.000 bar/dk (limit 1). %95 SMYS sonrasi basilan su = 2.5000 m³ (limit 2.0000 m³). BASINCLANDIRMAYI DURDURUN ve Idarenin talimatini bekleyin (14.2). 2 adimda 0,2 bar izleme araligi asildi.",
      rule: "%80-%95 SMYS artis hizi <= 1 bar/dk; %95 SMYS sonrasi basilan su <= %0.2 toplam hacim",
      margin: -0.5,
    };

    render(<DecisionCard decision={decision} testName="Basınçlandırma izleme" compact />);

    const summaryEl = screen.getByText(/2 adimda 0,2 bar izleme araligi asildi\./);
    expect(summaryEl).toBeInTheDocument();
    expect(summaryEl.textContent).toBe(decision.summary);
    expect(summaryEl.textContent).not.toContain("…");
    expect(screen.getByText(decision.rule)).toBeInTheDocument();
  });

  it("renders pending placeholder when decision is missing", () => {
    render(<DecisionCard decision={null} testName="Hava İçerik Testi" />);
    expect(screen.getByText("Bekliyor")).toBeInTheDocument();
    expect(screen.getByText(/henüz değerlendirme yapılmadı/i)).toBeInTheDocument();
  });
});
