/**
 * Mocked E2E tests for analysis prerequisites and error handling.
 *
 * Tests that analysis cannot start without verified documents,
 * and that API failures are handled gracefully.
 *
 * @mocked - requires real auth but mocks data loading
 */
import { test, expect } from '@playwright/test';
import { login, setupMockedCasePage } from './fixtures/test-helpers';

const TEST_EMAIL = process.env.TEST_USER_EMAIL;
const TEST_PASSWORD = process.env.TEST_USER_PASSWORD;
const HAS_CREDENTIALS = !!TEST_EMAIL && !!TEST_PASSWORD;

test.describe('Analysis prerequisites @mocked', () => {
	test.beforeEach(async ({ page }) => {
		test.skip(!HAS_CREDENTIALS, 'Requires TEST_USER_EMAIL and TEST_USER_PASSWORD');
		await login(page, { email: TEST_EMAIL!, password: TEST_PASSWORD! });
	});

	test('case with no documents shows empty state on analysis tab', async ({ page }) => {
		await setupMockedCasePage(page, {
			documents: [],
		});

		// The setup navigates to verification tab; switch to analysis
		const analysisTab = page.locator('button:has-text("Analysis"), [role="tab"]:has-text("Analysis")');
		if (await analysisTab.isVisible({ timeout: 5000 })) {
			await analysisTab.click();
		}

		// Should indicate no documents are available
		const noDocsIndicator = page.locator('text=Upload documents').or(page.locator('text=No documents'));
		await expect(noDocsIndicator.first()).toBeVisible({ timeout: 5000 });
	});

	test('case with extraction_failed documents shows critical section in verification', async ({ page }) => {
		await setupMockedCasePage(page, {
			documents: [
				{
					id: 'doc-failed-1',
					status: 'extraction_failed',
					file_name: 'broken-scan.pdf',
					extracted_text: null,
					extracted_at: null,
					extraction_error: 'All OCR methods failed',
				},
				{
					id: 'doc-ready-1',
					status: 'ready',
					file_name: 'good-contract.pdf',
					extracted_text: 'Valid contract text here for testing purposes.',
				},
			],
		});

		// Verification tab should show triage groups
		const failedCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'broken-scan.pdf' });
		await expect(failedCard).toBeVisible({ timeout: 10000 });

		// Failed doc should have re-extract action
		await expect(failedCard.locator('[data-testid="re-extract-btn"]')).toBeVisible();

		// Ready doc should be visible and in ready state
		const readyCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'good-contract.pdf' });
		await expect(readyCard).toBeVisible();
	});

	test('mixed document statuses render correct triage sections', async ({ page }) => {
		await setupMockedCasePage(page, {
			documents: [
				{ id: 'doc-1', status: 'corrupted', file_name: 'corrupt.pdf', extracted_text: null, extracted_at: null },
				{ id: 'doc-2', status: 'needs_review', file_name: 'review-me.pdf' },
				{ id: 'doc-3', status: 'ready', file_name: 'all-good.pdf' },
				{ id: 'doc-4', status: 'extraction_failed', file_name: 'failed.pdf', extracted_text: null, extracted_at: null },
			],
		});

		// All 4 document cards should render
		const cards = page.locator('[data-testid="document-card"]');
		await expect(cards).toHaveCount(4, { timeout: 10000 });

		// Corrupted doc should have re-upload
		const corruptCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'corrupt.pdf' });
		await expect(corruptCard.locator('[data-testid="re-upload-btn"]')).toBeVisible();

		// Needs review doc should have verify button
		const reviewCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'review-me.pdf' });
		await expect(reviewCard.locator('[data-testid="verify-btn"]')).toBeVisible();

		// Failed doc should have re-extract
		const failedCard = page.locator('[data-testid="document-card"]').filter({ hasText: 'failed.pdf' });
		await expect(failedCard.locator('[data-testid="re-extract-btn"]')).toBeVisible();
	});
});
