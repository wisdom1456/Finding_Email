/**
 * Tests for ClioConnect component button interactions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
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
	}
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
		expect(connectButton).toHaveClass('bg-accent');
	});

	it('connect button redirects to OAuth flow', async () => {
		// Mock API response
		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			json: async () => ({ connected: false })
		});

		// Mock window.location
		const originalLocation = window.location;
		delete (window as any).location;
		window.location = { ...originalLocation, href: '' } as any;

		render(ClioConnect);
		await screen.findByText('Connect to Clio');

		const connectButton = screen.getByRole('button', { name: /connect to clio/i });
		await fireEvent.click(connectButton);

		expect(window.location.href).toContain('/api/clio/authorize');
		expect(window.location.href).toContain('token=mock-token');

		// Restore
		window.location = originalLocation;
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
		await screen.findByText('Disconnect');

		const disconnectButton = screen.getByRole('button', { name: /disconnect/i });
		expect(disconnectButton).toBeInTheDocument();
		expect(disconnectButton).toHaveClass('text-red-700');
	});

	it('disconnect button shows confirmation dialog', async () => {
		// Mock confirm
		window.confirm = vi.fn().mockReturnValue(false);

		// Mock connected state
		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			json: async () => ({ connected: true, clio_user_id: 'user-123' })
		});

		render(ClioConnect);
		await screen.findByText('Disconnect');

		const disconnectButton = screen.getByRole('button', { name: /disconnect/i });
		await fireEvent.click(disconnectButton);

		expect(window.confirm).toHaveBeenCalledWith(
			expect.stringContaining('Are you sure')
		);
	});

	it('disconnect button calls API when confirmed', async () => {
		window.confirm = vi.fn().mockReturnValue(true);

		(global.fetch as any)
			.mockResolvedValueOnce({
				ok: true,
				json: async () => ({ connected: true })
			})
			.mockResolvedValueOnce({
				ok: true
			});

		const { clioStore } = await import('$lib/stores/clioStore');

		render(ClioConnect);
		await screen.findByText('Disconnect');

		const disconnectButton = screen.getByRole('button', { name: /disconnect/i });
		await fireEvent.click(disconnectButton);

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



