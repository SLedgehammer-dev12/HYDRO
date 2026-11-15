# HYDRO Codebase Map

Bu dosya `skills/graphify` tarafindan uretilmistir. Elle duzenlemeyin;
`python3 skills/graphify/scripts/graphify.py build` ve
`python3 tools/generate_codebase_map.py` komutlarini calistirin.

## Ozet

| Metrik | Deger |
| --- | ---: |
| Dosya | 119 |
| Sembol (sinif + fonksiyon) | 2136 |
| Dugum | 2269 |
| Kenar | 18838 |
| SQLite tablosu | 14 |
| Test edilen kaynak dosya | 54 / 64 |

## Paket Bagimliliklari

| Kaynak paket | Hedef paket | Import sayisi |
| --- | --- | ---: |
| `tests` | `hidrostatik_test.domain` | 29 |
| `webapp.backend.app.services` | `hidrostatik_test.domain` | 27 |
| `tests` | `hidrostatik_test.ui` | 13 |
| `tests` | `hidrostatik_test.services` | 11 |
| `hidrostatik_test.ui` | `hidrostatik_test.domain` | 10 |
| `tests` | `hidrostatik_test.data` | 9 |
| `webapp.backend.app.services` | `hidrostatik_test.data` | 7 |
| `hidrostatik_test.ui` | `hidrostatik_test.services` | 6 |
| `webapp.backend.app.domain_adapter.py` | `hidrostatik_test.domain` | 5 |
| `hidrostatik_test.ui` | `hidrostatik_test.data` | 4 |
| `webapp.backend.app.services` | `hidrostatik_test` | 4 |
| `webapp.backend.app.services` | `hidrostatik_test.services` | 4 |
| `hidrostatik_test.domain` | `hidrostatik_test.data` | 3 |
| `webapp.backend.tests.parity` | `hidrostatik_test.domain` | 3 |
| `Hidrostatik_Test_Chat.py` | `hidrostatik_test.ui` | 2 |
| `hidrostatik_test.services` | `hidrostatik_test.domain` | 2 |
| `tests` | `hidrostatik_test.app_metadata` | 2 |
| `tools` | `hidrostatik_test.services` | 2 |
| `webapp.backend.app.core` | `hidrostatik_test.domain` | 2 |
| `webapp.backend.app.services` | `hidrostatik_test.app_metadata` | 2 |
| `hidrostatik_test.__init__.py` | `hidrostatik_test.app_metadata` | 1 |
| `hidrostatik_test.domain` | `hidrostatik_test.services` | 1 |
| `hidrostatik_test.services` | `hidrostatik_test.app_metadata` | 1 |
| `hidrostatik_test.services` | `hidrostatik_test.data` | 1 |
| `hidrostatik_test.ui` | `hidrostatik_test.app_metadata` | 1 |
| `tests` | `hidrostatik_test` | 1 |
| `tools` | `hidrostatik_test.app_metadata` | 1 |
| `tools` | `hidrostatik_test.domain` | 1 |
| `webapp.backend.app.core` | `hidrostatik_test.data` | 1 |
| `webapp.backend.app.desktop_labels.py` | `hidrostatik_test.domain` | 1 |

## En Buyuk Dosyalar (sembol sayisina gore)

| Dosya | Sinif | Fonksiyon | Toplam |
| --- | ---: | ---: | ---: |
| `hidrostatik_test/ui/app.py` | 1 | 293 | 294 |
| `tests/test_ui_workflow.py` | 2 | 127 | 129 |
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
| `webapp/backend/app/services/ocr.py` | 0 | 31 | 31 |
| `webapp/backend/app/schemas.py` | 29 | 0 | 29 |
| `hidrostatik_test/services/download_manager.py` | 4 | 24 | 28 |
| `webapp/backend/app/services/sessions.py` | 0 | 27 | 27 |

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
| `hidrostatik_test/domain/pressure_profile.py` | `tests/test_pressure_profile.py`, `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py` |
| `hidrostatik_test/domain/pressurization.py` | `tests/test_pressurization.py`, `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_sessions.py` |
| `hidrostatik_test/domain/report_schema.py` | `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py` |
| `hidrostatik_test/domain/session_manager.py` | `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_wizard.py` |
| `hidrostatik_test/domain/time_series.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_time_series.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_sessions.py` |
| `hidrostatik_test/domain/units.py` | `tests/test_download_dialog.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_units.py`, `webapp/backend/tests/test_system.py` |
| `hidrostatik_test/domain/water_properties.py` | `tests/test_hydrotest_core.py`, `tests/test_water_properties.py`, `webapp/backend/tests/parity/test_domain_parity.py` |
| `hidrostatik_test/services/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/services/database.py` | `tests/test_database.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/services/download_manager.py` | `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py` |
| `hidrostatik_test/services/report_export.py` | `tests/test_report_export.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_sessions.py` |
| `hidrostatik_test/services/report_ocr.py` | `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/services/updater.py` | `tests/test_e2e_workflow.py`, `tests/test_updater.py` |
| `hidrostatik_test/services/water_property_table_builder.py` | `tests/test_water_property_table.py` |
| `hidrostatik_test/ui/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `hidrostatik_test/ui/app.py` | `tests/test_app_metadata.py`, `tests/test_database.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py` |
| `hidrostatik_test/ui/constants.py` | `tests/test_botas_reference_table.py`, `tests/test_constants.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/ui/download_dialog.py` | `tests/test_download_dialog.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/ui/helpers.py` | `tests/test_ui_helpers.py` |
| `hidrostatik_test/ui/report_ocr_dialog.py` | `tests/test_report_ocr_dialog.py`, `tests/test_ui_workflow.py` |
| `hidrostatik_test/ui/validators.py` | `tests/test_validators.py` |
| `hidrostatik_test/ui/wizard.py` | `tests/test_database.py`, `tests/test_session_manager.py`, `tests/test_wizard.py` |
| `webapp/backend/app/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `webapp/backend/app/api/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `webapp/backend/app/api/calculations.py` | `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/api/catalog.py` | `tests/test_pipe_catalog.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_catalog.py` |
| `webapp/backend/app/api/coefficients.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_coefficients.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/api/ocr.py` | `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/api/reports.py` | `tests/test_coefficient_sources.py`, `tests/test_report_ocr.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_wizard.py`, `webapp/backend/tests/test_sessions.py` |
| `webapp/backend/app/api/sessions.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/core/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `webapp/backend/app/core/config.py` | `tests/test_ui_workflow.py`, `tests/test_wizard.py` |
| `webapp/backend/app/core/context.py` | `tests/test_ab_control_table.py`, `tests/test_download_dialog.py`, `tests/test_report_ocr.py`, `tests/test_updater.py`, `tests/test_validators.py` |
| `webapp/backend/app/core/errors.py` | `tests/test_database.py`, `tests/test_download_manager.py`, `tests/test_session_manager.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/core/security.py` | `webapp/backend/tests/test_ocr.py` |
| `webapp/backend/app/db.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/main.py` | `tests/test_ab_control_table.py`, `tests/test_app_metadata.py`, `tests/test_botas_reference_table.py`, `tests/test_coefficient_manager.py`, `tests/test_coefficient_reference.py`, `tests/test_coefficient_sources.py`, `tests/test_constants.py`, `tests/test_database.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_gail_reference_table.py`, `tests/test_hydrotest_core.py`, `tests/test_operations.py`, `tests/test_pipe_catalog.py`, `tests/test_pressure_profile.py`, `tests/test_pressurization.py`, `tests/test_report_export.py`, `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_time_series.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_units.py`, `tests/test_updater.py`, `tests/test_validators.py`, `tests/test_water_properties.py`, `tests/test_water_property_table.py`, `tests/test_wizard.py`, `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/models.py` | `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/services/__init__.py` | `tests/test_download_dialog.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py` |
| `webapp/backend/app/services/audit.py` | `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py` |
| `webapp/backend/app/services/calculations.py` | `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/services/catalog.py` | `tests/test_pipe_catalog.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_catalog.py` |
| `webapp/backend/app/services/coefficients.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_coefficients.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/services/decisions.py` | `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py` |
| `webapp/backend/app/services/ocr.py` | `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/services/reports.py` | `tests/test_coefficient_sources.py`, `tests/test_report_ocr.py`, `tests/test_session_manager.py`, `tests/test_ui_workflow.py`, `tests/test_wizard.py`, `webapp/backend/tests/test_sessions.py` |
| `webapp/backend/app/services/scene.py` | `webapp/backend/tests/test_sessions.py` |
| `webapp/backend/app/services/sessions.py` | `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py` |
| `webapp/backend/app/services/snapshot.py` | `tests/test_download_manager.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_sessions.py` |

### Dogrudan test eslesmesi olmayan kaynak dosyalar

- `hidrostatik_test/_pyinstaller_hook.py`
- `webapp/backend/app/api/deps.py`
- `webapp/backend/app/api/imports.py`
- `webapp/backend/app/api/system.py`
- `webapp/backend/app/core/timeutil.py`
- `webapp/backend/app/desktop_labels.py`
- `webapp/backend/app/domain_adapter.py`
- `webapp/backend/app/schemas.py`
- `webapp/backend/app/services/storage.py`
- `webapp/backend/app/services/system.py`

## Cagri Grafigi Odaklari

| Sembol | Cagri noktasi | Ornek cagiranlar |
| --- | ---: | --- |
| `get` | 423 | `docs/legacy/Hidrostatik_Test_Chat_v0.py:calculate_A`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_air_content_test`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_pressure_test` (+420) |
| `assertEqual` | 359 | `tests/test_ab_control_table.py:test_default_load_keeps_permissive_behaviour`, `tests/test_ab_control_table.py:test_excessive_adjacent_jump_is_reported`, `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported` (+356) |
| `set` | 221 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/data/ab_control_table.py:_load_ab_control_repair_grid`, `hidrostatik_test/services/download_manager.py:cancel` (+218) |
| `str` | 204 | `hidrostatik_test/data/ab_control_table.py:_axis_from_metadata`, `hidrostatik_test/data/ab_control_table.py:_spec_from_metadata`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table` (+201) |
| `assertTrue` | 176 | `tests/test_ab_control_table.py:test_duplicate_grid_node_is_reported`, `tests/test_ab_control_table.py:test_exact_grid_node_matches_imported_workbook_value`, `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported` (+173) |
| `len` | 143 | `hidrostatik_test/data/ab_control_table.py:__init__`, `hidrostatik_test/data/ab_control_table.py:_axis_bounds`, `hidrostatik_test/data/ab_control_table.py:_axis_index_or_none` (+140) |
| `assertIn` | 139 | `tests/test_ab_control_table.py:test_exact_grid_node_matches_imported_workbook_value`, `tests/test_ab_control_table.py:test_midpoint_uses_bilinear_interpolation`, `tests/test_ab_control_table.py:test_seven_degree_anomaly_is_repaired_at_runtime` (+136) |
| `strip` | 127 | `hidrostatik_test/data/botas_reference_table.py:is_botas_reference_option`, `hidrostatik_test/data/coefficient_reference.py:find_reference_point`, `hidrostatik_test/data/gail_reference_table.py:is_gail_reference_option` (+124) |
| `Path` | 123 | `hidrostatik_test/data/ab_control_table.py:count_repaired_ab_control_points`, `hidrostatik_test/data/ab_control_table.py:find_ab_control_table_issues`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table` (+120) |
| `append` | 122 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/data/ab_control_table.py:find_ab_control_table_issues`, `hidrostatik_test/domain/report_schema.py:iter_fields` (+119) |
| `assertFalse` | 98 | `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported`, `tests/test_ab_control_table.py:test_runtime_repair_keeps_healthy_lookups_unchanged`, `tests/test_ab_control_table.py:test_small_table_anomaly_is_repaired_by_row_interpolation` (+95) |
| `post` | 91 | `webapp/backend/app/api/calculations.py:air_content`, `webapp/backend/app/api/calculations.py:geometry`, `webapp/backend/app/api/calculations.py:pig_speed` (+88) |
| `json` | 85 | `webapp/backend/tests/conftest.py:create_session`, `webapp/backend/tests/parity/test_domain_parity.py:test_parity_air_content`, `webapp/backend/tests/parity/test_domain_parity.py:test_parity_air_exact_limit_fails` (+82) |
| `float` | 74 | `docs/legacy/Hidrostatik_Test_Chat_v0.py:calculate_A`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_air_content_test`, `docs/legacy/Hidrostatik_Test_Chat_v0.py:run_pressure_test` (+71) |
| `isinstance` | 70 | `hidrostatik_test/data/ab_control_table.py:_axis_from_metadata`, `hidrostatik_test/data/ab_control_table.py:_spec_from_metadata`, `hidrostatik_test/data/pipe_catalog.py:_item_schedules` (+67) |
| `TemporaryDirectory` | 70 | `tests/test_ab_control_table.py:test_duplicate_grid_node_is_reported`, `tests/test_ab_control_table.py:test_excessive_adjacent_jump_is_reported`, `tests/test_ab_control_table.py:test_missing_grid_node_is_reported` (+67) |
| `assertRaises` | 68 | `tests/test_ab_control_table.py:test_out_of_range_lookup_raises_error`, `tests/test_ab_control_table.py:test_validate_flag_raises_with_attached_issues`, `tests/test_botas_reference_table.py:test_botas_rejects_26c_while_gail_still_serves_it` (+65) |
| `join` | 66 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/domain/coefficient_sources.py:normalize_b_source`, `hidrostatik_test/domain/hydrotest_core.py:normalize_steel_model` (+63) |
| `isclose` | 66 | `tests/test_ab_control_table.py:test_exact_grid_node_matches_imported_workbook_value`, `tests/test_ab_control_table.py:test_known_seven_degree_anomaly_is_reported`, `tests/test_ab_control_table.py:test_midpoint_uses_bilinear_interpolation` (+63) |
| `patch` | 65 | `tests/test_download_dialog.py:test_cancel_declined_keeps_download_running`, `tests/test_download_dialog.py:test_cancel_while_running_asks_once`, `tests/test_download_dialog.py:test_close_while_running_asks_and_cancels` (+62) |
| `items` | 57 | `hidrostatik_test/domain/coefficient_manager.py:as_dict`, `hidrostatik_test/domain/coefficient_manager.py:from_dict`, `hidrostatik_test/domain/report_schema.py:validate_report` (+54) |
| `_set_banner` | 47 | `hidrostatik_test/ui/app.py:_add_geometry_segment`, `hidrostatik_test/ui/app.py:_add_time_series_record`, `hidrostatik_test/ui/app.py:_apply_air_a_reference` (+44) |
| `getattr` | 46 | `hidrostatik_test/_pyinstaller_hook.py:_setup_numpy_dll_paths`, `hidrostatik_test/domain/report_schema.py:get_field`, `hidrostatik_test/services/download_manager.py:_content_length` (+43) |
| `configure` | 46 | `hidrostatik_test/ui/app.py:_append_result`, `hidrostatik_test/ui/app.py:_apply_b_helper_mode`, `hidrostatik_test/ui/app.py:_apply_field_visual_state` (+43) |
| `int` | 45 | `hidrostatik_test/data/ab_control_table.py:_axis_from_metadata`, `hidrostatik_test/data/ab_control_table.py:_spec_from_metadata`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table` (+42) |
| `exists` | 44 | `hidrostatik_test/data/ab_control_table.py:find_ab_control_table_issues`, `hidrostatik_test/data/ab_control_table.py:load_ab_control_table`, `hidrostatik_test/data/water_property_table.py:load_water_property_table` (+41) |
| `select` | 43 | `hidrostatik_test/ui/app.py:_active_tab_key`, `hidrostatik_test/ui/app.py:_apply_input_snapshot`, `hidrostatik_test/ui/app.py:_select_tab_by_key` (+40) |
| `assertIsNotNone` | 42 | `tests/test_database.py:test_timestamps_are_utc_iso8601`, `tests/test_download_manager.py:test_get_task_returns_detached_copy`, `tests/test_e2e_workflow.py:test_session_persistence_with_sqlite` (+39) |
| `cget` | 41 | `hidrostatik_test/ui/app.py:_apply_progress_button_appearance`, `hidrostatik_test/ui/app.py:_finish_progress_button`, `tests/test_download_dialog.py:test_cancel_while_running_asks_once` (+38) |
| `assertIsNone` | 41 | `tests/test_coefficient_reference.py:test_lookup_accepts_exact_labels_only`, `tests/test_database.py:test_delete_session_cascades`, `tests/test_download_dialog.py:test_cancel_declined_keeps_download_running` (+38) |

## Kritik Dosyalarin Etki Alani

### `hidrostatik_test/domain/hydrotest_core.py`

- Bagli testler: `tests/test_coefficient_sources.py`, `tests/test_e2e_workflow.py`, `tests/test_hydrotest_core.py`, `tests/test_ui_workflow.py`
- Etkilenen dosyalar (11): `hidrostatik_test/domain/__init__.py`, `hidrostatik_test/domain/coefficient_sources.py`, `hidrostatik_test/domain/operations.py`, `hidrostatik_test/domain/pressure_profile.py`, `hidrostatik_test/domain/pressurization.py`, `hidrostatik_test/ui/app.py`, `tests/test_coefficient_sources.py`, `tests/test_e2e_workflow.py`, `tests/test_hydrotest_core.py`, `tests/test_ui_workflow.py`, `webapp/backend/app/services/system.py`

### `hidrostatik_test/domain/water_properties.py`

- Bagli testler: `tests/test_hydrotest_core.py`, `tests/test_water_properties.py`, `webapp/backend/tests/parity/test_domain_parity.py`
- Etkilenen dosyalar (13): `hidrostatik_test/domain/__init__.py`, `hidrostatik_test/domain/coefficient_sources.py`, `hidrostatik_test/domain/hydrotest_core.py`, `hidrostatik_test/domain/pressure_profile.py`, `hidrostatik_test/services/water_property_table_builder.py`, `hidrostatik_test/ui/app.py`, `tests/test_hydrotest_core.py`, `tests/test_water_properties.py`, `webapp/backend/app/core/errors.py`, `webapp/backend/app/services/calculations.py`, `webapp/backend/app/services/coefficients.py`, `webapp/backend/app/services/scene.py`, `webapp/backend/tests/parity/test_domain_parity.py`

### `hidrostatik_test/domain/time_series.py`

- Bagli testler: `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `tests/test_time_series.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_sessions.py`
- Etkilenen dosyalar (7): `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/ui/app.py`, `tests/test_time_series.py`, `webapp/backend/app/services/calculations.py`, `webapp/backend/app/services/decisions.py`, `webapp/backend/app/services/sessions.py`, `webapp/backend/app/services/system.py`

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

- Bagli testler: `tests/test_report_export.py`, `tests/test_ui_workflow.py`, `webapp/backend/tests/test_sessions.py`
- Etkilenen dosyalar (3): `hidrostatik_test/ui/app.py`, `tests/test_report_export.py`, `webapp/backend/app/services/reports.py`

### `hidrostatik_test/ui/app.py`

- Bagli testler: `tests/test_app_metadata.py`, `tests/test_database.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_report_ocr_dialog.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`, `tests/test_wizard.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py`
- Etkilenen dosyalar (5): `Hidrostatik_Test_Chat.py`, `hidrostatik_test/ui/__init__.py`, `tests/test_e2e_workflow.py`, `tests/test_ui_workflow.py`, `tests/test_updater.py`

### `webapp/backend/app/main.py`

- Bagli testler: `tests/test_ab_control_table.py`, `tests/test_app_metadata.py`, `tests/test_botas_reference_table.py`, `tests/test_coefficient_manager.py`, `tests/test_coefficient_reference.py`, `tests/test_coefficient_sources.py`, `tests/test_constants.py`, `tests/test_database.py`, `tests/test_download_dialog.py`, `tests/test_download_manager.py`, `tests/test_e2e_workflow.py`, `tests/test_gail_reference_table.py`, `tests/test_hydrotest_core.py`, `tests/test_operations.py`, `tests/test_pipe_catalog.py`, `tests/test_pressure_profile.py`, `tests/test_pressurization.py`, `tests/test_report_export.py`, `tests/test_report_ocr.py`, `tests/test_report_ocr_dialog.py`, `tests/test_session_manager.py`, `tests/test_time_series.py`, `tests/test_ui_helpers.py`, `tests/test_ui_workflow.py`, `tests/test_units.py`, `tests/test_updater.py`, `tests/test_validators.py`, `tests/test_water_properties.py`, `tests/test_water_property_table.py`, `tests/test_wizard.py`, `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py`
- Etkilenen dosyalar (0): YOK

### `webapp/backend/app/api/calculations.py`

- Bagli testler: `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py`
- Etkilenen dosyalar (1): `webapp/backend/app/main.py`

### `webapp/backend/app/services/calculations.py`

- Bagli testler: `webapp/backend/tests/parity/test_domain_parity.py`, `webapp/backend/tests/test_calculations.py`, `webapp/backend/tests/test_system.py`
- Etkilenen dosyalar (3): `webapp/backend/app/api/calculations.py`, `webapp/backend/app/services/scene.py`, `webapp/backend/app/services/sessions.py`

### `webapp/backend/app/services/sessions.py`

- Bagli testler: `tests/test_database.py`, `tests/test_e2e_workflow.py`, `tests/test_session_manager.py`, `webapp/backend/tests/test_ocr.py`, `webapp/backend/tests/test_sessions.py`, `webapp/backend/tests/test_system.py`
- Etkilenen dosyalar (5): `webapp/backend/app/api/imports.py`, `webapp/backend/app/api/sessions.py`, `webapp/backend/app/api/system.py`, `webapp/backend/app/services/ocr.py`, `webapp/backend/app/services/scene.py`

## Veritabani Tablolari

| Tablo | Kullanan moduller |
| --- | --- |
| `IF` | `hidrostatik_test/_pyinstaller_hook.py`, `hidrostatik_test/data/ab_control_table.py`, `hidrostatik_test/data/botas_reference_table.py`, `hidrostatik_test/data/coefficient_reference.py`, `hidrostatik_test/data/gail_reference_table.py`, `hidrostatik_test/data/pipe_catalog.py`, `hidrostatik_test/data/water_property_table.py`, `hidrostatik_test/domain/coefficient_manager.py`, `hidrostatik_test/domain/coefficient_sources.py`, `hidrostatik_test/domain/hydrotest_core.py`, `hidrostatik_test/domain/operations.py`, `hidrostatik_test/domain/pressure_profile.py`, `hidrostatik_test/domain/pressurization.py`, `hidrostatik_test/domain/report_schema.py`, `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/domain/time_series.py`, `hidrostatik_test/domain/water_properties.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/services/download_manager.py`, `hidrostatik_test/services/report_export.py`, `hidrostatik_test/services/report_ocr.py`, `hidrostatik_test/services/updater.py`, `hidrostatik_test/ui/app.py`, `hidrostatik_test/ui/download_dialog.py`, `hidrostatik_test/ui/helpers.py`, `hidrostatik_test/ui/report_ocr_dialog.py`, `hidrostatik_test/ui/validators.py`, `hidrostatik_test/ui/wizard.py`, `webapp/backend/app/api/ocr.py`, `webapp/backend/app/api/reports.py`, `webapp/backend/app/api/sessions.py`, `webapp/backend/app/api/system.py`, `webapp/backend/app/core/config.py`, `webapp/backend/app/core/errors.py`, `webapp/backend/app/core/security.py`, `webapp/backend/app/core/timeutil.py`, `webapp/backend/app/db.py`, `webapp/backend/app/domain_adapter.py`, `webapp/backend/app/main.py`, `webapp/backend/app/services/calculations.py`, `webapp/backend/app/services/catalog.py`, `webapp/backend/app/services/coefficients.py`, `webapp/backend/app/services/decisions.py`, `webapp/backend/app/services/ocr.py`, `webapp/backend/app/services/reports.py`, `webapp/backend/app/services/scene.py`, `webapp/backend/app/services/sessions.py`, `webapp/backend/app/services/snapshot.py`, `webapp/backend/app/services/storage.py`, `webapp/backend/app/services/system.py` |
| `attachments` | `webapp/backend/app/models.py` |
| `audit_events` | `webapp/backend/app/api/sessions.py`, `webapp/backend/app/models.py` |
| `coefficients` | `hidrostatik_test/services/database.py`, `webapp/backend/app/api/coefficients.py`, `webapp/backend/app/main.py`, `webapp/backend/app/schemas.py`, `webapp/backend/app/services/calculations.py`, `webapp/backend/app/services/sessions.py` |
| `geometry_records` | `hidrostatik_test/services/database.py` |
| `ocr_analyses` | `webapp/backend/app/models.py` |
| `ocr_mapping_profiles` | `webapp/backend/app/models.py` |
| `projects` | `webapp/backend/app/models.py` |
| `schema_version` | `hidrostatik_test/data/ab_control_table.py`, `hidrostatik_test/data/water_property_table.py`, `hidrostatik_test/domain/report_schema.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/services/water_property_table_builder.py`, `hidrostatik_test/ui/app.py`, `webapp/backend/app/models.py`, `webapp/backend/app/schemas.py`, `webapp/backend/app/services/ocr.py`, `webapp/backend/app/services/scene.py`, `webapp/backend/app/services/sessions.py`, `webapp/backend/app/services/snapshot.py` |
| `sessions` | `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/ui/app.py`, `webapp/backend/app/api/imports.py`, `webapp/backend/app/api/sessions.py`, `webapp/backend/app/api/system.py`, `webapp/backend/app/main.py`, `webapp/backend/app/models.py`, `webapp/backend/app/schemas.py`, `webapp/backend/app/services/ocr.py`, `webapp/backend/app/services/scene.py` |
| `test_entries` | `hidrostatik_test/services/database.py` |
| `test_results` | `webapp/backend/app/api/reports.py`, `webapp/backend/app/models.py`, `webapp/backend/app/schemas.py`, `webapp/backend/app/services/reports.py` |
| `time_series` | `webapp/backend/app/models.py`, `webapp/backend/app/services/calculations.py`, `webapp/backend/app/services/decisions.py`, `webapp/backend/app/services/sessions.py`, `webapp/backend/app/services/system.py` |
| `time_series_records` | `hidrostatik_test/domain/session_manager.py`, `hidrostatik_test/services/database.py`, `hidrostatik_test/ui/app.py`, `webapp/backend/app/services/sessions.py` |

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
    P10["webapp.backend.app.core"]
    P11["webapp.backend.app.desktop_labels.py"]
    P12["webapp.backend.app.domain_adapter.py"]
    P13["webapp.backend.app.services"]
    P14["webapp.backend.tests.parity"]
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
    P10 -->|1| P4
    P10 -->|2| P5
    P11 -->|1| P5
    P12 -->|5| P5
    P13 -->|4| P1
    P13 -->|2| P3
    P13 -->|7| P4
    P13 -->|27| P5
    P13 -->|4| P6
    P14 -->|3| P5
```

