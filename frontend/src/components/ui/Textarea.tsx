import React from 'react';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const Textarea: React.FC<TextareaProps> = ({ className = '', ...props }) => {
  const base = 'w-full border border-hefaistos-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-hefaistos-primary';
  return <textarea className={`${base} ${className}`} {...props} />;
};
