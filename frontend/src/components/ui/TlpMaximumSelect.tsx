import React from 'react';
import { Select, SelectProps } from 'antd';
import { TLP_OPTIONS, TLP_UNCLEAR_SOURCE_URL, TlpBadge } from './TlpBadge';

export const TlpMaximumSelect: React.FC<SelectProps<string>> = ({ value = 'RED', className = '', ...props }) => {
  const levels = TLP_OPTIONS.filter(option => option.value !== 'UNCLEAR');
  const maximumIndex = levels.findIndex(option => option.value === value);
  const allowed = [...levels.slice(0, maximumIndex + 1).map(option => `TLP:${option.value}`), 'TLP:UNCLEAR'];
  return (
    <div>
      <Select
        aria-label="Required TLP Classification (Maximum)"
        style={{ width: '100%' }}
        {...props}
        className={`tlp-maximum-select ${className}`}
        classNames={{ popup: { root: 'tlp-maximum-select-dropdown' } }}
        value={value}
        options={TLP_OPTIONS.map(option => ({ value: option.value, label: <TlpBadge classification={option.value} className={`tlp-maximum-badge tlp-maximum-badge--${option.value.toLowerCase().replace('+', '-')}`} /> }))}
      />
      <div className="text-xs" style={{ color: 'var(--hef-text-muted)' }}>Permits {allowed.join(', ')}.</div>
      <a href={TLP_UNCLEAR_SOURCE_URL} target="_blank" rel="noopener noreferrer" className="text-xs underline" style={{ color: 'var(--hef-text-link)' }}>
        TLP:UNCLEAR is always included
      </a>
    </div>
  );
};
