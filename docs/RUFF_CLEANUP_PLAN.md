# Ruff Cleanup Plan

This document provides a detailed action plan for resolving 9 code quality issues identified by `ruff check` in the backend directory.

## Summary of Issues
- **5 bare except clauses (E722)** in `backend/tests/run_all_tests.py`
- **2 unused local variables (F841)** in `backend/tests/test_video_preservation.py`
- **2 unused imports (F401)** in `backend/utils/file_processors/__init__.py`

---

## Category 1: Bare `except` clauses (E722)

### Issue Description
Using bare `except:` clauses catches all exceptions including system-exiting exceptions like `SystemExit` and `KeyboardInterrupt`. This is dangerous and makes debugging difficult.

### Files Affected
- `backend/tests/run_all_tests.py` - Lines 128, 136, 143, 150, 158

### Fix Instructions

#### Line 128
- **Current:** Bare `except`
- **Action:** Replace with specific exception handling
- **Suggested Fix:** Catch `Exception` as a baseline, or more specific exceptions like `ImportError`, `AttributeError`, or `ValueError` depending on what the code block is doing

#### Line 136
- **Current:** Bare `except`
- **Action:** Replace with specific exception handling
- **Suggested Fix:** Catch `Exception` or specific test-related exceptions like `AssertionError` or `TestException`

#### Line 143
- **Current:** Bare `except`
- **Action:** Replace with specific exception handling
- **Suggested Fix:** Catch `Exception` or file/IO related exceptions like `IOError`, `FileNotFoundError`

#### Line 150
- **Current:** Bare `except`
- **Action:** Replace with specific exception handling
- **Suggested Fix:** Catch `Exception` or runtime exceptions relevant to the test execution context

#### Line 158
- **Current:** Bare `except`
- **Action:** Replace with specific exception handling
- **Suggested Fix:** Catch `Exception` or cleanup-related exceptions like `RuntimeError`, `OSError`

### Implementation Steps
1. Examine each bare `except` block to understand what exceptions it's meant to catch
2. Replace `except:` with `except Exception:` as a minimum improvement
3. Where possible, use more specific exception types based on the operation being performed
4. Add logging or error messages to track what exceptions are being caught

---

## Category 2: Unused local variables (F841)

### Issue Description
Variables are assigned values but never used, indicating dead code that should be removed.

### Files Affected
- `backend/tests/test_video_preservation.py` - Lines 170, 183

### Fix Instructions

#### Line 170
- **Variable:** `small_analysis`
- **Action:** Remove the variable assignment
- **Options:**
  1. Delete the entire line if the assigned value has no side effects
  2. Replace with `_` if the value needs to be unpacked but not used: `_ = ...`
  3. Use the variable in an assertion or verification if it was meant to be tested

#### Line 183
- **Variable:** `large_analysis`
- **Action:** Remove the variable assignment
- **Options:**
  1. Delete the entire line if the assigned value has no side effects
  2. Replace with `_` if the value needs to be unpacked but not used: `_ = ...`
  3. Use the variable in an assertion or verification if it was meant to be tested

### Implementation Steps
1. Check if these variables were intended for assertions or test verifications
2. If they should be tested, add appropriate assertions
3. If they're truly unused, remove the assignments completely
4. If the function calls have side effects that need to be preserved, use `_` as the variable name

---

## Category 3: Unused imports (F401)

### Issue Description
Modules are imported but never used in the file, creating unnecessary dependencies.

### Files Affected
- `backend/utils/file_processors/__init__.py` - Line 2

### Fix Instructions

#### Line 2, Position 60
- **Import:** `..data_models.FileType`
- **Action:** Remove this import from the import statement

#### Line 2, Position 70
- **Import:** `..data_models.SavedDocument`
- **Action:** Remove this import from the import statement

### Implementation Steps
1. Open `backend/utils/file_processors/__init__.py`
2. Locate line 2 which contains the import statement
3. Remove `FileType` and `SavedDocument` from the import list
4. If this was the only import from `..data_models`, remove the entire import line
5. Verify that removing these imports doesn't break any re-exports if this is an `__init__.py` file being used for public API

---

## Verification Steps

After implementing all fixes:

1. Run `ruff check backend/` to verify all issues are resolved
2. Run the test suite to ensure no functionality was broken
3. Review the changes to ensure exception handling is appropriate for each context
4. Consider adding `ruff` to pre-commit hooks to prevent future issues

## Priority Order

1. **First:** Fix bare except clauses (E722) - These are the most critical as they can hide serious errors
2. **Second:** Remove unused imports (F401) - Quick wins that reduce code complexity
3. **Third:** Handle unused variables (F841) - Ensure test coverage isn't accidentally reduced

## Expected Outcome

After completing this cleanup:
- All 9 ruff violations should be resolved
- Code will be more maintainable and debuggable
- Exception handling will be explicit and appropriate
- No dead code or unused imports will remain
