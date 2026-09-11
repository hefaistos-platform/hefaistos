import React from 'react';

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export const Checkbox: React.FC<CheckboxProps> = ({ label, className = '', ...props }) => {
  return (
    <label className="flex items-center space-x-2 cursor-pointer">
      <input
        type="checkbox"
        className="w-5 h-5 bg-white border-2 rounded-sm text-hefaistos-primary border-hefaistos-border focus:ring-hefaistos-primary focus:ring-opacity-50"
        {...props}
      />
      <span className="text-sm font-medium text-hefaistos-foreground">{label}</span>
    </label>
  );
};