<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { PUBLIC_API_URL } from '$env/static/public';
	import ClioConnect from '$lib/components/ClioConnect.svelte';
	import { clioStore } from '$lib/stores/clioStore';
	import { Menu, X, User, Settings, LogOut, Link2 } from 'lucide-svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: any } = $props();
	
	let showClioModal = $state(false);
	let clioConnected = $derived($clioStore.connected);
	let isMobileMenuOpen = $state(false);
	let isUserMenuOpen = $state(false);
	
	// Determine active route
	let currentPath = $derived($page.url.pathname);
	
	function isActive(path: string): boolean {
		if (path === '/app') {
			return currentPath === '/app';
		}
		return currentPath.startsWith(path);
	}

	// Check Clio connection status on mount
	onMount(async () => {
		await checkClioStatus();
	});

	async function checkClioStatus() {
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) return;

			// Validate the session by getting the user
			const { data: { user }, error } = await supabase.auth.getUser();
			if (error || !user) return;

			const apiUrl = PUBLIC_API_URL.includes('localhost') || PUBLIC_API_URL.includes('127.0.0.1') 
				? PUBLIC_API_URL 
				: '';
			
			const endpoint = apiUrl ? `${apiUrl}/api/clio/status` : '/api/clio/status';

			const response = await fetch(endpoint, {
				headers: { Authorization: `Bearer ${session.access_token}` }
			});

			if (response.ok) {
				const status = await response.json();
				clioStore.setConnected(status.connected, status.clio_user_id, status.expires_at);
			}
		} catch (error) {
			// Silently fail - user can still manually check via modal
			console.log('Could not check Clio status on load:', error);
		}
	}

	async function handleLogout() {
		await supabase.auth.signOut();
		goto('/login');
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

<div class="min-h-screen bg-gray-50">
	<!-- Navigation -->
	<nav class="bg-white shadow-sm">
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			<div class="flex justify-between h-16">
				<div class="flex">
					<div class="flex-shrink-0 flex items-center">
						<a href="/app" class="text-xl font-bold text-gray-900">
							Legal Document Analysis
						</a>
					</div>
					<!-- Desktop Navigation -->
					<div class="hidden md:ml-6 md:flex md:space-x-8">
						<a
							href="/app"
							class="{isActive('/app') && currentPath === '/app'
								? 'border-blue-500 text-gray-900'
								: 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors"
						>
							Dashboard
						</a>
						<a
							href="/app/cases"
							class="{isActive('/app/cases')
								? 'border-blue-500 text-gray-900'
								: 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors"
						>
							Cases
						</a>
						<a
							href="/app/settings"
							class="{isActive('/app/settings')
								? 'border-blue-500 text-gray-900'
								: 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors"
						>
							Settings
						</a>
					</div>
				</div>
				
				<!-- Desktop Right Side -->
				<div class="hidden md:flex md:items-center md:space-x-4">
					<!-- Clio Integration Button -->
					<button
						onclick={() => (showClioModal = !showClioModal)}
						class="inline-flex items-center px-3 py-2 border text-sm leading-4 font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors {clioConnected
							? 'border-green-500 text-green-700 bg-green-50 hover:bg-green-100'
							: 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'}"
						title={clioConnected ? 'Clio Connected' : 'Clio Integration'}
					>
						<Link2 class="h-4 w-4 mr-2" />
						Clio
						{#if clioConnected}
							<span class="ml-2 inline-block h-2 w-2 rounded-full bg-green-500"></span>
						{/if}
					</button>

					<!-- User Menu -->
					<div class="relative user-menu-container">
						<button
							onclick={toggleUserMenu}
							class="flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
						>
							<User class="h-5 w-5" />
							<span class="hidden lg:block">{data.user?.email}</span>
						</button>

						{#if isUserMenuOpen}
							<div class="absolute right-0 mt-2 w-56 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 z-10">
								<div class="py-1" role="menu">
									<div class="px-4 py-2 text-sm text-gray-700 border-b border-gray-100">
										<p class="font-medium truncate">{data.user?.email}</p>
									</div>
									<a
										href="/app/settings"
										class="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
										role="menuitem"
										onclick={closeMobileMenu}
									>
										<Settings class="h-4 w-4 mr-3" />
										Settings
									</a>
									<button
										onclick={handleLogout}
										class="w-full flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
										role="menuitem"
									>
										<LogOut class="h-4 w-4 mr-3" />
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
						class="inline-flex items-center justify-center p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
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
			<div class="md:hidden border-t border-gray-200">
				<div class="pt-2 pb-3 space-y-1">
					<a
						href="/app"
						onclick={closeMobileMenu}
						class="{isActive('/app') && currentPath === '/app'
							? 'bg-blue-50 border-blue-500 text-blue-700'
							: 'border-transparent text-gray-600 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-800'} block pl-3 pr-4 py-2 border-l-4 text-base font-medium transition-colors"
					>
						Dashboard
					</a>
					<a
						href="/app/cases"
						onclick={closeMobileMenu}
						class="{isActive('/app/cases')
							? 'bg-blue-50 border-blue-500 text-blue-700'
							: 'border-transparent text-gray-600 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-800'} block pl-3 pr-4 py-2 border-l-4 text-base font-medium transition-colors"
					>
						Cases
					</a>
					<a
						href="/app/settings"
						onclick={closeMobileMenu}
						class="{isActive('/app/settings')
							? 'bg-blue-50 border-blue-500 text-blue-700'
							: 'border-transparent text-gray-600 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-800'} block pl-3 pr-4 py-2 border-l-4 text-base font-medium transition-colors"
					>
						Settings
					</a>
				</div>
				<div class="pt-4 pb-3 border-t border-gray-200">
					<div class="flex items-center px-4 mb-3">
						<div class="flex-shrink-0">
							<User class="h-8 w-8 text-gray-400" />
						</div>
						<div class="ml-3">
							<div class="text-sm font-medium text-gray-800">{data.user?.email}</div>
						</div>
					</div>
					<div class="space-y-1">
						<button
							onclick={() => {
								closeMobileMenu();
								showClioModal = true;
							}}
							class="flex items-center w-full px-4 py-2 text-base font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 transition-colors"
						>
							<Link2 class="h-5 w-5 mr-3" />
							Clio Integration
							{#if clioConnected}
								<span class="ml-2 inline-block h-2 w-2 rounded-full bg-green-500"></span>
							{/if}
						</button>
						<button
							onclick={() => {
								closeMobileMenu();
								handleLogout();
							}}
							class="flex items-center w-full px-4 py-2 text-base font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 transition-colors"
						>
							<LogOut class="h-5 w-5 mr-3" />
							Logout
						</button>
					</div>
				</div>
			</div>
		{/if}
	</nav>

	<!-- Main Content -->
	<main class="py-10">
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			{@render children()}
		</div>
	</main>
</div>

<!-- Clio Integration Modal -->
{#if showClioModal}
	<div 
		class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50" 
		role="button"
		tabindex="0"
		onclick={() => showClioModal = false}
		onkeydown={(e) => { if (e.key === 'Escape') showClioModal = false; }}
		aria-label="Close modal"
	>
		<div 
			class="bg-white rounded-lg shadow-xl max-w-md w-full p-6" 
			role="dialog"
			aria-modal="true"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="flex justify-between items-center mb-4">
				<h3 class="text-lg font-medium text-gray-900">Clio Integration</h3>
				<button
					onclick={() => showClioModal = false}
					class="text-gray-400 hover:text-gray-500"
					aria-label="Close"
				>
					<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			
			<ClioConnect />
			
			<div class="mt-4 text-sm text-gray-500">
				<p>Connect your Clio account to import matter details, documents, communications, and notes across all your cases.</p>
			</div>
			
			<!-- OK Button -->
			<div class="mt-6 flex justify-end">
				<button
					onclick={() => showClioModal = false}
					class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
				>
					OK
				</button>
			</div>
		</div>
	</div>
{/if}

