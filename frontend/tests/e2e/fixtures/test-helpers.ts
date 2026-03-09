import { type Page } from '@playwright/test';

// ── Mock Data Factories ──

export interface MockDocumentOptions {
  id?: string;
  status?: string;
  file_name?: string;
  extracted_text?: string | null;
  manual_text?: string | null;
  extraction_error?: string | null;
  storage_path?: string | null;
  is_verified?: boolean;
  extracted_at?: string | null;
  extraction_quality?: string | null;
  metadata?: Record<string, any>;
}

export function mockDocument(overrides: MockDocumentOptions = {}) {
  // Use 'key in obj' checks for nullable fields where null is a meaningful value
  // (nullish coalescing ?? treats null as "not provided", which breaks null overrides)
  return {
    id: overrides.id ?? 'doc-001',
    case_id: 'case-001',
    file_name: overrides.file_name ?? 'test-contract.pdf',
    file_type: 'application/pdf',
    file_size: 102400,
    storage_path: 'storage_path' in overrides ? overrides.storage_path : 'user-1/case-001/doc-001.pdf',
    status: overrides.status ?? 'ready',
    extraction_method: 'Google Cloud Vision',
    extraction_quality: 'extraction_quality' in overrides ? overrides.extraction_quality : 'high',
    extracted_at: 'extracted_at' in overrides ? overrides.extracted_at : '2025-01-01T00:00:00Z',
    page_count: 3,
    ocr_provider: 'google_vision',
    extraction_error: 'extraction_error' in overrides ? overrides.extraction_error : null,
    is_verified: overrides.is_verified ?? false,
    is_flagged_as_junk: false,
    text_edited_at: null,
    extracted_text: 'extracted_text' in overrides ? overrides.extracted_text : 'Sample extracted text content for testing purposes with enough words to pass quality checks and validation requirements in the document card component.',
    manual_text: 'manual_text' in overrides ? overrides.manual_text : null,
    metadata: overrides.metadata ?? {},
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  };
}

export function mockCase(overrides: Record<string, any> = {}) {
  return {
    id: 'case-001',
    client_name: 'E2E Test Client',
    reference_number: 'E2E-001',
    description: 'Test case for E2E',
    status: 'active',
    user_id: 'user-1',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

// ── Full-Stack Login Helper ──

/**
 * Login via the real Supabase auth flow.
 * Required for all tests because SvelteKit server-side hooks
 * redirect unauthenticated requests to /login.
 */
export async function login(
  page: Page,
  credentials?: { email: string; password: string }
) {
  const email = credentials?.email ?? process.env.TEST_USER_EMAIL!;
  const password = credentials?.password ?? process.env.TEST_USER_PASSWORD!;

  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  if (!page.url().includes('/app/')) {
    await page.fill('input[type="email"]', email);
    await page.fill('input[type="password"]', password);
    await page.click('button:has-text("Sign in")');
    await page.waitForURL(/\/app/, { timeout: 15000 });
  }
}

export async function loginAndNavigate(
  page: Page,
  path: string,
  credentials?: { email: string; password: string }
) {
  await login(page, credentials);
  await page.goto(path);
  await page.waitForLoadState('networkidle');
}

// ── API Route Interception ──

/**
 * Sets up route interception for a case detail page with mocked documents.
 *
 * IMPORTANT: The page must be authenticated first (call `login()` before this).
 * SvelteKit server-side hooks validate auth via server-to-server calls to Supabase
 * which cannot be intercepted by Playwright. After auth passes, the page component
 * loads data client-side via browser requests that CAN be intercepted.
 *
 * This function:
 * 1. Sets up route interception for Supabase REST API + backend API calls
 * 2. Navigates to the case detail page
 * 3. Waits for the page to finish loading
 */
export async function setupMockedCasePage(
  page: Page,
  options: {
    documents?: MockDocumentOptions[];
    caseData?: Record<string, any>;
    extractResponse?: { status: number; body: any };
    verifyResponse?: { status: number; body: any };
    downloadResponse?: { status: number; body?: any; contentType?: string };
  } = {}
) {
  const docs = (options.documents ?? [{ status: 'ready' }]).map(d => mockDocument(d));
  const caseData = mockCase(options.caseData);

  // Intercept Supabase REST API — case query (single-row response)
  await page.route('**/rest/v1/cases?*', async (route) => {
    const url = route.request().url();
    if (url.includes('select=')) {
      // Supabase PostgREST returns the object directly when using .single()
      // but the frontend may use .eq() which returns an array
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(caseData),
        headers: { 'content-range': '0-0/1' },
      });
    } else {
      await route.fallback();
    }
  });

  // Intercept Supabase REST API — documents query
  await page.route('**/rest/v1/documents?*', async (route) => {
    const url = route.request().url();
    if (url.includes('select=')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(docs),
      });
    } else {
      await route.fallback();
    }
  });

  // Intercept Supabase REST API — analysis_results query
  await page.route('**/rest/v1/analysis_results?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(null),
    });
  });

  // Intercept backend API — extract endpoint
  if (options.extractResponse) {
    await page.route('**/api/documents/*/extract', async (route) => {
      await route.fulfill({
        status: options.extractResponse!.status,
        contentType: 'application/json',
        body: JSON.stringify(options.extractResponse!.body),
      });
    });
  }

  // Intercept backend API — verify endpoint
  if (options.verifyResponse) {
    await page.route('**/api/documents/*/verify', async (route) => {
      await route.fulfill({
        status: options.verifyResponse!.status,
        contentType: 'application/json',
        body: JSON.stringify(options.verifyResponse!.body),
      });
    });
  }

  // Intercept Supabase Storage — download
  if (options.downloadResponse) {
    await page.route('**/storage/v1/object/**/documents/**', async (route) => {
      if (options.downloadResponse!.status === 404) {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Object not found', message: 'The resource was not found' }),
        });
      } else {
        await route.fulfill({
          status: options.downloadResponse!.status,
          contentType: options.downloadResponse!.contentType ?? 'application/pdf',
          body: options.downloadResponse!.body ?? 'mock-file-content',
        });
      }
    });
  }

  // Intercept backend API — cross-document enrichment (prevent real call)
  await page.route('**/api/documents/case/*/enrich-cross-document', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ enriched: 0, registries_built: 0 }),
    });
  });

  // Intercept backend API — Clio status
  await page.route('**/api/clio/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ connected: false }),
    });
  });

  // Navigate to the case page on the verification tab where DocumentCards render.
  // Server-side auth will pass (we're logged in), then client-side data loading
  // will hit our intercepted routes.
  await page.goto('/app/cases/case-001?tab=verification');
  await page.waitForLoadState('networkidle');
}

// ── Assertion Helpers ──

/**
 * Wait for a toast notification containing specific text.
 * Returns the toast element locator.
 */
export async function waitForToast(page: Page, textPattern: string | RegExp) {
  const toast = page.locator('[role="alert"]').filter({
    hasText: typeof textPattern === 'string' ? textPattern : undefined,
  });

  if (typeof textPattern === 'string') {
    await toast.filter({ hasText: textPattern }).first().waitFor({ timeout: 10000 });
    return toast.filter({ hasText: textPattern }).first();
  } else {
    await toast.first().waitFor({ timeout: 10000 });
    return toast.first();
  }
}

/**
 * Wait for a toast error notification.
 */
export async function waitForErrorToast(page: Page, textPattern: string | RegExp) {
  return waitForToast(page, textPattern);
}
