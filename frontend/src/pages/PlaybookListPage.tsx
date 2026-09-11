import React, { useState, useMemo, useEffect } from 'react';
import type { Key } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation, useLazyQuery } from '@apollo/client/react';
import { Link, useNavigate } from 'react-router-dom';
import { useGraphQLErrorHandling } from '../utils/errorHandling';
import { usePlaybookMeta } from '../context/PlaybookMetaContext';
import { Table, Tag, Select, Space, Typography, Button, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';

// v2 Abstraction graphs
const GET_ALL_GRAPHS_QUERY = gql`
  query GetAllPlaybookGraphs {
    allPlaybookGraphs {
      id
      title
      status
      updatedAt
      author { username }
      isReadOnly
      ownerOrganizationName
      tags
    }
  }
`;
const ALL_TAGS_QUERY = gql`
  query AllTags { allTags { id name usageCount } }
`;

const CREATE_PLAYBOOK_GRAPH_MUTATION = gql`
  mutation CreatePlaybookGraph($title: String!) {
    createPlaybookGraph(title: $title) {
      graph { id title status updatedAt }
    }
  }
`;

type CreateGraphData = { createPlaybookGraph: { graph: { id: string; title?: string; status?: string; updatedAt?: string } } };

type CreatePlaybookData = { createPlaybook: { playbook: { id: string; title?: string; status?: string; playbookType?: string; updatedAt?: string; author?: { username: string } | null } } };

// Detection playbooks
const CREATE_PLAYBOOK_MUTATION = gql`
  mutation CreatePlaybook($title: String!, $description: String, $playbookType: String) {
    createPlaybook(title: $title, description: $description, playbookType: $playbookType) {
      playbook { id }
    }
  }
`;

// Define the TypeScript types for our data
interface PlaybookGraphRow {
  id: string;
  title: string;
  status: string;
  updatedAt: string;
  author: {
    username: string;
  } | null;
  isReadOnly: boolean;
  ownerOrganizationName: string | null;
}

interface AllPlaybookGraphsData {
  allPlaybookGraphs: PlaybookGraphRow[] | null;
}

// Delete graph mutation
const DELETE_GRAPH_MUTATION = gql`
  mutation DeletePlaybookGraph($graphId: UUID!) {
    deletePlaybookGraph(graphId: $graphId) { ok }
  }
`;

export const PlaybookListPage = () => {
  const { handleError } = useGraphQLErrorHandling('PlaybookListPage');
  const meta = usePlaybookMeta();
  const dynamicStatuses = (meta.data?.statuses && meta.data.statuses.length) ? meta.data.statuses : [
    { value: 'IDEA', label: 'Idea/Hypothesis' },
    { value: 'RESEARCH', label: 'In Research' },
    { value: 'DEVELOPMENT', label: 'In Development' },
    { value: 'REVIEW', label: 'Peer Review' },
    { value: 'APPROVED', label: 'Approved' },
    { value: 'TESTING', label: 'Testing/Validation' },
    { value: 'DEPLOYED', label: 'Deployed' },
    { value: 'TUNING', label: 'Tuning/Maintenance' },
  ];
  const navigate = useNavigate();
  const { data, loading, error } = useQuery<AllPlaybookGraphsData>(GET_ALL_GRAPHS_QUERY, {
    context: { componentName: 'PlaybookListPage' }
  });
  const [createGraph, { loading: creatingGraph }] = useMutation<CreateGraphData>(CREATE_PLAYBOOK_GRAPH_MUTATION);
  const [createPlaybook, { loading: creatingPlaybook }] = useMutation<CreatePlaybookData>(CREATE_PLAYBOOK_MUTATION);
  interface AllTagsData { allTags: { id: string; name: string; usageCount?: number }[] }
  const [loadTags, tagsQuery] = useLazyQuery<AllTagsData>(ALL_TAGS_QUERY);
  useEffect(() => { loadTags(); }, [loadTags]);

  // Listen for external requests (e.g., from Kanban) to create a detection playbook
  useEffect(() => {
    const handler = async (event: Event) => {
      const custom = event as CustomEvent<{ title?: string }>;
      const rawTitle = custom.detail?.title;
      const title = rawTitle || window.prompt('Name your new detection playbook', 'New Detection Playbook');
      if (!title) return;
      try {
        const res = await createPlaybook({
          variables: { title, description: '', playbookType: 'DETECTION' },
          optimisticResponse: {
            createPlaybook: {
              playbook: { id: 'temp-' + Date.now().toString() }
            }
          },
        });
        const id = res.data?.createPlaybook?.playbook?.id as string | undefined;
        if (id) navigate(`/playbooks/detail/${id}`);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('Create playbook failed', e);
      }
    };

    window.addEventListener('hefaistos:createDetectionPlaybook', handler as EventListener);
    return () => {
      window.removeEventListener('hefaistos:createDetectionPlaybook', handler as EventListener);
    };
  }, [createPlaybook, navigate]);
  

  // --- Filter State ---
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [tagFilter, setTagFilter] = useState<string[]>([]);

  // --- Derived Filtered List ---
  const [deleteGraph] = useMutation(DELETE_GRAPH_MUTATION, {
    refetchQueries: [{ query: GET_ALL_GRAPHS_QUERY }],
  });

  const filteredPlaybooks = useMemo(() => {
    const list = data?.allPlaybookGraphs ?? [];
    const statusFiltered = list.filter(playbook => statusFilter === 'ALL' || playbook.status === statusFilter);
    if (!tagFilter.length) return statusFiltered;
    const tagSet = new Set(tagFilter.map(t => t.toLowerCase()));
    return statusFiltered.filter(pb => (pb as any).tags?.some((t: string) => tagSet.has(t.toLowerCase())));
  }, [data, statusFilter, tagFilter]);

  if (loading) return <p>Loading playbooks...</p>;
  if (error) return <p style={{ color: 'red' }}>{handleError(error)}</p>;

  const columns: ColumnsType<PlaybookGraphRow> = [
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      render: (text: string, row: PlaybookGraphRow) => (
        <Space direction="vertical" size={0}>
          <Link to={`/playbooks/${row.id}`}>{text}</Link>
          {/* Removed 'View detection template' link per request */}
        </Space>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, row: PlaybookGraphRow) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/playbooks/${row.id}`)}>Edit</Button>
          <Button danger size="small" onClick={() => {
            if (!window.confirm('Delete this workbench? This cannot be undone.')) return;
            deleteGraph({ variables: { graphId: row.id }, refetchQueries: ['GetAllPlaybookGraphs'] }).catch(e => message.error(e.message));
          }}>Delete</Button>
        </Space>
      )
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          IDEA: 'default',
          RESEARCH: 'gold',
          DEVELOPMENT: 'blue',
          REVIEW: 'purple',
          TESTING: 'volcano',
          DEPLOYED: 'green',
          TUNING: 'orange',
        };
        return <Tag color={colorMap[status] || 'default'}>{status}</Tag>;
      },
      filters: dynamicStatuses.map(o => ({ text: o.label, value: o.value })),
      onFilter: (value: boolean | Key, record: PlaybookGraphRow) => record.status === String(value),
    },
    {
      title: 'Author',
      dataIndex: ['author', 'username'],
      key: 'author',
      render: (_: unknown, row: PlaybookGraphRow) => row.author?.username || 'N/A',
    },
    {
      title: 'Owner',
      dataIndex: 'ownerOrganizationName',
      key: 'owner',
      render: (_: unknown, row: PlaybookGraphRow) =>
        row.isReadOnly ? (
          <span className="px-2 py-1 bg-gray-200 text-gray-700 text-xs font-medium rounded">
            {row.ownerOrganizationName ?? 'Unknown'} (Shared)
          </span>
        ) : (
          <span className="text-gray-500 font-medium">You</span>
        ),
    },
    {
      title: 'Last Updated',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      render: (dt: string) => new Date(dt).toLocaleString(),
      defaultSortOrder: 'descend' as const,
      sorter: (a: PlaybookGraphRow, b: PlaybookGraphRow) => new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime(),
    },
  ];

  return (
    <>
      <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Workbench</Typography.Title>
        <Space>
          <Button
            type="primary"
            loading={creatingPlaybook}
            onClick={async () => {
              const title = window.prompt('Name your new detection playbook', 'New Detection Playbook');
              if (!title) return;
              try {
                const res = await createPlaybook({
                  variables: { title, description: '', playbookType: 'DETECTION' },
                  optimisticResponse: {
                    createPlaybook: {
                      playbook: { id: 'temp-' + Date.now().toString() }
                    }
                  },
                });
                const id = res.data?.createPlaybook?.playbook?.id as string | undefined;
                if (id) navigate(`/playbooks/detail/${id}`);
              } catch (e) {
                // eslint-disable-next-line no-console
                console.error('Create playbook failed', e);
              }
            }}
          >
            + New Detection Playbook
          </Button>
          <Button
            loading={creatingGraph}
            onClick={async () => {
              const title = window.prompt('Name your new abstraction graph', 'New Abstraction Graph');
              if (!title) return;
              try {
                const res = await createGraph({
                  variables: { title },
                  optimisticResponse: {
                    createPlaybookGraph: {
                      graph: {
                        id: 'temp-' + Date.now().toString(),
                        title,
                        status: 'IDEA',
                        updatedAt: new Date().toISOString(),
                      }
                    }
                  },
                  update(cache, result) {
                    const newGraph = result.data?.createPlaybookGraph?.graph;
                    if (!newGraph) return;
                    const existing = cache.readQuery<AllPlaybookGraphsData>({ query: GET_ALL_GRAPHS_QUERY });
                    if (existing?.allPlaybookGraphs) {
                      cache.writeQuery({ query: GET_ALL_GRAPHS_QUERY, data: { allPlaybookGraphs: [newGraph, ...existing.allPlaybookGraphs] } });
                    }
                  }
                });
                const id = res.data?.createPlaybookGraph?.graph?.id;
                if (id) navigate(`/playbooks/${id}`);
              } catch (e) {
                // eslint-disable-next-line no-console
                console.error('Create graph failed', e);
              }
            }}
          >
            + New Workbench
          </Button>
        </Space>
      </Space>

      <Space style={{ margin: '1rem 0' }} wrap>
        <Space>
          <Typography.Text strong>Status:</Typography.Text>
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ minWidth: 200 }}
            options={[{ label: 'All Statuses', value: 'ALL' }, ...dynamicStatuses.map(o => ({ label: o.label, value: o.value }))]}
          />
        </Space>
        <Space>
          <Typography.Text strong>My Tags:</Typography.Text>
          <Select
            mode="multiple"
            value={tagFilter}
            onChange={setTagFilter as any}
            allowClear
            style={{ minWidth: 260 }}
            placeholder="Filter by tags"
            options={[...(tagsQuery.data?.allTags || [])]
              .sort((a: any, b: any) => (b.usageCount || 0) - (a.usageCount || 0))
              .map((t: any) => ({ label: `${t.name} ${t.usageCount ? `(${t.usageCount})` : ''}`.trim(), value: t.name }))}
          />
        </Space>
        <Typography.Text>
          <strong>Showing {filteredPlaybooks.length}</strong> of {data?.allPlaybookGraphs?.length ?? 0} workbenches
        </Typography.Text>
      </Space>

      <Table
        rowKey="id"
        dataSource={filteredPlaybooks}
        columns={columns}
        size="middle"
        pagination={{ pageSize: 20 }}
      />
    </>
  );
};
