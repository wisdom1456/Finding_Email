/**
 * Tests for ClioConnect component button interactions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import ClioConnect from './ClioConnect.svelte';

// Mock stores
vi.mock('$lib/stores/clioStore', () => ({
	clioStore: {
		connected: false,
		clioUserId: null,
		expiresAt: null,
		setConnected: vi.fn(),
		disconnect: vi.fn(),
		subscribe: vi.fn((fn) => {
			fn({ connected: false, clioUserId: null, expiresAt: null });
			return () => {};
		})
	}
}));

// Mock Supabase
vi.mock('$lib/supabase', () => ({
	supabase: {
		auth: {
			getSession: vi.fn().mockResolvedValue({
				data: { session: { access_token: 'mock-token' } }
			})
		}
	},
	getSecureSession: vi.fn().mockResolvedValue({
		session: { access_token: 'mock-token' },
		user: { id: 'user-123', email: 'test@example.com' }
	})
}));

// Mock environment
vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'http://localhost:8000'
}));

describe('ClioConnect', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		global.fetch = vi.fn();
	});

	it('renders component and shows connect button when not connected', async () => {
		// Mock API response for status check
		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			json: async () => ({ connected: false })
		});

		render(ClioConnect);

		// Wait for loading to complete
		await screen.findByText('Connect to Clio');

		const connectButton = screen.getByRole('button', { name: /connect to clio/i });
		expect(connectButton).toBeInTheDocument();
		expect(connectButton).toHaveClass('btn-primary');
	});

	it('connect button fetches authorize URL with header auth and navigates', async () => {
		// Mock API responses: status check, then authorize-url
		(global.fetch as any)
			.mockResolvedValueOnce({
				ok: true,
				json: async () => ({ connected: false })
			})
			.mockResolvedValueOnce({
				ok: true,
				json: async () => ({ url: 'https://app.clio.com/oauth/authorize?state=signed' })
			});

		// Mock window.location
		const originalLocation = window.location;
		delete (window as any).location;
		(window as any).location = { ...originalLocation, href: '' };

		render(ClioConnect);
		await screen.findByText('Connect to Clio');

		const connectButton = screen.getByRole('button', { name: /connect to clio/i });
		await fireEvent.click(connectButton);

		// Authorization URL is fetched via POST with the bearer header —
		// the session token must never appear in the navigated URL.
		await waitFor(() => {
			expect(window.location.href).toBe('https://app.clio.com/oauth/authorize?state=signed');
		});
		const authorizeCall = (global.fetch as any).mock.calls.find(([url]: [string]) =>
			url.includes('/api/clio/authorize-url')
		);
		expect(authorizeCall).toBeTruthy();
		expect(authorizeCall[1].method).toBe('POST');
		expect(authorizeCall[1].headers.Authorization).toBe('Bearer mock-token');
		expect(window.location.href).not.toContain('token=mock-token');

		// Restore
		(window as any).location = originalLocation;
	});

	it('shows disconnect button when connected', async () => {
		// Mock connected state
		vi.mocked((await import('$lib/stores/clioStore')).clioStore.subscribe).mockImplementation(
			(fn) => {
				fn({ connected: true, clioUserId: 'user-123', expiresAt: null });
				return () => {};
			}
		);

		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			json: async () => ({
				connected: true,
				clio_user_id: 'user-123'
			})
		});

		render(ClioConnect);
		await screen.findByText('Disconnect Clio');

		const disconnectButton = screen.getByRole('button', { name: /disconnect clio/i });
		expect(disconnectButton).toBeInTheDocument();
		expect(disconnectButton).toHaveClass('text-red-600');
	});

	it('disconnect button shows confirmation dialog', async () => {
		// Mock connected state
		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			json: async () => ({ connected: true, clio_user_id: 'user-123' })
		});

		render(ClioConnect);
		await screen.findByText('Disconnect Clio');

		const disconnectButton = screen.getByRole('button', { name: /disconnect clio/i });
		await fireEvent.click(disconnectButton);

		// Check that confirmation dialog appears
		await screen.findByText(/are you sure you want to disconnect/i);
	});

	it('disconnect button calls API when confirmed', async () => {
		(global.fetch as any)
			.mockResolvedValueOnce({
				ok: true,
				json: async () => ({ connected: true, clio_user_id: 'user-123' })
			})
			.mockResolvedValueOnce({
				ok: true
			});

		const { clioStore } = await import('$lib/stores/clioStore');

		render(ClioConnect);
		await screen.findByText('Disconnect Clio');

		const disconnectButton = screen.getByRole('button', { name: /disconnect clio/i });
		await fireEvent.click(disconnectButton);

		// Confirm in the dialog
		const confirmButton = await screen.findByRole('button', { name: /^disconnect$/i });
		await fireEvent.click(confirmButton);

		// Check API was called
		expect(global.fetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/clio/disconnect',
			expect.objectContaining({
				method: 'DELETE',
				headers: expect.objectContaining({
					Authorization: 'Bearer mock-token'
				})
			})
		);
		expect(clioStore.disconnect).toHaveBeenCalled();
	});

	it('displays loading state initially', () => {
		(global.fetch as any).mockImplementation(
			() => new Promise(() => {}) // Never resolves
		);

		render(ClioConnect);

		expect(screen.getByText('Checking connection...')).toBeInTheDocument();
	});

	it('displays error message when API call fails', async () => {
		(global.fetch as any).mockRejectedValueOnce(new Error('Network error'));

		render(ClioConnect);

		await screen.findByText(/network error/i);
		expect(screen.getByText(/network error/i)).toBeInTheDocument();
	});
});



