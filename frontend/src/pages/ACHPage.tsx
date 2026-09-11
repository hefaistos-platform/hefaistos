import React, { useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Link } from 'react-router-dom';
import { Card, Button, Input, Form, Typography, Select, Space, Table, Tag, message, Popconfirm } from 'antd';
import { markdownToPlainText } from '../components/MarkdownRenderer';

const { Title, Text } = Typography;
const { TextArea } = Input;
const FILTER_OPTIONS = ['RESEARCH', 'FINISHED'];

interface ACHAnalysisListItem {
  id: string;
  title: string;
  description: string;
  status: 'RESEARCH' | 'FINISHED';
  updatedAt: string;
  owner: { id: string; username: string };
}

interface ACHTemplateListItem {
  id: string;
  title: string;
  description: string;
}

interface GetACHDataResponse {
  achAnalyses: ACHAnalysisListItem[];
  achTemplates: ACHTemplateListItem[];
  me: { id: string; username: string } | null;
}

interface CreateACHAnalysisResponse {
  createAchAnalysis: {
    analysis: {
      id: string;
      title: string;
    };
  };
}

const GET_ACH_DATA = gql`
  query GetACHData {
    achAnalyses {
      id
      title
      description
      status
      updatedAt
      owner { id username }
    }
    achTemplates {
      id
      title
      description
    }
    me { id username }
  }
`;

const CREATE_ACH_ANALYSIS = gql`
  mutation CreateACHAnalysis($title: String!, $description: String) {
    createAchAnalysis(title: $title, description: $description) {
      analysis {
        id
        title
      }
    }
  }
`;

const APPLY_TEMPLATE = gql`
  mutation ApplyACHTemplate($analysisId: UUID!, $templateId: ID!) {
    applyAchTemplate(analysisId: $analysisId, templateId: $templateId) {
      analysis {
        id
      }
    }
  }
`;

const UPDATE_ACH_STATUS = gql`
  mutation UpdateAchStatus($analysisId: UUID!, $status: String!) {
    updateAchStatus(analysisId: $analysisId, status: $status) {
      analysis { id status updatedAt }
    }
  }
`;

const DELETE_ACH_ANALYSIS = gql`
  mutation DeleteAchAnalysis($analysisId: UUID!) {
    deleteAchAnalysis(analysisId: $analysisId) { ok }
  }
`;

type ACHPageProps = {
  embedded?: boolean;
};

export const ACHPage: React.FC<ACHPageProps> = ({ embedded = false }) => {
  const { data, loading, error, refetch } = useQuery<GetACHDataResponse>(GET_ACH_DATA, { fetchPolicy: 'network-only' });
  const [createAnalysis] = useMutation<CreateACHAnalysisResponse>(CREATE_ACH_ANALYSIS);
  const [applyTemplate] = useMutation(APPLY_TEMPLATE);
  const [updateStatus] = useMutation(UPDATE_ACH_STATUS);
  const [deleteAnalysis] = useMutation(DELETE_ACH_ANALYSIS);
  
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [isCreating, setIsCreating] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [authorFilter, setAuthorFilter] = useState<string | null>(null);
  const [searchText, setSearchText] = useState('');

  const handleStatusChange = async (analysisId: string, status: 'RESEARCH' | 'FINISHED') => {
    try {
      await updateStatus({ variables: { analysisId, status }, refetchQueries: [{ query: GET_ACH_DATA }] });
      message.success('Status updated');
    } catch (err: any) {
      console.error(err);
      message.error(err?.message || 'Failed to update status');
    }
  };

  const filteredAnalyses = useMemo(() => {
    let result = data?.achAnalyses || [];
    if (statusFilter) {
      result = result.filter(a => a.status === statusFilter);
    }
    if (authorFilter) {
      result = result.filter(a => a.owner?.username === authorFilter);
    }
    if (searchText) {
      const lower = searchText.toLowerCase();
      result = result.filter(a =>
        a.title.toLowerCase().includes(lower) ||
        (a.description && a.description.toLowerCase().includes(lower))
      );
    }
    return result;
  }, [data?.achAnalyses, statusFilter, authorFilter, searchText]);

  const statusOptions = useMemo(() => [
    { label: 'All Statuses', value: null },
    ...FILTER_OPTIONS.map(s => ({ 
      label: s === 'FINISHED' ? 'Finished' : 'Research', 
      value: s 
    }))
  ], []);

  const authorOptions = useMemo(() => {
    const authors = new Set<string>();
    (data?.achAnalyses || []).forEach(a => {
      if (a.owner?.username) authors.add(a.owner.username);
    });
    return [
      { label: 'All Authors', value: null },
      ...Array.from(authors).sort().map(a => ({ label: a, value: a }))
    ];
  }, [data?.achAnalyses]);

  const statusTag = (status: ACHAnalysisListItem['status']) => {
    const color = status === 'FINISHED' ? 'green' : 'blue';
    const label = status === 'FINISHED' ? 'Finished' : 'Research';
    return <Tag color={color}>{label}</Tag>;
  };

  const columns = useMemo(() => {
    const currentUserId = data?.me?.id;
    return [
      {
        title: 'Title',
        dataIndex: 'title',
        key: 'title',
        render: (_: any, row: ACHAnalysisListItem) => (
          <Space direction="vertical" size={0}>
            <Link to={`/tools/ach/${row.id}`}>{row.title}</Link>
            {row.description && <Text type="secondary">{markdownToPlainText(row.description)}</Text>}
          </Space>
        )
      },
      {
        title: 'Actions',
        key: 'actions',
        render: (_: any, row: ACHAnalysisListItem) => {
          const isOwner = currentUserId && row.owner?.id === currentUserId;
          if (!isOwner) return null;
          const nextStatus = row.status === 'FINISHED' ? 'RESEARCH' : 'FINISHED';
          const btnLabel = row.status === 'FINISHED' ? 'Mark Research' : 'Mark Finished';
          return (
            <Space>
              <Button size="small" onClick={() => handleStatusChange(row.id, nextStatus)}>{btnLabel}</Button>
              <Link to={`/tools/ach/${row.id}`}><Button size="small" type="primary">Open</Button></Link>
              <Popconfirm
                title="Delete analysis?"
                description="This will permanently delete this ACH matrix."
                okText="Delete"
                okButtonProps={{ danger: true }}
                cancelText="Cancel"
                onConfirm={async () => {
                  try {
                    await deleteAnalysis({ 
                      variables: { analysisId: row.id },
                      update: (cache) => {
                        try {
                          const prev = cache.readQuery<GetACHDataResponse>({ query: GET_ACH_DATA });
                          if (prev) {
                            cache.writeQuery<GetACHDataResponse>({ 
                              query: GET_ACH_DATA, 
                              data: { 
                                ...prev,
                                achAnalyses: prev.achAnalyses.filter(a => a.id !== row.id)
                              }
                            });
                          }
                        } catch {}
                      }
                    });
                    message.success('Analysis deleted');
                  } catch (err: any) {
                    console.error(err);
                    message.error(err?.message || 'Failed to delete');
                  }
                }}
              >
                <Button size="small" danger>Delete</Button>
              </Popconfirm>
            </Space>
          );
        }
      },
      {
        title: 'Status',
        dataIndex: 'status',
        key: 'status',
        render: (status: ACHAnalysisListItem['status']) => statusTag(status)
      },
      {
        title: 'Author',
        key: 'author',
        render: (_: any, row: ACHAnalysisListItem) => row.owner?.username || 'N/A'
      },
      {
        title: 'Owner',
        key: 'owner',
        render: (_: any, row: ACHAnalysisListItem) => row.owner?.username ? (row.owner.username === data?.me?.username ? 'You' : row.owner.username) : 'N/A'
      },
      {
        title: 'Last Updated',
        dataIndex: 'updatedAt',
        key: 'updatedAt',
        render: (dt: string) => new Date(dt).toLocaleString()
      }
    ];
  }, [data?.me?.id, data?.me?.username]);

  const handleCreate = async () => {
    try {
      const res = await createAnalysis({ variables: { title: newTitle, description: newDesc } });
      const analysisId = res.data?.createAchAnalysis.analysis.id;

      if (selectedTemplate && analysisId) {
        await applyTemplate({ variables: { analysisId, templateId: selectedTemplate } });
      }

      setNewTitle('');
      setNewDesc('');
      setSelectedTemplate('');
      setIsCreating(false);
      refetch();
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) return <div style={{ padding: 24 }}>Loading...</div>;
  if (error) return <div style={{ padding: 24 }}><Text type="danger">Error: {error.message}</Text></div>;

  const containerStyle = embedded ? { padding: 0 } : { padding: 24 };

  const tableNode = (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Input.Search
          placeholder="Search by title or description..."
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          onSearch={setSearchText}
          allowClear
          style={{ minWidth: 260 }}
        />
        <Space>
          <Typography.Text strong>Status:</Typography.Text>
          <Select value={statusFilter} onChange={setStatusFilter} options={statusOptions} style={{ minWidth: 200 }} allowClear />
        </Space>
        <Space>
          <Typography.Text strong>Author:</Typography.Text>
          <Select value={authorFilter} onChange={setAuthorFilter} options={authorOptions} style={{ minWidth: 200 }} allowClear />
        </Space>
      </Space>
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={filteredAnalyses}
        columns={columns}
        pagination={{ pageSize: 15 }}
        locale={{ emptyText: 'No analyses found. Create one to get started.' }}
      />
    </Space>
  );

  return (
    <div style={containerStyle}>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>Analysis of Competing Hypotheses (ACH)</Title>
        <Button 
          type="primary"
          onClick={() => setIsCreating(!isCreating)}
        >
          {isCreating ? 'Cancel' : 'New Analysis'}
        </Button>
      </Space>

      {isCreating && (
        <Card style={{ marginBottom: 16 }}>
          <Title level={4}>Create New Analysis</Title>
          <Form onFinish={handleCreate} layout="vertical">
            <Form.Item label="Title" required>
              <Input 
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Enter analysis title"
                required
              />
            </Form.Item>
            <Form.Item label="Description">
              <TextArea 
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Enter description (optional)"
                rows={3}
              />
            </Form.Item>
            <Form.Item label="Use Template (Optional)">
              <Select
                value={selectedTemplate || undefined}
                onChange={(value) => setSelectedTemplate(value || '')}
                placeholder="-- None --"
                allowClear
              >
                {data?.achTemplates.map((t) => (
                  <Select.Option key={t.id} value={t.id}>{t.title}</Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                Create
              </Button>
            </Form.Item>
          </Form>
        </Card>
      )}

      {embedded ? tableNode : <Card>{tableNode}</Card>}
    </div>
  );
};
