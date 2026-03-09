import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

/**
 * Validate that a redirect target is a safe internal path.
 * Rejects absolute URLs, protocol-relative URLs, and paths with authority.
 */
export function sanitizeRedirectTarget(target: string): string {
	// Must start with / and not // (protocol-relative)
	if (!target.startsWith('/') || target.startsWith('//')) {
		return '/app';
	}
	// Reject backslash tricks (some browsers treat \ as /)
	if (target.includes('\\')) {
		return '/app';
	}
	// Strip any authority-like patterns (e.g., /\@evil.com)
	try {
		const url = new URL(target, 'http://localhost');
		if (url.hostname !== 'localhost') {
			return '/app';
		}
	} catch {
		return '/app';
	}
	return target;
}

export const GET: RequestHandler = async ({ url, locals: { supabase } }) => {
	const code = url.searchParams.get('code');
	const rawNext = url.searchParams.get('next') ?? '/app';
	const next = sanitizeRedirectTarget(rawNext);

	if (code) {
		try {
			const { error } = await supabase.auth.exchangeCodeForSession(code);

			if (error) {
				console.error('Error exchanging code for session:', error);
				throw redirect(303, `/login?error=${encodeURIComponent(error.message)}`);
			}
		} catch (err) {
			// Re-throw redirects (they're caught by the outer catch)
			if (err && typeof err === 'object' && 'status' in err) throw err;
			console.error('Auth callback error:', err);
			throw redirect(303, '/login?error=authentication_failed');
		}
	}

	throw redirect(303, next);
};

