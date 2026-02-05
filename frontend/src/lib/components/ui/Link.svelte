<!--
  Link - Reusable link component with consistent styling

  A wrapper component that provides consistent link styling with proper
  accessibility attributes and external link indicators.

  Features:
  - Consistent styling using design system colors
  - Automatic external link detection
  - External link icon indicator
  - Proper accessibility attributes (rel, target)
  - Multiple visual variants
  - Hover and focus states

  Props:
  - href: string - Link destination (required)
  - variant?: 'default' | 'subtle' | 'contrast' - Visual style (default: 'default')
  - external?: boolean - Force external link behavior
  - showIcon?: boolean - Show external link icon (default: true for external links)
  - class?: string - Additional CSS classes

  Usage:
    Basic link:
      Link with href="/app/cases"

    External link:
      Link with href="https://example.com" (auto-detected)

    Force external behavior:
      Link with href="/path" external=true

    No external icon:
      Link with href="https://example.com" showIcon=false

    Subtle variant:
      Link with variant="subtle" for less prominent links

    Contrast variant:
      Link with variant="contrast" for dark backgrounds

  Examples:
    - Navigation: Link to internal pages with default variant
    - External resources: Link to external sites with icon
    - In-content links: Subtle variant for body text
-->
<script lang="ts">
  import { ExternalLink } from 'lucide-svelte';

  type Variant = 'default' | 'subtle' | 'contrast';

  let {
    href,
    variant = 'default',
    external,
    showIcon,
    class: className = '',
    children,
    ...restProps
  }: {
    href: string;
    variant?: Variant;
    external?: boolean;
    showIcon?: boolean;
    class?: string;
    children?: any;
    [key: string]: any;
  } = $props();

  // Auto-detect external links
  const isExternal = $derived(external || href.startsWith('http') || href.startsWith('//'));

  // Show icon by default for external links unless explicitly disabled
  const shouldShowIcon = $derived(showIcon !== undefined ? showIcon : isExternal);

  // Variant classes
  const variantClasses: Record<Variant, string> = {
    default: 'text-accent-text hover:text-accent',
    subtle: 'text-gray-600 hover:text-gray-900',
    contrast: 'text-white hover:text-accent-light',
  };

  const linkClasses = $derived(
    `inline-flex items-center gap-1 transition-colors underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:rounded ${variantClasses[variant]} ${className}`
  );

  // External link attributes
  const externalAttrs = isExternal
    ? { target: '_blank', rel: 'noopener noreferrer' }
    : {};
</script>

<a
  {href}
  class={linkClasses}
  {...externalAttrs}
  {...restProps}
>
  {@render children?.()}
  {#if shouldShowIcon}
    <ExternalLink class="h-3 w-3 flex-shrink-0" aria-label="(opens in new tab)" />
  {/if}
</a>
