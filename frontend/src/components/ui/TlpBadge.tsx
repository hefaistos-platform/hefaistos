import React from 'react';

export const TLP_UNCLEAR_SOURCE_URL = 'https://tlp-unclear.org/';

export const TLP_OPTIONS = [
  { value: 'UNCLEAR', label: 'TLP:UNCLEAR — Source or sharing model unknown, unclear, or not used (tlp-unclear.org)', color: 'text-purple-700 bg-purple-100' },
  { value: 'CLEAR', label: 'TLP:CLEAR — Public disclosure', color: 'text-gray-700 bg-gray-100' },
  { value: 'GREEN', label: 'TLP:GREEN — Community sharing', color: 'text-green-700 bg-green-100' },
  { value: 'AMBER', label: 'TLP:AMBER — Limited disclosure', color: 'text-amber-700 bg-amber-100' },
  { value: 'AMBER+STRICT', label: 'TLP:AMBER+STRICT — Organization only', color: 'text-orange-700 bg-orange-100' },
  { value: 'RED', label: 'TLP:RED — Personal for named recipients', color: 'text-red-700 bg-red-100' },
];

interface TlpBadgeProps {
  classification?: string | null;
  className?: string;
}

export const TlpBadge: React.FC<TlpBadgeProps> = ({ classification, className = '' }) => {
  const normalized = classification?.trim().toUpperCase().replace(/^TLP:\s*/, '');
  const option = TLP_OPTIONS.find((entry) => entry.value === normalized) || TLP_OPTIONS[0];
  const value = option.value;

  return (
    <span
      title={option.label}
      className={`inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${option.color} ${className}`}
    >
      TLP:{value}
    </span>
  );
};
