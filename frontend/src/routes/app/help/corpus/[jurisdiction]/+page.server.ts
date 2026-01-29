import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { PUBLIC_API_URL } from '$env/static/public';
import { env } from '$env/dynamic/private';

const VALID_JURISDICTIONS = ['florida', 'new-mexico'] as const;

export const load: PageServerLoad = async ({ params, fetch }) => {
	const jurisdiction = params.jurisdiction?.toLowerCase() ?? '';

	if (!VALID_JURISDICTIONS.includes(jurisdiction as (typeof VALID_JURISDICTIONS)[number])) {
		throw error(404, 'Unknown jurisdiction');
	}

	let API_URL = 'http://127.0.0.1:8000';
	if (env.VERCEL_URL) {
		API_URL = '';
	} else if (PUBLIC_API_URL && !PUBLIC_API_URL.includes('supabase.co')) {
		API_URL = PUBLIC_API_URL;
	}

	const res = await fetch(`${API_URL}/api/corpus/${jurisdiction}`);
	if (!res.ok) {
		const text = await res.text();
		throw error(res.status, res.status === 404 ? 'Corpus not available' : 'Failed to load corpus');
	}

	const data = (await res.json()) as { markdown?: string };
	const markdown = typeof data?.markdown === 'string' ? data.markdown : '';

	return {
		markdown,
		jurisdiction
	};
};
