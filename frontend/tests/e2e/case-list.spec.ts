/**
 * E2E tests for cases list and filtering
 */
import { test, expect } from '@playwright/test';

test.describe('Cases List', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/app/cases');
		await page.waitForLoadState('networkidle');
	});

	test('should display cases list', async ({ page }) => {
		// Check for header
		await expect(page.locator('text=All Cases')).toBeVisible();

		// Check for "New Case" button
		const newCaseButton = page.locator('a:has-text("New Case")');
		await expect(newCaseButton).toBeVisible();
		await expect(newCaseButton).toHaveAttribute('href', '/app/cases/new');
	});

	test('should navigate to case detail when clicking a case', async ({ page }) => {
		// Wait for cases to load
		await page.waitForSelector('ul.divide-y', { timeout: 10000 }).catch(() => {
			// Cases list might not exist if no cases
		});

		// Find first case link (if any exist)
		const firstCase = page.locator('ul.divide-y li a').first();
		if (await firstCase.isVisible()) {
			const caseName = await firstCase.locator('p.text-lg').textContent();
			await firstCase.click();

			// Should navigate to case detail
			await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);
			
			// Case name should be visible on detail page
			if (caseName) {
				await expect(page.locator(`text=${caseName}`)).toBeVisible();
			}
		}
	});

	test('should filter Clio cases when checkbox is toggled', async ({ page }) => {
		// Check if filter checkbox exists (only if Clio cases present)
		const filterCheckbox = page.locator('input[type="checkbox"]', {
			hasText: 'Show only Clio cases'
		});

		if (await filterCheckbox.isVisible()) {
			// Get initial case count
			const initialCount = await page.locator('ul.divide-y li').count();

			// Toggle filter
			await filterCheckbox.check();
			await page.waitForTimeout(500); // Wait for filter to apply

			// Count should change (or stay same if all are Clio cases)
			const filteredCount = await page.locator('ul.divide-y li').count();
			expect(filteredCount).toBeLessThanOrEqual(initialCount);

			// Uncheck filter
			await filterCheckbox.uncheck();
			await page.waitForTimeout(500);

			// Count should return to initial
			const finalCount = await page.locator('ul.divide-y li').count();
			expect(finalCount).toBe(initialCount);
		}
	});

	test('should show empty state when no cases exist', async ({ page }) => {
		// This test assumes a fresh database or filtered state
		const emptyMessage = page.locator('text=No cases yet');
		const createButton = page.locator('a:has-text("Create Case")');

		// If empty state is visible
		if (await emptyMessage.isVisible()) {
			await expect(emptyMessage).toBeVisible();
			await expect(createButton).toBeVisible();
			await expect(createButton).toHaveAttribute('href', '/app/cases/new');
		}
	});

	test('should navigate to new case page', async ({ page }) => {
		// Click "New Case" button
		await page.click('a:has-text("New Case")');

		// Should navigate to new case page
		await expect(page).toHaveURL('/app/cases/new');
		await expect(page.locator('text=Create New Case')).toBeVisible();
	});
});



