/**
 * Playwright authentication setup
 * Creates authenticated session for tests
 */
import { test as setup, expect } from '@playwright/test';
import path from 'path';

const authFile = path.join(__dirname, '../.auth/user.json');

setup('authenticate', async ({ page }) => {
	// Navigate to login page
	await page.goto('/login');

	// Fill in login credentials
	await page.fill('input[type="email"]', process.env.TEST_USER_EMAIL || 'test@example.com');
	await page.fill('input[type="password"]', process.env.TEST_USER_PASSWORD || 'testpassword');

	// Click login button
	await page.click('button[type="submit"]');

	// Wait for navigation to app
	await page.waitForURL('/app/**');

	// Verify we're logged in
	await expect(page).toHaveURL(/\/app/);

	// Save authentication state
	await page.context().storageState({ path: authFile });
});

