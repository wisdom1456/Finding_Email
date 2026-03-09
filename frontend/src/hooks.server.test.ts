/**
 * hooks.server.ts — Auth guard and Supabase hook tests
 *
 * Tests the two Handle functions:
 * 1. supabase hook: creates Supabase client, attaches safeGetSession
 * 2. authGuard hook: enforces login, approval status, and redirects
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ──

const { mockGetSession, mockGetUser, mockFrom, mockSelect, mockEq, mockSingle } = vi.hoisted(() => ({
	mockGetSession: vi.fn(),
	mockGetUser: vi.fn(),
	mockFrom: vi.fn(),
	mockSelect: vi.fn(),
	mockEq: vi.fn(),
	mockSingle: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({
	createServerClient: vi.fn(() => ({
		auth: {
			getSession: mockGetSession,
			getUser: mockGetUser,
		},
		from: mockFrom,
	})),
}));

vi.mock('@sveltejs/kit/hooks', () => ({
	sequence: (...fns: any[]) => fns,
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_SUPABASE_URL: 'https://mock.supabase.co',
	PUBLIC_SUPABASE_ANON_KEY: 'mock-anon-key',
}));

// ── Helpers ──

function makeEvent(pathname: string) {
	return {
		url: new URL(`http://localhost${pathname}`),
		cookies: {
			getAll: vi.fn().mockReturnValue([]),
			set: vi.fn(),
		},
		locals: {} as Record<string, any>,
	};
}

function setupProfileQuery(profile: Record<string, any> | null) {
	mockSingle.mockResolvedValue({ data: profile, error: null });
	mockEq.mockReturnValue({ single: mockSingle });
	mockSelect.mockReturnValue({ eq: mockEq });
	mockFrom.mockReturnValue({ select: mockSelect });
}

// ── Tests ──

describe('safeGetSession', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	async function callSafeGetSession(sessionMock: any, getUserMock: any) {
		const event = makeEvent('/app');
		const { handle } = await import('./hooks.server');
		const [supabaseHook] = handle as unknown as Array<any>;

		mockGetSession.mockResolvedValue(sessionMock);
		if (getUserMock) mockGetUser.mockResolvedValue(getUserMock);

		await supabaseHook({
			event,
			resolve: vi.fn().mockResolvedValue(new Response()),
		});

		return event.locals.safeGetSession();
	}

	it('returns null session and user when no session exists', async () => {
		const result = await callSafeGetSession(
			{ data: { session: null } },
			null,
		);
		expect(result).toEqual({ session: null, user: null });
	});

	it('returns null when session exists but getUser returns error', async () => {
		const result = await callSafeGetSession(
			{ data: { session: { access_token: 'tok' } } },
			{ data: { user: null }, error: { message: 'Invalid token' } },
		);
		expect(result).toEqual({ session: null, user: null });
	});

	it('returns null when session exists but getUser returns null user without error', async () => {
		// This is the key contract fix: null user WITHOUT an error
		// must still invalidate the session
		const result = await callSafeGetSession(
			{ data: { session: { access_token: 'tok' } } },
			{ data: { user: null }, error: null },
		);
		expect(result).toEqual({ session: null, user: null });
	});

	it('returns session and user when both valid', async () => {
		const session = { access_token: 'valid-token' };
		const user = { id: 'user-1', email: 'test@test.com' };
		const result = await callSafeGetSession(
			{ data: { session } },
			{ data: { user }, error: null },
		);
		expect(result.session).toEqual(session);
		expect(result.user).toEqual(user);
	});

	it('never returns non-null session with null user', async () => {
		// Exhaustive contract check: try every way user can be null
		const staleSession = { access_token: 'stale-token' };

		// getUser error
		const r1 = await callSafeGetSession(
			{ data: { session: staleSession } },
			{ data: { user: null }, error: { message: 'expired' } },
		);
		expect(r1.session).toBeNull();
		expect(r1.user).toBeNull();

		// getUser null without error
		vi.clearAllMocks();
		const r2 = await callSafeGetSession(
			{ data: { session: staleSession } },
			{ data: { user: null }, error: null },
		);
		expect(r2.session).toBeNull();
		expect(r2.user).toBeNull();
	});

	it('invalidates stale session when getUser fails verification', async () => {
		// Simulates a session cookie that exists but the user was deleted/banned
		const result = await callSafeGetSession(
			{ data: { session: { access_token: 'stale-token-from-deleted-user' } } },
			{ data: { user: null }, error: { message: 'User not found' } },
		);
		expect(result).toEqual({ session: null, user: null });
	});
});

describe('authGuard', () => {
	let supabaseHook: any;
	let authGuardHook: any;
	const mockResolve = vi.fn().mockResolvedValue(new Response());

	beforeEach(async () => {
		vi.clearAllMocks();
		mockResolve.mockResolvedValue(new Response());

		const { handle } = await import('./hooks.server');
		const hooks = handle as unknown as Array<any>;
		supabaseHook = hooks[0];
		authGuardHook = hooks[1];
	});

	async function runAuthGuard(pathname: string, opts: {
		session?: any;
		user?: any;
		profile?: Record<string, any> | null;
	} = {}) {
		const event = makeEvent(pathname);

		// Set up safeGetSession
		const sessionVal = opts.session ?? null;
		const userVal = opts.user ?? null;
		mockGetSession.mockResolvedValue({ data: { session: sessionVal } });
		if (sessionVal) {
			mockGetUser.mockResolvedValue({ data: { user: userVal }, error: userVal ? null : { message: 'no user' } });
		}

		// Run supabase hook first to attach safeGetSession
		await supabaseHook({ event, resolve: mockResolve });

		// Set up profile query for authGuard
		if (opts.profile !== undefined) {
			setupProfileQuery(opts.profile);
		} else {
			setupProfileQuery(null);
		}

		return { event };
	}

	// ── Not logged in ──

	it('redirects to /login when unauthenticated user hits /app', async () => {
		const { event } = await runAuthGuard('/app/cases');
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/login' });
	});

	it('redirects to /login when unauthenticated user hits /app root', async () => {
		const { event } = await runAuthGuard('/app');
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/login' });
	});

	it('allows unauthenticated user to access /login', async () => {
		const { event } = await runAuthGuard('/login');
		await authGuardHook({ event, resolve: mockResolve });
		expect(mockResolve).toHaveBeenCalled();
	});

	it('allows unauthenticated user to access /register', async () => {
		const { event } = await runAuthGuard('/register');
		await authGuardHook({ event, resolve: mockResolve });
		expect(mockResolve).toHaveBeenCalled();
	});

	it('allows unauthenticated user to access / (home)', async () => {
		const { event } = await runAuthGuard('/');
		await authGuardHook({ event, resolve: mockResolve });
		expect(mockResolve).toHaveBeenCalled();
	});

	// ── Approved user ──

	it('allows approved user to access /app routes', async () => {
		const { event } = await runAuthGuard('/app/cases', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: true, role: 'user' },
		});
		await authGuardHook({ event, resolve: mockResolve });
		expect(mockResolve).toHaveBeenCalled();
	});

	it('redirects approved user from /login to /app', async () => {
		const { event } = await runAuthGuard('/login', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: true, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/app' });
	});

	it('redirects approved user from /register to /app', async () => {
		const { event } = await runAuthGuard('/register', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: true, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/app' });
	});

	it('redirects approved user from /account-pending to /app', async () => {
		const { event } = await runAuthGuard('/account-pending', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: true, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/app' });
	});

	// ── Unapproved user ──

	it('redirects unapproved user from /app to /account-pending', async () => {
		const { event } = await runAuthGuard('/app/cases', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: false, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	it('allows unapproved user to stay on /account-pending', async () => {
		const { event } = await runAuthGuard('/account-pending', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: false, role: 'user' },
		});
		await authGuardHook({ event, resolve: mockResolve });
		expect(mockResolve).toHaveBeenCalled();
	});

	it('redirects unapproved user from /login to /account-pending', async () => {
		const { event } = await runAuthGuard('/login', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: false, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	it('redirects unapproved user from /register to /account-pending', async () => {
		const { event } = await runAuthGuard('/register', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: false, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	// ── Null/undefined approval ──

	it('treats null approved as unapproved', async () => {
		const { event } = await runAuthGuard('/app', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: null, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	it('treats undefined approved as unapproved', async () => {
		const { event } = await runAuthGuard('/app', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	it('treats false approved as unapproved', async () => {
		const { event } = await runAuthGuard('/app', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: false, role: 'user' },
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	// ── Missing profile ──

	it('treats null profile as unapproved', async () => {
		const { event } = await runAuthGuard('/app', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: null,
		});
		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	// ── Invalid user.id — treated as unauthenticated ──

	it('redirects to /login when user.id is null', async () => {
		const event = makeEvent('/app/cases');
		mockGetSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
		mockGetUser.mockResolvedValue({ data: { user: { id: null } }, error: null });

		const { handle } = await import('./hooks.server');
		const hooks = handle as unknown as Array<any>;
		await hooks[0]({ event, resolve: mockResolve });

		await expect(
			hooks[1]({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/login' });
	});

	it('redirects to /login when user.id is undefined', async () => {
		const event = makeEvent('/app/cases');
		mockGetSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
		mockGetUser.mockResolvedValue({ data: { user: { email: 'test@test.com' } }, error: null });

		const { handle } = await import('./hooks.server');
		const hooks = handle as unknown as Array<any>;
		await hooks[0]({ event, resolve: mockResolve });

		await expect(
			hooks[1]({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/login' });
	});

	it('redirects to /login when user.id is empty string', async () => {
		const event = makeEvent('/app/cases');
		mockGetSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
		mockGetUser.mockResolvedValue({ data: { user: { id: '' } }, error: null });

		const { handle } = await import('./hooks.server');
		const hooks = handle as unknown as Array<any>;
		await hooks[0]({ event, resolve: mockResolve });

		await expect(
			hooks[1]({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/login' });
	});

	it('redirects to /login when user object is missing entirely', async () => {
		const event = makeEvent('/app/cases');
		mockGetSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
		mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

		const { handle } = await import('./hooks.server');
		const hooks = handle as unknown as Array<any>;
		await hooks[0]({ event, resolve: mockResolve });

		await expect(
			hooks[1]({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/login' });
	});

	it('allows null user.id on non-protected routes', async () => {
		const event = makeEvent('/');
		mockGetSession.mockResolvedValue({ data: { session: { access_token: 'tok' } } });
		mockGetUser.mockResolvedValue({ data: { user: { id: null } }, error: null });

		const { handle } = await import('./hooks.server');
		const hooks = handle as unknown as Array<any>;
		await hooks[0]({ event, resolve: mockResolve });

		// Non-/app routes should still resolve (no profile check, no redirect)
		await hooks[1]({ event, resolve: mockResolve });
		expect(mockResolve).toHaveBeenCalled();
	});

	// ── Profile fetch throws ──

	it('fails closed when profile fetch throws (network error)', async () => {
		const { event } = await runAuthGuard('/app/cases', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: true, role: 'user' },
		});

		// Override: make the profile query chain throw on .single()
		mockSingle.mockRejectedValue(new Error('Network error'));

		await expect(
			authGuardHook({ event, resolve: mockResolve })
		).rejects.toMatchObject({ status: 303, location: '/account-pending' });
	});

	it('sets profile to null when profile fetch throws', async () => {
		const { event } = await runAuthGuard('/', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: { approved: true, role: 'user' },
		});

		// Override: throw on profile fetch
		mockSingle.mockRejectedValue(new Error('Connection refused'));

		await authGuardHook({ event, resolve: mockResolve });
		expect(event.locals.profile).toBeNull();
	});

	// ── Locals are set correctly ──

	it('sets session and user on event.locals', async () => {
		const session = { access_token: 'tok' };
		const user = { id: 'user-1' };
		const { event } = await runAuthGuard('/', {
			session,
			user,
			profile: { approved: true, role: 'user' },
		});
		await authGuardHook({ event, resolve: mockResolve });
		expect(event.locals.session).toEqual(session);
		expect(event.locals.user).toEqual(user);
	});

	it('stores full profile on event.locals.profile', async () => {
		const fullProfile = { id: 'user-1', approved: true, role: 'admin', full_name: 'Test' };
		const { event } = await runAuthGuard('/', {
			session: { access_token: 'tok' },
			user: { id: 'user-1' },
			profile: fullProfile,
		});
		await authGuardHook({ event, resolve: mockResolve });
		expect(event.locals.profile).toEqual(fullProfile);
	});
});
