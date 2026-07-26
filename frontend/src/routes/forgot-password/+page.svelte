<script lang="ts">
	import { supabase } from '$lib/supabase';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import logoImg from '$lib/assets/logo-br.png';

	let email = $state('');
	let loading = $state(false);
	let submitted = $state(false);
	let errorMessage = $state('');

	async function handleSubmit() {
		loading = true;
		errorMessage = '';

		try {
			// Land the recovery link on our callback, which exchanges the code into
			// a session and then forwards to the set-a-new-password page.
			const redirectTo = `${window.location.origin}/auth/callback?next=/account/update-password`;

			// Non-enumerating: we intentionally do NOT inspect the returned error.
			// Supabase returns success regardless of whether the email exists, and
			// we surface the same confirmation either way so the page never reveals
			// which addresses are registered.
			await supabase.auth.resetPasswordForEmail(email, { redirectTo });
			submitted = true;
		} catch {
			// Only genuine transport failures (never "user not found") land here.
			errorMessage = 'Something went wrong. Please try again.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Reset Password | Bernhardt Riley</title>
</svelte:head>

<div class="min-h-screen flex flex-col justify-center bg-contrast py-12 px-4 sm:px-6 lg:px-8">
	<div class="sm:mx-auto sm:w-full sm:max-w-md">
		<div class="flex justify-center mb-8">
			<img src={logoImg} alt="Bernhardt Riley" class="h-20 sm:h-24 w-auto" />
		</div>

		<div class="card-standard">
			{#if submitted}
				<div class="text-center">
					<h2 class="text-2xl font-heading font-bold text-contrast mb-3">Check your email</h2>
					<p class="text-sm text-gray-500">
						If an account exists for that email, we've sent a password reset link.
						Check your inbox (and your spam folder).
					</p>
					<div class="mt-6">
						<a href="/login" class="text-sm font-medium text-accent hover:text-accent-hover transition-colors">
							Back to sign in
						</a>
					</div>
				</div>
			{:else}
				<div class="mb-6">
					<h2 class="text-2xl font-heading font-bold text-contrast text-center">
						Reset your password
					</h2>
					<p class="mt-2 text-center text-sm text-gray-500">
						Enter your email and we'll send you a reset link.
					</p>
				</div>

				<form class="space-y-5" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
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

					<div class="pt-2">
						<AsyncButton
							type="submit"
							loading={loading}
							variant="primary"
							loadingText="Sending..."
							class="w-full"
						>
							Send reset link
						</AsyncButton>
					</div>

					<div class="text-center pt-2">
						<a href="/login" class="text-sm font-medium text-accent hover:text-accent-hover transition-colors">
							Back to sign in
						</a>
					</div>
				</form>
			{/if}
		</div>

		<p class="mt-8 text-center text-xs text-gray-400">
			&copy; {new Date().getFullYear()} Bernhardt Riley, P.A. All rights reserved.
		</p>
	</div>
</div>
