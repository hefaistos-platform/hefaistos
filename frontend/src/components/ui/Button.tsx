import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'golden-orange' | 'light-blue';
}

export const Button: React.FC<ButtonProps> = ({ variant = 'secondary', className = '', children, type = 'button', ...props }) => {
  const base = 'inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  // Use standard Tailwind palette to ensure visibility even without custom theme tokens.
  const variants: Record<string, string> = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'border hover:opacity-95',
    ghost: 'bg-transparent hover:opacity-95',
    danger: 'bg-red-600 text-white hover:bg-red-700',
    'golden-orange': 'bg-amber-500 text-white hover:bg-amber-600 border border-amber-600',
    'light-blue': 'bg-sky-600 text-white hover:bg-sky-700 border border-sky-600',
  };
  const themedStyles: Record<string, React.CSSProperties> = {
    secondary: {
      background: 'var(--hef-bg-subtle)',
      color: 'var(--hef-text-primary)',
      borderColor: 'var(--hef-border)',
    },
    ghost: {
      color: 'var(--hef-text-secondary)',
    },
  };
  return (
    <button
      type={type}
      className={`${base} ${variants[variant]} ${className}`}
      style={themedStyles[variant]}
      {...props}
    >
      {children}
    </button>
  );
};
