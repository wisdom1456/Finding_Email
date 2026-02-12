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
