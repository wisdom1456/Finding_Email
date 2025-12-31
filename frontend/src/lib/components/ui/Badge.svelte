<!--
  Badge - Reusable status/tag component
  
  Variants:
  - status: ready, processing, error, pending, needs_review
  - semantic: success, warning, error, info, neutral
  - jurisdiction: florida, new-mexico
  
  Sizes: sm (default), xs
-->
<script lang="ts">
  type StatusVariant = 'ready' | 'completed' | 'processing' | 'error' | 'pending' | 'needs_review' | 'skipped' | 'duplicate';
  type SemanticVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'accent';
  type JurisdictionVariant = 'florida' | 'new-mexico';
  type Size = 'xs' | 'sm';

  let {
    variant = 'neutral',
    size = 'sm',
    class: className = '',
    children
  }: {
    variant?: StatusVariant | SemanticVariant | JurisdictionVariant;
    size?: Size;
    class?: string;
    children?: any;
  } = $props();

  // Map variants to Tailwind classes using brand colors
  const variantClasses: Record<string, string> = {
    // Status variants (case/document status)
    ready: 'bg-green-100 text-green-700',
    completed: 'bg-green-100 text-green-700',
    processing: 'bg-contrast-light/10 text-contrast-light',
    error: 'bg-red-100 text-red-700',
    pending: 'bg-gray-100 text-gray-600',
    needs_review: 'bg-amber-100 text-amber-700',
    skipped: 'bg-gray-100 text-gray-500',
    duplicate: 'bg-purple-100 text-purple-700',
    
    // Semantic variants
    success: 'bg-green-100 text-green-700',
    warning: 'bg-amber-100 text-amber-700',
    info: 'bg-contrast-light/10 text-contrast-light',
    neutral: 'bg-gray-100 text-gray-600',
    accent: 'bg-accent/10 text-accent',
    
    // Jurisdiction variants
    florida: 'bg-orange-100 text-orange-800',
    'new-mexico': 'bg-indigo-100 text-indigo-800',
  };

  const sizeClasses: Record<Size, string> = {
    xs: 'px-1.5 py-0.5 text-[10px]',
    sm: 'px-2.5 py-0.5 text-xs',
  };

  const baseClasses = 'inline-flex items-center font-medium rounded-full whitespace-nowrap';
  
  const classes = `${baseClasses} ${sizeClasses[size]} ${variantClasses[variant] || variantClasses.neutral} ${className}`;
</script>

<span class={classes}>
  {@render children?.()}
</span>

