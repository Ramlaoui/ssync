import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Utility function to merge Tailwind classes safely
 * Combines clsx for conditional classes and tailwind-merge to handle conflicts
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Common UI component variant classes
 */
export const variants = {
  button: {
    base: 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
    primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
    secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
    outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
    ghost: 'hover:bg-accent hover:text-accent-foreground',
    link: 'text-primary underline-offset-4 hover:underline',
    size: {
      sm: 'h-8 px-3 text-xs',
      md: 'h-10 px-4 text-sm',
      lg: 'h-12 px-8 text-base',
      icon: 'h-10 w-10'
    }
  },
  card: {
    base: 'rounded-lg border bg-card text-card-foreground shadow-sm',
    interactive: 'transition-all hover:shadow-md hover:-translate-y-0.5',
    padding: {
      sm: 'p-4',
      md: 'p-6',
      lg: 'p-8'
    }
  },
  input: {
    base: 'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'
  },
  badge: {
    base: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
    variant: {
      default: 'border-transparent bg-primary text-primary-foreground',
      secondary: 'border-transparent bg-secondary text-secondary-foreground',
      destructive: 'border-transparent bg-destructive text-destructive-foreground',
      outline: 'border border-input',
      success: 'border-transparent bg-green-100 text-green-800',
      warning: 'border-transparent bg-yellow-100 text-yellow-800',
      info: 'border-transparent bg-blue-100 text-blue-800'
    }
  },
  status: {
    running: 'text-green-600 bg-green-100',
    pending: 'text-yellow-600 bg-yellow-100',
    completed: 'text-blue-600 bg-blue-100',
    failed: 'text-red-600 bg-red-100',
    cancelled: 'text-gray-600 bg-gray-100'
  }
};

/**
 * Helper to build component classes
 */
export function buildClass(
  variant: keyof typeof variants,
  options?: {
    variant?: string;
    size?: string;
    className?: string;
    [key: string]: any;
  }
) {
  const variantConfig = variants[variant];
  const classes = [variantConfig.base];

  if (options?.variant && 'variant' in variantConfig) {
    classes.push(variantConfig.variant[options.variant as keyof typeof variantConfig.variant]);
  }

  if (options?.size && 'size' in variantConfig) {
    classes.push(variantConfig.size[options.size as keyof typeof variantConfig.size]);
  }

  if (options?.className) {
    classes.push(options.className);
  }

  return cn(...classes);
}