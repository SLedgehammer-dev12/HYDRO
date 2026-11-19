import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { SiteSurveyPanel } from "./SiteSurveyPanel";
import { createEmptyInputs } from "../../lib/mock";
import { useAppStore } from "../../store/useAppStore";

describe("SiteSurveyPanel accessibility, seeding, paste and validation", () => {
  beforeEach(() => {
    const empty = createEmptyInputs();
    empty.geometry = { outside_diameter_mm: 406.4, wall_thickness_mm: 8.74, length_m: 2000 };
    empty.section_profile = {
      highest_elevation_m: 320,
      lowest_elevation_m: 180,
      start_elevation_m: 200,
      end_elevation_m: 310,
      design_pressure_bar: 80,
      smys_mpa: 450,
    };
    useAppStore.setState({ inputs: empty, dirty: false });
  });

  it("shows approximate warnings initially and seeds real 4-point profile and default equipment", async () => {
    const user = userEvent.setup();
    render(<SiteSurveyPanel totalLength={2000} />);

    expect(screen.getByText("Yaklaşık Profil (4 nokta)")).toBeInTheDocument();
    expect(screen.getByText("Varsayılan Yerleşim")).toBeInTheDocument();
    expect(screen.getByText("Yaklaşık kot profili kullanılıyor")).toBeInTheDocument();
    expect(screen.getByText("Varsayılan ekipman yerleşimi gösteriliyor")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /4 Kottan Başlat/i }));
    await user.click(screen.getByRole("button", { name: /Varsayılanlardan Başlat/i }));

    expect(screen.getByText("Gerçek Profil (4 nokta)")).toBeInTheDocument();
    expect(screen.getByText("Gerçek Ekipman (5)")).toBeInTheDocument();
    expect(useAppStore.getState().inputs.profile_points).toHaveLength(4);
    expect(useAppStore.getState().inputs.equipment).toHaveLength(5);

    const regions = screen.getAllByRole("region");
    expect(regions).toHaveLength(2);
    for (const region of regions) {
      expect(region).toHaveAttribute("aria-labelledby");
    }
  });

  it("imports pasted TSV profile coordinates via CSV/TSV paste panel", async () => {
    const user = userEvent.setup();
    render(<SiteSurveyPanel totalLength={2000} />);

    await user.click(screen.getByRole("button", { name: /CSV \/ TSV Yapıştır/i }));
    const textarea = screen.getByLabelText(/İstasyon \(m veya KP\) ve Kot \(m\)/i);
    await user.type(textarea, "0\t100\n1000\t220\n2000\t180");
    await user.click(screen.getByRole("button", { name: "Uygula" }));

    expect(useAppStore.getState().inputs.profile_points).toEqual([
      { station_m: 0, elevation_m: 100 },
      { station_m: 1000, elevation_m: 220 },
      { station_m: 2000, elevation_m: 180 },
    ]);
    expect(screen.getByText("Gerçek Profil (3 nokta)")).toBeInTheDocument();
  });

  it("defers aria-invalid and aria-describedby validation feedback until after blur", async () => {
    const user = userEvent.setup();
    useAppStore.getState().setProfilePoints([
      { station_m: 0, elevation_m: 100 },
      { station_m: 1000, elevation_m: 200 },
    ]);
    render(<SiteSurveyPanel totalLength={2000} />);

    const elevInput = screen.getByLabelText("Kot noktası 1 kot");
    expect(elevInput).toHaveAttribute("aria-invalid", "false");
    expect(elevInput).not.toHaveAttribute("aria-describedby");

    await user.clear(elevInput);
    await user.type(elevInput, "99999");
    expect(elevInput).toHaveAttribute("aria-invalid", "false");

    await user.tab();
    expect(elevInput).toHaveAttribute("aria-invalid", "true");
    const errId = elevInput.getAttribute("aria-describedby");
    expect(errId).toBeTruthy();
    expect(document.getElementById(errId!)).toHaveTextContent("-500 ile 10.000 m");

    await user.clear(elevInput);
    await user.type(elevInput, "250");
    // Mid-typing must not commit partial value before blur
    expect(useAppStore.getState().inputs.profile_points[0].elevation_m).toBe(100);
    await user.tab();
    expect(elevInput).toHaveAttribute("aria-invalid", "false");
    expect(elevInput).not.toHaveAttribute("aria-describedby");
    expect(useAppStore.getState().inputs.profile_points[0].elevation_m).toBe(250);
  });
});
