/**
 * E2E tests for case creation workflow
 */
import { test, expect } from '@playwright/test';

test.describe('Case Creation Flow', () => {
	test.beforeEach(async ({ page }) => {
		// Navigate to cases list
		await page.goto('/app/cases');
	});

	test('should create a manual case successfully', async ({ page }) => {
		// Click "New Case" button
		await page.click('text=New Case');
		await expect(page).toHaveURL('/app/cases/new');

		// Wait for page to load
		await page.waitForLoadState('networkidle');

		// Click "Create Manual Case" button if Clio is not connected
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		if (await manualButton.isVisible()) {
			await manualButton.click();
		}

		// Fill in the form
		await page.fill('input[id="client_name"]', 'E2E Test Client');
		await page.fill('input[id="reference_number"]', 'E2E-2024-001');
		await page.fill('textarea[id="description"]', 'This is an end-to-end test case');

		// Submit the form
		await page.click('button[type="submit"]:has-text("Create Case")');

		// Wait for navigation to case detail page
		await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);

		// Verify we're on the case detail page
		await expect(page.locator('text=E2E Test Client')).toBeVisible();
	});

	test('should show validation error for empty client name', async ({ page }) => {
		await page.goto('/app/cases/new');
		await page.waitForLoadState('networkidle');

		// Try to find manual case button
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		if (await manualButton.isVisible()) {
			await manualButton.click();
		}

		// Leave client name empty and try to submit
		const submitButton = page.locator('button[type="submit"]:has-text("Create Case")');
		
		// Button should be disabled
		await expect(submitButton).toBeDisabled();
	});

	test('should toggle between Clio search and manual form', async ({ page }) => {
		await page.goto('/app/cases/new');
		await page.waitForLoadState('networkidle');

		// Check if we can toggle to manual form
		const toggleButton = page.locator('text=Create case manually without Clio');
		if (await toggleButton.isVisible()) {
			await toggleButton.click();

			// Should now show manual form
			await expect(page.locator('input[id="client_name"]')).toBeVisible();

			// Should have back button
			const backButton = page.locator('text=Back to Clio Search');
			await expect(backButton).toBeVisible();
			
			// Click back
			await backButton.click();
			
			// Should show Clio search again
			await expect(page.locator('text=Find Your Clio Matter')).toBeVisible();
		}
	});
});

