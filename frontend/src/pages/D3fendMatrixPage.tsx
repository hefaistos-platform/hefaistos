import React, { useState } from 'react';
import { Card, Table, Tag, Input, Select, Spin, Alert, Typography, Space, Button, Tooltip } from 'antd';
import { SearchOutlined, FilterOutlined, DownloadOutlined } from '@ant-design/icons';
import { useQuery, gql } from '@apollo/client';

const { Title, Text } = Typography;
const { Option } = Select;

// GraphQL query for D3FEND coverage matrix
const D3FEND_COVERAGE_MATRIX = gql`
  query D3fendCoverageMatrix {
    d3fendCoverageMatrix {
      tactic
      techniques {
        technique {
          id
          d3fendId
          name
          definition
        }
        isCovered
        implementingPlaybooks
      }
    }
  }
`;

const D3fendMatrixPage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTactic, setSelectedTactic] = useState<string>('all');
  
  const { loading, error, data, refetch } = useQuery(D3FEND_COVERAGE_MATRIX);

  // Filter techniques based on search and tactic selection
  const getFilteredData = () => {
    if (!data?.d3fendCoverageMatrix) return [];

    let filtered = data.d3fendCoverageMatrix;

    // Filter by tactic
    if (selectedTactic !== 'all') {
      filtered = filtered.filter((item: any) => item.tactic === selectedTactic);
    }

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.map((item: any) => ({
        ...item,
        techniques: item.techniques.filter((tech: any) => 
          tech.technique.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          tech.technique.d3fendId.toLowerCase().includes(searchTerm.toLowerCase())
        )
      })).filter((item: any) => item.techniques.length > 0);
    }

    return filtered;
  };

  const exportToCSV = () => {
    const filteredData = getFilteredData();
    const rows: string[] = ['Tactic,D3FEND ID,Technique Name,Covered,Implementing Playbooks'];
    
    filteredData.forEach((tacticGroup: any) => {
      tacticGroup.techniques.forEach((tech: any) => {
        const covered = tech.isCovered ? 'Yes' : 'No';
        const playbooks = tech.implementingPlaybooks.join('; ');
        rows.push(`${tacticGroup.tactic},${tech.technique.d3fendId},${tech.technique.name},${covered},"${playbooks}"`);
      });
    });

    const csvContent = rows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'd3fend_coverage.csv';
    a.click();
  };

  const getCoverageColor = (isCovered: boolean) => {
    return isCovered ? 'green' : 'default';
  };

  const getCoverageStats = () => {
    if (!data?.d3fendCoverageMatrix) return { total: 0, covered: 0, percentage: 0 };
    
    let total = 0;
    let covered = 0;
    
    data.d3fendCoverageMatrix.forEach((tacticGroup: any) => {
      tacticGroup.techniques.forEach((tech: any) => {
        total++;
        if (tech.isCovered) covered++;
      });
    });
    
    return { total, covered, percentage: total > 0 ? Math.round((covered / total) * 100) : 0 };
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (error) return <Alert message="Error loading D3FEND data" description={error.message} type="error" />;

  const filteredData = getFilteredData();
  const stats = getCoverageStats();
  const tactics = ['all', 'Detect', 'Harden', 'Isolate', 'Deceive', 'Evict', 'Model'];

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>D3FEND Defense Matrix</Title>
      <Text type="secondary">
        Visualize and track D3FEND defensive technique coverage across your deployed playbooks
      </Text>

      {/* Stats Summary */}
      <Card style={{ marginTop: '24px', marginBottom: '24px' }}>
        <Space size="large">
          <div>
            <Text strong style={{ fontSize: '24px', color: '#1890ff' }}>{stats.covered}</Text>
            <Text type="secondary"> / {stats.total} Techniques Covered</Text>
          </div>
          <div>
            <Text strong style={{ fontSize: '24px', color: stats.percentage > 50 ? '#52c41a' : '#faad14' }}>
              {stats.percentage}%
            </Text>
            <Text type="secondary"> Coverage</Text>
          </div>
        </Space>
      </Card>

      {/* Filters */}
      <Card style={{ marginBottom: '24px' }}>
        <Space size="large" style={{ width: '100%' }}>
          <Input
            placeholder="Search techniques..."
            prefix={<SearchOutlined />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ width: '300px' }}
          />
          <Select
            value={selectedTactic}
            onChange={setSelectedTactic}
            style={{ width: '200px' }}
            prefix={<FilterOutlined />}
          >
            {tactics.map(tactic => (
              <Option key={tactic} value={tactic}>
                {tactic === 'all' ? 'All Tactics' : tactic}
              </Option>
            ))}
          </Select>
          <Button icon={<DownloadOutlined />} onClick={exportToCSV}>
            Export CSV
          </Button>
          <Button onClick={() => refetch()}>Refresh</Button>
        </Space>
      </Card>

      {/* Matrix Display */}
      {filteredData.map((tacticGroup: any) => {
        const columns = [
          {
            title: 'D3FEND ID',
            dataIndex: ['technique', 'd3fendId'],
            key: 'd3fendId',
            width: 120,
            render: (text: string) => <Tag color="blue">{text}</Tag>
          },
          {
            title: 'Technique Name',
            dataIndex: ['technique', 'name'],
            key: 'name',
            width: 300,
          },
          {
            title: 'Definition',
            dataIndex: ['technique', 'definition'],
            key: 'definition',
            ellipsis: {
              showTitle: false,
            },
            render: (text: string) => (
              <Tooltip title={text} placement="topLeft" overlayStyle={{ maxWidth: 500 }}>
                <Text type="secondary" style={{ cursor: 'help' }}>
                  {text || 'N/A'}
                </Text>
              </Tooltip>
            )
          },
          {
            title: 'Coverage',
            dataIndex: 'isCovered',
            key: 'isCovered',
            width: 100,
            render: (isCovered: boolean) => (
              <Tag color={getCoverageColor(isCovered)}>
                {isCovered ? 'Covered' : 'Not Covered'}
              </Tag>
            )
          },
          {
            title: 'Implementing Playbooks',
            dataIndex: 'implementingPlaybooks',
            key: 'playbooks',
            width: 250,
            render: (playbooks: string[]) => (
              <>
                {playbooks.length > 0 ? (
                  playbooks.map((pb, idx) => <Tag key={idx}>{pb}</Tag>)
                ) : (
                  <Text type="secondary">None</Text>
                )}
              </>
            )
          }
        ];

        return (
          <Card 
            key={tacticGroup.tactic}
            title={
              <Space>
                <Tag color="purple" style={{ fontSize: '14px', padding: '4px 12px' }}>
                  {tacticGroup.tactic}
                </Tag>
                <Text type="secondary">
                  {tacticGroup.techniques.filter((t: any) => t.isCovered).length} / {tacticGroup.techniques.length} Covered
                </Text>
              </Space>
            }
            style={{ marginBottom: '24px' }}
          >
            <Table
              dataSource={tacticGroup.techniques}
              columns={columns}
              rowKey={(record: any) => record.technique.id}
              pagination={{ pageSize: 10 }}
              size="small"
            />
          </Card>
        );
      })}

      {filteredData.length === 0 && (
        <Alert
          message="No techniques found"
          description="Try adjusting your search or filter criteria"
          type="info"
          showIcon
        />
      )}
    </div>
  );
};

export default D3fendMatrixPage;
