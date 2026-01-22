<script lang="ts">
	import { supabase } from '$lib/supabase';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import logoImg from '$lib/assets/logo-br.png';

	let email = $state('');
	let password = $state('');
	let loading = $state(false);
	let errorMessage = $state('');

	async function handleLogin() {
		loading = true;
		errorMessage = '';

		try {
			const { error } = await supabase.auth.signInWithPassword({
				email,
				password
			});

			if (error) throw error;

			// Use full page reload to ensure layout data is refreshed with new user
			window.location.href = '/app';
		} catch (error: any) {
			errorMessage = error.message || 'An error occurred during login';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Sign In | Bernhardt Riley</title>
</svelte:head>

<div class="min-h-screen flex flex-col justify-center bg-contrast py-12 px-4 sm:px-6 lg:px-8">
	<div class="sm:mx-auto sm:w-full sm:max-w-md">
		<!-- Logo -->
		<div class="flex justify-center mb-8">
			<img src={logoImg} alt="Bernhardt Riley" class="h-20 sm:h-24 w-auto" />
		</div>
		
		<!-- Card -->
		<div class="bg-white rounded-lg shadow-card p-6">
			<div class="mb-6">
				<h2 class="text-2xl font-heading font-bold text-contrast text-center">
					Welcome Back
				</h2>
				<p class="mt-2 text-center text-sm text-gray-500">
					Sign in to your account
				</p>
			</div>
			
			<form class="space-y-5" onsubmit={(e) => { e.preventDefault(); handleLogin(); }}>
				<div>
					<label for="email-address" class="block text-sm font-medium text-contrast mb-1">
						Email address
					</label>
					<input
						id="email-address"
						name="email"
						type="email"
						autocomplete="email"
						required
						bind:value={email}
						class="input-standard focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						placeholder="you@example.com"
					/>
				</div>
				
				<div>
					<label for="password" class="block text-sm font-medium text-contrast mb-1">
						Password
					</label>
					<input
						id="password"
						name="password"
						type="password"
						autocomplete="current-password"
						required
						bind:value={password}
						class="input-standard focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						placeholder="••••••••"
					/>
				</div>

				{#if errorMessage}
					<div class="rounded-md bg-red-50 border border-red-200 p-3">
						<p class="text-sm text-red-700">{errorMessage}</p>
					</div>
				{/if}

			<div class="pt-2">
				<AsyncButton
					type="submit"
					loading={loading}
					variant="primary"
					loadingText="Signing in..."
					class="w-full"
				>
					Sign in
				</AsyncButton>
			</div>

				<div class="text-center pt-2">
					<a href="/register" class="text-sm font-medium text-accent hover:text-accent-hover transition-colors">
						Don't have an account? Register
					</a>
				</div>
			</form>
		</div>
		
		<!-- Footer -->
		<p class="mt-8 text-center text-xs text-gray-400">
			&copy; {new Date().getFullYear()} Bernhardt Riley, P.A. All rights reserved.
		</p>
	</div>
</div>
