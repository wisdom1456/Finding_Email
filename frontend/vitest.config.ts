import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import path from 'path';

export default defineConfig({
	plugins: [
		svelte({
			hot: !process.env.VITEST,
			compilerOptions: {
				// Use client-side mode for tests - runes mode
				runes: true
			}
		})
	],
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'happy-dom',
		globals: true,
		setupFiles: ['./src/tests/setup.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json', 'html'],
			exclude: [
				'node_modules/',
				'src/tests/',
				'**/*.d.ts',
				'**/*.config.*',
				'**/mockData/',
				'dist/',
			],
		},
		alias: {
			'$lib': path.resolve('./src/lib'),
			'$app': path.resolve('./.svelte-kit/runtime/app')
		}
	},
	resolve: {
		alias: {
			'$lib': path.resolve('./src/lib'),
			'$app/environment': path.resolve('./src/tests/mocks/$app/environment.ts'),
			'$app/navigation': path.resolve('./src/tests/mocks/$app/navigation.ts'),
			'$app/stores': path.resolve('./src/tests/mocks/$app/stores.ts'),
			'$env/static/public': path.resolve('./src/tests/mocks/$env/static/public.ts'),
			'$env/dynamic/public': path.resolve('./src/tests/mocks/$env/dynamic/public.ts')
		}
	}
});

