<!--
  SkeletonCard - Loading placeholder for card content

  Pre-composed skeleton pattern for loading card-based content.
  Use this instead of building your own card skeleton from scratch.

  Props:
  - hasImage?: boolean - Include image placeholder (default: false)
  - lines?: number - Number of text lines (default: 3)
  - class?: string - Additional CSS classes

  Usage:
    Basic card loading:
      SkeletonCard with default props

    With image:
      SkeletonCard with hasImage=true

    Custom line count:
      SkeletonCard with lines=5
-->
<script lang="ts">
  import Skeleton from './Skeleton.svelte';
  import Card from './Card.svelte';

  let {
    hasImage = false,
    lines = 3,
    class: className = '',
  }: {
    hasImage?: boolean;
    lines?: number;
    class?: string;
  } = $props();
</script>

<Card class={className}>
  {#if hasImage}
    <Skeleton variant="rectangle" height="160px" class="mb-4" />
  {/if}

  <Skeleton width="60%" height="24px" class="mb-3" />

  {#each Array(lines) as _, i}
    <Skeleton
      width={i === lines - 1 ? '80%' : '100%'}
      height="16px"
      class="mb-2"
    />
  {/each}

  <div class="flex gap-2 mt-4">
    <Skeleton width="80px" height="32px" />
    <Skeleton width="80px" height="32px" />
  </div>
</Card>
