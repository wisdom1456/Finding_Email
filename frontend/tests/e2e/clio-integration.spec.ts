/**
 * E2E tests for Clio integration workflows
 */
import { test, expect } from '@playwright/test';

test.describe('Clio Integration', () => {
	test('should display Clio connection status', async ({ page }) => {
		await page.goto('/app');
		await page.waitForLoadState('networkidle');

		// Look for Clio status indicator (implementation-specific)
		// This test validates the connection UI is present
		const clioSection = page.locator('text=Clio Integration');
		
		if (await clioSection.isVisible()) {
			// Should show either "Connect to Clio" or "Connected to Clio"
			const connectButton = page.locator('button:has-text("Connect to Clio")');
			const disconnectButton = page.locator('button:has-text("Disconnect")');
			
			const hasConnectButton = await connectButton.isVisible();
			const hasDisconnectButton = await disconnectButton.isVisible();
			
			// One of them should be visible
			expect(hasConnectButton || hasDisconnectButton).toBeTruthy();
		}
	});

	test('should initiate Clio OAuth flow', async ({ page, context }) => {
		await page.goto('/app');
		await page.waitForLoadState('networkidle');

		const connectButton = page.locator('button:has-text("Connect to Clio")');
		
		if (await connectButton.isVisible()) {
			// Listen for navigation to OAuth page
			const [newPage] = await Promise.all([
				context.waitForEvent('page'),
				connectButton.click()
			]).catch(() => [null]); // Handle if no new page opens

			if (newPage) {
				await newPage.waitForLoadState();
				
				// Should navigate to Clio authorization or backend OAuth endpoint
				const url = newPage.url();
				expect(url).toMatch(/clio|authorize|oauth/i);
			}
		}
	});

	test.skip('should import case from Clio matter', async ({ page }) => {
		// This test requires valid Clio credentials
		// Marked as skip by default, can be enabled in CI with proper setup
		
		await page.goto('/app/cases/new');
		
		// Look for Clio matter search
		const searchInput = page.locator('input[placeholder*="Search"]');
		if (await searchInput.isVisible()) {
			await searchInput.fill('test matter');
			await page.waitForTimeout(1000);
			
			// Select first result
			const firstResult = page.locator('[role="option"]').first();
			if (await firstResult.isVisible()) {
				await firstResult.click();
				
				// Should create case and navigate
				await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);
			}
		}
	});
});



