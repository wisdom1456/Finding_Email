/**
 * Login page — the "Forgot password?" entry point is gated behind
 * PUBLIC_ENABLE_PASSWORD_RESET. This file covers the flag-ENABLED case.
 * The disabled (default) case lives in forgotPasswordLinkHidden.test.ts.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';

vi.mock('$lib/assets/logo-br.png', () => ({ default: 'logo.png' }));
vi.mock('$lib/supabase', () => ({
	supabase: { auth: { signInWithPassword: vi.fn() } }
}));
vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_ENABLE_PASSWORD_RESET: 'true' }
}));

import LoginPage from './+page.svelte';

describe('Login page — forgot-password link (flag enabled)', () => {
	it('renders a "Forgot password" link to /forgot-password', () => {
		render(LoginPage);
		const link = screen.getByRole('link', { name: /forgot/i });
		expect(link).toHaveAttribute('href', '/forgot-password');
	});
});
