/**
 * Shared mock factories for component tests.
 */
import { vi } from 'vitest';
import type { Session, User } from '@supabase/supabase-js';

/** Standard mock for $lib/supabase — returns a null session. */
export function mockSupabaseSession() {
	return {
		getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
	};
}

/** Standard mock for $lib/config — returns localhost API URL. */
export function mockApiUrl(url = 'http://localhost:8000') {
	return {
		getApiUrl: () => url,
	};
}

/** Standard mock for $lib/stores/toastStore */
export function mockToastStore() {
	return {
		toastStore: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
	};
}

/** Minimal User that satisfies the Supabase User interface. */
export function makeTestUser(overrides: Partial<User> = {}): User {
	return {
		id: 'user-1',
		app_metadata: {},
		user_metadata: {},
		aud: 'authenticated',
		created_at: '2025-01-01T00:00:00Z',
		...overrides,
	};
}

/** Minimal Session that satisfies the Supabase Session interface. */
export function makeTestSession(overrides: Partial<Session> = {}): Session {
	return {
		access_token: 'test-token',
		refresh_token: 'test-refresh-token',
		expires_in: 3600,
		token_type: 'bearer',
		user: makeTestUser(),
		...overrides,
	};
}

/**
 * Authenticated session result matching getSecureSession()'s return type.
 * Usage: vi.mocked(getSecureSession).mockResolvedValue(makeAuthenticatedSession())
 */
export function makeAuthenticatedSession(
	sessionOverrides: Partial<Session> = {},
	userOverrides: Partial<User> = {},
): { session: Session; user: User } {
	const user = makeTestUser(userOverrides);
	const session = makeTestSession({ user, ...sessionOverrides });
	return { session, user };
}
