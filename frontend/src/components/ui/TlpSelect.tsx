import React from 'react';
import { Select, SelectProps } from 'antd';
import { TLP_OPTIONS, TLP_UNCLEAR_SOURCE_URL, TlpBadge } from './TlpBadge';

export const TlpSelect: React.FC<SelectProps<string>> = ({ value, ...props }) => (
  <div>
    <Select
      aria-label="TLP Classification"
      style={{ width: '100%' }}
      {...props}
      value={value || 'UNCLEAR'}
      options={TLP_OPTIONS.map((option) => ({
        value: option.value,
        label: <TlpBadge classification={option.value} />,
        description: option.label,
      }))}
      optionRender={(option) => <span style={{ whiteSpace: 'normal' }}>{option.data.description}</span>}
    />
    {(!value || value === 'UNCLEAR') && (
      <a href={TLP_UNCLEAR_SOURCE_URL} target="_blank" rel="noopener noreferrer" className="text-xs text-purple-700 underline">
        About TLP:UNCLEAR
      </a>
    )}
  </div>
);
