import React from 'react';
import { Select, SelectProps } from 'antd';
import { TLP_OPTIONS, TLP_UNCLEAR_SOURCE_URL, TlpBadge } from './TlpBadge';

export const TlpMaximumSelect: React.FC<SelectProps<string>> = ({ value = 'RED', ...props }) => {
  const levels = TLP_OPTIONS.filter(option => option.value !== 'UNCLEAR');
  const maximumIndex = levels.findIndex(option => option.value === value);
  const allowed = [...levels.slice(0, maximumIndex + 1).map(option => `TLP:${option.value}`), 'TLP:UNCLEAR'];
  return (
    <div>
      <Select
        aria-label="Required TLP Classification (Maximum)"
        style={{ width: '100%' }}
        {...props}
        value={value}
        options={levels.map(option => ({ value: option.value, label: <TlpBadge classification={option.value} /> }))}
      />
      <div className="text-xs text-gray-500">Permits {allowed.join(', ')}.</div>
      <a href={TLP_UNCLEAR_SOURCE_URL} target="_blank" rel="noopener noreferrer" className="text-xs text-purple-700 underline">
        TLP:UNCLEAR is always included
      </a>
    </div>
  );
};
