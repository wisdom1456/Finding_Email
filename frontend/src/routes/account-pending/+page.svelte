<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';

	let isLoggingOut = $state(false);

	async function handleLogout() {
		isLoggingOut = true;
		try {
			await supabase.auth.signOut();
			goto('/login');
		} catch (error) {
			console.error('Error logging out:', error);
			isLoggingOut = false;
		}
	}
</script>

<div class="min-h-screen flex items-center justify-center bg-gray-50 px-4">
	<div class="max-w-md w-full bg-white rounded-lg shadow-md p-8 text-center">
		<div class="mb-6">
			<div
				class="mx-auto w-16 h-16 bg-yellow-100 rounded-full flex items-center justify-center mb-4"
			>
				<svg
					class="w-8 h-8 text-yellow-600"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
			</div>
			<h1 class="text-2xl font-bold text-gray-900 mb-2">Account Pending Approval</h1>
			<p class="text-gray-600">
				Your account has been created successfully, but it requires administrator approval before
				you can access the application.
			</p>
		</div>

		<div class="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6">
			<p class="text-sm text-blue-800">
				You will receive an email notification once your account has been approved. This typically
				takes 1-2 business days.
			</p>
		</div>

		<button
			onclick={handleLogout}
			disabled={isLoggingOut}
			class="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-400 text-white font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
		>
			{isLoggingOut ? 'Logging out...' : 'Log Out'}
		</button>
	</div>
</div>

