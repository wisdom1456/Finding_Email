import type { PageServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async ({ params }) => {
	throw redirect(307, `/app/cases/${params.id}?tab=analysis&view=results`);
};
