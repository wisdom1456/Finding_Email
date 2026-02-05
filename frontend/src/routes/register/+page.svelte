<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import Input from '$lib/components/ui/Input.svelte';
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
		<div class="card-standard">
			<div class="mb-6">
				<h2 class="text-2xl font-heading font-bold text-contrast text-center">
					Create Your Account
				</h2>
				<p class="mt-2 text-center text-sm text-gray-500">
					Join the Legal Document Analysis Portal
				</p>
			</div>
			
			<form class="space-y-5" onsubmit={(e) => { e.preventDefault(); handleRegister(); }}>
				<Input
					id="full-name"
					label="Full Name"
					name="fullName"
					type="text"
					required
					bind:value={fullName}
					placeholder="John Doe"
					error={errorMessage}
				/>

				<Input
					id="email-address"
					label="Email Address"
					name="email"
					type="email"
					autocomplete="email"
					required
					bind:value={email}
					placeholder="you@example.com"
					error={errorMessage}
				/>

				<Input
					id="password"
					label="Password"
					name="password"
					type="password"
					autocomplete="new-password"
					required
					bind:value={password}
					placeholder="Min. 8 characters"
					minlength="8"
					error={errorMessage}
					helper="Minimum 8 characters required"
				/>

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
