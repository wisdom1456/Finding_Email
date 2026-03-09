/**
 * Auth callback handler tests
 *
 * Tests the OAuth callback at /auth/callback:
 * - Valid code exchange
 * - Missing code param
 * - Invalid/expired code
 * - Open redirect prevention via sanitizeRedirectTarget
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { sanitizeRedirectTarget } from './+server';

// ── sanitizeRedirectTarget (exported utility) ──

describe('sanitizeRedirectTarget', () => {
	it('allows valid internal paths', () => {
		expect(sanitizeRedirectTarget('/app')).toBe('/app');
		expect(sanitizeRedirectTarget('/app/cases/123')).toBe('/app/cases/123');
		expect(sanitizeRedirectTarget('/app/cases?tab=analysis')).toBe('/app/cases?tab=analysis');
		expect(sanitizeRedirectTarget('/')).toBe('/');
	});

	it('rejects absolute URLs (open redirect)', () => {
		expect(sanitizeRedirectTarget('https://evil.com')).toBe('/app');
		expect(sanitizeRedirectTarget('http://evil.com/path')).toBe('/app');
	});

	it('rejects protocol-relative URLs', () => {
		expect(sanitizeRedirectTarget('//evil.com')).toBe('/app');
		expect(sanitizeRedirectTarget('//evil.com/path')).toBe('/app');
	});

	it('rejects backslash tricks', () => {
		expect(sanitizeRedirectTarget('/\\evil.com')).toBe('/app');
		expect(sanitizeRedirectTarget('\\evil.com')).toBe('/app');
	});

	it('rejects paths that dont start with /', () => {
		expect(sanitizeRedirectTarget('evil.com')).toBe('/app');
		expect(sanitizeRedirectTarget('javascript:alert(1)')).toBe('/app');
		expect(sanitizeRedirectTarget('')).toBe('/app');
	});

	it('defaults to /app for empty input', () => {
		expect(sanitizeRedirectTarget('')).toBe('/app');
	});

	it('allows paths with query params and fragments', () => {
		expect(sanitizeRedirectTarget('/app?foo=bar')).toBe('/app?foo=bar');
		expect(sanitizeRedirectTarget('/app#section')).toBe('/app#section');
	});
});

// ── GET handler ──

describe('GET /auth/callback', () => {
	const mockExchangeCodeForSession = vi.fn();
	let mockSupabase: any;

	beforeEach(() => {
		vi.clearAllMocks();
		mockExchangeCodeForSession.mockReset();
		mockSupabase = {
			auth: {
				exchangeCodeForSession: mockExchangeCodeForSession,
			},
		};
	});

	async function callHandler(searchParams: Record<string, string> = {}) {
		const { GET } = await import('./+server');
		const url = new URL('http://localhost/auth/callback');
		for (const [k, v] of Object.entries(searchParams)) {
			url.searchParams.set(k, v);
		}
		return GET({
			url,
			locals: { supabase: mockSupabase },
		} as any);
	}

	it('exchanges valid code and redirects to /app', async () => {
		mockExchangeCodeForSession.mockResolvedValue({ error: null });

		await expect(callHandler({ code: 'valid-code' })).rejects.toMatchObject({
			status: 303,
			location: '/app',
		});

		expect(mockExchangeCodeForSession).toHaveBeenCalledWith('valid-code');
	});

	it('uses sanitized next param for redirect after valid exchange', async () => {
		mockExchangeCodeForSession.mockResolvedValue({ error: null });

		await expect(
			callHandler({ code: 'valid-code', next: '/app/cases/123' })
		).rejects.toMatchObject({
			status: 303,
			location: '/app/cases/123',
		});
	});

	it('sanitizes external next param to /app', async () => {
		mockExchangeCodeForSession.mockResolvedValue({ error: null });

		await expect(
			callHandler({ code: 'valid-code', next: 'https://evil.com' })
		).rejects.toMatchObject({
			status: 303,
			location: '/app',
		});
	});

	it('redirects to /app when no code param provided', async () => {
		await expect(callHandler({})).rejects.toMatchObject({
			status: 303,
			location: '/app',
		});
		// Should not attempt exchange
		expect(mockExchangeCodeForSession).not.toHaveBeenCalled();
	});

	it('redirects to /login with error when code exchange fails', async () => {
		mockExchangeCodeForSession.mockResolvedValue({
			error: { message: 'Invalid code' },
		});

		await expect(callHandler({ code: 'expired-code' })).rejects.toMatchObject({
			status: 303,
			location: '/login?error=Invalid%20code',
		});
	});

	it('redirects to /login on exchange exception', async () => {
		mockExchangeCodeForSession.mockRejectedValue(new Error('Network error'));

		await expect(callHandler({ code: 'bad-code' })).rejects.toMatchObject({
			status: 303,
			location: '/login?error=authentication_failed',
		});
	});
});
