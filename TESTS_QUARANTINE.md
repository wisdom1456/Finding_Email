# Quarantined Tests

Tests marked `@pytest.mark.xfail(strict=False)` because they fail for reasons
unrelated to a live product regression (stale mocks, changed-but-unbaselined
assertions, or unimplemented aspirational behavior). Quarantining keeps the CI
suite green so a **red build means a real regression**, while every skipped
assertion stays visible and tracked here.

`strict=False` means: if a quarantined test starts passing again it reports as
`XPASS` (not a failure) — that's the signal to remove its marker and delete its
row below.

Established 2026-07-02 during the CI-repair effort. Baseline before repair was
23 full-suite failures; 14 were fixed (11 event-loop pollution in
`test_synthesis_gate`, 3 stale `FakeLetterOpenAIClient` methods) and 2
credential-dependent embedding tests now skip under mock/CI creds.

**2026-07-02 un-quarantine pass:** 8 of the 9 pytest tests and all 3 vitest
tests below were fixed and un-quarantined (root causes were stale mocks/fixtures
and taxonomy drift, not product bugs). Verified against the full suites:
pytest `1237 passed, 2 skipped, 1 xfailed` and vitest `649 passed, 1 skipped`,
zero failures. The one remaining pytest row is blocked on a product decision.

| Test | Reason quarantined | Fix owed |
|------|--------------------|----------|
| `tests/api/test_service_role_resilience.py::test_cancel_case_succeeds_without_service_role_key` | Asserts `cancel_case` succeeds without `SUPABASE_SERVICE_KEY`; code currently raises | **Product decision**: implement user-client fallback, or update the test to the intended contract |

### Resolved 2026-07-02 (kept for traceability)

- `tests/api/test_analysis_lifecycle.py::test_get_status_success` /
  `::test_get_status_not_found` — the `_configure_supabase` mock dispatcher was
  missing `.in_`, so the status route's `.in_("status", [...])` call returned an
  unconfigured `MagicMock` whose `.data` was truthy, short-circuiting the handler
  into returning a `MagicMock` row that failed `AnalysisResponse` validation.
  Fixed by stubbing `mock_table.in_` in the dispatcher.
- `tests/api/test_letter_stream_integration.py::test_findings_stream_event_order_with_strategy_critic_and_repair`
  — the fake `repair_letter_constraints` asserted `model == "gpt-5-mini"`, but the
  route now calls it with `model="gpt-5.4-mini"`; the uncaught `AssertionError`
  killed the SSE generator right after the `repair` phase (so `finalizing` never
  emitted). Fixed by aligning the fake to the current model id.
- `tests/unit/test_cache_redis_toggle.py::TestCacheManagerRedisToggle::test_redis_enabled_attempts_connection`
  — patched `cache_manager.redis`, which only exists as a module attribute when
  the `redis` package is installed (it isn't, in CI). Fixed with `create=True` on
  the patch.
- `tests/integration/test_workflows.py` x4
  (`test_full_document_processing_workflow`, `test_cost_tracking_aggregates_correctly`,
  `test_workflow_graceful_failure`, `test_workflow_skips_document_summary_when_no_case_documents`)
  — the `SimpleNamespace` settings stubs were missing newer feature-flag fields
  (`enable_group_detection`, `enable_group_summarization`, `enable_document_triage`,
  `duplicate_similarity_threshold`), so `process_case_documents` raised
  `AttributeError` and every run resolved to `failed`. Fixed by adding the flags
  (matching production defaults; triage set `False` to bypass into the classic
  T1 path the mocks target). Also added an autouse `_isolate_summary_cache`
  fixture — the T1 path reads a persistent on-disk `DocumentCache` (`.cache`),
  which made `await_count` assertions order- and machine-dependent.
- `progressStore.test.ts` x2 — legacy stage ids `doc_summary`/`issue_mapping`
  renamed in `DEFAULT_STAGES` to `doc_analysis`/`legal_mapping`; the merge drops
  unknown stage ids, so the `.find()` returned `undefined`. Fixed by updating the
  test stage ids.
- `results/tabSwitchBehavior.test.ts::startListening called exactly once even after hide/show cycle`
  — `startListening` gained an options arg (`{ jobId, pollingOnly }`), so the
  strict `toHaveBeenCalledWith('analysis-42')` failed on the extra argument. Fixed
  by asserting the analysisId positionally.

## Frontend (vitest `it.skip`)

All 3 previously-quarantined vitest tests were un-quarantined 2026-07-02 (see
the Resolved list above). Baseline before repair was 4 vitest failures; 1 was
fixed then (the `DEFAULT_STAGES` count grew 5→6) and the remaining 3 are now
fixed. No vitest tests remain quarantined.

## Advisory (not blocking, tracked debt)

- **svelte-check** — burned to **0 errors / 0 warnings** and re-blocked
  2026-07-02 (`continue-on-error` dropped in `.github/workflows/test.yml`). A new
  frontend type error now fails the build. Root causes were 6 test-file type
  errors (missing required `analysisId` prop; `defaultJurisdiction` accessed on a
  `PageLoad` type that includes `void`) and 2 redundant `!== 'error'` guards in
  `DemandLetterSection.svelte` that TS control-flow analysis proved dead (the
  error-setting path throws / the state is already narrowed).
- **ruff style** backlog remains advisory (`continue-on-error`), same pattern as
  Python `mypy`. Widen the blocking `--select` list as categories reach zero.

## CI environment notes (not test debt)

The Test Suite workflow was fully repaired 2026-07-02 (first all-green run:
Actions run 28627988199). Beyond the quarantines above, these were CI
infrastructure fixes, not product/test issues:

- **Mock credentials must be validation-passing.** `OPENAI_API_KEY` must start
  with `sk-`/`sk-proj-` or the app's Settings validator aborts import (suite-wide
  collection errors). CI uses `sk-proj-ci-placeholder…`. `CI_MOCK_SERVICES=true`
  makes live-service tests skip.
- **Frontend build** needs `PUBLIC_API_URL` / `PUBLIC_SUPABASE_URL` /
  `PUBLIC_SUPABASE_ANON_KEY` at build time (static `$env/public` imports).
- **`requirements-dev.txt` doesn't include runtime deps** — CI jobs install both
  `requirements.txt` and `requirements-dev.txt`. (`numpy` was also undeclared and
  is now in `requirements.txt`.)
- **Integration (local Supabase):** install the CLI via `supabase/setup-cli@v1`
  (curl|sh landed off-PATH); extract the running instance's real JWTs (a fresh
  CLI signs with a different secret than hardcoded demo keys); and after
  `supabase db reset`, restore standard API-role grants (a fresh reset omits them
  on migration-created tables) while re-asserting the profiles hardening. If
  migration `20260702000000`'s profiles column lists change, update the grant
  step in `.github/workflows/test.yml` to match.
- **E2E** runs only when `TEST_USER_EMAIL`/`TEST_USER_PASSWORD` secrets exist;
  otherwise it skips green (non-blocking).

## How to un-quarantine

1. Run the test locally with a real `.env`: `venv/bin/pytest <path>::<test> -v`.
2. Fix the underlying mock/fixture/assertion (or product code, for the
   service-role case, with a product decision).
3. Remove the `@pytest.mark.xfail(...)` decorator and its row above.
4. Confirm it passes in the full suite (not just in isolation).
