import React from 'react';

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const Select: React.FC<SelectProps> = ({ className = '', children, ...props }) => {
  const base = 'w-full border border-hefaistos-border rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-hefaistos-primary';
  return (
    <select className={`${base} ${className}`} {...props}>
      {children}
    </select>
  );
};
