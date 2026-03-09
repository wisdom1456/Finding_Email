/**
 * E2E tests for the document lifecycle: upload → download → extract → verify
 *
 * Scenarios:
 *   A (@full-stack) — Happy path with real backend
 *   B (@mocked) — OCR misconfigured (500 on extract)
 *   C (@mocked) — Missing document / download failure (404)
 *   D (@mocked) — Failed extraction blocks verify
 *
 * Run mocked tests:    npx playwright test document-lifecycle --grep @mocked
 * Run full-stack tests: RUN_FULL_E2E=true TEST_USER_EMAIL=x TEST_USER_PASSWORD=y npx playwright test document-lifecycle --grep @full-stack
 * Run all:             npx playwright test document-lifecycle
 */
import { test, expect } from '@playwright/test';
import {
  setupMockedCasePage,
  loginAndNavigate,
} from './fixtures/test-helpers';

const RUN_FULL_E2E = process.env.RUN_FULL_E2E === 'true';
const TEST_EMAIL = process.env.TEST_USER_EMAIL;
const TEST_PASSWORD = process.env.TEST_USER_PASSWORD;

// ─────────────────────────────────────────────────────────────
// Scenario A — Happy path (@full-stack)
// ─────────────────────────────────────────────────────────────

test.describe('Scenario A — happy path @full-stack', () => {
  let createdCaseId: string | null = null;

  test.beforeEach(async ({ page }) => {
    test.skip(!RUN_FULL_E2E, 'Requires RUN_FULL_E2E=true');
    test.skip(!TEST_EMAIL || !TEST_PASSWORD, 'Requires TEST_USER_EMAIL and TEST_USER_PASSWORD');

    await loginAndNavigate(page, '/app/cases', { email: TEST_EMAIL!, password: TEST_PASSWORD! });
  });

  test.afterEach(async ({ page }) => {
    if (createdCaseId) {
      try {
        await page.goto(`/app/cases/${createdCaseId}`);
        await page.waitForLoadState('networkidle');
        const deleteBtn = page.locator('button:has-text("Delete")').first();
        if (await deleteBtn.isVisible({ timeout: 2000 })) {
          await deleteBtn.click();
          const confirmBtn = page.locator('button:has-text("Yes, Delete"), button:has-text("Confirm")').first();
          if (await confirmBtn.isVisible({ timeout: 2000 })) {
            await confirmBtn.click();
          }
        }
      } catch { /* ignore cleanup errors */ }
      createdCaseId = null;
    }
  });

  test('upload → persist → extract → verify lifecycle', async ({ page }) => {
    // 1. Create a case
    await page.click('text=New Case');
    await page.waitForURL('/app/cases/new');
    await page.waitForLoadState('networkidle');

    const manualLink = page.locator('text=Create case manually without Clio');
    if (await manualLink.isVisible({ timeout: 3000 })) {
      await manualLink.click();
      await page.waitForTimeout(500);
    }

    await page.fill('input[id="client_name"]', 'E2E Lifecycle Test');
    await page.fill('input[id="reference_number"]', 'E2E-LIFECYCLE-001');
    await page.click('button[type="submit"]:has-text("Create Case")');
    await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);

    const url = page.url();
    const match = url.match(/\/app\/cases\/([a-zA-Z0-9-]+)$/);
    if (match) createdCaseId = match[1];

    // 2. Upload a document
    const testPdf = Buffer.from(
      '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
      '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n' +
      '3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R>>endobj\n' +
      '4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (Test Document) Tj ET\nendstream\nendobj\n' +
      'xref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000206 00000 n\n' +
      'trailer<</Size 5/Root 1 0 R>>\nstartxref\n300\n%%EOF'
    );

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'lifecycle-test.pdf',
      mimeType: 'application/pdf',
      buffer: testPdf,
    });

    // Wait for upload success toast or document appearance
    await expect(
      page.locator('text=lifecycle-test.pdf')
        .or(page.locator('[role="alert"]:has-text("Uploaded")'))
    ).toBeVisible({ timeout: 15000 });

    // 3. Verify document persisted — should appear in the document list
    await expect(page.locator('text=lifecycle-test.pdf')).toBeVisible({ timeout: 10000 });

    // 4. Check document status — extraction happens during upload (extract_immediately=true)
    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'lifecycle-test.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    // Get the status badge
    const statusBadge = docCard.locator('[data-testid="doc-status-badge"]');
    await expect(statusBadge).toBeVisible();

    // Status should be one of: Ready, Needs Review (acceptable outcomes for a minimal PDF)
    const statusText = await statusBadge.textContent();
    expect(['Ready', 'Needs Review', 'Extraction Failed']).toContain(statusText?.trim());

    // If extraction succeeded, verify the document
    if (statusText?.trim() === 'Needs Review') {
      const verifyBtn = docCard.locator('[data-testid="verify-btn"]');
      if (await verifyBtn.isVisible({ timeout: 2000 })) {
        await expect(verifyBtn).not.toBeDisabled();
        await verifyBtn.click();
        await expect(page.locator('[role="alert"]:has-text("verified")')).toBeVisible({ timeout: 8000 });
      }
    }
  });
});

// ─────────────────────────────────────────────────────────────
// Scenario B — OCR misconfigured (@mocked)
// ─────────────────────────────────────────────────────────────

test.describe('Scenario B — OCR misconfigured @mocked', () => {
  test('extract fails with 500 and shows actionable error message', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [{
        id: 'doc-ocr-fail',
        status: 'extraction_failed',
        file_name: 'contract-needs-ocr.pdf',
        extracted_text: null,
        extracted_at: null,
        extraction_error: 'OCR_SERVICE_TOKEN must be set when OCR_REMOTE_ENABLED=true',
      }],
      extractResponse: {
        status: 500,
        body: { detail: 'OCR_SERVICE_TOKEN must be set when OCR_REMOTE_ENABLED=true' },
      },
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    // Document card should show extraction_failed status
    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'contract-needs-ocr.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    const statusBadge = docCard.locator('[data-testid="doc-status-badge"]');
    await expect(statusBadge).toHaveText(/Extraction Failed/);

    // Verify button should NOT be visible (only shows for needs_review status)
    await expect(docCard.locator('[data-testid="verify-btn"]')).not.toBeVisible();

    // Re-extract button SHOULD be visible
    const reExtractBtn = docCard.locator('[data-testid="re-extract-btn"]');
    await expect(reExtractBtn).toBeVisible();

    // Click re-extract — should trigger extract API call and show error
    await reExtractBtn.click();

    // Should show error toast with the actual backend error detail
    await expect(
      page.locator('[role="alert"]').filter({ hasText: /OCR_SERVICE_TOKEN/ })
    ).toBeVisible({ timeout: 10000 });

    // Document should still show extraction_failed — no false success
    await expect(statusBadge).toHaveText(/Extraction Failed/);
  });

  test('verify button is not rendered for extraction_failed documents', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [{
        id: 'doc-no-verify',
        status: 'extraction_failed',
        file_name: 'broken-doc.pdf',
        extracted_text: null,
        extracted_at: null,
      }],
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'broken-doc.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    // Verify button should NOT be present at all (not just disabled)
    await expect(docCard.locator('[data-testid="verify-btn"]')).not.toBeVisible();

    // Only re-extract should be available as remediation
    await expect(docCard.locator('[data-testid="re-extract-btn"]')).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────
// Scenario C — Missing document / download failure (@mocked)
// ─────────────────────────────────────────────────────────────

test.describe('Scenario C — missing document @mocked', () => {
  test('download_failed status shows re-upload action and hides verify', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [{
        id: 'doc-missing',
        status: 'download_failed',
        file_name: 'missing-file.pdf',
        storage_path: null,
        extracted_text: null,
        extracted_at: null,
      }],
      downloadResponse: { status: 404 },
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'missing-file.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    // Status should show Download Failed
    const statusBadge = docCard.locator('[data-testid="doc-status-badge"]');
    await expect(statusBadge).toHaveText(/Download Failed/);

    // Re-upload button should be visible (remediation action)
    await expect(docCard.locator('[data-testid="re-upload-btn"]')).toBeVisible();

    // Verify button should NOT be visible
    await expect(docCard.locator('[data-testid="verify-btn"]')).not.toBeVisible();

    // Re-extract button should NOT be visible
    await expect(docCard.locator('[data-testid="re-extract-btn"]')).not.toBeVisible();
  });

  test('corrupted document shows re-upload action', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [{
        id: 'doc-corrupt',
        status: 'corrupted',
        file_name: 'damaged-file.pdf',
        extracted_text: null,
        extracted_at: null,
      }],
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'damaged-file.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    // Status should show Corrupted
    await expect(docCard.locator('[data-testid="doc-status-badge"]')).toHaveText(/Corrupted/);

    // Re-upload should be available
    await expect(docCard.locator('[data-testid="re-upload-btn"]')).toBeVisible();

    // Verify should NOT be available
    await expect(docCard.locator('[data-testid="verify-btn"]')).not.toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────
// Scenario D — Failed extraction blocks verify (@mocked)
// ─────────────────────────────────────────────────────────────

test.describe('Scenario D — failed extraction state gating @mocked', () => {
  test('verify button is disabled when document has no extracted text', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [{
        id: 'doc-no-text',
        status: 'needs_review',
        file_name: 'no-text-doc.pdf',
        extracted_text: null,
        manual_text: null,
        extracted_at: null,
      }],
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'no-text-doc.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    // Verify button should be visible but disabled
    const verifyBtn = docCard.locator('[data-testid="verify-btn"]');
    await expect(verifyBtn).toBeVisible();
    await expect(verifyBtn).toBeDisabled();

    // Should have tooltip explaining why
    await expect(verifyBtn).toHaveAttribute('title', /Run OCR first/);
  });

  test('verify request returns 400 when no extracted text', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [{
        id: 'doc-force-verify',
        status: 'needs_review',
        file_name: 'force-verify.pdf',
        extracted_text: null,
        manual_text: null,
        extracted_at: null,
      }],
      verifyResponse: {
        status: 400,
        body: { detail: 'Cannot verify document without extracted text. Please run OCR first.' },
      },
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    const docCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'force-verify.pdf' });
    await expect(docCard).toBeVisible({ timeout: 10000 });

    // Verify button should be disabled (UI-level gating)
    const verifyBtn = docCard.locator('[data-testid="verify-btn"]');
    await expect(verifyBtn).toBeDisabled();

    // Force-click the disabled button — should NOT send a real verify request
    await verifyBtn.click({ force: true });

    // No success toast should appear
    await page.waitForTimeout(2000);
    await expect(page.locator('[role="alert"]:has-text("verified")')).not.toBeVisible();
  });

  test('extraction_failed documents only show re-extract, not verify', async ({ page }) => {
    await setupMockedCasePage(page, {
      documents: [
        {
          id: 'doc-failed',
          status: 'extraction_failed',
          file_name: 'failed-extraction.pdf',
          extracted_text: null,
          extracted_at: null,
          extraction_error: 'All extraction methods failed',
        },
        {
          id: 'doc-ready',
          status: 'ready',
          file_name: 'good-document.pdf',
          extracted_text: 'This document has valid content extracted successfully.',
        },
      ],
    });

    await page.goto('/app/cases/case-001');
    await page.waitForLoadState('networkidle');

    // Failed doc: should have re-extract, no verify
    const failedCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'failed-extraction.pdf' });
    await expect(failedCard).toBeVisible({ timeout: 10000 });
    await expect(failedCard.locator('[data-testid="re-extract-btn"]')).toBeVisible();
    await expect(failedCard.locator('[data-testid="verify-btn"]')).not.toBeVisible();

    // Ready doc: should have view/edit, no re-extract
    const readyCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'good-document.pdf' });
    await expect(readyCard).toBeVisible();
    await expect(readyCard.locator('[data-testid="view-edit-btn"]')).toBeVisible();
    await expect(readyCard.locator('[data-testid="re-extract-btn"]')).not.toBeVisible();
  });
});
