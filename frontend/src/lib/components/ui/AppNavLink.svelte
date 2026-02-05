<!--
  AppNavLink - Navigation link with automatic active state detection

  A navigation link component that automatically highlights based on the current route.
  Provides consistent styling for both desktop and mobile navigation patterns.

  Features:
  - Automatic active state detection via current path
  - Exact matching mode for root routes
  - Separate desktop and mobile styling
  - Icon support via children
  - Accessibility attributes

  Props:
  - href: string (required) - The target route path
  - exact?: boolean - Use exact path matching (default: false)
  - class?: string - Additional CSS classes
  - onclick?: () => void - Click handler (useful for closing mobile menu)
-->
<script lang="ts">
	import { browser } from '$app/environment';

	type NavLinkProps = {
		href: string;
		exact?: boolean;  // Exact match for active state (useful for "/" routes)
		class?: string;
		children?: any;
		onclick?: () => void;
	};

	let {
		href,
		exact = false,
		class: className = '',
		children,
		onclick
	}: NavLinkProps = $props();

	// Get current path safely - only on client side
	let currentPath = $state('');
	let isActive = $state(false);

	// Update active state on client only
	$effect(() => {
		if (browser) {
			currentPath = window.location.pathname;
			isActive = exact
				? currentPath === href
				: currentPath.startsWith(href);
		}
	});

	// Desktop nav classes
	const desktopBaseClasses = 'inline-flex items-center px-4 py-2 text-sm font-semibold transition-colors rounded-md';
	const desktopActiveClasses = 'bg-white/20 text-white border-b-2 border-accent';
	const desktopInactiveClasses = 'text-white/90 hover:bg-white/10 hover:text-white';

	// Mobile nav classes
	const mobileBaseClasses = 'block px-3 py-2 rounded-md text-base font-semibold transition-colors';
	const mobileActiveClasses = 'bg-white/20 text-white border-l-4 border-accent';
	const mobileInactiveClasses = 'text-white/90 hover:bg-white/10 hover:text-white';

	// Determine if we're in mobile or desktop context based on className
	const isMobile = $derived(className.includes('mobile'));

	const linkClasses = $derived(
		`${isMobile ? mobileBaseClasses : desktopBaseClasses} ${
			isActive
				? (isMobile ? mobileActiveClasses : desktopActiveClasses)
				: (isMobile ? mobileInactiveClasses : desktopInactiveClasses)
		} ${className}`
	);
</script>

<a {href} class={linkClasses} {onclick}>
	{@render children?.()}
</a>
