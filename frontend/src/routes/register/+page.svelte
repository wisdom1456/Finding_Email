<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
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
				// Create profile
				const { error: profileError } = await supabase.from('profiles').insert({
					id: data.user.id,
					email: data.user.email!,
					full_name: fullName
				});

				if (profileError) throw profileError;

				successMessage = 'Account created successfully! Redirecting...';
				setTimeout(() => goto('/app'), 2000);
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
		<div class="bg-white rounded-lg shadow-lg p-8">
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
						class="block w-full px-3 py-2.5 border border-gray-300 rounded-md text-contrast placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
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
						class="block w-full px-3 py-2.5 border border-gray-300 rounded-md text-contrast placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
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
						class="block w-full px-3 py-2.5 border border-gray-300 rounded-md text-contrast placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
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
					<button
						type="submit"
						disabled={loading}
						class="w-full flex justify-center py-2.5 px-4 text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
					>
						{#if loading}
							<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
							</svg>
							Creating account...
						{:else}
							Create account
						{/if}
					</button>
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
