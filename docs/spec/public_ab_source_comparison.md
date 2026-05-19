# BOTAŞ Reference Table Source Comparison

## Scope

This note records the source basis for the `BOTAŞ referans tablosu` option used
in the UI. The table is derived from public-source `A/B` coefficient charts used
in pipeline hydrostatic testing and compared against the local workbook-derived
table `ab_control_table_v1.csv`.

## Downloaded Public Sources

- `d:\İş\Python USB\_research\ab_public_sources\gail_technicalvol3.pdf`
  Source: `https://gailtenders.in/Gailtenders/writereaddata/Tender/technicalvol3_20240827_123931.pdf`
- `d:\İş\Python USB\_research\ab_public_sources\bggl_vol2.pdf`
  Source: `https://www.bglgas.com/downloads/620-VOL-2.pdf`
- `d:\İş\Python USB\_research\ab_public_sources\pipemath_hydrotest_manual.pdf`
  Source: `https://pipemath.com/Manuals/Guide%20-%20Hydrotest_Manual%20SI%20CSA%20Z662.pdf`

## Public Definitions Confirmed

The downloaded GAIL and BGGL specifications both define the hydrotest
temperature-pressure relationship with the same `A/B` concept:

- `A`: water isothermal compressibility at the measured pressure/temperature
- `B`: difference between water thermal expansion and steel thermal expansion
- `B` is read from `Table-1`
- `A` is read from `Fig-1 Water Compressibility Factor`

## What Was Publicly Recoverable

- `B` was publicly recoverable as a machine-readable table from GAIL/BGGL PDF
  text extraction.
- `A` was recoverable as a raster chart from `Fig.1 Water Compressibility
  Factor` and has now been converted into an estimated numeric table by
  OCR-assisted axis calibration plus curve peak tracking.
- No public copy of the original local workbook name `A ve B Katsayisi.xlsx`
  was found.

## Public A Comparison

`A` was compared against the local workbook-derived `ab_control_table_v1.csv`
on overlapping nodes:

- public chart curves available: `2,4,...,30 degC`
- comparison range used: `2-24 degC`, `30-120 bar`, `1 bar` step
- comparison rows: `1092`
- mean absolute error: `0.062185`
- max absolute error: `0.229057`
- mean absolute percentage error: `0.134614%`
- max absolute percentage error: `0.501849%`

Sample points:

| Temp (degC) | Pressure (bar) | Local A | Public A | Delta | Delta % |
|---|---:|---:|---:|---:|---:|
| 2 | 30 | 49.205 | 49.172955 | -0.032045 | -0.065125 |
| 2 | 120 | 48.307 | 48.368161 | +0.061161 | +0.126609 |
| 10 | 50 | 46.775 | 46.824270 | +0.049270 | +0.105334 |
| 20 | 50 | 44.968 | 44.951892 | -0.016108 | -0.035821 |
| 24 | 120 | 43.710 | 43.752913 | +0.042913 | +0.098177 |

Interpretation:

- The public `A` chart and the local workbook-derived `A` values are very close.
- The residual error is small enough that the local workbook appears consistent
  with the public `Fig.1` family.
- Because the public values came from chart digitization rather than a native
  table, they should still be treated as validation data, not as a primary
  runtime source without signoff.

## Sample B Comparison

Public `Table-1` values were compared against the local workbook-derived
`ab_control_table_v1.csv` at matching `(T, P)` nodes.

| Temp (degC) | Pressure (bar) | Local B | Public B | Delta | Delta % |
|---|---:|---:|---:|---:|---:|
| 1 | 30 | -84.373 | -88.740 | +4.367 | -4.921118 |
| 10 | 50 | 64.923 | 60.450 | +4.473 | +7.399504 |
| 15 | 30 | 125.052 | 120.490 | +4.562 | +3.786206 |
| 20 | 50 | 184.557 | 179.930 | +4.627 | +2.571556 |
| 25 | 120 | 241.501 | 236.790 | +4.711 | +1.989527 |

## Interpretation

The public `B` table and the local workbook table are clearly from the same
engineering family, but they are not numerically identical.

Observed behavior:

- The local workbook `B` values are consistently higher than the public `Table-1` values.
- The offset stays in a narrow `~4.4 to 4.7` range across sampled points.

Inference:

- This pattern suggests the local workbook is not a direct copy of the public
  GAIL/BGGL `Table-1`.
- A likely explanation is a different steel thermal expansion assumption or a
  different source/correction basis applied while preparing the workbook.

This is an inference from the sampled values, not direct proof of the workbook's
origin.

## Practical Result

- Public sources can be used to validate the `A` trend, `B` trend and
  terminology behind the `BOTAŞ referans tablosu`.
- Public `A` extraction now supports a high-confidence trend comparison against
  the workbook table.
- Public `B` extraction remains exact at the published `10 bar` nodes and still
  shows a systematic offset relative to the workbook table.
- The local workbook remains the better operational source for runtime use,
  while the public GAIL extraction is now a useful provenance and validation
  layer.
