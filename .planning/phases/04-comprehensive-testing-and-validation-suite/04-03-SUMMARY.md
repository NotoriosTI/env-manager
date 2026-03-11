---
plan: 04-03
status: complete
---

# Summary: 04-03 Error Message Content Audit and Assertion Strengthening

## What Was Built

Audited every `pytest.raises` call across the test suite and strengthened assertions to ensure error messages contain contextual identifying information (variable names, environment names, or file paths). Two tests needed strengthening; all others already had thorough assertions.

## Key Files

### Modified
- `tests/test_resolution_validation.py` - Added `assert "OPTIONAL_TOKEN" in str(exc.value)` to `test_strict_mode_raises_before_optional_fallback`
- `tests/test_manager.py` - Added `assert "DB_PASSWORD" in str(exc.value)` to `test_strict_mode_raises_on_missing`

## Audit Findings

All `pytest.raises` calls reviewed:

| File | Test | Status |
|------|------|--------|
| test_resolution_validation.py | test_required_sourced_variable_missing_raises_runtime_error_with_context | Already thorough (variable, env, path) |
| test_resolution_validation.py | test_strict_mode_raises_before_optional_fallback | **Strengthened** - added variable name assertion |
| test_resolution_validation.py | test_missing_explicit_per_variable_dotenv_raises_only_when_lookup_needs_file | Already thorough (variable, env, path) |
| test_environment_integration.py | test_undefined_environment_raises_value_error | Adequate (match="unknown") |
| test_environment_integration.py | test_undefined_environment_error_lists_available | Already thorough (all env names) |
| test_environment_integration.py | test_variable_override_validation_rejects_unknown_environment | Already thorough (variable, env name) |
| test_environment_integration.py | test_variable_override_validation_rejects_invalid_origin | Already thorough (variable, "origin", value) |
| test_manager.py | test_missing_required_variable_raises | Already thorough (variable name) |
| test_manager.py | test_strict_mode_raises_on_missing | **Strengthened** - added variable name assertion |
| test_manager.py | test_missing_active_environment_dotenv_raises_with_absolute_path_when_needed | Already thorough (env name, path) |
| test_validation.py | test_required_variable_missing_raises | Already thorough (variable name) |

## Decisions

- Strengthened `test_manager.py::test_strict_mode_raises_on_missing` beyond the plan's explicit list since it had the same pattern as the identified case (strict mode assertion without variable name). The error message format `"Strict mode: variable '{var_name}' is missing..."` confirms `DB_PASSWORD` will appear.
- Did not modify tests added by plan 04-02 (line 438 in test_environment_integration.py already had proper assertions).

## Self-Check: PASSED
