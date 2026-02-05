<!--
  Button - Reusable button component

  A wrapper component that provides consistent button styling across the application.
  Encapsulates the .btn pattern with variant and size support.

  Features:
  - Consistent button styling (padding, border-radius, transitions)
  - Multiple variants: primary, secondary, danger, ghost, success
  - Three size options: sm, default, lg
  - Built-in disabled state styling
  - Active press effect
  - Full type attribute support

  Props:
  - variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'success' - Visual style (default: 'primary')
  - size?: 'sm' | 'default' | 'lg' - Size variant (default: 'default')
  - type?: 'button' | 'submit' | 'reset' - Button type attribute (default: 'button')
  - disabled?: boolean - Disable button (default: false)
  - class?: string - Additional CSS classes
  - onclick?: (event: MouseEvent) => void - Click handler

  Variants:
  - primary: Teal background, white text (main CTAs)
  - secondary: White background, dark text, border (secondary actions)
  - danger: Red background, white text (destructive actions)
  - ghost: Transparent background, subtle hover (tertiary actions)
  - success: Green background, white text (confirmations)

  Sizes:
  - sm: Compact (px-3 py-1.5 text-xs) - For tight spaces
  - default: Standard (px-4 py-2 text-sm) - Most common use
  - lg: Large (px-5 py-2.5 text-base) - Prominent actions

  Usage:
    <!-- Basic button -->
    <Button>Click Me</Button>

    <!-- Primary CTA -->
    <Button variant="primary" size="lg">Get Started</Button>

    <!-- Secondary action -->
    <Button variant="secondary">Cancel</Button>

    <!-- Destructive action -->
    <Button variant="danger" onclick={handleDelete}>
      Delete Account
    </Button>

    <!-- Submit form -->
    <Button type="submit" variant="primary">
      Save Changes
    </Button>

    <!-- Disabled button -->
    <Button disabled>Unavailable</Button>

    <!-- With icon -->
    <Button variant="primary">
      <Plus class="h-4 w-4 mr-2" />
      New Item
    </Button>

  Examples:
    - Form submission: <Button type="submit" variant="primary">Submit</Button>
    - Modal actions: <Button variant="secondary">Cancel</Button> <Button variant="primary">Confirm</Button>
    - Destructive: <Button variant="danger">Delete</Button>
    - Ghost link-style: <Button variant="ghost" size="sm">Learn more</Button>

  Note: For async operations with loading states, use AsyncButton component instead.
-->
<script lang="ts">
  type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success';
  type Size = 'sm' | 'default' | 'lg';
  type ButtonType = 'button' | 'submit' | 'reset';

  let {
    variant = 'primary',
    size = 'default',
    type = 'button',
    disabled = false,
    class: className = '',
    onclick,
    children,
    ...restProps
  }: {
    variant?: Variant;
    size?: Size;
    type?: ButtonType;
    disabled?: boolean;
    class?: string;
    onclick?: (event: MouseEvent) => void;
    children?: any;
    [key: string]: any;
  } = $props();

  // Variant classes from app.css
  const variantClasses: Record<Variant, string> = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    danger: 'btn-danger',
    ghost: 'btn-ghost',
    success: 'btn-success',
  };

  // Size classes
  const sizeClasses: Record<Size, string> = {
    sm: 'px-3 py-1.5 text-xs',
    default: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-base',
  };

  const buttonClasses = $derived(
    `btn ${variantClasses[variant]} ${sizeClasses[size]} btn-active ${className}`
  );
</script>

<button
  {type}
  {disabled}
  class={buttonClasses}
  {onclick}
  {...restProps}
>
  {@render children?.()}
</button>
