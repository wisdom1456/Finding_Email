<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { supabase, getSecureSession } from '$lib/supabase';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import logoImg from '$lib/assets/logo-br.png';

	const MIN_LENGTH = 8;

	let password = $state('');
	let confirm = $state('');
	let loading = $state(false);
	let errorMessage = $state('');
	// Gate the form on a valid recovery session. The recovery link establishes
	// one via /auth/callback; without it this page has nothing to update.
	let checking = $state(true);

	onMount(async () => {
		const { session } = await getSecureSession();
		if (!session) {
			goto('/login');
			return;
		}
		checking = false;
	});

	async function handleSubmit() {
		errorMessage = '';

		if (password.length < MIN_LENGTH) {
			errorMessage = `Password must be at least ${MIN_LENGTH} characters.`;
			return;
		}
		if (password !== confirm) {
			errorMessage = 'Passwords do not match.';
			return;
		}

		loading = true;
		try {
			const { error } = await supabase.auth.updateUser({ password });
			if (error) throw error;
			goto('/app');
		} catch (error: any) {
			errorMessage = error?.message || 'Could not update your password. Please try again.';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Set a New Password | Bernhardt Riley</title>
</svelte:head>

<div class="min-h-screen flex flex-col justify-center bg-contrast py-12 px-4 sm:px-6 lg:px-8">
	<div class="sm:mx-auto sm:w-full sm:max-w-md">
		<div class="flex justify-center mb-8">
			<img src={logoImg} alt="Bernhardt Riley" class="h-20 sm:h-24 w-auto" />
		</div>

		<div class="card-standard">
			{#if checking}
				<p class="text-center text-sm text-gray-500">Loading…</p>
			{:else}
				<div class="mb-6">
					<h2 class="text-2xl font-heading font-bold text-contrast text-center">
						Set a new password
					</h2>
					<p class="mt-2 text-center text-sm text-gray-500">
						Choose a new password for your account.
					</p>
				</div>

				<form class="space-y-5" onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
					<Input
						id="new-password"
						label="New password"
						type="password"
						name="new-password"
						autocomplete="new-password"
						required
						bind:value={password}
						placeholder="••••••••"
						helper={`Minimum ${MIN_LENGTH} characters.`}
					/>

					<Input
						id="confirm-password"
						label="Confirm password"
						type="password"
						name="confirm-password"
						autocomplete="new-password"
						required
						bind:value={confirm}
						placeholder="••••••••"
						error={errorMessage}
					/>

					<div class="pt-2">
						<AsyncButton
							type="submit"
							loading={loading}
							variant="primary"
							loadingText="Updating..."
							class="w-full"
						>
							Update password
						</AsyncButton>
					</div>
				</form>
			{/if}
		</div>

		<p class="mt-8 text-center text-xs text-gray-400">
			&copy; {new Date().getFullYear()} Bernhardt Riley, P.A. All rights reserved.
		</p>
	</div>
</div>
