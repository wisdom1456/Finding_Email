/**
 * Load function for the New Case page.
 *
 * Why this exists: previously +page.svelte had
 *   let jurisdiction = $state('Florida');
 * followed by an async profile fetch in onMount. A fast-clicker could
 * create a case before the profile fetch resolved, silently defaulting
 * to Florida regardless of the user's actual default_jurisdiction.
 *
 * Running this in +page.ts moves the fetch BEFORE the component mounts.
 * The component receives the jurisdiction as a prop — no race window.
 *
 * Empty default is intentional. If the user's profile lacks a
 * default_jurisdiction (or fetch fails), the form shows a "Select
 * jurisdiction" placeholder rather than silently picking Florida.
 */

import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const res = await fetch('/api/profile');
		if (!res.ok) return { defaultJurisdiction: '' };
		const profile = await res.json();
		return { defaultJurisdiction: profile?.default_jurisdiction ?? '' };
	} catch {
		return { defaultJurisdiction: '' };
	}
};
