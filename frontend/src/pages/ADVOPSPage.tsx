import React, { useMemo, useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation, useLazyQuery } from '@apollo/client/react';
import { App, Card, Table, Button, Modal, Tag, Space, Typography, Select, Input } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ADVOPSReport } from '../types/advops';
import { ADVOPSForm } from '../components/advops/ADVOPSForm';

const { Title } = Typography;

interface MISPInstanceOption { id: string; name: string; url: string; }

const GET_ALL_ADVOPS_REPORTS = gql`
  query GetAllAdvopsReports {
    allAdvopsReports {
      id
      huntId
      hypothesis
      status
      priority
      allowRemotePull
      author { username }
      createdAt
      updatedAt
      verificationSummary
      infrastructureSummary
      pivotSummary
      falsePositiveSummary
      mitreSummary
      detectionLogicSummary
    }
  }
`;

const GET_NEXT_HUNT_ID = gql`
  query GetNextHuntId {
    nextHuntId
  }
`;

const CREATE_ADVOPS_REPORT = gql`
  mutation CreateAdvopsReport($input: ADVOPSReportInput!) {
    createAdvopsReport(input: $input) {
      report {
        id
        huntId
        hypothesis
        status
        priority
        author { username }
        createdAt
        updatedAt
        verificationSummary
        infrastructureSummary
        pivotSummary
        falsePositiveSummary
        mitreSummary
        detectionLogicSummary
      }
    }
  }
`;

const UPDATE_ADVOPS_REPORT = gql`
  mutation UpdateAdvopsReport($id: UUID!, $input: ADVOPSReportInput!) {
    updateAdvopsReport(id: $id, input: $input) {
      report {
        id
        huntId
        hypothesis
        status
        priority
        allowRemotePull
        author { username }
        createdAt
        updatedAt
        verificationSummary
        infrastructureSummary
        pivotSummary
        falsePositiveSummary
        mitreSummary
        detectionLogicSummary
      }
    }
  }
`;

const SET_ADVOPS_REMOTE_PULL = gql`
  mutation SetAdvopsRemotePull($id: UUID!, $enabled: Boolean!) {
    setAdvopsRemotePull(id: $id, enabled: $enabled) {
      success
      message
      report { id allowRemotePull }
    }
  }
`;

const DELETE_ADVOPS_REPORT = gql`
  mutation DeleteAdvopsReport($id: UUID!) {
    deleteAdvopsReport(id: $id) {
      ok
    }
  }
`;

const PUSH_ADVOPS_REPORT_TO_MISP = gql`
  mutation PushAdvopsReportToMISP($id: UUID!, $mispInstanceId: UUID) {
    pushAdvopsReportToMisp(id: $id, mispInstanceId: $mispInstanceId) {
      success
      message
      eventId
    }
  }
`;

const GET_MISP_INSTANCES = gql`
  query GetMISPInstancesForPush {
    mispInstances {
      id
      name
      url
    }
  }
`;

const CREATE_PLAYBOOK_GRAPH = gql`
  mutation CreatePlaybookGraph($title: String!) {
    createPlaybookGraph(title: $title) {
      graph {
        id
        title
        goal
        technicalContext
      }
    }
  }
`;

const UPDATE_PLAYBOOK_DETAILS = gql`
  mutation UpdatePlaybookDetails(
    $graphId: UUID!
    $goal: String
    $technicalContext: String
    $falsePositives: String
  ) {
    updatePlaybookDetails(
      graphId: $graphId
      goal: $goal
      technicalContext: $technicalContext
      falsePositives: $falsePositives
    ) {
      graph {
        id
        title
        goal
        technicalContext
        falsePositives
      }
    }
  }
`;

interface PushToMISPResponse {
  pushAdvopsReportToMisp: {
    success: boolean;
    message: string;
    eventId: number | null;
  };
}

interface CreatePlaybookGraphResponse {
  createPlaybookGraph: {
    graph: {
      id: string;
      title: string;
      goal: string | null;
      technicalContext: string | null;
    };
  };
}

interface UpdatePlaybookDetailsResponse {
  updatePlaybookDetails: {
    graph: {
      id: string;
      title: string;
      goal: string | null;
      technicalContext: string | null;
      falsePositives: string | null;
    };
  };
}

interface ADVOPSPageProps {
  embedded?: boolean;
}

export const ADVOPSPage: React.FC<ADVOPSPageProps> = ({ embedded = false }) => {
  const { message, notification } = App.useApp();
  const { id: paramsId } = useParams<{ id?: string }>();
  const [searchParams] = useSearchParams();
  const idFromSearch = searchParams.get('id');
  const targetId = paramsId || idFromSearch;
  const navigate = useNavigate();
  const { data, loading, refetch } = useQuery<{ allAdvopsReports: ADVOPSReport[] }>(GET_ALL_ADVOPS_REPORTS);
  const [getNextHuntId] = useLazyQuery<{ nextHuntId: string }>(GET_NEXT_HUNT_ID, {
    fetchPolicy: 'network-only', // Always fetch fresh ID from server, never use cache
  });
  const { data: mispData } = useQuery<{ mispInstances: MISPInstanceOption[] }>(GET_MISP_INSTANCES, { fetchPolicy: 'cache-and-network' });
  const [createReport] = useMutation(CREATE_ADVOPS_REPORT);
  const [updateReport] = useMutation(UPDATE_ADVOPS_REPORT);
  const [deleteReport] = useMutation(DELETE_ADVOPS_REPORT);
  const [setAdvopsRemotePull, { loading: togglingRemotePull }] = useMutation(SET_ADVOPS_REMOTE_PULL);
  const [pushToMISP] = useMutation<PushToMISPResponse>(PUSH_ADVOPS_REPORT_TO_MISP);
  const [createWorkbench] = useMutation<CreatePlaybookGraphResponse>(CREATE_PLAYBOOK_GRAPH);
  const [updateWorkbenchDetails] = useMutation<UpdatePlaybookDetailsResponse>(UPDATE_PLAYBOOK_DETAILS);
  
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<ADVOPSReport | null>(null);
  const [nextHuntId, setNextHuntId] = useState<string | null>(null);
  const [workbenchLoading, setWorkbenchLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [priorityFilter, setPriorityFilter] = useState<string | null>(null);
  const [authorFilter, setAuthorFilter] = useState<string | null>(null);
  const [searchText, setSearchText] = useState('');
  const [mispSelectVisible, setMispSelectVisible] = useState(false);
  const [selectedMispInstanceId, setSelectedMispInstanceId] = useState<string | null>(null);
  const reports = data?.allAdvopsReports || [];
  const mispInstances = mispData?.mispInstances || [];

  // Auto-open modal if URL contains an ID (from /advops/:id or ?id=...)
  useEffect(() => {
    if (targetId && reports.length > 0) {
      const report = reports.find(r => r.id === targetId);
      if (report) {
        setEditing(report);
        setModalVisible(true);
      }
    }
  }, [targetId, reports]);

  // Clear URL param when modal closes
  const handleModalClose = () => {
    setModalVisible(false);
    setEditing(null);
    setNextHuntId(null); // Clear next hunt ID
    navigate('/advops');
  };

  const filteredReports = useMemo(() => {
    let result = reports;
    if (statusFilter) {
      result = result.filter(r => r.status === statusFilter);
    }
    if (priorityFilter) {
      result = result.filter(r => r.priority === priorityFilter);
    }
    if (authorFilter) {
      result = result.filter(r => r.author?.username === authorFilter);
    }
    if (searchText) {
      const lower = searchText.toLowerCase();
      result = result.filter(r =>
        r.huntId.toLowerCase().includes(lower) ||
        r.hypothesis.toLowerCase().includes(lower)
      );
    }
    return result;
  }, [reports, statusFilter, priorityFilter, authorFilter, searchText]);

  const statusOptions = useMemo(() => {
    const statuses = new Set<string>();
    reports.forEach(r => statuses.add(r.status));
    const sorted = Array.from(statuses).sort();
    return [{ label: 'All Statuses', value: null }, ...sorted.map(s => ({ label: s, value: s }))];
  }, [reports]);

  const priorityOptions = useMemo(() => {
    const priorities = new Set<string>();
    reports.forEach(r => priorities.add(r.priority));
    const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
    const sorted = order.filter(p => priorities.has(p));
    return [{ label: 'All Priorities', value: null }, ...sorted.map(p => ({ label: p, value: p }))];
  }, [reports]);

  const authorOptions = useMemo(() => {
    const authors = new Set<string>();
    reports.forEach(r => {
      if (r.author?.username) authors.add(r.author.username);
    });
    return [{ label: 'All Authors', value: null }, ...Array.from(authors).sort().map(a => ({ label: a, value: a }))];
  }, [reports]);

  const columns = useMemo(
    () => [
      { 
        title: 'Hunt ID', 
        dataIndex: 'huntId', 
        key: 'huntId',
        render: (text: string, record: ADVOPSReport) => (
          <a onClick={() => onEdit(record)} style={{ cursor: 'pointer' }}>{text}</a>
        ),
      },
      { 
        title: 'Hypothesis', 
        dataIndex: 'hypothesis', 
        key: 'hypothesis',
        render: (text: string, record: ADVOPSReport) => (
          <a onClick={() => onEdit(record)} style={{ cursor: 'pointer' }}>{text}</a>
        ),
      },
      {
        title: 'Status',
        dataIndex: 'status',
        key: 'status',
        render: (status: ADVOPSReport['status']) => <Tag>{status}</Tag>,
      },
      {
        title: 'Priority',
        dataIndex: 'priority',
        key: 'priority',
        render: (p: ADVOPSReport['priority']) => <Tag color={p === 'CRITICAL' ? 'red' : p === 'HIGH' ? 'volcano' : p === 'MEDIUM' ? 'blue' : 'default'}>{p}</Tag>,
      },
      {
        title: 'Author',
        dataIndex: ['author', 'username'],
        key: 'author',
        render: (_: unknown, record: ADVOPSReport) => record.author?.username || 'N/A',
      },
      {
        title: 'Actions',
        key: 'actions',
        render: (_: unknown, record: ADVOPSReport) => (
          <Space>
            <Button size="small" onClick={() => onEdit(record)}>Edit</Button>
            <Button size="small" danger onClick={() => onDelete(record.id)}>Delete</Button>
          </Space>
        ),
      },
    ],
    [reports]
  );

  const onCreate = async () => {
    setEditing(null);
    // Fetch next hunt ID before opening modal
    try {
      const { data: huntIdData } = await getNextHuntId();
      if (huntIdData?.nextHuntId) {
        setNextHuntId(huntIdData.nextHuntId);
      }
    } catch (e: any) {
      console.error('Failed to fetch next hunt ID:', e);
      message.error('Failed to generate hunt ID. Please try again or contact support.');
    }
    setModalVisible(true);
  };

  const onEdit = (report: ADVOPSReport) => {
    setEditing(report);
    setNextHuntId(null); // Clear next hunt ID when editing
    setModalVisible(true);
  };

  const onDelete = (id: string) => {
    if (!window.confirm('Delete this hunt?')) return;
    deleteReport({ variables: { id } })
      .then(() => {
        message.success('Hunt deleted');
        refetch();
      })
      .catch(e => message.error(e.message));
  };

  const executePushToMISP = (mispInstanceId?: string) => {
    if (!editing) return;
    const hideLoading = message.loading('Pushing to MISP...', 0);
    pushToMISP({ variables: { id: editing.id, mispInstanceId: mispInstanceId || null } })
      .then((result) => {
        hideLoading();
        const mispResult = result.data?.pushAdvopsReportToMisp;
        if (mispResult?.success) {
          const eventId = mispResult?.eventId;
          const eventText = eventId ? `MISP event #${eventId} created` : 'Pushed to MISP successfully';
          message.success(eventText);
          notification.success({
            message: 'Hunt Pushed to MISP',
            description: eventId ? `MISP event #${eventId} created successfully.` : 'MISP event created successfully.',
            icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
            placement: 'topRight',
          });
        } else {
          const errorMsg = mispResult?.message || 'Unknown error';
          message.error({ content: `Failed to push to MISP: ${errorMsg}`, duration: 5 });
        }
      })
      .catch((e) => {
        hideLoading();
        const errorMsg = e.message || 'Failed to push to MISP';
        if (e.graphQLErrors && e.graphQLErrors.length > 0) {
          message.error({ content: `⚠️ ${e.graphQLErrors[0].message}`, duration: 6 });
        } else {
          message.error({ content: `❌ ${errorMsg}`, duration: 5 });
        }
        console.error('Push to MISP error:', e);
      });
  };

  const onPushToMISP = () => {
    if (!editing) {
      message.error('Please save the hunt first');
      return;
    }
    if (mispInstances.length === 0) {
      // Fall back to global settings-based push
      executePushToMISP();
      return;
    }
    if (mispInstances.length === 1) {
      executePushToMISP(mispInstances[0].id);
      return;
    }
    // Multiple instances — show selection modal
    setSelectedMispInstanceId(mispInstances[0].id);
    setMispSelectVisible(true);
  };

  const onToggleRemotePull = async () => {
    if (!editing) return;
    try {
      const result = await setAdvopsRemotePull({
        variables: { id: editing.id, enabled: !Boolean(editing.allowRemotePull) },
      });
      const payload = result.data?.setAdvopsRemotePull;
      if (!payload?.success) {
        message.error(payload?.message || 'Failed to update remote pull access');
        return;
      }
      message.success(payload.message || 'Remote pull access updated');
      await refetch();
      setEditing((current) => (
        current
          ? { ...current, allowRemotePull: !Boolean(current.allowRemotePull) }
          : current
      ));
    } catch (err: any) {
      message.error(err?.message || 'Failed to update remote pull access');
    }
  };

  const onCreateWorkbench = async () => {
    if (!editing) {
      message.error('Please save the hunt first');
      return;
    }

    // Extract first line from MITRE Mapping
    const mitreLine = editing.mitreSummary?.split('\n')[0]?.trim() || 'MITRE Mapping';

    setWorkbenchLoading(true);
    
    // Show loading notification
    const hideLoading = message.loading('Creating workbench...', 0);
    
    try {
      const createResult = await createWorkbench({
        variables: {
          title: mitreLine,
        },
      });

      const graphId = createResult.data?.createPlaybookGraph?.graph?.id;

      if (!graphId) {
        hideLoading();
        message.error('Failed to create workbench: No ID returned');
        setWorkbenchLoading(false);
        return;
      }

      // Update the workbench with fields from ADVOPS
      await updateWorkbenchDetails({
        variables: {
          graphId: graphId,
          goal: editing.hypothesis,
          technicalContext: editing.huntId,
          falsePositives: editing.falsePositiveSummary || '',
        },
      });

      hideLoading();
      
      message.success({
        content: (
          <span>
            Workbench created. <a href={`/playbooks/${graphId}`} target="_blank" rel="noreferrer">Open in new tab</a>
          </span>
        ),
        duration: 6,
      });

      notification.success({
        message: 'Workbench Created',
        description: (
          <span>
            Workbench <strong>{mitreLine}</strong> created and populated.{' '}
            <a href={`/playbooks/${graphId}`} target="_blank" rel="noreferrer">Open workbench</a>
          </span>
        ),
        icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
        placement: 'topRight',
        duration: 6,
      });

    } catch (error: any) {
      hideLoading();
      const errorMsg = error.message || 'Unknown error occurred';
      message.error({
        content: `❌ Failed to create workbench: ${errorMsg}`,
        duration: 6,
      });
      console.error('Create workbench error:', error);
    } finally {
      setWorkbenchLoading(false);
    }
  };

  const handleSubmit = async (values: Partial<ADVOPSReport>) => {
    try {
      if (editing) {
        await updateReport({
          variables: {
            id: editing.id,
            input: {
              huntId: values.huntId || editing.huntId,
              hypothesis: values.hypothesis || '',
              status: values.status || editing.status,
              priority: values.priority || editing.priority,
              verificationSummary: values.verificationSummary || '',
              infrastructureSummary: values.infrastructureSummary || '',
              pivotSummary: values.pivotSummary || '',
              falsePositiveSummary: values.falsePositiveSummary || '',
              mitreSummary: values.mitreSummary || '',
              detectionLogicSummary: values.detectionLogicSummary || '',
            },
          },
        });
        message.success('Hunt updated');
      } else {
        // For new hunts, send huntId if provided (from form or strAIn), otherwise backend will auto-generate
        const input: any = {
          hypothesis: values.hypothesis || '',
          status: values.status || 'IDEA',
          priority: values.priority || 'MEDIUM',
          verificationSummary: values.verificationSummary || '',
          infrastructureSummary: values.infrastructureSummary || '',
          pivotSummary: values.pivotSummary || '',
          falsePositiveSummary: values.falsePositiveSummary || '',
          mitreSummary: values.mitreSummary || '',
          detectionLogicSummary: values.detectionLogicSummary || '',
        };
        // Include huntId if it's provided in the form
        if (values.huntId) {
          input.huntId = values.huntId;
        }
        await createReport({
          variables: { input },
        });
        message.success('Hunt created');
      }
      setModalVisible(false);
      setNextHuntId(null); // Clear the next hunt ID after successful creation
      refetch();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const containerStyle = embedded ? { padding: 0 } : { padding: 16 };
  const headerStyle = embedded ? { marginBottom: 8 } : { marginBottom: 16 };

  const tableNode = (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Input.Search
          placeholder="Search by hunt ID or hypothesis..."
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
          <Typography.Text strong>Priority:</Typography.Text>
          <Select value={priorityFilter} onChange={setPriorityFilter} options={priorityOptions} style={{ minWidth: 200 }} allowClear />
        </Space>
        <Space>
          <Typography.Text strong>Author:</Typography.Text>
          <Select value={authorFilter} onChange={setAuthorFilter} options={authorOptions} style={{ minWidth: 200 }} allowClear />
        </Space>
      </Space>
      <Table 
        rowKey="id" 
        dataSource={filteredReports} 
        columns={columns} 
        pagination={{ pageSize: 10 }}
        loading={loading}
      />
    </Space>
  );

  return (
    <div style={containerStyle}>
      {!embedded && (
        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={3} style={{ margin: 0 }}>ADVOPS Hunts</Title>
          <Button type="primary" onClick={onCreate}>New Hunt</Button>
        </Space>
      )}

      {embedded ? tableNode : (
        <>
          <Card>
            {tableNode}
          </Card>
        </>
      )}

      <Modal
        title={editing ? 'Edit ADVOPS Hunt' : 'Create ADVOPS Hunt'}
        open={modalVisible}
        onCancel={handleModalClose}
        footer={null}
        destroyOnClose
        width={1200}
        className="advops-theme-modal"
      >
        <ADVOPSForm
          initial={editing || (nextHuntId ? { huntId: nextHuntId } : undefined)}
          onSubmit={handleSubmit}
          onCancel={handleModalClose}
          onPushToMISP={onPushToMISP}
          onCreateWorkbench={onCreateWorkbench}
          remotePullEnabled={Boolean(editing?.allowRemotePull)}
          onToggleRemotePull={editing ? onToggleRemotePull : undefined}
          togglingRemotePull={togglingRemotePull}
          workbenchLoading={workbenchLoading}
        />
      </Modal>

      <Modal
        title="Select MISP Instance"
        open={mispSelectVisible}
        onCancel={() => setMispSelectVisible(false)}
        onOk={() => {
          setMispSelectVisible(false);
          if (selectedMispInstanceId) executePushToMISP(selectedMispInstanceId);
        }}
        okText="Push to MISP"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text>Your organization has multiple MISP instances. Select one to push to:</Typography.Text>
          <Select
            value={selectedMispInstanceId}
            onChange={setSelectedMispInstanceId}
            style={{ width: '100%' }}
            options={mispInstances.map((inst) => ({ label: `${inst.name} (${inst.url})`, value: inst.id }))}
          />
        </Space>
      </Modal>
    </div>
  );
};

export default ADVOPSPage;
