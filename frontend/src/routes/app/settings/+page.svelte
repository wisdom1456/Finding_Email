<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { getApiUrl } from '$lib/config';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import { Info, CheckCircle, XCircle } from 'lucide-svelte';

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
	let defaultJurisdiction = $state('Florida');

	// AI Model Preferences
	let documentAnalysisModel = $state('gpt-4o');
	let letterGenerationModel = $state('gpt-4o');
	let caseChatModel = $state('gpt-4o');
	let multiStageAnalysisModel = $state('gpt-4o');
	let blacklistedDocuments = $state('');

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
				defaultJurisdiction = profile.default_jurisdiction || 'Florida';

				// Load AI preferences
				if (profile.ai_preferences) {
					documentAnalysisModel = profile.ai_preferences.document_analysis || 'gpt-4o';
					letterGenerationModel = profile.ai_preferences.letter_generation || 'gpt-4o';
					caseChatModel = profile.ai_preferences.case_chat || 'gpt-4o';
					multiStageAnalysisModel = profile.ai_preferences.multi_stage_analysis || 'gpt-4o';
					
					if (profile.ai_preferences.blacklisted_documents) {
						blacklistedDocuments = profile.ai_preferences.blacklisted_documents.join(', ');
					}
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
				default_jurisdiction: defaultJurisdiction,
				ai_preferences: {
					document_analysis: documentAnalysisModel,
					letter_generation: letterGenerationModel,
					case_chat: caseChatModel,
					multi_stage_analysis: multiStageAnalysisModel,
					blacklisted_documents: blacklistedDocuments
						.split(',')
						.map((d) => d.trim())
						.filter((d) => d.length > 0)
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

<svelte:head>
	<title>Settings | Bernhardt Riley</title>
</svelte:head>

<div class="space-y-6">
	<PageHeader
		title="Settings"
		subtitle="Manage your profile information and AI model preferences"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/app' },
			{ label: 'Settings' }
		]}
	/>

	{#if loading}
		<div class="bg-white shadow-card rounded-lg p-6">
			<div class="animate-pulse space-y-4">
				<div class="h-4 bg-gray-200 rounded w-3/4"></div>
				<div class="h-4 bg-gray-200 rounded w-1/2"></div>
			</div>
		</div>
	{:else}
		<form onsubmit={(e) => { e.preventDefault(); saveProfile(); }}>
			<!-- Contact Information Section -->
			<div class="bg-white shadow-card rounded-lg p-6 mb-6">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-4">Contact Information</h2>
				
				<div class="space-y-4">
					<div>
						<label for="fullName" class="block text-sm font-medium text-contrast mb-1">
							Full Name
						</label>
						<input
							type="text"
							id="fullName"
							bind:value={fullName}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
							placeholder="John Doe"
						/>
					</div>

					<div>
						<label for="email" class="block text-sm font-medium text-contrast mb-1">
							Email
						</label>
						<input
							type="email"
							id="email"
							value={email}
							disabled
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md bg-gray-100 text-gray-500 cursor-not-allowed"
						/>
						<p class="mt-1 text-xs text-gray-500">Email cannot be changed</p>
					</div>

					<div>
						<label for="phone" class="block text-sm font-medium text-contrast mb-1">
							Phone Number
						</label>
						<input
							type="tel"
							id="phone"
							bind:value={phone}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
							placeholder="(555) 123-4567"
						/>
					</div>

					<div>
						<label for="firmName" class="block text-sm font-medium text-contrast mb-1">
							Firm Name
						</label>
						<input
							type="text"
							id="firmName"
							bind:value={firmName}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
							placeholder="Your Law Firm"
						/>
					</div>

					<div>
						<label for="firmAddress" class="block text-sm font-medium text-contrast mb-1">
							Firm Address
						</label>
						<textarea
							id="firmAddress"
							bind:value={firmAddress}
							rows="3"
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors resize-none"
							placeholder="Street Address&#10;Suite/Unit&#10;City, State ZIP"
						></textarea>
					</div>
				</div>
			</div>

			<!-- Legal Jurisdiction Section -->
			<div class="bg-white shadow-card rounded-lg p-6 mb-6">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-2">Legal Jurisdiction Preference</h2>
				<p class="text-sm text-gray-500 mb-6">
					Set your default state for new cases. This will pre-select the appropriate legal corpus and statute validation rules.
				</p>

				<div class="space-y-4">
					<div>
						<label for="defaultJurisdiction" class="block text-sm font-medium text-contrast mb-1">
							Default State
						</label>
						<select
							id="defaultJurisdiction"
							bind:value={defaultJurisdiction}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						>
							<option value="Florida">Florida</option>
							<option value="New Mexico">New Mexico</option>
						</select>
					</div>
				</div>
			</div>

			<!-- AI Model Preferences Section -->
			<div class="bg-white shadow-card rounded-lg p-6 mb-6">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-2">AI Model Preferences</h2>
				<p class="text-sm text-gray-500 mb-6">
					Choose which AI models to use for different operations. These preferences will be applied to all your cases.
				</p>

				<div class="space-y-4">
					<div>
						<label for="documentAnalysisModel" class="block text-sm font-medium text-contrast mb-1">
							Document Analysis
						</label>
						<select
							id="documentAnalysisModel"
							bind:value={documentAnalysisModel}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label} - {model.description}</option>
							{/each}
						</select>
					</div>

					<div>
						<label for="letterGenerationModel" class="block text-sm font-medium text-contrast mb-1">
							Letter Generation
						</label>
						<select
							id="letterGenerationModel"
							bind:value={letterGenerationModel}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label} - {model.description}</option>
							{/each}
						</select>
					</div>

					<div>
						<label for="caseChatModel" class="block text-sm font-medium text-contrast mb-1">
							Case Chat
						</label>
						<select
							id="caseChatModel"
							bind:value={caseChatModel}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label} - {model.description}</option>
							{/each}
						</select>
					</div>

					<div>
						<label for="multiStageAnalysisModel" class="block text-sm font-medium text-contrast mb-1">
							Multi-Stage Analysis
						</label>
						<select
							id="multiStageAnalysisModel"
							bind:value={multiStageAnalysisModel}
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label} - {model.description}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="mt-6 bg-contrast-light/5 border border-contrast-light/20 rounded-lg p-4">
					<div class="flex">
						<Info class="h-5 w-5 text-contrast-light flex-shrink-0" />
						<div class="ml-3">
							<h3 class="text-sm font-medium text-contrast-light">Model Information</h3>
							<div class="mt-2 text-sm text-gray-600">
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

			<!-- Document Handling Preferences Section -->
			<div class="bg-white shadow-card rounded-lg p-6 mb-6">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-2">Document Handling</h2>
				<p class="text-sm text-gray-500 mb-6">
					Configure how documents are handled during import and analysis.
				</p>

				<div class="space-y-4">
					<div>
						<label for="blacklistedDocuments" class="block text-sm font-medium text-contrast mb-1">
							Always Exclude (Blacklist)
						</label>
						<p class="text-xs text-gray-500 mb-2">
							Documents with these names will be automatically skipped during import. Separate names with commas.
						</p>
						<textarea
							id="blacklistedDocuments"
							bind:value={blacklistedDocuments}
							rows="3"
							class="w-full px-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors resize-none"
							placeholder="e.g. Terms of Service.pdf, Privacy Policy.docx, clio_invoice.pdf"
						></textarea>
					</div>
				</div>
			</div>

			<!-- Message Display -->
			{#if message}
				<div class="mb-6">
					<div class="rounded-lg p-4 flex items-start {messageType === 'success' ? 'bg-accent/10 border border-accent/30' : 'bg-red-50 border border-red-200'}">
						<div class="flex-shrink-0">
							{#if messageType === 'success'}
								<CheckCircle class="h-5 w-5 text-accent" />
							{:else}
								<XCircle class="h-5 w-5 text-red-500" />
							{/if}
						</div>
						<div class="ml-3">
							<p class="text-sm font-medium {messageType === 'success' ? 'text-accent' : 'text-red-700'}">{message}</p>
						</div>
					</div>
				</div>
			{/if}

		<!-- Save Button -->
		<div class="flex justify-end">
			<AsyncButton
				type="submit"
				loading={saving}
				variant="primary"
				loadingText="Saving..."
				class="px-6"
			>
				Save Changes
			</AsyncButton>
		</div>
		</form>
	{/if}
</div>
