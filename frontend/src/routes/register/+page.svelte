<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import logoImg from '$lib/assets/logo-br.png';

	let email = $state('');
	let password = $state('');
	let fullName = $state('');
	let loading = $state(false);
	let errorMessage = $state('');
	let successMessage = $state('');

	async function handleRegister() {
		loading = true;
		errorMessage = '';
		successMessage = '';

		try {
			const { data, error } = await supabase.auth.signUp({
				email,
				password,
				options: {
					data: {
						full_name: fullName
					}
				}
			});

			if (error) throw error;

			if (data.user) {
				// Profile is created automatically by database trigger (handle_new_user)
				// No need to manually insert - just redirect
				successMessage = 'Account created! Please check your email to verify, then log in.';
				setTimeout(() => goto('/login'), 3000);
			}
		} catch (error: any) {
			errorMessage = error.message || 'An error occurred during registration';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Register | Bernhardt Riley</title>
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
					Create Your Account
				</h2>
				<p class="mt-2 text-center text-sm text-gray-500">
					Join the Legal Document Analysis Portal
				</p>
			</div>
			
			<form class="space-y-5" onsubmit={(e) => { e.preventDefault(); handleRegister(); }}>
				<div>
					<label for="full-name" class="block text-sm font-medium text-contrast mb-1">
						Full Name
					</label>
					<input
						id="full-name"
						name="fullName"
						type="text"
						required
						bind:value={fullName}
						class="input-standard focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						placeholder="John Doe"
					/>
				</div>
				
				<div>
					<label for="email-address" class="block text-sm font-medium text-contrast mb-1">
						Email Address
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
						autocomplete="new-password"
						required
						bind:value={password}
						class="input-standard focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						placeholder="Min. 8 characters"
						minlength="8"
					/>
				</div>

				{#if errorMessage}
					<div class="rounded-md bg-red-50 border border-red-200 p-3">
						<p class="text-sm text-red-700">{errorMessage}</p>
					</div>
				{/if}

				{#if successMessage}
					<div class="rounded-md bg-accent/10 border border-accent/30 p-3">
						<p class="text-sm text-accent">{successMessage}</p>
					</div>
				{/if}

			<div class="pt-2">
				<AsyncButton
					type="submit"
					loading={loading}
					variant="primary"
					loadingText="Creating account..."
					class="w-full"
				>
					Create account
				</AsyncButton>
			</div>

				<div class="text-center pt-2">
					<a href="/login" class="text-sm font-medium text-accent hover:text-accent-hover transition-colors">
						Already have an account? Sign in
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
