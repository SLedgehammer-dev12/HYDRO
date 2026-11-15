# HYDRO Codebase Map

Bu dosya `skills/graphify` tarafindan uretilmistir. Elle duzenlemeyin;
`python3 skills/graphify/scripts/graphify.py build` ve
`python3 tools/generate_codebase_map.py` komutlarini calistirin.

## Ozet

| Metrik | Deger |
| --- | ---: |
| Dosya | 74 |
| Sembol (sinif + fonksiyon) | 1707 |
| Dugum | 1788 |
| Kenar | 15039 |
| SQLite tablosu | 7 |
| Test edilen kaynak dosya | 31 / 32 |

## Paket Bagimliliklari

| Kaynak paket | Hedef paket | Import sayisi |
| --- | --- | ---: |
| `tests` | `hidrostatik_test.domain` | 29 |
| `tests` | `hidrostatik_test.ui` | 13 |
| `tests` | `hidrostatik_test.services` | 11 |
| `hidrostatik_test.ui` | `hidrostatik_test.domain` | 10 |
| `tests` | `hidrostatik_test.data` | 9 |
| `hidrostatik_test.ui` | `hidrostatik_test.services` | 6 |
| `hidrostatik_test.ui` | `hidrostatik_test.data` | 4 |
| `hidrostatik_test.domain` | `hidrostatik_test.data` | 3 |
| `Hidrostatik_Test_Chat.py` | `hidrostatik_test.ui` | 2 |
| `hidrostatik_test.services` | `hidrostatik_test.domain` | 2 |
| `tests` | `hidrostatik_test.app_metadata` | 2 |
| `tools` | `hidrostatik_test.services` | 2 |
| `hidrostatik_test.__init__.py` | `hidrostatik_test.app_metadata` | 1 |
| `hidrostatik_test.domain` | `hidrostatik_test.services` | 1 |
| `hidrostatik_test.services` | `hidrostatik_test.app_metadata` | 1 |
| `hidrostatik_test.services` | `hidrostatik_test.data` | 1 |
| `hidrostatik_test.ui` | `hidrostatik_test.app_metadata` | 1 |
| `tests` | `hidrostatik_test` | 1 |
| `tools` | `hidrostatik_test.app_metadata` | 1 |
| `tools` | `hidrostatik_test.domain` | 1 |

## En Buyuk Dosyalar (sembol sayisina gore)

| Dosya | Sinif | Fonksiyon | Toplam |
| --- | ---: | ---: | ---: |
| `hidrostatik_test/ui/app.py` | 1 | 293 | 294 |
| `tests/test_ui_workflow.py` | 2 | 125 | 127 |
| `tests/test_updater.py` | 8 | 93 | 101 |
| `tests/test_wizard.py` | 14 | 55 | 69 |
| `tests/test_validators.py` | 6 | 60 | 66 |
| `tests/test_report_ocr.py` | 8 | 54 | 62 |
| `hidrostatik_test/services/report_ocr.py` | 6 | 51 | 57 |
| `hidrostatik_test/services/updater.py` | 4 | 48 | 52 |
| `tests/test_water_properties.py` | 5 | 38 | 43 |
| `hidrostatik_test/ui/wizard.py` | 2 | 40 | 42 |
| `tests/test_time_series.py` | 3 | 34 | 37 |
| `tests/test_session_manager.py` | 5 | 31 | 36 |
| `tests/test_hydrotest_core.py` | 6 | 29 | 35 |
| `tests/test_coefficient_manager.py` | 2 | 32 | 34 |
| `tests/test_download_dialog.py` | 4 | 29 | 33 |
| `hidrostatik_test/domain/session_manager.py` | 2 | 30 | 32 |
| `hidrostatik_test/services/download_manager.py` | 4 | 24 | 28 |
| `hidrostatik_test/ui/report_ocr_dialog.py` | 1 | 26 | 27 |
| `hidrostatik_test/data/ab_control_table.py` | 8 | 19 | 27 |
| `hidrostatik_test/domain/water_properties.py` | 6 | 21 | 27 |

## Test Haritasi

| Kaynak dosya | Bagli test dosyalari |
| --- | --- |
| `hidrostatik_test/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/app_metadata.py` | `tests/test_app_metadata.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py` |
| `hidrostatik_test/data/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/data/ab_control_table.py` | `tests/test_ab_control_table.py` |
| `hidrostatik_test/data/botas_reference_table.py` | `tests/test_botas_reference_table.py` |
| `hidrostatik_test/data/coefficient_reference.py` | `tests/test_coefficient_reference.py` |
| `hidrostatik_test/data/gail_reference_table.py` | `tests/test_gail_reference_table.py` |
| `hidrostatik_test/data/pipe_catalog.py` | `tests/test_pipe_catalog.py` |
| `hidrostatik_test/data/water_property_table.py` | `tests/test_water_property_table.py` |
| `hidrostatik_test/domain/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/domain/coefficient_manager.py` | `tests/test_coefficient_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/domain/coefficient_sources.py` | `tests/test_coefficient_sources.py` |
| `hidrostatik_test/domain/hydrotest_core.py` | `tests/test_coefficient_sources.py`, `tests/test_e2e_workflow.py`, `tests/test_hydrotest_core.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/domain/operations.py` | `tests/test_operations.py`, `tests/test_time_series.py` |
| `hidrostatik_test/domain/pressure_profile.py` | `tests/test_pressure_profile.py` |
| `hidrostatik_test/domain/pressurization.py` | `tests/test_pressurization.py` |
| `hidrostatik_test/domain/report_schema.py` | `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py` |
| `hidrostatik_test/domain/session_manager.py` | `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_wizard.py` |
| `hidrostatik_test/domain/time_series.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_time_series.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/domain/units.py` | `tests/test_download_dialog.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_units.py` |
| `hidrostatik_test/domain/water_properties.py` | `tests/test_hydrotest_core.py`, `tests/test_water_properties.py` |
| `hidrostatik_test/services/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/services/database.py` | `tests/test_database.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/services/download_manager.py` | `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py` |
| `hidrostatik_test/services/report_export.py` | `tests/test_report_export.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/services/report_ocr.py` | `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/services/updater.py` | `tests/test_e2e_workflow.py`, `tests/test_updater.py` |
| `hidrostatik_test/services/water_property_table_builder.py` | `tests/test_water_property_table.py` |
| `hidrostatik_test/ui/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/ui/app.py` | `tests/test_app_metadata.py`, `tests/test_database.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/ui/constants.py` | `tests/test_botas_reference_table.py`, `tests/test_constants.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/ui/download_dialog.py` | `tests/test_download_dialog.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/ui/helpers.py` | `tests/test_ui_helpers.py` |
| `hidrostatik_test/ui/report_ocr_dialog.py` | `tests/test_report_ocr_dialog.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/ui/validators.py` | `tests/test_validators.py` |
| `hidrostatik_test/ui/wizard.py` | `tests/test_database.py`, `tests/test_session_manager.py`, `tests/test_wizard.py` |

### Dogrudan test eslesmesi olmayan kaynak dosyalar

- `hidrostatik_test/_pyinstaller_hook.py`

## Cagri Grafigi Odaklari

| Sembol | Cagri noktasi | Ornek cagiranlar |
| --- | ---: | --- |
| `assertEqual` | 357 | `tests/test_ab_control_table.py:test_default_load_keeps_permissive_behaviour`, `tests/test_ab_control_table.py:test_excessive_adjacent_jump_is_reported`, `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported` (+354) |
| `get` | 312 | `docs/legacy/Hidrostatik_Test_Chat_v0.py:calculate_A`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_air_content_test`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_pressure_test` (+309) |
| `set` | 217 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/data/ab_control_table.py:_load_ab_control_repair_grid`, `hidrostatik_test/services/download_manager.py:cancel` (+214) |
| `assertTrue` | 176 | `tests/test_ab_control_table.py:test_duplicate_grid_node_is_reported`, `tests/test_ab_control_table.py:test_exact_grid_node_matches_imported_workbook_value`, `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported` (+173) |
| `str` | 163 | `hidrostatik_test/data/ab_control_table.py:_axis_from_metadata`, `hidrostatik_test/data/ab_control_table.py:_spec_from_metadata`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table` (+160) |
| `assertIn` | 139 | `tests/test_ab_control_table.py:test_exact_grid_node_matches_imported_workbook_value`, `tests/test_ab_control_table.py:test_midpoint_uses_bilinear_interpolation`, `tests/test_ab_control_table.py:test_seven_degree_anomaly_is_repaired_at_runtime` (+136) |
| `len` | 119 | `hidrostatik_test/data/ab_control_table.py:__init__`, `hidrostatik_test/data/ab_control_table.py:_axis_bounds`, `hidrostatik_test/data/ab_control_table.py:_axis_index_or_none` (+116) |
| `Path` | 118 | `hidrostatik_test/data/ab_control_table.py:count_repaired_ab_control_points`, `hidrostatik_test/data/ab_control_table.py:find_ab_control_table_issues`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table` (+115) |
| `strip` | 103 | `hidrostatik_test/data/botas_reference_table.py:is_botas_reference_option`, `hidrostatik_test/data/coefficient_reference.py:find_reference_point`, `hidrostatik_test/data/gail_reference_table.py:is_gail_reference_option` (+100) |
| `assertFalse` | 98 | `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported`, `tests/test_ab_control_table.py:test_runtime_repair_keeps_healthy_lookups_unchanged`, `tests/test_ab_control_table.py:test_small_table_anomaly_is_repaired_by_row_interpolation` (+95) |
| `append` | 93 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/data/ab_control_table.py:find_ab_control_table_issues`, `hidrostatik_test/domain/report_schema.py:iter_fields` (+90) |
| `TemporaryDirectory` | 70 | `tests/test_ab_control_table.py:test_duplicate_grid_node_is_reported`, `tests/test_ab_control_table.py:test_excessive_adjacent_jump_is_reported`, `tests/test_ab_control_table.py:test_missing_grid_node_is_reported` (+67) |
| `assertRaises` | 68 | `tests/test_ab_control_table.py:test_out_of_range_lookup_raises_error`, `tests/test_ab_control_table.py:test_validate_flag_raises_with_attached_issues`, `tests/test_botas_reference_table.py:test_botas_rejects_26c_while_gail_still_serves_it` (+65) |
| `patch` | 65 | `tests/test_download_dialog.py:test_cancel_declined_keeps_download_running`, `tests/test_download_dialog.py:test_cancel_while_running_asks_once`, `tests/test_download_dialog.py:test_close_while_running_asks_and_cancels` (+62) |
| `float` | 63 | `docs/legacy/Hidrostatik_Test_Chat_v0.py:calculate_A`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_air_content_test`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_pressure_test` (+60) |
| `join` | 62 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/domain/coefficient_sources.py:normalize_b_source`, `hidrostatik_test/domain/hydrotest_core.py:normalize_steel_model` (+59) |
| `isclose` | 53 | `tests/test_ab_control_table.py:test_exact_grid_node_matches_imported_workbook_value`, `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported`, `tests/test_ab_control_table.py:test_midpoint_uses_bilinear_interpolation` (+50) |
| `_set_banner` | 47 | `hidrostatik_test/ui/app.py:_add_geometry_segment`, `hidrostatik_test/ui/app.py:_add_time_series_record`, `hidrostatik_test/ui/app.py:_apply_air_a_reference` (+44) |
| `configure` | 46 | `hidrostatik_test/ui/app.py:_append_result`, `hidrostatik_test/ui/app.py:_apply_b_helper_mode`, `hidrostatik_test/ui/app.py:_apply_field_visual_state` (+43) |
| `assertIsNotNone` | 42 | `tests/test_database.py:test_timestamps_are_utc_iso8601`, `tests/test_download_manager.py:test_get_task_returns_detached_copy`, `tests/test_e2e_workflow.py:test_session_persistence_with_sqlite` (+39) |
| `items` | 41 | `hidrostatik_test/domain/coefficient_manager.py:as_dict`, `hidrostatik_test/domain/coefficient_manager.py:from_dict`, `hidrostatik_test/domain/report_schema.py:validate_report` (+38) |
| `assertIsNone` | 41 | `tests/test_coefficient_reference.py:test_lookup_accepts_exact_labels_only`, `tests/test_database.py:test_delete_session_cascades`, `tests/test_download_dialog.py:test_cancel_declined_keeps_download_running` (+38) |
| `exists` | 40 | `hidrostatik_test/data/ab_control_table.py:find_ab_control_table_issues`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table`, `hidrostatik_test/data/water_property_table.py:load_water_property_table` (+37) |
| `isinstance` | 40 | `hidrostatik_test/data/ab_control_table.py:_axis_from_metadata`, `hidrostatik_test/data/ab_control_table.py:_spec_from_metadata`, `hidrostatik_test/data/pipe_catalog.py:_item_schedules` (+37) |
| `cget` | 39 | `hidrostatik_test/ui/app.py:_apply_progress_button_appearance`, `hidrostatik_test/ui/app.py:_finish_progress_button`, `tests/test_download_dialog.py:test_cancel_while_running_asks_once` (+36) |
| `getattr` | 36 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/domain/report_schema.py:get_field`, `hidrostatik_test/services/download_manager.py:_content_length` (+33) |
| `assertAlmostEqual` | 35 | `tests/test_coefficient_sources.py:test_auto_linear_value_preserves_historic_model`, `tests/test_coefficient_sources.py:test_auto_volumetric_value_uses_three_alpha`, `tests/test_operations.py:test_cleaning_pig_speed_passes_when_below_limit` (+32) |
| `_safe_float` | 35 | `hidrostatik_test/ui/app.py:_active_monitored_pressure_bar`, `hidrostatik_test/ui/app.py:_add_time_series_record`, `hidrostatik_test/ui/app.py:_build_air_control_table_summary` (+32) |
| `write_bytes` | 33 | `tests/test_download_manager.py:test_partial_file_is_restarted_when_server_ignores_range`, `tests/test_report_ocr.py:test_corrupt_image`, `tests/test_updater.py:fake_download` (+30) |
| `add` | 31 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/data/ab_control_table.py:_load_ab_control_repair_grid`, `hidrostatik_test/services/report_ocr.py:_build_alias_patterns` (+28) |

## Kritik Dosyalarin Etki Alani

### `hidrostatik_test/domain/hydrotest_core.py`

- Bagli testler: `tests/test_coefficient_sources.py`, `tests/test_e2e_workflow.py`, `tests/test_hydrotest_core.py`, `tests/test_ui_workflow.py`
- Etkilenen dosyalar (10): `hidrostatik_test/domain/__init__.py`, `hidrostatik_test/domain/coefficient_sources.py`, `hidrostatik_test/domain/operations.py`, `hidrostatik_test/domain/pressure_profile.py`, `hidrostatik_test/domain/pressurization.py`, `hidrostatik_test/ui/app.py`, `tests/test_coefficient_sources.py`, `tests/test_e2e_workflow.py`, `tests/test_hydrotest_core.py`, `tests/test_ui_workflow.py`

### `hidrostatik_test/domain/water_properties.py`

- Bagli testler: `tests/test_hydrotest_core.py`, `tests/test_water_properties.py`
- Etkilenen dosyalar (8): `hidrostatik_test/domain/__init__.py`, `hidrostatik_test/domain/coefficient_sources.py`, `hidrostatik_test/domain/hydrotest_core.py`, `hidrostatik_test/domain/pressure_profile.py`, `hidrostatik_test/services/water_property_table_builder.py`, `hidrostatik_test/ui/app.py`, `tests/test_hydrotest_core.py`, `tests/test_water_properties.py`

### `hidrostatik_test/domain/time_series.py`

- Bagli testler: `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_time_series.py`, `tests/test_ui_workflow.py`
- Etkilenen dosyalar (3): `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/ui/app.py`, `tests/test_time_series.py`

### `hidrostatik_test/services/updater.py`

- Bagli testler: `tests/test_e2e_workflow.py`, `tests/test_updater.py`
- Etkilenen dosyalar (4): `hidrostatik_test/services/__init__.py`, `hidrostatik_test/ui/app.py`, `tests/test_e2e_workflow.py`, `tests/test_updater.py`

### `hidrostatik_test/services/download_manager.py`

- Bagli testler: `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`
- Etkilenen dosyalar (6): `hidrostatik_test/services/updater.py`, `hidrostatik_test/ui/app.py`, `hidrostatik_test/ui/download_dialog.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_ui_workflow.py`

### `hidrostatik_test/services/database.py`

- Bagli testler: `tests/test_database.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`
- Etkilenen dosyalar (2): `hidrostatik_test/domain/session_manager.py`, `tests/test_database.py`

### `hidrostatik_test/services/report_export.py`

- Bagli testler: `tests/test_report_export.py`, `tests/test_ui_workflow.py`
- Etkilenen dosyalar (2): `hidrostatik_test/ui/app.py`, `tests/test_report_export.py`

### `hidrostatik_test/ui/app.py`

- Bagli testler: `tests/test_app_metadata.py`, `tests/test_database.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py`
- Etkilenen dosyalar (5): `Hidrostatik_Test_Chat.py`, `hidrostatik_test/ui/__init__.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`

## Veritabani Tablolari

| Tablo | Kullanan moduller |
| --- | --- |
| `IF` | `hidrostatik_test/_pyinstaller_hook.py`, `hidrostatik_test/data/ab_control_table.py`, `hidrostatik_test/data/botas_reference_table.py`, `hidrostatik_test/data/coefficient_reference.py`, `hidrostatik_test/data/gail_reference_table.py`, `hidrostatik_test/data/pipe_catalog.py`, `hidrostatik_test/data/water_property_table.py`, `hidrostatik_test/domain/coefficient_manager.py`, `hidrostatik_test/domain/coefficient_sources.py`, `hidrostatik_test/domain/hydrotest_core.py`, `hidrostatik_test/domain/operations.py`, `hidrostatik_test/domain/pressure_profile.py`, `hidrostatik_test/domain/pressurization.py`, `hidrostatik_test/domain/report_schema.py`, `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/domain/time_series.py`, `hidrostatik_test/domain/water_properties.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/services/download_manager.py`, `hidrostatik_test/services/report_export.py`, `hidrostatik_test/services/report_ocr.py`, `hidrostatik_test/services/updater.py`, `hidrostatik_test/ui/app.py`, `hidrostatik_test/ui/download_dialog.py`, `hidrostatik_test/ui/helpers.py`, `hidrostatik_test/ui/report_ocr_dialog.py`, `hidrostatik_test/ui/validators.py`, `hidrostatik_test/ui/wizard.py` |
| `coefficients` | `hidrostatik_test/services/database.py` |
| `geometry_records` | `hidrostatik_test/services/database.py` |
| `schema_version` | `hidrostatik_test/data/ab_control_table.py`, `hidrostatik_test/data/water_property_table.py`, `hidrostatik_test/domain/report_schema.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/services/water_property_table_builder.py`, `hidrostatik_test/ui/app.py` |
| `sessions` | `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/ui/app.py` |
| `test_entries` | `hidrostatik_test/services/database.py` |
| `time_series_records` | `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/ui/app.py` |

## Mermaid: Paket Bagimliligi

```mermaid
graph LR
    P0["Hidrostatik_Test_Chat.py"]
    P1["hidrostatik_test"]
    P2["hidrostatik_test.__init__.py"]
    P3["hidrostatik_test.app_metadata"]
    P4["hidrostatik_test.data"]
    P5["hidrostatik_test.domain"]
    P6["hidrostatik_test.services"]
    P7["hidrostatik_test.ui"]
    P8["tests"]
    P9["tools"]
    P0 -->|2| P7
    P2 -->|1| P3
    P5 -->|3| P4
    P5 -->|1| P6
    P6 -->|1| P3
    P6 -->|1| P4
    P6 -->|2| P5
    P7 -->|1| P3
    P7 -->|4| P4
    P7 -->|10| P5
    P7 -->|6| P6
    P8 -->|1| P1
    P8 -->|2| P3
    P8 -->|9| P4
    P8 -->|29| P5
    P8 -->|11| P6
    P8 -->|13| P7
    P9 -->|1| P3
    P9 -->|1| P5
    P9 -->|2| P6
```

