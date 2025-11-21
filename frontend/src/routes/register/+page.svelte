<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';

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

<div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
	<div class="max-w-md w-full space-y-8">
		<div>
			<h2 class="mt-6 text-center text-3xl font-extrabold text-gray-900">
				Create your account
			</h2>
			<p class="mt-2 text-center text-sm text-gray-600">
				Join the Legal Document Analysis Portal
			</p>
		</div>
		<form class="mt-8 space-y-6" on:submit|preventDefault={handleRegister}>
			<div class="rounded-md shadow-sm space-y-2">
				<div>
					<label for="full-name" class="sr-only">Full name</label>
					<input
						id="full-name"
						name="fullName"
						type="text"
						required
						bind:value={fullName}
						class="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
						placeholder="Full name"
					/>
				</div>
				<div>
					<label for="email-address" class="sr-only">Email address</label>
					<input
						id="email-address"
						name="email"
						type="email"
						autocomplete="email"
						required
						bind:value={email}
						class="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
						placeholder="Email address"
					/>
				</div>
				<div>
					<label for="password" class="sr-only">Password</label>
					<input
						id="password"
						name="password"
						type="password"
						autocomplete="new-password"
						required
						bind:value={password}
						class="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
						placeholder="Password (min. 8 characters)"
						minlength="8"
					/>
				</div>
			</div>

			{#if errorMessage}
				<div class="rounded-md bg-red-50 p-4">
					<p class="text-sm text-red-800">{errorMessage}</p>
				</div>
			{/if}

			{#if successMessage}
				<div class="rounded-md bg-green-50 p-4">
					<p class="text-sm text-green-800">{successMessage}</p>
				</div>
			{/if}

			<div>
				<button
					type="submit"
					disabled={loading}
					class="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{loading ? 'Creating account...' : 'Create account'}
				</button>
			</div>

			<div class="text-center">
				<a href="/login" class="font-medium text-blue-600 hover:text-blue-500">
					Already have an account? Sign in
				</a>
			</div>
		</form>
	</div>
</div>

