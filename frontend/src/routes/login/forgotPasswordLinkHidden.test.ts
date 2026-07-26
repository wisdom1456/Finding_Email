/**
 * Login page — the "Forgot password?" link must be ABSENT when
 * PUBLIC_ENABLE_PASSWORD_RESET is unset/false (the safe default). This is the
 * "additive and inert until the flag is enabled" guarantee for the rollout.
 *
 * No $env/dynamic/public mock here -> the shared test alias supplies an env
 * object with no PUBLIC_ENABLE_PASSWORD_RESET, i.e. the flag is off.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';

vi.mock('$lib/assets/logo-br.png', () => ({ default: 'logo.png' }));
vi.mock('$lib/supabase', () => ({
	supabase: { auth: { signInWithPassword: vi.fn() } }
}));

import LoginPage from './+page.svelte';

describe('Login page — forgot-password link (flag off by default)', () => {
	it('does not render a forgot-password link', () => {
		render(LoginPage);
		expect(screen.queryByRole('link', { name: /forgot/i })).not.toBeInTheDocument();
	});
});
