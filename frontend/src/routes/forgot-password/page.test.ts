/**
 * Tests for the Forgot Password page (request a reset link).
 *
 * Behaviour under test:
 *   - Renders an email field + submit.
 *   - Submitting calls supabase.auth.resetPasswordForEmail with the entered
 *     email and a redirectTo that lands on /auth/callback -> update-password.
 *   - Shows a GENERIC confirmation afterwards, and the SAME message even when
 *     Supabase returns an error, so the page never reveals whether an account
 *     exists (no enumeration).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';

vi.mock('$lib/assets/logo-br.png', () => ({ default: 'logo.png' }));

const mockReset = vi.fn();
vi.mock('$lib/supabase', () => ({
	supabase: {
		auth: {
			resetPasswordForEmail: (...args: any[]) => mockReset(...args)
		}
	}
}));

import ForgotPasswordPage from './+page.svelte';

describe('Forgot Password page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockReset.mockResolvedValue({ data: {}, error: null });
	});

	it('renders an email field and a submit button', () => {
		render(ForgotPasswordPage);
		expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
	});

	it('calls resetPasswordForEmail with the email and a callback redirect to update-password', async () => {
		const user = userEvent.setup();
		render(ForgotPasswordPage);
		await user.type(screen.getByLabelText(/email/i), 'ceryn@example.com');
		await user.click(screen.getByRole('button', { name: /send reset link/i }));
		await waitFor(() => {
			expect(mockReset).toHaveBeenCalledWith(
				'ceryn@example.com',
				expect.objectContaining({
					redirectTo: expect.stringContaining('/auth/callback?next=/account/update-password')
				})
			);
		});
	});

	it('shows a generic confirmation after submitting (no enumeration)', async () => {
		const user = userEvent.setup();
		render(ForgotPasswordPage);
		await user.type(screen.getByLabelText(/email/i), 'someone@example.com');
		await user.click(screen.getByRole('button', { name: /send reset link/i }));
		await waitFor(() => {
			expect(screen.getByText(/if an account exists/i)).toBeInTheDocument();
		});
	});

	it('shows the SAME generic confirmation when Supabase returns an error (no enumeration)', async () => {
		mockReset.mockResolvedValue({ data: {}, error: { message: 'User not found' } });
		const user = userEvent.setup();
		render(ForgotPasswordPage);
		await user.type(screen.getByLabelText(/email/i), 'nobody@example.com');
		await user.click(screen.getByRole('button', { name: /send reset link/i }));
		await waitFor(() => {
			expect(screen.getByText(/if an account exists/i)).toBeInTheDocument();
		});
		// Must not leak the underlying error to the user.
		expect(screen.queryByText(/user not found/i)).not.toBeInTheDocument();
	});
});
