import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input: React.FC<InputProps> = ({ className = '', ...props }) => {
  const base = 'w-full border border-hefaistos-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-hefaistos-primary';
  return <input className={`${base} ${className}`} {...props} />;
};
