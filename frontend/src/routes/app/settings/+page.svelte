<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { getApiUrl } from '$lib/config';

	let loading = $state(true);
	let saving = $state(false);
	let message = $state('');
	let messageType = $state<'success' | 'error'>('success');

	// Profile data with defaults
	let fullName = $state('');
	let email = $state('');
	let phone = $state('(727) 275-9575');
	let firmName = $state('Bernhardt Riley Law Firm');
	let firmAddress = $state(`2706 US-19 ALT
Suite 213
Palm Harbor, FL 34683`);

	// AI Model Preferences
	let documentAnalysisModel = $state('gpt-4o');
	let letterGenerationModel = $state('gpt-4o');
	let caseChatModel = $state('gpt-4o');
	let multiStageAnalysisModel = $state('gpt-4o');

	const availableModels = [
		{ value: 'gpt-4o', label: 'GPT-4o (Recommended)', description: 'Fastest, best for most uses' },
		{ value: 'gpt-4o-mini', label: 'GPT-4o Mini', description: 'Most cost-effective, good quality' },
		{ value: 'gpt-4-turbo', label: 'GPT-4 Turbo', description: 'Longer context, complex cases' },
		{ value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo', description: 'Faster, lower cost' }
	];

	onMount(async () => {
		await loadProfile();
	});

	async function loadProfile() {
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) {
				message = 'Please sign in to access settings';
				messageType = 'error';
				loading = false;
				return;
			}

			// Get email from session
			email = session.user.email || '';

			// Fetch profile data
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/profile`, {
				headers: {
					'Authorization': `Bearer ${session.access_token}`,
					'Content-Type': 'application/json'
				}
			});

			if (response.ok) {
				const profile = await response.json();
				fullName = profile.full_name || '';
				phone = profile.phone || '(727) 275-9575';
				firmName = profile.firm_name || 'Bernhardt Riley Law Firm';
				firmAddress = profile.firm_address || firmAddress;

				// Load AI preferences
				if (profile.ai_preferences) {
					documentAnalysisModel = profile.ai_preferences.document_analysis || 'gpt-4o';
					letterGenerationModel = profile.ai_preferences.letter_generation || 'gpt-4o';
					caseChatModel = profile.ai_preferences.case_chat || 'gpt-4o';
					multiStageAnalysisModel = profile.ai_preferences.multi_stage_analysis || 'gpt-4o';
				}
			}
		} catch (error: any) {
			message = `Error loading profile: ${error.message}`;
			messageType = 'error';
		} finally {
			loading = false;
		}
	}

	async function saveProfile() {
		saving = true;
		message = '';

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) {
				message = 'Session expired. Please sign in again.';
				messageType = 'error';
				return;
			}

			const profileData = {
				full_name: fullName,
				phone: phone,
				firm_name: firmName,
				firm_address: firmAddress,
				ai_preferences: {
					document_analysis: documentAnalysisModel,
					letter_generation: letterGenerationModel,
					case_chat: caseChatModel,
					multi_stage_analysis: multiStageAnalysisModel
				}
			};

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/profile`, {
				method: 'PUT',
				headers: {
					'Authorization': `Bearer ${session.access_token}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(profileData)
			});

			if (response.ok) {
				message = 'Profile saved successfully!';
				messageType = 'success';
				setTimeout(() => { message = ''; }, 3000);
			} else {
				const error = await response.json();
				message = `Error saving profile: ${error.detail || 'Unknown error'}`;
				messageType = 'error';
			}
		} catch (error: any) {
			message = `Error saving profile: ${error.message}`;
			messageType = 'error';
		} finally {
			saving = false;
		}
	}
</script>

<div class="min-h-screen bg-gray-50 py-8 px-4 sm:px-6 lg:px-8">
	<div class="max-w-4xl mx-auto">
		<div class="mb-8">
			<h1 class="text-3xl font-bold text-gray-900">Settings</h1>
			<p class="mt-2 text-sm text-gray-600">
				Manage your profile information and AI model preferences
			</p>
		</div>

		{#if loading}
			<div class="bg-white shadow rounded-lg p-6">
				<div class="animate-pulse space-y-4">
					<div class="h-4 bg-gray-200 rounded w-3/4"></div>
					<div class="h-4 bg-gray-200 rounded w-1/2"></div>
				</div>
			</div>
		{:else}
			<form onsubmit={(e) => { e.preventDefault(); saveProfile(); }}>
				<!-- Contact Information Section -->
				<div class="bg-white shadow rounded-lg p-6 mb-6">
					<h2 class="text-xl font-semibold text-gray-900 mb-4">Contact Information</h2>
					
					<div class="space-y-4">
						<div>
							<label for="fullName" class="block text-sm font-medium text-gray-700 mb-1">
								Full Name
							</label>
							<input
								type="text"
								id="fullName"
								bind:value={fullName}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								placeholder="John Doe"
							/>
						</div>

						<div>
							<label for="email" class="block text-sm font-medium text-gray-700 mb-1">
								Email
							</label>
							<input
								type="email"
								id="email"
								value={email}
								disabled
								class="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-100 text-gray-500 cursor-not-allowed"
							/>
							<p class="mt-1 text-xs text-gray-500">Email cannot be changed</p>
						</div>

						<div>
							<label for="phone" class="block text-sm font-medium text-gray-700 mb-1">
								Phone Number
							</label>
							<input
								type="tel"
								id="phone"
								bind:value={phone}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								placeholder="(555) 123-4567"
							/>
						</div>

						<div>
							<label for="firmName" class="block text-sm font-medium text-gray-700 mb-1">
								Firm Name
							</label>
							<input
								type="text"
								id="firmName"
								bind:value={firmName}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								placeholder="Your Law Firm"
							/>
						</div>

						<div>
							<label for="firmAddress" class="block text-sm font-medium text-gray-700 mb-1">
								Firm Address
							</label>
							<textarea
								id="firmAddress"
								bind:value={firmAddress}
								rows="3"
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								placeholder="Street Address&#10;Suite/Unit&#10;City, State ZIP"
							></textarea>
						</div>
					</div>
				</div>

				<!-- AI Model Preferences Section -->
				<div class="bg-white shadow rounded-lg p-6 mb-6">
					<h2 class="text-xl font-semibold text-gray-900 mb-4">AI Model Preferences</h2>
					<p class="text-sm text-gray-600 mb-4">
						Choose which AI models to use for different operations. These preferences will be applied to all your cases.
					</p>

					<div class="space-y-4">
						<div>
							<label for="documentAnalysisModel" class="block text-sm font-medium text-gray-700 mb-1">
								Document Analysis
							</label>
							<select
								id="documentAnalysisModel"
								bind:value={documentAnalysisModel}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							>
								{#each availableModels as model}
									<option value={model.value}>{model.label} - {model.description}</option>
								{/each}
							</select>
						</div>

						<div>
							<label for="letterGenerationModel" class="block text-sm font-medium text-gray-700 mb-1">
								Letter Generation
							</label>
							<select
								id="letterGenerationModel"
								bind:value={letterGenerationModel}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							>
								{#each availableModels as model}
									<option value={model.value}>{model.label} - {model.description}</option>
								{/each}
							</select>
						</div>

						<div>
							<label for="caseChatModel" class="block text-sm font-medium text-gray-700 mb-1">
								Case Chat
							</label>
							<select
								id="caseChatModel"
								bind:value={caseChatModel}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							>
								{#each availableModels as model}
									<option value={model.value}>{model.label} - {model.description}</option>
								{/each}
							</select>
						</div>

						<div>
							<label for="multiStageAnalysisModel" class="block text-sm font-medium text-gray-700 mb-1">
								Multi-Stage Analysis
							</label>
							<select
								id="multiStageAnalysisModel"
								bind:value={multiStageAnalysisModel}
								class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
							>
								{#each availableModels as model}
									<option value={model.value}>{model.label} - {model.description}</option>
								{/each}
							</select>
						</div>
					</div>

					<div class="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
						<div class="flex">
							<div class="flex-shrink-0">
								<svg class="h-5 w-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
								</svg>
							</div>
							<div class="ml-3">
								<h3 class="text-sm font-medium text-blue-800">Model Information</h3>
								<div class="mt-2 text-sm text-blue-700">
									<ul class="list-disc list-inside space-y-1">
										<li><strong>GPT-4o:</strong> Best balance of speed and quality - recommended for most cases</li>
										<li><strong>GPT-4o Mini:</strong> Faster and more economical while maintaining good quality</li>
										<li><strong>GPT-4 Turbo:</strong> Handles longer documents and complex cases with larger context</li>
										<li><strong>GPT-3.5 Turbo:</strong> Fastest option with lower cost, good for simple tasks</li>
									</ul>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Message Display -->
				{#if message}
					<div class="mb-6">
						<div class={`rounded-lg p-4 ${messageType === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
							<div class="flex">
								<div class="flex-shrink-0">
									{#if messageType === 'success'}
										<svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
										</svg>
									{:else}
										<svg class="h-5 w-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
										</svg>
									{/if}
								</div>
								<div class="ml-3">
									<p class="text-sm font-medium">{message}</p>
								</div>
							</div>
						</div>
					</div>
				{/if}

				<!-- Save Button -->
				<div class="flex justify-end">
					<button
						type="submit"
						disabled={saving}
						class="px-6 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
					>
						{saving ? 'Saving...' : 'Save Changes'}
					</button>
				</div>
			</form>
		{/if}
	</div>
</div>

