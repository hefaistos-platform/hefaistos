import React, { useState, useEffect, useRef, useMemo } from 'react';
import { AutoComplete, Input, Typography, Space, Tag, Button, Empty } from 'antd';
import { SearchOutlined, PlusOutlined, DatabaseOutlined } from '@ant-design/icons';
import { gql } from '@apollo/client';
import { useLazyQuery } from '@apollo/client/react';
import { useNavigate } from 'react-router-dom';

const SEARCH_DATA_SOURCES = gql`
  query SearchDataSources($query: String!, $limit: Int) {
    searchDataSources(query: $query, limit: $limit) {
      id
      name
      platform
      description
    }
  }
`;

interface SearchDataSourcesResult {
  searchDataSources: DataSourceOption[];
}

export interface DataSourceOption {
  id: string;
  name: string;
  platform?: string;
  description?: string;
}

interface DataSourcePickerProps {
  value?: DataSourceOption | null;
  onChange?: (dataSource: DataSourceOption | null) => void;
  placeholder?: string;
  style?: React.CSSProperties;
  allowCreate?: boolean;
}

const DataSourcePicker: React.FC<DataSourcePickerProps> = ({
  value,
  onChange,
  placeholder = 'Search data sources...',
  style,
  allowCreate = true,
}) => {
  const navigate = useNavigate();
  const [searchValue, setSearchValue] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [searchDataSources, { loading, data }] = useLazyQuery<SearchDataSourcesResult>(SEARCH_DATA_SOURCES, {
    fetchPolicy: 'network-only',
  });

  // Build options from query data
  const options = useMemo(() => {
    const results = data?.searchDataSources || [];
    const opts: Array<{ value: string; label: React.ReactNode; dataSource: DataSourceOption | null }> = results.map((ds: DataSourceOption) => ({
      value: ds.id,
      label: (
        <Space direction="vertical" size={0} style={{ width: '100%' }}>
          <Space>
            <DatabaseOutlined />
            <Typography.Text strong>{ds.name}</Typography.Text>
            {ds.platform && <Tag color="blue">{ds.platform}</Tag>}
          </Space>
          {ds.description && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {ds.description.length > 80 ? ds.description.slice(0, 80) + '...' : ds.description}
            </Typography.Text>
          )}
        </Space>
      ),
      dataSource: ds,
    }));

    // Add "Create New" option if allowed and there's a search query
    if (allowCreate && searchValue.trim()) {
      opts.push({
        value: '__create_new__',
        label: (
          <Space>
            <PlusOutlined />
            <Typography.Text type="secondary">
              Create new data source "{searchValue}"
            </Typography.Text>
          </Space>
        ),
        dataSource: null,
      });
    }

    return opts;
  }, [data, searchValue, allowCreate]);

  // Debounced search using useEffect
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (searchValue.trim().length >= 2) {
      debounceRef.current = setTimeout(() => {
        searchDataSources({ variables: { query: searchValue, limit: 10 } });
      }, 300);
    }

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [searchValue, searchDataSources]);

  const handleSearch = (query: string) => {
    setSearchValue(query);
  };

  const handleSelect = (selectedValue: string, option: any) => {
    if (selectedValue === '__create_new__') {
      navigate('/catalog/new', { state: { suggestedName: searchValue } });
      return;
    }

    const selectedDs = option.dataSource;
    if (selectedDs && onChange) {
      onChange(selectedDs);
      setSearchValue(selectedDs.name);
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
      value={value ? value.name : searchValue}
      notFoundContent={
        searchValue.length >= 2 && !loading && options.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" size={4}>
                <Typography.Text type="secondary">No data sources found</Typography.Text>
                {allowCreate && (
                  <Button
                    type="link"
                    icon={<PlusOutlined />}
                    onClick={() => navigate('/catalog/new', { state: { suggestedName: searchValue } })}
                  >
                    Create new data source
                  </Button>
                )}
              </Space>
            }
          />
        ) : null
      }
    >
      <Input
        placeholder={placeholder}
        prefix={<SearchOutlined />}
        suffix={
          value ? (
            <Button type="text" size="small" onClick={handleClear}>
              ×
            </Button>
          ) : null
        }
        allowClear
      />
    </AutoComplete>
  );
};

export default DataSourcePicker;
export { DataSourcePicker };
