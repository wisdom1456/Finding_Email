<!--
  Skeleton - Loading placeholder component

  Displays animated skeleton placeholders while content is loading,
  providing better perceived performance and user experience.

  Features:
  - Smooth shimmer animation
  - Multiple shape variants (text, circle, rectangle)
  - Responsive sizing
  - Respects reduced motion preferences

  Props:
  - variant?: 'text' | 'circle' | 'rectangle' - Shape of skeleton (default: 'text')
  - width?: string - Custom width (CSS value, e.g., '100%', '200px')
  - height?: string - Custom height (CSS value)
  - class?: string - Additional CSS classes

  Usage:
    Text placeholder (single line):
      Skeleton component with variant="text"

    Circle placeholder (avatar):
      Skeleton with variant="circle", width="48px", height="48px"

    Rectangle placeholder (image):
      Skeleton with variant="rectangle", width="100%", height="200px"

    Custom sizing:
      Skeleton with width="120px" height="20px"

  Examples:
    - Loading profile: Circle skeleton for avatar, text skeletons for name/email
    - Loading cards: Rectangle for image, text lines for title/description
    - Loading lists: Multiple text skeletons stacked vertically
-->
<script lang="ts">
  let {
    variant = 'text',
    width,
    height,
    class: className = '',
  }: {
    variant?: 'text' | 'circle' | 'rectangle';
    width?: string;
    height?: string;
    class?: string;
  } = $props();

  const variantClasses = {
    text: 'h-4 rounded w-full',
    circle: 'rounded-full',
    rectangle: 'rounded-lg w-full h-32',
  };

  const baseClasses = 'skeleton-shimmer bg-gray-200 animate-pulse';
  const classes = `${baseClasses} ${variantClasses[variant]} ${className}`;

  const styles = [
    width ? `width: ${width}` : '',
    height ? `height: ${height}` : '',
  ].filter(Boolean).join('; ');
</script>

<div class={classes} style={styles} role="status" aria-label="Loading..."></div>

<style>
  .skeleton-shimmer {
    background: linear-gradient(
      90deg,
      #f3f4f6 0%,
      #e5e7eb 50%,
      #f3f4f6 100%
    );
    background-size: 200% 100%;
  }

  @keyframes shimmer {
    0% {
      background-position: -200% 0;
    }
    100% {
      background-position: 200% 0;
    }
  }

  .skeleton-shimmer {
    animation: shimmer 2s infinite linear;
  }

  @media (prefers-reduced-motion: reduce) {
    .skeleton-shimmer {
      animation: none;
    }
  }
</style>
