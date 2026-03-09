import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock Supabase SSR — use vi.hoisted to avoid initialization order issues
const { mockGetSession, mockGetUser, mockRefreshSession } = vi.hoisted(() => ({
	mockGetSession: vi.fn(),
	mockGetUser: vi.fn(),
	mockRefreshSession: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({
	createBrowserClient: () => ({
		auth: {
			getSession: mockGetSession,
			getUser: mockGetUser,
			refreshSession: mockRefreshSession,
		},
	}),
}));

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_SUPABASE_URL: 'https://test.supabase.co',
		PUBLIC_SUPABASE_ANON_KEY: 'test-anon-key',
	},
}));

import { getSecureSession, getSecureAccessToken } from './supabase';

const fakeSession = { access_token: 'valid-token', refresh_token: 'refresh' };
const fakeUser = { id: 'user-1', email: 'test@test.com' };

describe('getSecureSession', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('returns null when no session in storage', async () => {
		mockGetSession.mockResolvedValue({ data: { session: null } });
		const result = await getSecureSession();
		expect(result).toEqual({ session: null, user: null });
		expect(mockGetUser).not.toHaveBeenCalled();
	});

	it('returns session and user when validation succeeds', async () => {
		mockGetSession.mockResolvedValue({ data: { session: fakeSession } });
		mockGetUser.mockResolvedValue({ data: { user: fakeUser }, error: null });

		const result = await getSecureSession();
		expect(result.session).toBeTruthy();
		expect(result.user).toEqual(fakeUser);
	});

	it('attempts refresh when getUser fails', async () => {
		const refreshedSession = { access_token: 'new-token', refresh_token: 'new-refresh' };
		const refreshedUser = { id: 'user-1', email: 'test@test.com' };

		mockGetSession.mockResolvedValue({ data: { session: fakeSession } });
		mockGetUser.mockResolvedValue({ data: { user: null }, error: { message: 'expired' } });
		mockRefreshSession.mockResolvedValue({
			data: { session: refreshedSession, user: refreshedUser },
			error: null,
		});

		const result = await getSecureSession();
		expect(mockRefreshSession).toHaveBeenCalled();
		expect(result.session).toEqual(refreshedSession);
		expect(result.user).toEqual(refreshedUser);
	});

	it('returns null when both getUser and refresh fail', async () => {
		mockGetSession.mockResolvedValue({ data: { session: fakeSession } });
		mockGetUser.mockResolvedValue({ data: { user: null }, error: { message: 'invalid' } });
		mockRefreshSession.mockResolvedValue({
			data: { session: null, user: null },
			error: { message: 'refresh failed' },
		});

		const result = await getSecureSession();
		expect(result).toEqual({ session: null, user: null });
	});

	it('re-fetches session after successful validation (may have refreshed)', async () => {
		const freshSession = { access_token: 'fresh-token', refresh_token: 'refresh' };
		mockGetSession
			.mockResolvedValueOnce({ data: { session: fakeSession } })
			.mockResolvedValueOnce({ data: { session: freshSession } });
		mockGetUser.mockResolvedValue({ data: { user: fakeUser }, error: null });

		const result = await getSecureSession();
		expect(mockGetSession).toHaveBeenCalledTimes(2);
		expect(result.session?.access_token).toBe('fresh-token');
	});
});

describe('getSecureAccessToken', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('returns access token when session is valid', async () => {
		mockGetSession.mockResolvedValue({ data: { session: fakeSession } });
		mockGetUser.mockResolvedValue({ data: { user: fakeUser }, error: null });

		const token = await getSecureAccessToken();
		expect(token).toBe('valid-token');
	});

	it('returns null when no session', async () => {
		mockGetSession.mockResolvedValue({ data: { session: null } });
		const token = await getSecureAccessToken();
		expect(token).toBeNull();
	});
});
