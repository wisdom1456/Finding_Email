/**
 * Tests for the Update Password page (set a new password from a recovery session).
 *
 * Behaviour under test:
 *   - Requires a session (the recovery link establishes one via /auth/callback).
 *     No session -> redirect to /login.
 *   - With a session, renders new/confirm password fields.
 *   - Valid input -> supabase.auth.updateUser({ password }) -> redirect to /app.
 *   - Mismatch / too-short -> inline error, updateUser NOT called.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { goto } from '$app/navigation';

vi.mock('$lib/assets/logo-br.png', () => ({ default: 'logo.png' }));

const mockUpdateUser = vi.fn();
const mockGetSecureSession = vi.fn();
vi.mock('$lib/supabase', () => ({
	supabase: { auth: { updateUser: (...a: any[]) => mockUpdateUser(...a) } },
	getSecureSession: (...a: any[]) => mockGetSecureSession(...a)
}));

import UpdatePasswordPage from './+page.svelte';

describe('Update Password page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockGetSecureSession.mockResolvedValue({
			session: { access_token: 't' },
			user: { id: 'u1' }
		});
		mockUpdateUser.mockResolvedValue({ data: {}, error: null });
	});

	it('redirects to /login when there is no recovery session', async () => {
		mockGetSecureSession.mockResolvedValue({ session: null, user: null });
		render(UpdatePasswordPage);
		await waitFor(() => {
			expect(goto).toHaveBeenCalledWith('/login');
		});
	});

	it('renders the new-password form when a session is present', async () => {
		render(UpdatePasswordPage);
		expect(await screen.findByLabelText(/new password/i)).toBeInTheDocument();
		expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
	});

	it('updates the password and redirects to /app on success', async () => {
		const user = userEvent.setup();
		render(UpdatePasswordPage);
		const pw = await screen.findByLabelText(/new password/i);
		await user.type(pw, 'NewStrongPass1');
		await user.type(screen.getByLabelText(/confirm password/i), 'NewStrongPass1');
		await user.click(screen.getByRole('button', { name: /update password/i }));
		await waitFor(() => {
			expect(mockUpdateUser).toHaveBeenCalledWith({ password: 'NewStrongPass1' });
			expect(goto).toHaveBeenCalledWith('/app');
		});
	});

	it('shows an error and does not submit when passwords do not match', async () => {
		const user = userEvent.setup();
		render(UpdatePasswordPage);
		const pw = await screen.findByLabelText(/new password/i);
		await user.type(pw, 'NewStrongPass1');
		await user.type(screen.getByLabelText(/confirm password/i), 'Different1');
		await user.click(screen.getByRole('button', { name: /update password/i }));
		await waitFor(() => {
			expect(screen.getByText(/do not match/i)).toBeInTheDocument();
		});
		expect(mockUpdateUser).not.toHaveBeenCalled();
	});

	it('rejects a too-short password without calling updateUser', async () => {
		const user = userEvent.setup();
		render(UpdatePasswordPage);
		const pw = await screen.findByLabelText(/new password/i);
		await user.type(pw, 'short');
		await user.type(screen.getByLabelText(/confirm password/i), 'short');
		await user.click(screen.getByRole('button', { name: /update password/i }));
		await waitFor(() => {
			expect(screen.getByText(/at least 8/i)).toBeInTheDocument();
		});
		expect(mockUpdateUser).not.toHaveBeenCalled();
	});
});
