import React, { useMemo, useState, Suspense, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Tabs, Table, Tag, Space, Typography, Button, Select, Input, message, Dropdown } from 'antd';
import { UploadOutlined, DownOutlined, FileAddOutlined, GithubOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useGraphQLErrorHandling } from '../utils/errorHandling';
import ImportWorkbenchModal from '../components/playbook/ImportWorkbenchModal';
import ImportFromHefModal from '../components/playbook/ImportFromHefModal';
import { MaieuticEngineModal } from '../components/maieutic/MaieuticEngineModal';
import { applyMaieuticToWorkbench } from '../utils/maieuticMapping';
import { MaieuticOutput, MaieuticImportSelections } from '../types/maieutic';
import { Button as CustomButton } from '../components/ui/Button';
import { PixelIcon } from '../components/ui/PixelIcon';

const AchPageLazy = React.lazy(() => import('./ACHPage').then(m => ({ default: m.ACHPage })));
const AdvopsPageLazy = React.lazy(() => import('./ADVOPSPage').then(m => ({ default: m.ADVOPSPage ?? m.default })));
const MveWorkbenchTabLazy = React.lazy(() => import('../components/mve/MveWorkbenchTab'));

const GET_ALL_GRAPHS_QUERY = gql`
  query GetAllPlaybookGraphs {
    allPlaybookGraphs {
      id
      title
      status
      updatedAt
      tags
      author { id username }
      mitreTechnique { id techniqueId name }
      isReadOnly
      ownerOrganizationName
    }
    me { id username }
  }
`;

const CREATE_PLAYBOOK_GRAPH_MUTATION = gql`
  mutation CreatePlaybookGraph($title: String!) {
    createPlaybookGraph(title: $title) {
      graph { id title status updatedAt }
    }
  }
`;

const UPDATE_PLAYBOOK_DETAILS_MUTATION = gql`
  mutation UpdatePlaybookDetails(
    $graphId: UUID!,
    $goal: String,
    $technicalContext: String,
    $blindSpots: String,
    $triageGuidance: String,
    $falsePositives: String,
    $responsePlaybook: String,
    $detectionRule: String,
    $testScenario: String,
    $testExpectedOutput: String,
    $alertTrigger: String,
    $defaultSeverity: String,
    $enrichmentSteps: JSONString,
    $containmentSteps: JSONString,
    $notificationSteps: JSONString,
    $downstreamCorrelationRequirements: JSONString,
    $robustnessLevel: Int,
    $dataSourceMaturity: String,
    $conversationHistory: JSONString
  ) {
    updatePlaybookDetails(
      graphId: $graphId,
      goal: $goal,
      technicalContext: $technicalContext,
      blindSpots: $blindSpots,
      triageGuidance: $triageGuidance,
      falsePositives: $falsePositives,
      responsePlaybook: $responsePlaybook,
      detectionRule: $detectionRule,
      testScenario: $testScenario,
      testExpectedOutput: $testExpectedOutput,
      alertTrigger: $alertTrigger,
      defaultSeverity: $defaultSeverity,
      enrichmentSteps: $enrichmentSteps,
      containmentSteps: $containmentSteps,
      notificationSteps: $notificationSteps,
      downstreamCorrelationRequirements: $downstreamCorrelationRequirements,
      robustnessLevel: $robustnessLevel,
      dataSourceMaturity: $dataSourceMaturity,
      conversationHistory: $conversationHistory
    ) {
      graph { id }
    }
  }
`;

const DELETE_GRAPH_MUTATION = gql`
  mutation DeletePlaybookGraph($graphId: UUID!) {
    deletePlaybookGraph(graphId: $graphId) { ok }
  }
`;

interface GraphRow {
  id: string;
  title: string;
  status: string;
  updatedAt: string;
  tags?: string[];
  author: { id: string; username: string } | null;
  mitreTechnique: { id: string; techniqueId: string; name: string } | null;
  isReadOnly: boolean;
  ownerOrganizationName: string | null;
}

interface MeData {
  id: string;
  username: string;
}

const WORKBENCH_STATUS_OPTIONS = [
  { label: 'All Statuses', value: 'ALL' },
  { label: 'Idea/Hypothesis', value: 'IDEA' },
  { label: 'In Research', value: 'RESEARCH' },
  { label: 'In Development', value: 'DEVELOPMENT' },
  { label: 'Peer Review', value: 'REVIEW' },
  { label: 'Testing/Validation', value: 'TESTING' },
  { label: 'Deployed', value: 'DEPLOYED' },
  { label: 'Tuning/Maintenance', value: 'TUNING' },
];

const SORT_OPTIONS = [
  { label: 'Date (Latest First)', value: 'date_desc' },
  { label: 'Date (Oldest First)', value: 'date_asc' },
  { label: 'Name (A–Z)', value: 'name_asc' },
  { label: 'Name (Z–A)', value: 'name_desc' },
  { label: 'Detected TTP', value: 'ttp' },
];

export const PlaybooksHubPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { handleError } = useGraphQLErrorHandling('PlaybooksHubPage');
  const { data: graphData, loading: loadingGraphs, error: errorGraphs, refetch: refetchGraphs } = useQuery<{ allPlaybookGraphs: GraphRow[] | null; me: MeData | null }>(GET_ALL_GRAPHS_QUERY);
  const currentUserId = graphData?.me?.id;
  const [createGraph, { loading: creatingGraph }] = useMutation<{ createPlaybookGraph: { graph: GraphRow } }, { title: string }>(CREATE_PLAYBOOK_GRAPH_MUTATION);
  const [deleteGraph] = useMutation(DELETE_GRAPH_MUTATION);
  const [updatePlaybookDetails] = useMutation(UPDATE_PLAYBOOK_DETAILS_MUTATION);

  const [statusFilterGraphs, setStatusFilterGraphs] = useState('ALL');
  const [authorFilterGraphs, setAuthorFilterGraphs] = useState<string | null>(null);
  const [techniqueFilterGraphs, setTechniqueFilterGraphs] = useState<string | null>(null);
  const [searchTextGraphs, setSearchTextGraphs] = useState('');
  const [sortByGraphs, setSortByGraphs] = useState('date_desc');
  const [activeTab, setActiveTab] = useState(() => {
    const tab = searchParams.get('tab');
    return tab === 'ach' ? 'ach' : tab === 'advops' ? 'advops' : tab === 'mve' ? 'mve' : 'graphs';
  });
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [importHefModalVisible, setImportHefModalVisible] = useState(false);
  const [maieuticModalVisible, setMaieuticModalVisible] = useState(false);
  const [creatingFromMaieutic, setCreatingFromMaieutic] = useState(false);

  // Handle successful import - refresh the workbenches list
  const handleImportSuccess = () => {
    refetchGraphs();
  };

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && tab !== activeTab) {
      setActiveTab(tab === 'ach' ? 'ach' : tab === 'advops' ? 'advops' : tab === 'mve' ? 'mve' : 'graphs');
    }
  }, [searchParams, activeTab]);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    const next = new URLSearchParams(searchParams);
    next.set('tab', key);
    setSearchParams(next, { replace: true });
  };

  const filteredGraphs = useMemo(() => {
    let result = [...(graphData?.allPlaybookGraphs || [])];
    if (statusFilterGraphs !== 'ALL') {
      result = result.filter((g: GraphRow) => g.status === statusFilterGraphs);
    }
    if (authorFilterGraphs) {
      result = result.filter((g: GraphRow) => g.author?.username === authorFilterGraphs);
    }
    if (techniqueFilterGraphs) {
      result = result.filter((g: GraphRow) => g.mitreTechnique?.techniqueId === techniqueFilterGraphs);
    }
    if (searchTextGraphs) {
      const lower = searchTextGraphs.toLowerCase();
      result = result.filter((g: GraphRow) =>
        g.title.toLowerCase().includes(lower) ||
        (g.tags && g.tags.some(t => t.toLowerCase().includes(lower)))
      );
    }
    switch (sortByGraphs) {
      case 'date_desc':
        result.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
        break;
      case 'date_asc':
        result.sort((a, b) => new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime());
        break;
      case 'name_asc':
        result.sort((a, b) => a.title.localeCompare(b.title));
        break;
      case 'name_desc':
        result.sort((a, b) => b.title.localeCompare(a.title));
        break;
      case 'ttp':
        result.sort((a, b) => {
          const ta = a.mitreTechnique?.techniqueId || '';
          const tb = b.mitreTechnique?.techniqueId || '';
          return ta.localeCompare(tb);
        });
        break;
      default:
        break;
    }
    return result;
  }, [graphData, statusFilterGraphs, authorFilterGraphs, techniqueFilterGraphs, searchTextGraphs, sortByGraphs]);

  const authorOptions = useMemo(() => {
    const authors = new Set<string>();
    (graphData?.allPlaybookGraphs || []).forEach((g: GraphRow) => {
      if (g.author?.username) authors.add(g.author.username);
    });
    return [{ label: 'All Authors', value: null }, ...Array.from(authors).sort().map(a => ({ label: a, value: a }))];
  }, [graphData]);

  const techniqueOptions = useMemo(() => {
    const techniques = new Map<string, string>();
    (graphData?.allPlaybookGraphs || []).forEach((g: GraphRow) => {
      if (g.mitreTechnique?.techniqueId) {
        techniques.set(g.mitreTechnique.techniqueId, g.mitreTechnique.name);
      }
    });
    const sorted = Array.from(techniques.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([id, name]) => ({ label: `${id}: ${name}`, value: id }));
    return [{ label: 'All Techniques', value: null }, ...sorted];
  }, [graphData]);

  const statusColor: Record<string, string> = {
    IDEA: 'default', RESEARCH: 'gold', DEVELOPMENT: 'blue', REVIEW: 'purple', TESTING: 'volcano', DEPLOYED: 'green', TUNING: 'orange'
  };

  const graphColumns = [
    {
      title: 'Title', dataIndex: 'title', key: 'title', render: (_: any, row: GraphRow) => (
        <Space direction="vertical" size={0}>
          <Link to={`/playbooks/${row.id}`}>{row.title}</Link>
          {/* Removed 'View detection template' link per request */}
          {!!(row.tags && row.tags.length) && (
            <div style={{ marginTop: 4 }}>
              {row.tags.slice(0, 6).map((t) => (
                <Link key={t} to={`/rules?tags=${encodeURIComponent(t)}`}>
                  <Tag bordered>{t}</Tag>
                </Link>
              ))}
              {row.tags.length > 6 && (
                <Typography.Text type="secondary" style={{ marginLeft: 8 }}>+{row.tags.length - 6} more</Typography.Text>
              )}
            </div>
          )}
        </Space>
      )
    },
    {
      title: 'Actions', key: 'actions', render: (_: any, row: GraphRow) => {
        const isAuthor = currentUserId && row.author?.id === currentUserId;
        const canDelete = isAuthor && row.status !== 'DEPLOYED';
        if (!canDelete) return null;
        return (
          <Button danger size="small" onClick={() => {
            if (!window.confirm('Delete this graph? This cannot be undone.')) return;
            deleteGraph({ variables: { graphId: row.id }, refetchQueries: [{ query: GET_ALL_GRAPHS_QUERY }] }).catch(e => message.error(e.message));
          }}>Delete</Button>
        );
      }
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (status: string) => <Tag color={statusColor[status] || 'default'}>{status}</Tag> },
    { title: 'Author', dataIndex: ['author','username'], key: 'author', render: (_: any, row: GraphRow) => row.author?.username || 'N/A' },
    { title: 'Last Update', dataIndex: 'updatedAt', key: 'updatedAt', render: (dt: string) => new Date(dt).toLocaleString() }
  ];

  const handleCreateGraph = async () => {
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
              author: { id: 'temp-user', username: 'You' },
              mitreTechnique: null,
              isReadOnly: false,
              ownerOrganizationName: null
            }
          }
        },
        update(cache, result) {
          const newGraph = result.data?.createPlaybookGraph?.graph;
          if (!newGraph) return;
          const existing = cache.readQuery<{ allPlaybookGraphs: GraphRow[] }>({ query: GET_ALL_GRAPHS_QUERY });
          if (existing?.allPlaybookGraphs) {
            cache.writeQuery({ query: GET_ALL_GRAPHS_QUERY, data: { allPlaybookGraphs: [newGraph, ...existing.allPlaybookGraphs] } });
          }
        }
      });
      const id = res.data?.createPlaybookGraph.graph.id;
      message.success('Graph created');
      if (id) navigate(`/playbooks/${id}`);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Create graph failed', e);
      message.error('Failed to create graph');
    }
  };

  const handleMaieuticCreate = async (output: MaieuticOutput, selections: MaieuticImportSelections) => {
    const defaultTitle = output.hypothesis.capability?.trim()
      ? `Maieutic: ${output.hypothesis.capability.trim().slice(0, 60)}`
      : 'Maieutic Workbench';
    const title = window.prompt('Name your new workbench', defaultTitle);
    if (!title) return;

    setCreatingFromMaieutic(true);
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
              author: { id: 'temp-user', username: 'You' },
              mitreTechnique: null,
              isReadOnly: false,
              ownerOrganizationName: null
            }
          }
        },
        update(cache, result) {
          const newGraph = result.data?.createPlaybookGraph?.graph;
          if (!newGraph) return;
          const existing = cache.readQuery<{ allPlaybookGraphs: GraphRow[] }>({ query: GET_ALL_GRAPHS_QUERY });
          if (existing?.allPlaybookGraphs) {
            cache.writeQuery({ query: GET_ALL_GRAPHS_QUERY, data: { allPlaybookGraphs: [newGraph, ...existing.allPlaybookGraphs] } });
          }
        }
      });

      const graphId = res.data?.createPlaybookGraph?.graph?.id;
      if (!graphId) {
        throw new Error('Failed to create workbench');
      }

      const updatedFormState = applyMaieuticToWorkbench(output, selections, {
        goal: '',
        technicalContext: '',
        blindSpots: '',
        falsePositives: '',
        responsePlaybook: '',
        detectionRule: '',
      });

      await updatePlaybookDetails({
        variables: {
          graphId,
          goal: updatedFormState.goal,
          technicalContext: updatedFormState.technicalContext,
          blindSpots: updatedFormState.blindSpots,
          triageGuidance: updatedFormState.triageGuidance,
          falsePositives: updatedFormState.falsePositives,
          responsePlaybook: updatedFormState.responsePlaybook,
          detectionRule: updatedFormState.detectionRule,
          testScenario: updatedFormState.testScenario,
          testExpectedOutput: updatedFormState.testExpectedOutput,
          alertTrigger: updatedFormState.alertTrigger,
          defaultSeverity: updatedFormState.defaultSeverity,
          enrichmentSteps: updatedFormState.enrichmentSteps
            ? JSON.stringify(updatedFormState.enrichmentSteps)
            : undefined,
          containmentSteps: updatedFormState.containmentSteps
            ? JSON.stringify(updatedFormState.containmentSteps)
            : undefined,
          notificationSteps: updatedFormState.notificationSteps
            ? JSON.stringify(updatedFormState.notificationSteps)
            : undefined,
          downstreamCorrelationRequirements: updatedFormState.downstreamCorrelationRequirements
            ? JSON.stringify(updatedFormState.downstreamCorrelationRequirements)
            : undefined,
          robustnessLevel: updatedFormState.robustnessLevel,
          dataSourceMaturity: updatedFormState.dataSourceMaturity,
          conversationHistory: JSON.stringify(output.conversationHistory || []),
        },
      });

      message.success('Workbench created from Maieutic output');
      setMaieuticModalVisible(false);
      navigate(`/playbooks/${graphId}`);
    } catch (e: any) {
      console.error('Failed to create workbench from Maieutic output', e);
      message.error(e?.message || 'Failed to create workbench from Maieutic output');
    } finally {
      setCreatingFromMaieutic(false);
    }
  };

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Playbooks</Typography.Title>
        <Space wrap>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'hex',
                  icon: <FileAddOutlined />,
                  label: 'From HEX v2.0 file',
                  onClick: () => setImportModalVisible(true),
                },
                {
                  key: 'hef',
                  icon: <GithubOutlined />,
                  label: 'From OpenTIDE HEF (GitHub)',
                  onClick: () => setImportHefModalVisible(true),
                },
              ],
            }}
            trigger={['click']}
          >
            <Button icon={<UploadOutlined />}>
              Import Workbench <DownOutlined />
            </Button>
          </Dropdown>
          <Button loading={creatingGraph} onClick={handleCreateGraph}>+ New Workbench</Button>
          <CustomButton 
            variant="golden-orange"
            disabled={creatingFromMaieutic}
            onClick={() => setMaieuticModalVisible(true)}
            className="flex items-center gap-1"
            title="Launch hypothesis-driven detection engineering workflow"
          >
            <PixelIcon name="lightbulb" className="w-4 h-4" />
            Maieutic Engine
          </CustomButton>
        </Space>
      </Space>
      
      {/* Import Modal */}
      <ImportWorkbenchModal
        visible={importModalVisible}
        onClose={() => setImportModalVisible(false)}
        onImportSuccess={handleImportSuccess}
      />

      {/* Import from OpenTIDE HEF (GitHub) Modal */}
      <ImportFromHefModal
        visible={importHefModalVisible}
        onClose={() => setImportHefModalVisible(false)}
        onImportSuccess={handleImportSuccess}
      />

      <MaieuticEngineModal
        isOpen={maieuticModalVisible}
        onClose={() => setMaieuticModalVisible(false)}
        onSubmit={handleMaieuticCreate}
        submitLabel="Create Workbench"
      />
      
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        destroyInactiveTabPane
        items={[
          {
            key: 'graphs',
            label: 'Workbench',
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space wrap>
                  <Input.Search
                    placeholder="Search by title or tag..."
                    value={searchTextGraphs}
                    onChange={e => setSearchTextGraphs(e.target.value)}
                    onSearch={setSearchTextGraphs}
                    allowClear
                    style={{ minWidth: 260 }}
                  />
                  <Space>
                    <Typography.Text strong>Status:</Typography.Text>
                    <Select value={statusFilterGraphs} onChange={setStatusFilterGraphs} options={WORKBENCH_STATUS_OPTIONS} style={{ minWidth: 220 }} />
                  </Space>
                  <Space>
                    <Typography.Text strong>Author:</Typography.Text>
                    <Select value={authorFilterGraphs} onChange={setAuthorFilterGraphs} options={authorOptions} style={{ minWidth: 200 }} allowClear />
                  </Space>
                  <Space>
                    <Typography.Text strong>Technique:</Typography.Text>
                    <Select value={techniqueFilterGraphs} onChange={setTechniqueFilterGraphs} options={techniqueOptions} style={{ minWidth: 300 }} allowClear />
                  </Space>
                  <Space>
                    <Typography.Text strong>Sort By:</Typography.Text>
                    <Select value={sortByGraphs} onChange={setSortByGraphs} options={SORT_OPTIONS} style={{ minWidth: 200 }} />
                  </Space>
                </Space>
                <Table
                  rowKey="id"
                  size="middle"
                  loading={loadingGraphs}
                  dataSource={filteredGraphs}
                  columns={graphColumns}
                  pagination={{ pageSize: 15 }}
                />
                {errorGraphs && <Typography.Text type="danger">{handleError(errorGraphs)}</Typography.Text>}
              </Space>
            )
          },
          {
            key: 'ach',
            label: 'ACH Matrix',
            children: (
              <Suspense fallback={<div style={{ padding: 16 }}>Loading ACH…</div>}>
                <AchPageLazy embedded />
              </Suspense>
            )
          },
          {
            key: 'advops',
            label: 'ADVOPS',
            children: (
              <Suspense fallback={<div style={{ padding: 16 }}>Loading ADVOPS…</div>}>
                <AdvopsPageLazy />
              </Suspense>
            )
          },
          {
            key: 'mve',
            label: 'Machina Velocity Engine',
            children: (
              <Suspense fallback={<div style={{ padding: 16 }}>Loading MVE…</div>}>
                <MveWorkbenchTabLazy />
              </Suspense>
            )
          }
        ]}
      />
    </Space>
  );
};
