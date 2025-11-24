import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url, locals: { supabase } }) => {
	const code = url.searchParams.get('code');
	const next = url.searchParams.get('next') ?? '/app';

	if (code) {
		try {
			const { error } = await supabase.auth.exchangeCodeForSession(code);
			
			if (error) {
				console.error('Error exchanging code for session:', error);
				throw redirect(303, `/login?error=${encodeURIComponent(error.message)}`);
			}
		} catch (err) {
			console.error('Auth callback error:', err);
			throw redirect(303, '/login?error=authentication_failed');
		}
	}

	throw redirect(303, next);
};

