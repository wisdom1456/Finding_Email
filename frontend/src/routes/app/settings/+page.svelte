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
	let documentAnalysisModel = $state('gpt-5-mini');
	let letterGenerationModel = $state('gpt-5.2');
	let caseChatModel = $state('gpt-5-mini');
	let multiStageAnalysisModel = $state('gpt-5.2');
	let blacklistedDocuments = $state('');

	const availableModels = [
		{ value: 'gpt-5.2', label: 'GPT-5.2 (Recommended)', description: 'Most intelligent, complex reasoning' },
		{ value: 'gpt-5-mini', label: 'GPT-5 Mini', description: 'Cost-optimized, fast and capable' },
		{ value: 'gpt-5-nano', label: 'GPT-5 Nano', description: 'High-throughput, simple tasks' },
		{ value: 'gpt-4o', label: 'GPT-4o (Legacy)', description: 'Previous generation model' }
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
					documentAnalysisModel = profile.ai_preferences.document_analysis || 'gpt-5-mini';
					letterGenerationModel = profile.ai_preferences.letter_generation || 'gpt-5.2';
					caseChatModel = profile.ai_preferences.case_chat || 'gpt-5-mini';
					multiStageAnalysisModel = profile.ai_preferences.multi_stage_analysis || 'gpt-5.2';
					
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

<div class="page-spacing">
	<PageHeader
		title="Settings"
		subtitle="Manage your profile information and AI model preferences"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/app' },
			{ label: 'Settings' }
		]}
	/>

	{#if loading}
		<div class="card-standard">
			<div class="animate-pulse space-y-4">
				<div class="h-4 bg-gray-200 rounded w-3/4"></div>
				<div class="h-4 bg-gray-200 rounded w-1/2"></div>
			</div>
		</div>
	{:else}
		<form onsubmit={(e) => { e.preventDefault(); saveProfile(); }} class="page-spacing">
			<!-- Contact Information Section -->
			<div class="card-standard">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-6">Contact Information</h2>
				
				<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
					<div class="col-span-1">
						<label for="fullName" class="block text-sm font-semibold text-contrast mb-1">
							Full Name
						</label>
						<input
							type="text"
							id="fullName"
							bind:value={fullName}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
							placeholder="John Doe"
						/>
					</div>

					<div class="col-span-1">
						<label for="email" class="block text-sm font-semibold text-contrast mb-1">
							Email
						</label>
						<input
							type="email"
							id="email"
							value={email}
							disabled
							class="input-standard bg-gray-50 text-gray-500 cursor-not-allowed opacity-75"
						/>
						<p class="mt-1 text-xs text-gray-400 italic">Email cannot be changed</p>
					</div>

					<div class="col-span-1">
						<label for="phone" class="block text-sm font-semibold text-contrast mb-1">
							Phone Number
						</label>
						<input
							type="tel"
							id="phone"
							bind:value={phone}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
							placeholder="(555) 123-4567"
						/>
					</div>

					<div class="col-span-1">
						<label for="firmName" class="block text-sm font-semibold text-contrast mb-1">
							Firm Name
						</label>
						<input
							type="text"
							id="firmName"
							bind:value={firmName}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
							placeholder="Your Law Firm"
						/>
					</div>

					<div class="col-span-2">
						<label for="firmAddress" class="block text-sm font-semibold text-contrast mb-1">
							Firm Address
						</label>
						<textarea
							id="firmAddress"
							bind:value={firmAddress}
							rows="3"
							class="input-standard focus:ring-accent focus:border-transparent transition-colors resize-none"
							placeholder="Street Address&#10;Suite/Unit&#10;City, State ZIP"
						></textarea>
					</div>
				</div>
			</div>

			<!-- Legal Jurisdiction Section -->
			<div class="card-standard">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-2">Legal Jurisdiction Preference</h2>
				<p class="text-sm text-gray-500 mb-6">
					Set your default state for new cases. This will pre-select the appropriate legal corpus and statute validation rules.
				</p>

				<div class="max-w-md">
					<label for="defaultJurisdiction" class="block text-sm font-semibold text-contrast mb-1">
							Default State
						</label>
						<select
							id="defaultJurisdiction"
							bind:value={defaultJurisdiction}
						class="input-standard focus:ring-accent focus:border-transparent transition-colors"
						>
							<option value="Florida">Florida</option>
							<option value="New Mexico">New Mexico</option>
						</select>
				</div>
			</div>

			<!-- AI Model Preferences Section -->
			<div class="card-standard">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-2">AI Model Preferences</h2>
				<p class="text-sm text-gray-500 mb-6">
					Choose which AI models to use for different operations. These preferences will be applied to all your cases.
				</p>

				<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
					<div>
						<label for="documentAnalysisModel" class="block text-sm font-semibold text-contrast mb-1">
							Document Analysis
						</label>
						<select
							id="documentAnalysisModel"
							bind:value={documentAnalysisModel}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label}</option>
							{/each}
						</select>
					</div>

					<div>
						<label for="letterGenerationModel" class="block text-sm font-semibold text-contrast mb-1">
							Letter Generation
						</label>
						<select
							id="letterGenerationModel"
							bind:value={letterGenerationModel}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label}</option>
							{/each}
						</select>
					</div>

					<div>
						<label for="caseChatModel" class="block text-sm font-semibold text-contrast mb-1">
							Case Chat
						</label>
						<select
							id="caseChatModel"
							bind:value={caseChatModel}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label}</option>
							{/each}
						</select>
					</div>

					<div>
						<label for="multiStageAnalysisModel" class="block text-sm font-semibold text-contrast mb-1">
							Multi-Stage Analysis
						</label>
						<select
							id="multiStageAnalysisModel"
							bind:value={multiStageAnalysisModel}
							class="input-standard focus:ring-accent focus:border-transparent transition-colors"
						>
							{#each availableModels as model}
								<option value={model.value}>{model.label}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="mt-8 info-box info-box-blue">
					<div class="flex">
						<Info class="h-5 w-5 text-contrast-light flex-shrink-0" />
						<div class="ml-3">
							<h3 class="text-sm font-bold text-contrast-light">Model Information</h3>
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
			<div class="card-standard">
				<h2 class="text-lg font-heading font-semibold text-contrast mb-2">Document Handling</h2>
				<p class="text-sm text-gray-500 mb-6">
					Configure how documents are handled during import and analysis.
				</p>

					<div>
					<label for="blacklistedDocuments" class="block text-sm font-semibold text-contrast mb-1">
							Always Exclude (Blacklist)
						</label>
					<p class="text-xs text-gray-500 mb-3 italic">
							Documents with these names will be automatically skipped during import. Separate names with commas.
						</p>
						<textarea
							id="blacklistedDocuments"
							bind:value={blacklistedDocuments}
							rows="3"
						class="input-standard focus:ring-accent focus:border-transparent transition-colors resize-none"
							placeholder="e.g. Terms of Service.pdf, Privacy Policy.docx, clio_invoice.pdf"
						></textarea>
				</div>
			</div>

			<!-- Message Display -->
			{#if message}
				<div class="info-box {messageType === 'success' ? 'bg-accent/10 border-accent/30 text-accent' : 'bg-red-50 border-red-200 text-red-700'}">
					<div class="flex items-start">
						<div class="flex-shrink-0">
							{#if messageType === 'success'}
								<CheckCircle class="h-5 w-5" />
							{:else}
								<XCircle class="h-5 w-5" />
							{/if}
						</div>
						<div class="ml-3">
							<p class="text-sm font-semibold">{message}</p>
						</div>
					</div>
				</div>
			{/if}

		<!-- Save Button -->
			<div class="flex justify-end pt-4">
			<AsyncButton
				type="submit"
				loading={saving}
				variant="primary"
					loadingText="Saving Changes..."
					class="px-8 py-3 text-base shadow-sm"
			>
				Save Changes
			</AsyncButton>
		</div>
		</form>
	{/if}
</div>
