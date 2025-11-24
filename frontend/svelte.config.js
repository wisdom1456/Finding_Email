import adapter from '@sveltejs/adapter-vercel';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// Vercel adapter configuration
		adapter: adapter({
			runtime: 'nodejs20.x',
			regions: ['iad1'], // US East - adjust as needed
			split: false
		})
	}
};

export default config;
