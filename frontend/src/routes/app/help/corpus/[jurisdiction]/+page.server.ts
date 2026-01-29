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

	const [docRes, entriesRes] = await Promise.all([
		fetch(`${API_URL}/api/corpus/${jurisdiction}`),
		fetch(`${API_URL}/api/corpus/${jurisdiction}/entries`)
	]);

	if (!entriesRes.ok) {
		const text = await entriesRes.text();
		throw error(
			entriesRes.status,
			entriesRes.status === 404 ? 'Corpus not available' : 'Failed to load corpus entries'
		);
	}

	const entriesData = (await entriesRes.json()) as { statutes?: unknown[]; rules?: unknown[] };
	const statutes = Array.isArray(entriesData?.statutes) ? entriesData.statutes : [];
	const rules = Array.isArray(entriesData?.rules) ? entriesData.rules : [];

	let markdown = '';
	if (docRes.ok) {
		const docData = (await docRes.json()) as { markdown?: string };
		markdown = typeof docData?.markdown === 'string' ? docData.markdown : '';
	}

	return {
		markdown,
		statutes,
		rules,
		jurisdiction
	};
};
