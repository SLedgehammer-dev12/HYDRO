import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NumberField, SelectField, TextField } from "./Field";

describe("Field controls accessibility", () => {
  it("associates SelectField label, help text and error alert with native select", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    const { rerender } = render(
      <SelectField
        label="Boşaltma yeri"
        value=""
        onChange={onChange}
        help="Başka bölüme aktarımda gerekmez."
        options={[
          { value: "", label: "Seçiniz" },
          { value: "other_section", label: "Başka test bölümüne aktarım" },
        ]}
      />,
    );

    const select = screen.getByLabelText("Boşaltma yeri");
    expect(select).toHaveClass("select");
    expect(select).toHaveAttribute("aria-describedby", `${select.id}-help`);

    await user.selectOptions(select, "other_section");
    expect(onChange).toHaveBeenCalledWith("other_section");

    rerender(
      <SelectField
        label="Boşaltma yeri"
        value=""
        onChange={onChange}
        error="Seçim zorunludur."
        options={[{ value: "", label: "Seçiniz" }]}
      />,
    );
    expect(select).toHaveAttribute("aria-invalid", "true");
    expect(select).toHaveAttribute("aria-describedby", `${select.id}-error`);
    expect(screen.getByRole("alert")).toHaveTextContent("Seçim zorunludur.");
  });

  it("wires TextField aria-describedby and parses Turkish decimal comma in NumberField", async () => {
    const user = userEvent.setup();
    const onNumberChange = vi.fn();
    const onTextChange = vi.fn();

    render(
      <>
        <TextField label="Kullanılan pig" value="" help="Örn. PIG-01" onChange={onTextChange} />
        <NumberField label="Basınç" unit="bar" value={null} onChange={onNumberChange} />
      </>,
    );

    const textInput = screen.getByLabelText("Kullanılan pig");
    expect(textInput).toHaveAttribute("aria-describedby", `${textInput.id}-help`);

    const numInput = screen.getByLabelText(/Basınç/);
    await user.type(numInput, "12,5");
    expect(onNumberChange).toHaveBeenLastCalledWith(12.5);

    await user.clear(numInput);
    await user.type(numInput, "12-3");
    expect(screen.getByRole("alert")).toHaveTextContent("Geçerli bir sayı girin");

    await user.tab();
    expect(numInput).toHaveValue("12-3");
    expect(numInput).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Geçerli bir sayı girin");
  });
});
