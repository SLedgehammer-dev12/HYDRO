# Formula Source Map

## Source Document

- Uploaded file: `c:\Users\omere\OneDrive\Desktop\techvol3_20240823_143533.pdf`
- Document family: `GAIL-STD-PL-DOC-TS-012`

## Program Formula -> Document Mapping

### 1. Pressurization / Air Content Water Volume

Program logic reduces the specification equation to the hydrotest case where the air
content check is performed with a `1.0 bar` pressure rise.

- Program-side implementation:
  - `Vp = ((0.884 x ri / s) + A) x 10^-6 x Vt x K`
  - Source code: `hidrostatik_test/domain/hydrotest_core.py`
- Document-side exact form:
  - `Vp = (0.884 r1/t + A) x 10^-6 x Vt x P x K`
  - PDF page: `56`

### 2. Temperature-Corrected Pressure Change

- Program-side implementation:
  - `DeltaP = (B x DeltaT) / ((0.884 x ri / s) + A)`
  - Source code: `hidrostatik_test/domain/hydrotest_core.py`
- Document-side exact form:
  - `P = B x T / { (0.884 r1 / t) + A }`
  - PDF page: `57`

### 3. Coefficient Definitions

- `A`
  - Document definition: water isothermal compressibility at measured pressure/temperature
  - Reference in PDF: page `57`
  - Raw source figure extracted to:
    - `docs/spec/gail_fig1_water_compressibility_factor.png`
- `B`
  - Document definition: difference between water thermal expansion and steel thermal expansion
  - Reference in PDF: page `57`
  - Numeric table source pages: `56-59`

## Extracted Program-Usable Files

- `docs/spec/gail_table1_b_from_pdf.csv`
  - Long-form CSV
  - Columns:
    - `temp_c`
    - `pressure_bar`
    - `b_micro_per_c`
    - `source_page`
- `docs/spec/gail_table1_b_from_pdf.meta.json`
  - Extraction notes, axis definitions and parse summary
- `docs/spec/gail_fig1_a_from_pdf_estimated.csv`
  - Long-form CSV derived from `Fig.1`
  - Columns:
    - `temp_c`
    - `pressure_bar`
    - `a_micro_per_bar_estimated`
    - `plot_x_px`
    - `plot_y_px`
- `docs/spec/gail_fig1_a_from_pdf_estimated.meta.json`
  - OCR-assisted axis calibration and comparison summary
- `docs/spec/botas_reference_table_2c_10bar.csv`
  - Combined reference table on exact overlapping nodes
  - Columns:
    - `temp_c`
    - `pressure_bar`
    - `a_micro_per_bar_estimated`
    - `b_micro_per_c`
    - `a_source_kind`
    - `b_source_kind`
- `docs/spec/gail_fig1_water_compressibility_factor.png`
  - Raw extracted `Fig.1` image

## Current Status

- `B` values have been successfully extracted into a program-usable CSV.
- `A` values have been converted into an estimated numeric table for the public
  `2,4,...,30 degC` curves over `30-120 barg`.
- The combined `A/B` set is now exposed to users as `BOTAŞ referans tablosu`.
- Extraction method:
  - OCR-assisted axis calibration
  - raster peak tracking on the chart image
- Reliability note:
  - `A` values are suitable for provenance and trend comparison
  - they are still estimated chart values, not direct machine-readable source values

## Recommendation

Next safe step:

1. Review `docs/spec/gail_fig1_a_vs_local_comparison.csv` and
   `docs/spec/gail_table1_b_vs_local_comparison.csv`
2. Use `docs/spec/botas_reference_table_2c_10bar.csv` as the named optional
   reference backend while keeping its provenance tied to the GAIL document
3. Keep the workbook-derived runtime table as the operational source until public
   chart-derived `A` values receive engineering signoff
