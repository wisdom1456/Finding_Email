import { error } from '@sveltejs/kit';

// Internal design-system reference — dev builds only. In production it
// exposed token/hex internals to any approved user.
export function load() {
	if (!import.meta.env.DEV) {
		throw error(404, 'Not found');
	}
	return {};
}
