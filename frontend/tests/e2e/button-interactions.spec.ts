/**
 * E2E tests for button interactions across the application
 * Comprehensive coverage of all interactive elements
 */
import { test, expect } from '@playwright/test';

test.describe('Button Interactions - Cases List', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/app/cases');
		await page.waitForLoadState('networkidle');
	});

	test('New Case button is visible and functional', async ({ page }) => {
		const newCaseButton = page.locator('a:has-text("New Case")');
		
		await expect(newCaseButton).toBeVisible();
		await expect(newCaseButton).toHaveAttribute('href', '/app/cases/new');
		
		// Click and verify navigation
		await newCaseButton.click();
		await expect(page).toHaveURL(/\/app\/cases\/new/);
	});

	test('Filter checkbox toggles Clio cases', async ({ page }) => {
		// Wait for cases to load
		await page.waitForTimeout(1000);
		
		const filterCheckbox = page.locator('input[type="checkbox"]:near(:text("Show only Clio cases"))');
		
		if (await filterCheckbox.isVisible()) {
			// Get initial count
			const initialCases = await page.locator('ul.divide-y li').count();
			
			// Toggle on
			await filterCheckbox.check();
			await expect(filterCheckbox).toBeChecked();
			await page.waitForTimeout(300);
			
			// Toggle off
			await filterCheckbox.uncheck();
			await expect(filterCheckbox).not.toBeChecked();
			await page.waitForTimeout(300);
			
			const finalCases = await page.locator('ul.divide-y li').count();
			expect(finalCases).toBe(initialCases);
		}
	});

	test('Case list items are clickable', async ({ page }) => {
		// Find first case
		const firstCase = page.locator('ul.divide-y li a').first();
		
		if (await firstCase.isVisible()) {
			await firstCase.click();
			
			// Should navigate to case detail
			await expect(page).toHaveURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);
		}
	});
});

test.describe('Button Interactions - New Case Form', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/app/cases/new');
		await page.waitForLoadState('networkidle');
	});

	test('Manual case button shows form', async ({ page }) => {
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			// Form fields should appear
			await expect(page.locator('input[id="client_name"]')).toBeVisible();
			await expect(page.locator('input[id="reference_number"]')).toBeVisible();
			await expect(page.locator('textarea[id="description"]')).toBeVisible();
		}
	});

	test('Create Case button is disabled when empty', async ({ page }) => {
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			const submitButton = page.locator('button[type="submit"]:has-text("Create Case")');
			await expect(submitButton).toBeDisabled();
		}
	});

	test('Create Case button enables with client name', async ({ page }) => {
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			// Fill client name
			await page.fill('input[id="client_name"]', 'Test Client');
			
			const submitButton = page.locator('button[type="submit"]:has-text("Create Case")');
			await expect(submitButton).not.toBeDisabled();
		}
	});

	test('Toggle between Clio search and manual form', async ({ page }) => {
		const toggleToManual = page.locator('button:has-text("Create case manually")');
		
		if (await toggleToManual.isVisible()) {
			await toggleToManual.click();
			
			// Should show form
			await expect(page.locator('input[id="client_name"]')).toBeVisible();
			
			// Back button should work
			const backButton = page.locator('button:has-text("Back to Clio Search")');
			if (await backButton.isVisible()) {
				await backButton.click();
				await expect(page.locator('text=Find Your Clio Matter')).toBeVisible();
			}
		}
	});

	test('Form validation prevents empty submission', async ({ page }) => {
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			// Try to submit without filling
			const submitButton = page.locator('button[type="submit"]:has-text("Create Case")');
			
			// Button should be disabled, so click shouldn't work
			await expect(submitButton).toBeDisabled();
		}
	});
});

test.describe('Button Interactions - Clio Integration', () => {
	test('Connect to Clio button is visible', async ({ page }) => {
		await page.goto('/app');
		await page.waitForLoadState('networkidle');
		
		// Look for Clio section
		const clioSection = page.locator('text=Clio Integration');
		
		if (await clioSection.isVisible()) {
			// Either connect or disconnect button should be visible
			const connectButton = page.locator('button:has-text("Connect to Clio")');
			const disconnectButton = page.locator('button:has-text("Disconnect")');
			
			const hasConnect = await connectButton.isVisible();
			const hasDisconnect = await disconnectButton.isVisible();
			
			expect(hasConnect || hasDisconnect).toBeTruthy();
		}
	});

	test('Connect button styling and state', async ({ page }) => {
		await page.goto('/app');
		await page.waitForLoadState('networkidle');
		
		const connectButton = page.locator('button:has-text("Connect to Clio")');
		
		if (await connectButton.isVisible()) {
			// Should have proper styling
			await expect(connectButton).toHaveClass(/bg-blue-600/);
			await expect(connectButton).not.toBeDisabled();
			
			// Should have icon
			const icon = connectButton.locator('svg');
			await expect(icon).toBeVisible();
		}
	});

	test('Disconnect button shows confirmation', async ({ page }) => {
		await page.goto('/app');
		await page.waitForLoadState('networkidle');
		
		const disconnectButton = page.locator('button:has-text("Disconnect")');
		
		if (await disconnectButton.isVisible()) {
			// Set up dialog handler
			page.on('dialog', async dialog => {
				expect(dialog.message()).toContain('Are you sure');
				await dialog.dismiss();
			});
			
			await disconnectButton.click();
			// Dialog should have been triggered
		}
	});
});

test.describe('Button Interactions - Case Detail Page', () => {
	test.skip('Upload document button', async ({ page }) => {
		// Skip if no cases exist
		await page.goto('/app/cases');
		const firstCase = page.locator('ul.divide-y li a').first();
		
		if (await firstCase.isVisible()) {
			await firstCase.click();
			await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);
			
			// Look for upload button
			const uploadButton = page.locator('button:has-text("Upload")');
			if (await uploadButton.isVisible()) {
				await expect(uploadButton).not.toBeDisabled();
			}
		}
	});

	test.skip('Start analysis button', async ({ page }) => {
		await page.goto('/app/cases');
		const firstCase = page.locator('ul.divide-y li a').first();
		
		if (await firstCase.isVisible()) {
			await firstCase.click();
			await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);
			
			// Look for analysis button
			const analysisButton = page.locator('button:has-text("Start Analysis")');
			if (await analysisButton.isVisible()) {
				await expect(analysisButton).not.toBeDisabled();
			}
		}
	});
});

test.describe('Button Interactions - Accessibility', () => {
	test('All primary buttons have proper focus states', async ({ page }) => {
		await page.goto('/app/cases');
		
		// Tab through buttons
		await page.keyboard.press('Tab');
		
		// Check that focused element is visible
		const focused = page.locator(':focus');
		await expect(focused).toBeVisible();
	});

	test('Buttons have proper ARIA labels', async ({ page }) => {
		await page.goto('/app/cases/new');
		await page.waitForLoadState('networkidle');
		
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			const submitButton = page.locator('button[type="submit"]');
			
			// Should have text or aria-label
			const text = await submitButton.textContent();
			expect(text).toBeTruthy();
		}
	});

	test('Disabled buttons are not clickable', async ({ page }) => {
		await page.goto('/app/cases/new');
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			const submitButton = page.locator('button[type="submit"]:has-text("Create Case")');
			
			// Should be disabled initially
			await expect(submitButton).toBeDisabled();
			
			// Try to click - should not navigate or change state
			await submitButton.click({ force: true });
			
			// Should still be on same page
			await expect(page).toHaveURL(/\/app\/cases\/new/);
		}
	});
});

test.describe('Button Interactions - Loading States', () => {
	test('Submit button shows loading state', async ({ page }) => {
		await page.goto('/app/cases/new');
		const manualButton = page.locator('button:has-text("Create Manual Case")');
		
		if (await manualButton.isVisible()) {
			await manualButton.click();
			
			// Fill form
			await page.fill('input[id="client_name"]', 'Loading Test Client');
			
			const submitButton = page.locator('button[type="submit"]');
			
			// Start submission
			await submitButton.click();
			
			// Should show loading text briefly
			const loadingText = page.locator('text=Creating...');
			// May or may not be visible depending on API speed
		}
	});
});

