# Legal Portal Comprehensive Test Plan

This plan translates the approved roadmap into concrete actions across backend APIs, frontend GUI interactions, and cross-stack validation. It prioritizes the high-risk areas called out by the team: email discovery workflows, administrator/reporting dashboards, GUI button interactions, and FastAPI endpoint reliability. Day-to-day suites use fast feedback stacks (`pytest` with FastAPI `TestClient`, `Vitest` + `@testing-library/svelte`), with Playwright reserved for targeted end-to-end coverage.

---

## 1. Requirements & Inventory Snapshot

- **Reference docs reviewed:** `README.md`, `TESTING_GUIDE.md`, memory bank entries (case analysis + Clio integration), existing Python suites under `tests/`.
- **Core components to protect:**
  - `src/legal_portal/api/routes/` (cases, documents, intake, analysis, health, Clio import/export)
  - `src/legal_portal/services/main_processor.py` and downstream AI/corpus services
  - SvelteKit routes under `frontend/src/routes/app` and shared components in `frontend/src/lib/components`
- **Existing automation:** ~26 pytest cases freezing legacy Streamlit behaviour (`tests/README.md`). These continue to guard business logic while new suites target FastAPI/SvelteKit.
- **Environments:** Backend at `http://localhost:8000`, frontend at `http://localhost:5173`, Supabase (RLS enforced). Logs available in `backend.log` / `frontend.log` for triage hooks.

---

## 2. Backend Test Plan (FastAPI + pytest)

### 2.1 Testing Layers

| Layer | Scope | Tooling | Notes |
| --- | --- | --- | --- |
| Unit | Pure services/utilities (`cost_calculator`, `corpus_coverage_service`, `ai_analyzer` helpers) | `pytest`, `pytest-mock`, `freezegun` | Expand existing unit files with new fixtures, especially for token/cost regressions |
| Integration/API | FastAPI routes exercising auth, Supabase RLS and Clio adapters | `pytest` + `httpx.AsyncClient` via `TestClient` fixture | Run against in-memory app factory with mocked Supabase; real Supabase smoke hits reserved for nightly pipeline |
| Contract/Regression | External touchpoints (Supabase schemas, Clio API, AI prompt schema) | JSON schema validators, snapshot testing | Capture serialized responses to shield frontend contract |

### 2.2 Fixtures & Utilities

- **`app_client` fixture:** Instantiate FastAPI app (`legal_portal.api.main.create_app`) and yield `AsyncClient`.
- **Supabase mocks:** Use `monkeypatch` to plug deterministic fake clients (mirroring approach in legacy tests) to avoid network calls while still checking RLS headers.
- **JWT/auth helpers:** Generate signed tokens for `get_current_user` via local secret to cover authorized/unauthorized paths.
- **Document factory:** Minimal case + document payload generator stored in `tests/factories.py` for reuse by cases/documents/analysis scenarios.

### 2.3 Endpoint Matrix (priority focus: email discovery + admin/reporting)

| Group | Endpoint | Priority | Core Assertions |
| --- | --- | --- | --- |
| Health | `GET /api/health`, `GET /api/health/detailed` | P1 | Base uptime, Supabase/OpenAI check gating |
| Cases | `POST /api/cases`, `GET /api/cases`, `GET /api/cases/{id}`, `PATCH /api/cases/{id}`, `DELETE /api/cases/{id}` | **P0** (email discovery entry point) | Auth required, RLS enforcement, status transitions, cascade deletes (documents + storage) |
| Documents | `POST /api/documents/upload`, `GET /api/cases/{id}/documents` | P0 | Allowed file types, storage path propagation, duplicate detection, error mapping |
| Intake & Analysis | `POST /api/intake/analyze`, `POST /api/analysis/start`, `GET /api/analysis/{case_id}` | P0 | Intake ingestion, job dispatch, timeline updates, error bubble-up, QA warnings |
| Email Discovery | `POST /api/analysis/email_discovery`, `GET /api/analysis/email_discovery/{case_id}` (verify actual route names) | **P0** | Ensure structured discovery payload, status states (queued, running, ready), edge cases (missing documents) |
| Admin/Reporting | `GET /api/admin/dashboard`, `GET /api/cost/sessions`, `GET /api/metrics` (as available) | **P1** | Aggregations, role-based gating, pagination |
| Clio Integration | `POST /api/clio/matters/{id}/import`, `GET /api/clio/matters` | P1 | Token refresh, partial failures, retry hints |

*(Verify exact route names/paths while implementing; placeholders reflect folder structure.)*

### 2.4 Representative Test Cases

1. **Case creation happy path** – Valid JWT + payload → 201 + persisted row; confirm `user_id` matches token and `status=pending`.
2. **Case list RLS** – User A creates case, User B queries list → empty result, ensures Supabase session uses B’s access token.
3. **Document upload rejects unsupported extension** – `.exe` file triggers 400 with audit log entry.
4. **Analysis trigger without intake** – Start analysis when no intake data exists → 400 with actionable message.
5. **Email discovery end-to-end** – Insert mock analysis result then hit discovery endpoint → returns deduped email set and actionable metadata.
6. **Admin dashboard requires role** – Non-admin token receives 403; admin sees aggregated totals with expected schema.

### 2.5 Coverage & Metrics

- **Per-module targets:** 80% statements for `src/legal_portal/api/routes/` and `services/main_processor.py`.
- **Blocking criteria:** Any regression in case/analysis/email discovery endpoints fails CI gate.
- **Reporting:** `pytest --cov=src/legal_portal --cov-report=xml` for CI; HTML locally.

---

## 3. Frontend Test Plan (SvelteKit + Vitest)

### 3.1 Tooling & Configuration

- **Stack:** `Vitest`, `@testing-library/svelte`, `@testing-library/user-event`, `msw` (Mock Service Worker) for REST mocks.
- **Project setup:** Add `vitest.config.ts` aligned with `tsconfig.json`; ensure `package.json` scripts include `test`, `test:ui` (watch).
- **Shared mocks:** Supabase client shim under `frontend/src/lib/__mocks__/supabase.ts` plus `window.matchMedia` polyfill for Tailwind breakpoints.

### 3.2 Coverage Tiers

| Tier | Focus | Representative Scope |
| --- | --- | --- |
| Smoke | Render + minimal interaction | `routes/+page.svelte` (landing/login), layout auth redirects |
| Interaction (priority) | Button workflows, validation, state changes | Buttons for login/register, “New Case”, “Start Analysis”, “Run Email Discovery”, admin toggles |
| Visual Regression | Critical pages snapshot comparison | Optional Percy/Chromatic after core tests land |

### 3.3 Button Interaction Matrix (high priority)

| View | Button(s) | Assertions |
| --- | --- | --- |
| `login/+page.svelte` | “Sign In”, “Forgot password?” link | Form validation (disabled state), Supabase auth call, error banners |
| `register/+page.svelte` | “Create Account” | Password strength hints, success toast, routing to login |
| `app/+page.svelte` dashboard | “Create Case”, filter buttons, admin cards | Button enables form modal, triggers store updates, responsive layout (mobile vs desktop) |
| `app/cases/+page.svelte` | “New Case”, “Import from Clio”, row action buttons | API mutation fired, optimistic updates, disabled while pending |
| `app/cases/[id]/+page.svelte` | “Upload Document”, “Start Analysis”, “Run Email Discovery”, “Generate Letter” | Multi-step modals, button spinner states, error toasts, ensures backend calls invoked with correct payload |
| `app/cases/[id]/results/+page.svelte` | “Download PDF/HTML”, “Refresh results” | Buttons call download endpoints, handle empty states |
| Admin/reporting (if under `app/+layout` sidebar) | Status filter chips, “Export CSV” button | Data table updates, export call triggered, loading overlay toggles |

Each button test should:
1. Render component with deterministic mocked data.
2. Simulate user action (`userEvent.click`).
3. Assert side effects: store writes (`clioStore`), `fetch` calls via `msw`, button disabled/enabled toggles, success/error banners.
4. Include accessibility checks (button has descriptive text, `aria-busy` when loading; keyboard activation via `Enter`/`Space`).

### 3.4 State & Store Tests

- Unit-test `frontend/src/lib/stores/clioStore.ts` to ensure derived state updates when new Clio matter imported or when import fails.
- Derived selectors verifying that email discovery data surfaces correctly within `ClioLinkedMatter` component.

### 3.5 Accessibility & Responsiveness

- Add `@testing-library/jest-dom` matchers (`toHaveAccessibleName`, `toHaveAttribute`).
- Use `vitest-axe` (or `axe-core` via helper) on key pages to catch regressions in high-density button grids.
- Snapshot different viewport classes by setting `document.documentElement.clientWidth` before rendering components requiring responsive behaviour.

### 3.6 Coverage Targets

- 90%+ interaction coverage for the button matrix above.
- All route-level components must have at least one smoke + one interaction test.

---

## 4. End-to-End & CI Strategy

### 4.1 Targeted Playwright Suites

| Scenario | Steps | Validations |
| --- | --- | --- |
| Email Discovery Happy Path | Login → create case → upload sample doc → start analysis → run email discovery → view results | Buttons transition states, backend receives requests, UI displays discovered emails + citations |
| Admin Dashboard Reporting | Login as admin → open dashboard → toggle filters → export cost report | Chart/table updates, download triggered, backend metrics endpoint hit |
| Clio Import Quick Check | Login → navigate to Clio integration → trigger import → confirm progress modal | Ensure progress indicator updates + success banner, fallback error path |

- Use seeded data/fixtures in Supabase dev project to keep deterministic.
- Playwright config: run headless in CI, video on failure, parallel workers=2 to keep runtime reasonable.

### 4.2 CI Integration

1. **Workflow structure (GitHub Actions or equivalent):**
   - `lint` job: `ruff`, `npm run lint`
   - `backend-tests` job: `pytest --cov`
   - `frontend-tests` job: `npm run test -- --runInBand`
   - `e2e` job: Spin up backend (`uvicorn legal_portal.api.main:app --reload`), frontend (`npm run dev -- --host`), run `npx playwright test`
2. **Artifacts:** Upload coverage XML, Vitest JUnit, Playwright traces on failure.
3. **Gates:** Require backend + frontend jobs to pass on every PR; Playwright optional on demand or nightly if runtime is a concern.
4. **Environment variables:** Inject Supabase anon/service keys through CI secrets; use `.env.ci` template with safe defaults for mocks.

### 4.3 Reporting & Alerts

- Post coverage summaries to PR via `actions/github-script`.
- Hook Playwright failures to Slack/email with trace links for faster triage.
- Maintain `reports/baseline.json` updated weekly from Playwright + API contract snapshots to detect drift.

---

## 5. Next Steps & Ownership

1. **Backend team:** Extend pytest suites per matrix, prioritize cases/documents/analysis/email discovery endpoints.
2. **Frontend team:** Stand up Vitest harness, implement button interaction suite starting with login/new case/analysis triggers.
3. **Infra/QA:** Configure Playwright pipeline + nightly run, ensure Supabase test data reset script exists.

Once these pillars are in place, expand coverage incrementally (e.g., Streamlit fallback UI) and enforce thresholds via CI to prevent regressions.

