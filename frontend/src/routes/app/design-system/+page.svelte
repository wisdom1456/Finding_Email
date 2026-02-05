<script lang="ts">
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import SkeletonCard from '$lib/components/ui/SkeletonCard.svelte';
	import SkeletonList from '$lib/components/ui/SkeletonList.svelte';
	import Link from '$lib/components/ui/Link.svelte';
	import { Check, X, AlertCircle, Info } from 'lucide-svelte';

	// Demo state
	let sampleText = $state('Sample text input');
	let loading = $state(false);

	const colors = [
		{ name: 'Navy (Primary)', var: '--color-contrast', hex: '#181A31', contrast: '15.8:1' },
		{ name: 'Navy Light', var: '--color-contrast-light', hex: '#39428E', contrast: '5.5:1' },
		{ name: 'Teal (Accent)', var: '--color-accent', hex: '#5AB7A3', contrast: '2.5:1 (UI only)' },
		{ name: 'Teal (Text)', var: '--color-accent-text', hex: '#316660', contrast: '5.2:1 ✅ AA' },
		{ name: 'Teal Hover', var: '--color-accent-hover', hex: '#49998A', contrast: '3.2:1' },
		{ name: 'Teal Light', var: '--color-accent-light', hex: '#E8F5F2', contrast: 'N/A (bg)' },
	];

	const typography = [
		{ tag: 'h1', class: 'text-4xl', size: '2.25rem (36px)', weight: '700', font: 'Raleway' },
		{ tag: 'h2', class: 'text-3xl', size: '1.875rem (30px)', weight: '700', font: 'Raleway' },
		{ tag: 'h3', class: 'text-2xl', size: '1.5rem (24px)', weight: '700', font: 'Raleway' },
		{ tag: 'h4', class: 'text-xl', size: '1.25rem (20px)', weight: '700', font: 'Raleway' },
		{ tag: 'h5', class: 'text-lg', size: '1.125rem (18px)', weight: '700', font: 'Raleway' },
		{ tag: 'h6', class: 'text-base', size: '1rem (16px)', weight: '600', font: 'Raleway' },
		{ tag: 'body', class: 'text-base', size: '1rem (16px)', weight: '400', font: 'Montserrat' },
		{ tag: 'small', class: 'text-sm', size: '0.875rem (14px)', weight: '400', font: 'Montserrat' },
		{ tag: 'tiny', class: 'text-xs', size: '0.75rem (12px)', weight: '400', font: 'Montserrat' },
	];
</script>

<svelte:head>
	<title>Design System | Bernhardt Riley</title>
</svelte:head>

<PageHeader title="Design System" subtitle="Component library and design tokens for the Findings Email Generator" />

<div class="space-y-8">
	<!-- Color Palette -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Color Palette</h2>
		<p class="text-sm text-gray-600 mb-6">
			Brand colors with WCAG AA compliance. Navy + Teal creates a distinctive, professional identity.
		</p>

		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each colors as color}
				<div class="border border-gray-200 rounded-lg overflow-hidden">
					<div
						class="h-24 w-full"
						style="background-color: var({color.var});"
					></div>
					<div class="p-3 bg-white">
						<div class="font-semibold text-sm text-contrast">{color.name}</div>
						<div class="text-xs text-gray-500 mt-1">{color.hex}</div>
						<div class="text-xs text-gray-500">{color.contrast}</div>
						<div class="text-xs font-mono text-gray-400 mt-1">var({color.var})</div>
					</div>
				</div>
			{/each}
		</div>
	</Card>

	<!-- Typography -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Typography</h2>
		<p class="text-sm text-gray-600 mb-6">
			Raleway for headings, Montserrat for body text. Type scale based on 1.25 ratio.
		</p>

		<div class="space-y-4">
			{#each typography as type}
				<div class="flex items-baseline gap-4 border-b border-gray-100 pb-3">
					<div class="w-20 text-xs text-gray-500 font-mono">{type.tag}</div>
					<div class="flex-1">
						{#if type.tag === 'h1'}
							<h1>The quick brown fox jumps</h1>
						{:else if type.tag === 'h2'}
							<h2>The quick brown fox jumps</h2>
						{:else if type.tag === 'h3'}
							<h3>The quick brown fox jumps</h3>
						{:else if type.tag === 'h4'}
							<h4>The quick brown fox jumps</h4>
						{:else if type.tag === 'h5'}
							<h5>The quick brown fox jumps</h5>
						{:else if type.tag === 'h6'}
							<h6>The quick brown fox jumps</h6>
						{:else if type.tag === 'body'}
							<p>The quick brown fox jumps over the lazy dog</p>
						{:else if type.tag === 'small'}
							<p class="text-sm">The quick brown fox jumps over the lazy dog</p>
						{:else if type.tag === 'tiny'}
							<p class="text-xs">The quick brown fox jumps over the lazy dog</p>
						{/if}
					</div>
					<div class="text-xs text-gray-500 text-right">
						<div>{type.size}</div>
						<div class="font-mono">{type.weight} {type.font}</div>
					</div>
				</div>
			{/each}
		</div>
	</Card>

	<!-- Buttons -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Buttons</h2>
		<p class="text-sm text-gray-600 mb-6">
			Five variants with three size options. All buttons include active press effect.
		</p>

		<div class="space-y-6">
			<!-- Primary -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Primary</h3>
				<div class="flex flex-wrap gap-3">
					<Button variant="primary" size="sm">Small</Button>
					<Button variant="primary">Default</Button>
					<Button variant="primary" size="lg">Large</Button>
					<Button variant="primary" disabled>Disabled</Button>
				</div>
			</div>

			<!-- Secondary -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Secondary</h3>
				<div class="flex flex-wrap gap-3">
					<Button variant="secondary" size="sm">Small</Button>
					<Button variant="secondary">Default</Button>
					<Button variant="secondary" size="lg">Large</Button>
					<Button variant="secondary" disabled>Disabled</Button>
				</div>
			</div>

			<!-- Danger -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Danger</h3>
				<div class="flex flex-wrap gap-3">
					<Button variant="danger" size="sm">Small</Button>
					<Button variant="danger">Default</Button>
					<Button variant="danger" size="lg">Large</Button>
					<Button variant="danger" disabled>Disabled</Button>
				</div>
			</div>

			<!-- Ghost -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Ghost</h3>
				<div class="flex flex-wrap gap-3">
					<Button variant="ghost" size="sm">Small</Button>
					<Button variant="ghost">Default</Button>
					<Button variant="ghost" size="lg">Large</Button>
					<Button variant="ghost" disabled>Disabled</Button>
				</div>
			</div>

			<!-- Success -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Success</h3>
				<div class="flex flex-wrap gap-3">
					<Button variant="success" size="sm">Small</Button>
					<Button variant="success">Default</Button>
					<Button variant="success" size="lg">Large</Button>
					<Button variant="success" disabled>Disabled</Button>
				</div>
			</div>

			<!-- Async Button -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Async Button (with loading state)</h3>
				<div class="flex flex-wrap gap-3 items-center">
					<AsyncButton
						variant="primary"
						bind:loading={loading}
						onclick={() => {
							loading = true;
							setTimeout(() => loading = false, 2000);
						}}
					>
						Click to Load
					</AsyncButton>
					{#if loading}
						<span class="text-sm text-gray-500">Loading for 2 seconds...</span>
					{/if}
				</div>
			</div>
		</div>
	</Card>

	<!-- Form Inputs -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Form Inputs</h2>
		<p class="text-sm text-gray-600 mb-6">
			Input component with label, error handling, and full accessibility (WCAG AA).
		</p>

		<div class="space-y-4 max-w-md">
			<Input
				id="demo-text"
				label="Text Input"
				type="text"
				bind:value={sampleText}
				placeholder="Enter some text..."
			/>

			<Input
				id="demo-email"
				label="Email Address"
				type="email"
				value="user@example.com"
				helper="We'll never share your email"
			/>

			<Input
				id="demo-password"
				label="Password"
				type="password"
				value="password123"
				required
			/>

			<Input
				id="demo-error"
				label="With Error"
				type="text"
				value=""
				error="This field is required"
			/>

			<Input
				id="demo-disabled"
				label="Disabled"
				type="text"
				value="Cannot edit"
				disabled
			/>
		</div>
	</Card>

	<!-- Links -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Links</h2>
		<p class="text-sm text-gray-600 mb-6">
			Consistent link styling with automatic external link detection and accessibility.
		</p>

		<div class="space-y-4">
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-2">Default Variant</h3>
				<div class="space-y-2">
					<div>
						<Link href="/app/cases">Internal Link</Link>
					</div>
					<div>
						<Link href="https://example.com">External Link (with icon)</Link>
					</div>
					<div>
						<Link href="https://example.com" showIcon={false}>External Link (no icon)</Link>
					</div>
				</div>
			</div>

			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-2">Subtle Variant</h3>
				<div class="space-y-2">
					<div>
						<Link href="/app/settings" variant="subtle">Subtle Internal Link</Link>
					</div>
					<div>
						<Link href="https://example.com" variant="subtle">Subtle External Link</Link>
					</div>
				</div>
			</div>

			<div class="bg-contrast p-4 rounded-lg">
				<h3 class="text-sm font-semibold text-white mb-2">Contrast Variant (for dark backgrounds)</h3>
				<div class="space-y-2">
					<div>
						<Link href="/app" variant="contrast">Contrast Internal Link</Link>
					</div>
					<div>
						<Link href="https://example.com" variant="contrast">Contrast External Link</Link>
					</div>
				</div>
			</div>
		</div>
	</Card>

	<!-- Badges -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Badges</h2>
		<p class="text-sm text-gray-600 mb-6">
			Status indicators with semantic colors.
		</p>

		<div class="flex flex-wrap gap-3">
			<Badge variant="success">
				<Check class="h-3 w-3 mr-1" />
				Success
			</Badge>
			<Badge variant="error">
				<X class="h-3 w-3 mr-1" />
				Error
			</Badge>
			<Badge variant="warning">
				<AlertCircle class="h-3 w-3 mr-1" />
				Warning
			</Badge>
			<Badge variant="info">
				<Info class="h-3 w-3 mr-1" />
				Info
			</Badge>
			<Badge variant="neutral">Neutral</Badge>
		</div>
	</Card>

	<!-- Loading Spinners -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Loading Spinners</h2>
		<p class="text-sm text-gray-600 mb-6">
			Animated loading indicators with three size options.
		</p>

		<div class="flex flex-wrap items-center gap-8">
			<div>
				<div class="text-xs text-gray-500 mb-2">Small</div>
				<Spinner size="sm" />
			</div>
			<div>
				<div class="text-xs text-gray-500 mb-2">Default</div>
				<Spinner />
			</div>
			<div>
				<div class="text-xs text-gray-500 mb-2">Large</div>
				<Spinner size="lg" />
			</div>
			<div>
				<div class="text-xs text-gray-500 mb-2">With Label</div>
				<Spinner label="Loading..." />
			</div>
		</div>
	</Card>

	<!-- Skeleton Loaders -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Skeleton Loaders</h2>
		<p class="text-sm text-gray-600 mb-6">
			Content placeholders that improve perceived performance during loading states.
			Animated with smooth shimmer effect.
		</p>

		<div class="space-y-6">
			<!-- Basic Skeletons -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Basic Shapes</h3>
				<div class="space-y-3">
					<div>
						<div class="text-xs text-gray-500 mb-1">Text Line</div>
						<Skeleton variant="text" width="200px" />
					</div>
					<div>
						<div class="text-xs text-gray-500 mb-1">Circle (Avatar)</div>
						<Skeleton variant="circle" width="48px" height="48px" />
					</div>
					<div>
						<div class="text-xs text-gray-500 mb-1">Rectangle (Image)</div>
						<Skeleton variant="rectangle" width="300px" height="150px" />
					</div>
				</div>
			</div>

			<!-- Composed Patterns -->
			<div>
				<h3 class="text-sm font-semibold text-gray-700 mb-3">Composed Patterns</h3>
				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					<div>
						<div class="text-xs text-gray-500 mb-2">Card Skeleton</div>
						<SkeletonCard hasImage lines={3} />
					</div>
					<div>
						<div class="text-xs text-gray-500 mb-2">List Skeleton</div>
						<SkeletonList count={3} hasAvatar />
					</div>
				</div>
			</div>
		</div>
	</Card>

	<!-- Cards -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Cards</h2>
		<p class="text-sm text-gray-600 mb-6">
			Container component with optional hover effect. Standard shadow: 0 2px 8px rgba(24, 26, 49, 0.08).
		</p>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
			<Card>
				<h3 class="text-lg font-semibold text-contrast mb-2">Standard Card</h3>
				<p class="text-sm text-gray-600">
					Basic card with default styling. No hover effect.
				</p>
			</Card>

			<Card hover>
				<h3 class="text-lg font-semibold text-contrast mb-2">Hover Card</h3>
				<p class="text-sm text-gray-600">
					Card with hover lift effect. Try hovering over this card.
				</p>
			</Card>
		</div>
	</Card>

	<!-- Spacing & Shadows -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Design Tokens</h2>
		<p class="text-sm text-gray-600 mb-6">
			Core design tokens for spacing, shadows, and borders.
		</p>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
			<!-- Spacing -->
			<div>
				<h3 class="text-base font-semibold text-contrast mb-3">Spacing (8px base)</h3>
				<div class="space-y-2 text-sm">
					<div class="flex items-center gap-3">
						<div class="w-16 h-1 bg-accent"></div>
						<span class="text-gray-600">4px (0.25rem)</span>
					</div>
					<div class="flex items-center gap-3">
						<div class="w-24 h-1 bg-accent"></div>
						<span class="text-gray-600">8px (0.5rem)</span>
					</div>
					<div class="flex items-center gap-3">
						<div class="w-32 h-1 bg-accent"></div>
						<span class="text-gray-600">16px (1rem)</span>
					</div>
					<div class="flex items-center gap-3">
						<div class="w-48 h-1 bg-accent"></div>
						<span class="text-gray-600">24px (1.5rem)</span>
					</div>
				</div>
			</div>

			<!-- Shadows -->
			<div>
				<h3 class="text-base font-semibold text-contrast mb-3">Shadows</h3>
				<div class="space-y-3">
					<div class="p-3 bg-white shadow-sm border border-gray-100">
						<span class="text-xs text-gray-600">shadow-sm</span>
					</div>
					<div class="p-3 bg-white shadow border border-gray-100">
						<span class="text-xs text-gray-600">shadow (default)</span>
					</div>
					<div class="p-3 bg-white shadow-md">
						<span class="text-xs text-gray-600">shadow-md</span>
					</div>
					<div class="p-3 bg-white shadow-lg">
						<span class="text-xs text-gray-600">shadow-lg</span>
					</div>
				</div>
			</div>
		</div>
	</Card>

	<!-- Border Radius -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Border Radius</h2>
		<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
			<div class="text-center">
				<div class="w-20 h-20 mx-auto bg-accent rounded" style="border-radius: 6px;"></div>
				<div class="text-xs text-gray-600 mt-2">6px (buttons)</div>
			</div>
			<div class="text-center">
				<div class="w-20 h-20 mx-auto bg-accent rounded-lg" style="border-radius: 8px;"></div>
				<div class="text-xs text-gray-600 mt-2">8px (cards)</div>
			</div>
			<div class="text-center">
				<div class="w-20 h-20 mx-auto bg-accent rounded-xl" style="border-radius: 12px;"></div>
				<div class="text-xs text-gray-600 mt-2">12px (modals)</div>
			</div>
			<div class="text-center">
				<div class="w-20 h-20 mx-auto bg-accent rounded-full"></div>
				<div class="text-xs text-gray-600 mt-2">9999px (pill)</div>
			</div>
		</div>
	</Card>

	<!-- Component List -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Component Library</h2>
		<p class="text-sm text-gray-600 mb-4">
			Complete UI component toolkit (18 components):
		</p>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Input</strong> - Form input with labels & errors</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Button</strong> - 5 variants, 3 sizes</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>AsyncButton</strong> - With loading states</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Link</strong> - Consistent link styling</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Card</strong> - Container with optional hover</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>NavLink</strong> - Navigation with auto-active</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Modal</strong> - With focus trap</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Badge</strong> - Status indicators</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Spinner</strong> - Loading indicators</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Skeleton</strong> - Content placeholders</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>SkeletonCard</strong> - Card loading pattern</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>SkeletonList</strong> - List loading pattern</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>PageHeader</strong> - Page titles & subtitles</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Tabs</strong> - Tab navigation</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>Toast</strong> - Notifications</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>ConfirmDialog</strong> - Confirmations</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>LoadingOverlay</strong> - Full-page loading</span>
			</div>
			<div class="flex items-center gap-2">
				<Check class="h-4 w-4 text-accent" />
				<span><strong>AccordionItem</strong> - Collapsible sections</span>
			</div>
		</div>
	</Card>

	<!-- Accessibility -->
	<Card>
		<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Accessibility (WCAG 2.1 AA)</h2>
		<p class="text-sm text-gray-600 mb-4">
			All components meet WCAG 2.1 Level AA standards:
		</p>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
			<div class="flex items-start gap-2">
				<Check class="h-4 w-4 text-accent mt-0.5 flex-shrink-0" />
				<span><strong>Color Contrast:</strong> All text meets 4.5:1 minimum</span>
			</div>
			<div class="flex items-start gap-2">
				<Check class="h-4 w-4 text-accent mt-0.5 flex-shrink-0" />
				<span><strong>Keyboard:</strong> All interactive elements accessible</span>
			</div>
			<div class="flex items-start gap-2">
				<Check class="h-4 w-4 text-accent mt-0.5 flex-shrink-0" />
				<span><strong>Focus States:</strong> Consistent 2px teal ring</span>
			</div>
			<div class="flex items-start gap-2">
				<Check class="h-4 w-4 text-accent mt-0.5 flex-shrink-0" />
				<span><strong>Screen Readers:</strong> Comprehensive ARIA attributes</span>
			</div>
			<div class="flex items-start gap-2">
				<Check class="h-4 w-4 text-accent mt-0.5 flex-shrink-0" />
				<span><strong>Modal Focus Trap:</strong> Prevents escape to background</span>
			</div>
			<div class="flex items-start gap-2">
				<Check class="h-4 w-4 text-accent mt-0.5 flex-shrink-0" />
				<span><strong>Skip Link:</strong> Bypass navigation for keyboard users</span>
			</div>
		</div>
	</Card>
</div>
