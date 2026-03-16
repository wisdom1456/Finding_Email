import type { LayoutServerLoad } from './$types';
import type { Profile } from '$lib/types';

export const load: LayoutServerLoad = async ({ locals: { safeGetSession, supabase, user } }) => {
	const { session } = await safeGetSession();

	// Fetch profile data if user is logged in
	let profile = null;
	if (user) {
		const { data } = await supabase
			.from('profiles')
			.select('id, email, full_name, avatar_url, approved, role, created_at, updated_at')
			.eq('id', user.id)
			.single();
		profile = data as Profile | null;
	}

	return {
		session,
		user,
		profile
	};
};

