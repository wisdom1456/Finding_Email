<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, getSecureSession } from '$lib/supabase';
	import { page } from '$app/stores';
	import { getApiUrl } from '$lib/config';
	import ClioConnect from '$lib/components/ClioConnect.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import AppNavLink from '$lib/components/ui/AppNavLink.svelte';
	import ProfileCompleteBanner from '$lib/components/ProfileCompleteBanner.svelte';
	import { clioStore } from '$lib/stores/clioStore';
	import { Menu, X, User, Settings, LogOut, Link2, HelpCircle } from 'lucide-svelte';
	import type { LayoutData } from './$types';
	import type { LetterProfile } from '$lib/profile';
	import logoImg from '$lib/assets/logo-br.png';

	let { data, children }: { data: LayoutData; children: any } = $props();

	let showClioModal = $state(false);
	let clioConnected = $derived($clioStore.connected);
	let isMobileMenuOpen = $state(false);
	let isUserMenuOpen = $state(false);
	let profile = $state<LetterProfile | null>(null);

	// Check Clio connection status + load profile completeness check on mount
	onMount(async () => {
		await Promise.all([checkClioStatus(), loadProfile()]);
	});

	async function loadProfile() {
		try {
			const { data: { user } } = await supabase.auth.getUser();
			if (!user) return;
			const { data: profileRow } = await supabase
				.from('profiles')
				.select('full_name, default_jurisdiction')
				.eq('id', user.id)
				.single();
			if (profileRow) {
				profile = profileRow as LetterProfile;
			}
		} catch (err) {
			// Banner stays hidden if profile fetch fails — fail-safe
			console.debug('Profile completeness check skipped:', err);
		}
	}

	async function checkClioStatus() {
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) return;

			// Use getApiUrl() to ensure we get the correct runtime value (relative path in Vercel)
			const apiUrl = getApiUrl();
			const endpoint = `${apiUrl}/api/clio/status`;

			const response = await fetch(endpoint, {
				headers: { Authorization: `Bearer ${session.access_token}` }
			});

			if (response.ok) {
				const status = await response.json();
				clioStore.setConnected(status.connected, status.clio_user_id, status.expires_at);
			}
		} catch (error: any) {
			// Silently fail - user can still manually check via modal
			console.debug('Could not check Clio status on load:', error);
		}
	}

	async function handleLogout() {
		await supabase.auth.signOut();
		// Use full page reload to ensure layout data is cleared
		window.location.href = '/login';
	}
	
	function closeMobileMenu() {
		isMobileMenuOpen = false;
	}
	
	function toggleUserMenu() {
		isUserMenuOpen = !isUserMenuOpen;
	}
	
	// Close user menu when clicking outside
	function handleClickOutside(event: MouseEvent) {
		const target = event.target as HTMLElement;
		if (!target.closest('.user-menu-container')) {
			isUserMenuOpen = false;
		}
	}
	
	onMount(() => {
		document.addEventListener('click', handleClickOutside);
		return () => {
			document.removeEventListener('click', handleClickOutside);
		};
	});
</script>

<div class="min-h-screen bg-[#F8FAFB]">
	<!-- Skip to Content Link (Accessibility) -->
	<a href="#main-content" class="skip-to-content">
		Skip to main content
	</a>

	<!-- Navigation -->
	<nav class="bg-contrast shadow-md">
			<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
				<div class="flex justify-between h-20">
				<div class="flex">
					<div class="flex-shrink-0 flex items-center">
						<a href="/app" class="flex items-center">
							<img src={logoImg} alt="Bernhardt Riley" class="h-16 w-auto" />
						</a>
					</div>
					<!-- Desktop Navigation -->
					<div class="hidden md:ml-8 md:flex md:space-x-1">
						<AppNavLink href="/app" exact>Dashboard</AppNavLink>
						<AppNavLink href="/app/cases">Cases</AppNavLink>
						<AppNavLink href="/app/settings">Settings</AppNavLink>
						<AppNavLink href="/app/help">
							<HelpCircle class="h-4 w-4 mr-1.5" />
							Help
						</AppNavLink>
					</div>
				</div>
				
				<!-- Desktop Right Side -->
				<div class="hidden md:flex md:items-center md:space-x-3">
					<!-- Clio Integration Button -->
					<button
						onclick={() => (showClioModal = !showClioModal)}
						class="inline-flex items-center px-3 py-2 text-sm font-semibold rounded-md transition-colors {clioConnected
							? 'bg-white/20 text-white border border-accent hover:bg-white/25'
							: 'bg-white/10 text-white/90 border border-white/20 hover:bg-white/20'}"
						title={clioConnected ? 'Clio Connected' : 'Clio Integration'}
					>
						<Link2 class="h-4 w-4 mr-2" />
						Clio
						{#if clioConnected}
							<span class="ml-2 inline-block h-2 w-2 rounded-full bg-accent shadow-lg shadow-accent/50"></span>
						{/if}
					</button>

					<!-- User Menu -->
					<div class="relative user-menu-container">
						<button
							onclick={toggleUserMenu}
							class="flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-semibold text-white/90 hover:bg-white/10 hover:text-white transition-colors"
						>
							<User class="h-5 w-5" />
							<span class="hidden lg:block max-w-[150px] truncate">{data.user?.email}</span>
						</button>

						{#if isUserMenuOpen}
							<div class="absolute right-0 mt-2 w-56 rounded-lg shadow-dropdown bg-white ring-1 ring-black ring-opacity-5 z-10">
								<div class="py-1" role="menu">
									<div class="px-4 py-3 border-b border-gray-100">
										<p class="text-sm font-medium text-contrast truncate">{data.user?.email}</p>
									</div>
									<a
										href="/app/settings"
										class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
										role="menuitem"
										onclick={closeMobileMenu}
									>
										<Settings class="h-4 w-4 mr-3 text-gray-400" />
										Settings
									</a>
									<button
										onclick={handleLogout}
										class="w-full flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
										role="menuitem"
									>
										<LogOut class="h-4 w-4 mr-3 text-gray-400" />
										Logout
									</button>
								</div>
							</div>
						{/if}
					</div>
				</div>

				<!-- Mobile Menu Button -->
				<div class="flex items-center md:hidden">
					<button
						onclick={() => (isMobileMenuOpen = !isMobileMenuOpen)}
						class="inline-flex items-center justify-center p-2 rounded-md text-white/90 hover:text-white hover:bg-white/10 transition-colors"
						aria-expanded={isMobileMenuOpen}
					>
						<span class="sr-only">Open main menu</span>
						{#if isMobileMenuOpen}
							<X class="h-6 w-6" />
						{:else}
							<Menu class="h-6 w-6" />
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- Mobile Menu -->
		{#if isMobileMenuOpen}
			<div class="md:hidden border-t border-white/10">
				<div class="pt-2 pb-3 space-y-1 px-2">
					<AppNavLink href="/app" exact class="mobile" onclick={closeMobileMenu}>
						Dashboard
					</AppNavLink>
					<AppNavLink href="/app/cases" class="mobile" onclick={closeMobileMenu}>
						Cases
					</AppNavLink>
					<AppNavLink href="/app/settings" class="mobile" onclick={closeMobileMenu}>
						Settings
					</AppNavLink>
					<AppNavLink href="/app/help" class="mobile flex items-center" onclick={closeMobileMenu}>
						<HelpCircle class="h-5 w-5 mr-3" />
						Help
					</AppNavLink>
				</div>
				<div class="pt-4 pb-3 border-t border-white/10">
					<div class="flex items-center px-5 mb-3">
						<div class="flex-shrink-0">
							<User class="h-8 w-8 text-white/70" />
						</div>
						<div class="ml-3">
							<div class="text-sm font-semibold text-white">{data.user?.email}</div>
						</div>
					</div>
					<div class="space-y-1 px-2">
						<button
							onclick={() => {
								closeMobileMenu();
								showClioModal = true;
							}}
							class="flex items-center w-full px-3 py-2 rounded-md text-base font-semibold text-white/90 hover:bg-white/10 hover:text-white transition-colors"
						>
							<Link2 class="h-5 w-5 mr-3" />
							Clio Integration
							{#if clioConnected}
								<span class="ml-2 inline-block h-2 w-2 rounded-full bg-accent"></span>
							{/if}
						</button>
						<button
							onclick={() => {
								closeMobileMenu();
								handleLogout();
							}}
							class="flex items-center w-full px-3 py-2 rounded-md text-base font-semibold text-white/90 hover:bg-white/10 hover:text-white transition-colors"
						>
							<LogOut class="h-5 w-5 mr-3" />
							Logout
						</button>
					</div>
				</div>
			</div>
		{/if}
	</nav>

	<!-- Profile completeness banner (shows only when incomplete) -->
	<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4">
		<ProfileCompleteBanner {profile} />
	</div>

	<!-- Main Content -->
	<main id="main-content" class="py-8" tabindex="-1">
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			{@render children()}
		</div>
	</main>
</div>

<!-- Clio Integration Modal -->
<Modal bind:open={showClioModal} title="Clio Integration" size="md">
	<ClioConnect />

	<div class="mt-4 text-sm text-gray-500">
		<p>Connect your Clio account to import matter details, documents, communications, and notes across all your cases.</p>
	</div>

	{#snippet footer()}
		<button
			onclick={() => showClioModal = false}
			class="btn btn-primary"
		>
			OK
		</button>
	{/snippet}
</Modal>
