<script lang="ts">
	import { supabase } from '$lib/supabase';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import Input from '$lib/components/ui/Input.svelte';
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
		<div class="card-standard">
			<div class="mb-6">
				<h2 class="text-2xl font-heading font-bold text-contrast text-center">
					Welcome Back
				</h2>
				<p class="mt-2 text-center text-sm text-gray-500">
					Sign in to your account
				</p>
			</div>
			
			<form class="space-y-5" onsubmit={(e) => { e.preventDefault(); handleLogin(); }}>
				<Input
					id="email-address"
					label="Email address"
					type="email"
					name="email"
					autocomplete="email"
					required
					bind:value={email}
					placeholder="you@example.com"
					error={errorMessage}
				/>

				<Input
					id="password"
					label="Password"
					type="password"
					name="password"
					autocomplete="current-password"
					required
					bind:value={password}
					placeholder="••••••••"
					error={errorMessage}
				/>

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
