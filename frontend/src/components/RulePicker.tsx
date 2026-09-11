import React, { useState, useEffect, useRef, useMemo } from 'react';
import { AutoComplete, Input, Typography, Space, Tag, Empty } from 'antd';
import { SearchOutlined, FileTextOutlined } from '@ant-design/icons';
import { gql } from '@apollo/client';
import { useLazyQuery } from '@apollo/client/react';

const SEARCH_ALL_RULES = gql`
  query SearchAllRules($query: String!, $format: String, $limit: Int) {
    searchAllRules(query: $query, format: $format, limit: $limit) {
      id
      title
      format
      status
      description
      rawContent
      author
    }
  }
`;

interface SearchAllRulesResult {
  searchAllRules: RuleOption[];
}

export interface RuleOption {
  id: string;
  title: string;
  format?: string;
  status?: string;
  description?: string;
  rawContent?: string;
  author?: string;
}

interface RulePickerProps {
  value?: RuleOption | null;
  onChange?: (rule: RuleOption | null) => void;
  onRuleSelected?: (rule: RuleOption) => void;
  placeholder?: string;
  style?: React.CSSProperties;
  formatFilter?: 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER';
}

const formatColors: Record<string, string> = {
  KQL: 'blue',
  EQL: 'gold',
  WAZUH: 'orange',
  SPL: 'cyan',
  AQL: 'magenta',
  OTHER: 'default',
};

const statusColors: Record<string, string> = {
  experimental: 'gold',
  test: 'cyan',
  stable: 'green',
  deprecated: 'red',
};

const RulePicker: React.FC<RulePickerProps> = ({
  value,
  onChange,
  onRuleSelected,
  placeholder = 'Search existing rules...',
  style,
  formatFilter,
}) => {
  const [searchValue, setSearchValue] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [searchRules, { loading, data }] = useLazyQuery<SearchAllRulesResult>(SEARCH_ALL_RULES, {
    fetchPolicy: 'network-only',
  });

  // Build options from query data
  const options = useMemo(() => {
    const results = data?.searchAllRules || [];
    return results.map((rule: RuleOption) => ({
      value: rule.id,
      label: (
        <Space direction="vertical" size={0} style={{ width: '100%' }}>
          <Space>
            <FileTextOutlined />
            <Typography.Text strong style={{ maxWidth: 300 }} ellipsis>
              {rule.title}
            </Typography.Text>
            <Tag color={formatColors[rule.format || 'OTHER']}>{rule.format || 'OTHER'}</Tag>
            {rule.status && (
              <Tag color={statusColors[rule.status.toLowerCase()] || 'default'}>
                {rule.status}
              </Tag>
            )}
          </Space>
          {rule.description && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {rule.description.length > 100 ? rule.description.slice(0, 100) + '...' : rule.description}
            </Typography.Text>
          )}
          {rule.author && (
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              by {rule.author}
            </Typography.Text>
          )}
        </Space>
      ),
      rule: rule,
    }));
  }, [data]);

  // Debounced search using useEffect
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (searchValue.trim().length >= 2) {
      debounceRef.current = setTimeout(() => {
        searchRules({
          variables: {
            query: searchValue,
            format: formatFilter,
            limit: 15,
          },
        });
      }, 300);
    }

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [searchValue, formatFilter, searchRules]);

  const handleSearch = (query: string) => {
    setSearchValue(query);
  };

  const handleSelect = (selectedValue: string, option: any) => {
    const selectedRule = option.rule;
    if (selectedRule) {
      if (onChange) {
        onChange(selectedRule);
      }
      if (onRuleSelected) {
        onRuleSelected(selectedRule);
      }
      setSearchValue(selectedRule.title);
    }
  };

  const handleClear = () => {
    setSearchValue('');
    if (onChange) {
      onChange(null);
    }
  };

  return (
    <AutoComplete
      style={{ width: '100%', ...style }}
      options={options}
      onSearch={handleSearch}
      onSelect={handleSelect}
      value={value ? value.title : searchValue}
      notFoundContent={
        searchValue.length >= 2 && !loading && options.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Typography.Text type="secondary">
                No rules found matching "{searchValue}"
              </Typography.Text>
            }
          />
        ) : null
      }
    >
      <Input
        placeholder={placeholder}
        prefix={<SearchOutlined />}
        allowClear
        onClear={handleClear}
      />
    </AutoComplete>
  );
};

export default RulePicker;
export { RulePicker };
