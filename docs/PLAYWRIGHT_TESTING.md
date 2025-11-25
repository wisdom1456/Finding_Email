# Playwright Testing Guide

## Overview

We use Playwright for comprehensive end-to-end testing, focusing on real user interactions and button workflows. This approach provides better coverage and reliability than unit tests for Svelte 5 components.

## Why Playwright?

1. **Real Browser Testing** - Tests run in actual browsers (Chromium, Firefox, WebKit)
2. **User-Focused** - Tests interactions as users experience them
3. **Framework Agnostic** - Works with any framework including Svelte 5
4. **Visual Feedback** - Can capture screenshots and videos of failures
5. **Better for GUI Testing** - Validates actual button clicks, navigation, and state changes

## Test Structure

### Location
All E2E tests are in `frontend/tests/e2e/`

### Test Files

1. **`case-creation.spec.ts`** - Case creation workflows
   - Manual case creation form
   - Form validation
   - Clio matter import (when connected)

2. **`case-list.spec.ts`** - Cases list page
   - Display and navigation
   - Filtering (Clio vs manual cases)
   - Empty states

3. **`clio-integration.spec.ts`** - Clio OAuth and connection
   - Connect/disconnect buttons
   - OAuth flow initiation
   - Connection status display

4. **`button-interactions.spec.ts`** - Comprehensive button testing
   - All clickable elements
   - Button states (enabled/disabled/loading)
   - Form submissions
   - Navigation
   - Accessibility (focus, ARIA)

### Auth Setup
`auth.setup.ts` - Creates authenticated session for tests

## Running Tests

### Prerequisites

```bash
# Install Playwright browsers (first time only)
cd frontend
npx playwright install
```

### Commands

```bash
cd frontend/

# Run all tests (headless)
npm run test:e2e

# Run with UI mode (recommended for development)
npm run test:e2e:ui

# Run in debug mode
npm run test:e2e:debug

# Run specific test file
npx playwright test case-creation.spec.ts

# Run specific test
npx playwright test -g "should create a manual case"

# Run in headed mode (see browser)
npx playwright test --headed

# Run on specific browser
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

## Test Pattern Examples

### Basic Button Click Test

```typescript
test('button is clickable', async ({ page }) => {
  await page.goto('/app/cases');
  
  const button = page.locator('button:has-text("New Case")');
  
  // Verify visible
  await expect(button).toBeVisible();
  
  // Click
  await button.click();
  
  // Verify result
  await expect(page).toHaveURL(/\/app\/cases\/new/);
});
```

### Form Interaction Test

```typescript
test('form validation works', async ({ page }) => {
  await page.goto('/app/cases/new');
  
  // Fill form
  await page.fill('input[id="client_name"]', 'Test Client');
  await page.fill('textarea[id="description"]', 'Test description');
  
  // Submit
  await page.click('button[type="submit"]');
  
  // Verify navigation
  await page.waitForURL(/\/app\/cases\/[a-zA-Z0-9-]+$/);
});
```

### Testing Button States

```typescript
test('button disables appropriately', async ({ page }) => {
  await page.goto('/form');
  
  const submitButton = page.locator('button[type="submit"]');
  
  // Initially disabled
  await expect(submitButton).toBeDisabled();
  
  // Fill required field
  await page.fill('input[required]', 'value');
  
  // Now enabled
  await expect(submitButton).not.toBeDisabled();
});
```

### Testing Loading States

```typescript
test('shows loading spinner', async ({ page }) => {
  await page.goto('/app');
  
  await page.click('button:has-text("Load Data")');
  
  // Loading indicator appears
  await expect(page.locator('.spinner')).toBeVisible();
  
  // Wait for completion
  await expect(page.locator('.spinner')).not.toBeVisible();
});
```

### Testing Conditional UI

```typescript
test('shows correct button based on state', async ({ page }) => {
  await page.goto('/app');
  
  const connectButton = page.locator('button:has-text("Connect")');
  const disconnectButton = page.locator('button:has-text("Disconnect")');
  
  // One or the other should be visible
  const hasConnect = await connectButton.isVisible();
  const hasDisconnect = await disconnectButton.isVisible();
  
  expect(hasConnect || hasDisconnect).toBeTruthy();
});
```

## Selectors Best Practices

### Preferred Selectors (in order)

1. **User-facing attributes**
   ```typescript
   page.getByRole('button', { name: 'Submit' })
   page.getByLabel('Email address')
   page.getByPlaceholder('Enter email')
   page.getByText('Welcome')
   ```

2. **Data test IDs** (add to components)
   ```typescript
   page.locator('[data-testid="submit-button"]')
   ```

3. **CSS selectors** (when necessary)
   ```typescript
   page.locator('button.primary')
   page.locator('button:has-text("Submit")')
   ```

### Avoid

- Overly specific CSS paths
- XPath selectors
- Brittle selectors tied to implementation details

## Handling Dynamic Content

### Wait for Network

```typescript
await page.waitForLoadState('networkidle');
```

### Wait for Specific Element

```typescript
await page.waitForSelector('.data-loaded');
```

### Wait for URL

```typescript
await page.waitForURL(/\/app\/cases\/\d+/);
```

### Custom Waits

```typescript
await page.waitForFunction(() => {
  return document.querySelectorAll('.case-item').length > 0;
});
```

## Testing Checklist

For each user workflow, ensure you test:

- [ ] Button is visible and accessible
- [ ] Button has proper styling
- [ ] Button responds to click
- [ ] Button shows correct state (enabled/disabled)
- [ ] Button shows loading state during async operations
- [ ] Form validation prevents invalid submission
- [ ] Success message or navigation occurs
- [ ] Error messages display when appropriate
- [ ] Accessibility (keyboard navigation, focus states)
- [ ] Mobile responsiveness (if applicable)

## Debugging Tests

### Visual Debugging

```bash
# UI Mode - best for debugging
npx playwright test --ui

# Headed mode
npx playwright test --headed

# Debug specific test
npx playwright test --debug -g "test name"
```

### Screenshots and Traces

Playwright automatically captures:
- Screenshots on failure
- Video recordings (in CI)
- Traces for debugging

View traces:
```bash
npx playwright show-trace trace.zip
```

### Console Logs

```typescript
page.on('console', msg => console.log(msg.text()));
```

## CI/CD Integration

Tests run automatically in GitHub Actions:

```yaml
# .github/workflows/test.yml
- name: Run Playwright tests
  working-directory: ./frontend
  run: npm run test:e2e
```

Results are uploaded as artifacts:
- HTML report
- Screenshots
- Videos (on failure)

## Best Practices

1. **Keep tests independent** - Each test should work in isolation
2. **Use beforeEach for setup** - Navigate and set up state
3. **Test user flows, not implementation** - Focus on what users do
4. **Handle waits properly** - Use appropriate wait strategies
5. **Name tests clearly** - Describe the behavior being tested
6. **Group related tests** - Use `describe` blocks
7. **Mark flaky tests** - Use `.skip` or `.fixme` temporarily
8. **Test error states** - Don't just test happy paths
9. **Keep tests maintainable** - Extract common actions to helpers
10. **Review test failures** - Failed tests indicate real issues

## Common Patterns

### Page Object Model (Optional)

```typescript
// pages/CasesPage.ts
export class CasesPage {
  constructor(private page: Page) {}
  
  async goto() {
    await this.page.goto('/app/cases');
  }
  
  async clickNewCase() {
    await this.page.click('a:has-text("New Case")');
  }
  
  async getFirstCase() {
    return this.page.locator('ul.divide-y li').first();
  }
}

// In test
const casesPage = new CasesPage(page);
await casesPage.goto();
await casesPage.clickNewCase();
```

### Fixtures for Common Setup

```typescript
import { test as base } from '@playwright/test';

const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    // Log in
    await page.goto('/login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('/app');
    
    await use(page);
  },
});

// Use in tests
test('shows user dashboard', async ({ authenticatedPage }) => {
  // Already logged in
  await expect(authenticatedPage.locator('text=Dashboard')).toBeVisible();
});
```

## Troubleshooting

### Test Times Out

- Check `waitForLoadState()` usage
- Increase timeout: `test.setTimeout(60000)`
- Verify element selector is correct

### Element Not Found

- Use `await page.pause()` to inspect
- Check if element is in different frame
- Verify page has loaded completely

### Flaky Tests

- Add proper waits (avoid `waitForTimeout`)
- Check for race conditions
- Use `test.retry(2)` as last resort

### Authentication Issues

- Check auth.setup.ts configuration
- Verify environment variables
- Check cookie/session persistence

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Selectors Guide](https://playwright.dev/docs/selectors)
- [Debugging Guide](https://playwright.dev/docs/debug)


