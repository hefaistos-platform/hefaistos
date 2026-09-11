import React, { useEffect, useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import {
  Button,
  Checkbox,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';

type WaitingCase = {
  id: string;
  createdBy?: { id: string } | null;
  title: string;
  shortDescription: string;
  detectionObjective: string;
  mappedTtps: string[];
  estimatedDetectionComplexity: string;
  sourceType: string;
  mispEventId: string;
  status: string;
  enrichmentError: string;
  promotedAt?: string | null;
  promotedGraph?: { id: string; title: string } | null;
  updatedAt: string;
};

type MeData = {
  me: {
    id: string;
    role: string;
    isSuperuser: boolean;
  };
};

type WaitingCasesData = {
  waitingCases: WaitingCase[];
};

type MispData = {
  mispInstances: { id: string; name: string }[];
};

const GET_WAITING_CASES = gql`
  query GetWaitingCases {
    waitingCases {
      id
      createdBy {
        id
      }
      title
      shortDescription
      detectionObjective
      mappedTtps
      estimatedDetectionComplexity
      sourceType
      mispEventId
      status
      enrichmentError
      promotedAt
      updatedAt
      promotedGraph {
        id
        title
      }
    }
  }
`;

const GET_ME = gql`
  query WaitingRoomMe {
    me {
      id
      role
      isSuperuser
    }
  }
`;

const GET_MISP_INSTANCES = gql`
  query WaitingRoomMispInstances {
    mispInstances {
      id
      name
    }
  }
`;

const CREATE_WAITING_CASE = gql`
  mutation CreateWaitingCase($input: WaitingCaseInput!, $autoEnrich: Boolean) {
    createWaitingCase(input: $input, autoEnrich: $autoEnrich) {
      waitingCase {
        id
      }
    }
  }
`;

const UPDATE_WAITING_CASE = gql`
  mutation UpdateWaitingCase($id: UUID!, $input: WaitingCaseInput!, $autoEnrich: Boolean) {
    updateWaitingCase(id: $id, input: $input, autoEnrich: $autoEnrich) {
      waitingCase {
        id
      }
    }
  }
`;

const IMPORT_FROM_MISP = gql`
  mutation ImportWaitingCasesFromMisp(
    $mispInstanceId: UUID!
    $eventId: String
    $tag: String
    $limit: Int
    $runAiEnrichment: Boolean
  ) {
    importWaitingCasesFromMisp(
      mispInstanceId: $mispInstanceId
      eventId: $eventId
      tag: $tag
      limit: $limit
      runAiEnrichment: $runAiEnrichment
    ) {
      success
      message
      importedCount
      skippedCount
    }
  }
`;

const PROMOTE_WAITING_CASE = gql`
  mutation PromoteWaitingCaseToWorkbench($id: UUID!, $title: String) {
    promoteWaitingCaseToWorkbench(id: $id, title: $title) {
      success
      message
      workbench {
        id
      }
    }
  }
`;

const DELETE_WAITING_CASE = gql`
  mutation DeleteWaitingCase($id: UUID!) {
    deleteWaitingCase(id: $id) {
      success
      message
    }
  }
`;

const STATUS_COLORS: Record<string, string> = {
  NEW: 'default',
  ENRICHING: 'processing',
  READY: 'blue',
  PROMOTED: 'green',
  FAILED: 'red',
};

const toMappedTtpsArray = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === 'string') {
    try {
      const parsed: unknown = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      // not JSON, ignore
    }
  }
  return [];
};

export const WaitingRoomPage: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [createOpen, setCreateOpen] = useState(false);
  const [mispOpen, setMispOpen] = useState(false);
  const [selectedCase, setSelectedCase] = useState<WaitingCase | null>(null);
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);

  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [mispForm] = Form.useForm();
  const [promoteForm] = Form.useForm();

  const { data: meData } = useQuery<MeData>(GET_ME);
  const { data: waitingData, loading, refetch } = useQuery<WaitingCasesData>(GET_WAITING_CASES);
  const { data: mispData } = useQuery<MispData>(GET_MISP_INSTANCES);

  const [createWaitingCase, { loading: creating }] = useMutation(CREATE_WAITING_CASE);
  const [updateWaitingCase, { loading: updating }] = useMutation(UPDATE_WAITING_CASE);
  const [importFromMisp, { loading: importing }] = useMutation(IMPORT_FROM_MISP);
  const [promoteWaitingCase, { loading: promoting }] = useMutation(PROMOTE_WAITING_CASE);
  const [deleteWaitingCase] = useMutation(DELETE_WAITING_CASE);

  const role = (meData?.me?.role || '').toUpperCase();
  const isSuperuser = !!meData?.me?.isSuperuser;
  const canCreateEdit = role === 'REVIEWER' || role === 'ADMIN' || isSuperuser;
  const canPromote = role === 'ANALYST' || isSuperuser;

  const rows = waitingData?.waitingCases || [];

  useEffect(() => {
    if (!selectedCase) return;
    editForm.setFieldsValue({
      title: selectedCase.title,
      shortDescription: selectedCase.shortDescription,
      detectionObjective: selectedCase.detectionObjective,
      mappedTtps: toMappedTtpsArray(selectedCase.mappedTtps).join(', '),
      estimatedDetectionComplexity: selectedCase.estimatedDetectionComplexity,
    });
  }, [selectedCase, editForm]);

  const sourceFilters = useMemo(
    () => [
      { text: 'Manual', value: 'MANUAL' },
      { text: 'MISP', value: 'MISP' },
    ],
    [],
  );

  const canDeleteCase = (row: WaitingCase) => {
    const currentUserId = meData?.me?.id;
    const isAuthor = !!currentUserId && row.createdBy?.id === currentUserId;
    const isAdmin = role === 'ADMIN';
    return isAuthor || isAdmin || isSuperuser;
  };

  const openCaseEditor = (row: WaitingCase) => {
    setSelectedCase(row);
  };

  const columns = [
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      render: (_: string, row: WaitingCase) => (
        <Button type="link" onClick={() => openCaseEditor(row)}>
          {row.title}
        </Button>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => <Tag color={STATUS_COLORS[value] || 'default'}>{value}</Tag>,
    },
    {
      title: 'Source',
      dataIndex: 'sourceType',
      key: 'sourceType',
      filters: sourceFilters,
      onFilter: (value: boolean | React.Key, record: WaitingCase) => record.sourceType === value,
      render: (value: string, row: WaitingCase) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text>{value}</Typography.Text>
          {row.mispEventId && <Typography.Text type="secondary">event: {row.mispEventId}</Typography.Text>}
        </Space>
      ),
    },
    {
      title: 'Enrichment',
      key: 'enrichment',
      render: (_: string, row: WaitingCase) => {
        if (row.status === 'FAILED' && row.enrichmentError) {
          return <Typography.Text type="danger">{row.enrichmentError}</Typography.Text>;
        }
        if (row.status === 'ENRICHING') return <Typography.Text type="secondary">Running</Typography.Text>;
        return <Typography.Text type="secondary">Done</Typography.Text>;
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: string, row: WaitingCase) => (
        <Space>
          {canCreateEdit && (
            <Button size="small" onClick={() => openCaseEditor(row)}>
              Edit
            </Button>
          )}
          {canDeleteCase(row) && (
            <Popconfirm
              title="Delete waiting case?"
              description="This action cannot be undone."
              onConfirm={() => {
                void handleDeleteCase(row);
              }}
              okButtonProps={{ danger: true, loading: deletingCaseId === row.id }}
              okText="Delete"
            >
              <Button size="small" danger loading={deletingCaseId === row.id}>
                Delete
              </Button>
            </Popconfirm>
          )}
          {canPromote && row.status !== 'PROMOTED' && (
            <Button
              size="small"
              onClick={() => {
                setSelectedCase(row);
                promoteForm.setFieldsValue({ title: row.title });
                setPromoteOpen(true);
              }}
            >
              Promote to Workbench
            </Button>
          )}
          {row.promotedGraph?.id && (
            <Button size="small" type="link" href={`/playbooks/${row.promotedGraph.id}`}>
              Open Workbench
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const parseMappedTtps = (value?: string) =>
    (value || '')
      .split(',')
      .map((entry) => entry.trim().toUpperCase())
      .filter(Boolean);

  const handleCreate = async () => {
    const values = await createForm.validateFields();
    await createWaitingCase({
      variables: {
        input: {
          title: values.title,
          shortDescription: values.shortDescription,
          detectionObjective: values.detectionObjective || '',
          mappedTtps: parseMappedTtps(values.mappedTtps),
          estimatedDetectionComplexity: values.estimatedDetectionComplexity || '',
        },
        autoEnrich: !!values.autoEnrich,
      },
    });
    messageApi.success('Waiting case created.');
    createForm.resetFields();
    setCreateOpen(false);
    await refetch();
  };

  const handleUpdate = async () => {
    if (!selectedCase) return;
    const values = await editForm.validateFields();
    await updateWaitingCase({
      variables: {
        id: selectedCase.id,
        input: {
          title: values.title,
          shortDescription: values.shortDescription,
          detectionObjective: values.detectionObjective || '',
          mappedTtps: parseMappedTtps(values.mappedTtps),
          estimatedDetectionComplexity: values.estimatedDetectionComplexity || '',
        },
        autoEnrich: !!values.autoEnrich,
      },
    });
    messageApi.success('Waiting case updated.');
    await refetch();
  };

  const handleImportMisp = async () => {
    const values = await mispForm.validateFields();
    const response = await importFromMisp({
      variables: {
        mispInstanceId: values.mispInstanceId,
        eventId: values.eventId || null,
        tag: values.tag || null,
        limit: Number(values.limit || 25),
        runAiEnrichment: !!values.runAiEnrichment,
      },
    });
    const payload = response.data?.importWaitingCasesFromMisp;
    messageApi.success(payload?.message || 'MISP import finished.');
    setMispOpen(false);
    await refetch();
  };

  const handlePromote = async () => {
    if (!selectedCase) return;
    const values = await promoteForm.validateFields();
    const response = await promoteWaitingCase({
      variables: {
        id: selectedCase.id,
        title: values.title,
      },
    });
    const payload = response.data?.promoteWaitingCaseToWorkbench;
    if (payload?.success) {
      messageApi.success(payload.message || 'Promoted to Workbench.');
      setPromoteOpen(false);
      await refetch();
      if (payload.workbench?.id) {
        window.location.assign(`/playbooks/${payload.workbench.id}`);
      }
      return;
    }
    messageApi.error(payload?.message || 'Promotion failed.');
  };

  const handleDeleteCase = async (row: WaitingCase) => {
    setDeletingCaseId(row.id);
    try {
      const response = await deleteWaitingCase({ variables: { id: row.id } });
      const payload = response.data?.deleteWaitingCase;
      if (!payload?.success) {
        messageApi.error(payload?.message || 'Delete failed.');
        return;
      }
      messageApi.success(payload.message || 'Waiting case deleted.');
      if (selectedCase?.id === row.id) setSelectedCase(null);
      await refetch();
    } catch (err) {
      const error = err as Error;
      messageApi.error(error.message || 'Delete failed.');
    } finally {
      setDeletingCaseId(null);
    }
  };

  return (
    <div>
      {contextHolder}
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Waiting Room
        </Typography.Title>
        <Space>
          {canCreateEdit && (
            <Button onClick={() => setMispOpen(true)}>
              Import from MISP
            </Button>
          )}
          {canCreateEdit && (
            <Button type="primary" onClick={() => setCreateOpen(true)}>
              Create case
            </Button>
          )}
        </Space>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title="Create waiting case"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => {
          void handleCreate().catch((err) => messageApi.error(err.message || 'Create failed'));
        }}
        confirmLoading={creating}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="title" label="Title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="shortDescription" label="Short description" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="detectionObjective" label="Detection objective">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="mappedTtps" label="Mapped TTPs (comma-separated)">
            <Input placeholder="T1059.001, T1027" />
          </Form.Item>
          <Form.Item name="estimatedDetectionComplexity" label="Estimated complexity">
            <Input placeholder="LOW / MEDIUM / HIGH" />
          </Form.Item>
          <Form.Item
            name="autoEnrich"
            label="Run AI Enrichment"
            valuePropName="checked"
            extra="If enabled, HEFAISTOS uses your configured AI provider to suggest enriched description, objectives, ATT&CK TTPs, and estimated complexity."
          >
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Import waiting cases from MISP"
        open={mispOpen}
        onCancel={() => setMispOpen(false)}
        onOk={() => {
          void handleImportMisp().catch((err) => messageApi.error(err.message || 'Import failed'));
        }}
        confirmLoading={importing}
      >
        <Form form={mispForm} layout="vertical" initialValues={{ limit: 25, tag: 'HEFAISTOS' }}>
          <Form.Item name="mispInstanceId" label="MISP instance" rules={[{ required: true }]}>
            <Select options={(mispData?.mispInstances || []).map((instance) => ({ label: instance.name, value: instance.id }))} />
          </Form.Item>
          <Form.Item name="eventId" label="Specific event ID (optional)">
            <Input />
          </Form.Item>
          <Form.Item name="tag" label="Required tag (optional)" extra="Clear this field to import all events regardless of tag.">
            <Input placeholder="HEFAISTOS" />
          </Form.Item>
          <Form.Item name="limit" label="Import limit">
            <Input type="number" />
          </Form.Item>
          <Form.Item
            name="runAiEnrichment"
            label="Run AI Enrichment"
            valuePropName="checked"
            extra="If enabled, imported cases are automatically enriched by AI right after import."
          >
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        open={!!selectedCase}
        size="large"
        title={selectedCase?.title || 'Waiting case'}
        onClose={() => setSelectedCase(null)}
        extra={
          canCreateEdit ? (
            <Button
              type="primary"
              onClick={() => {
                void handleUpdate().catch((err) => messageApi.error(err.message || 'Update failed'));
              }}
              loading={updating}
            >
              Save
            </Button>
          ) : null
        }
      >
        {selectedCase && (
          <>
            {!canCreateEdit && (
              <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                <Typography.Text strong>{selectedCase.title}</Typography.Text>
                <Typography.Paragraph>{selectedCase.shortDescription}</Typography.Paragraph>
                <Typography.Paragraph type="secondary">{selectedCase.detectionObjective}</Typography.Paragraph>
                <Typography.Text>Mapped TTPs: {toMappedTtpsArray(selectedCase.mappedTtps).join(', ') || 'N/A'}</Typography.Text>
              </Space>
            )}
            {canCreateEdit && (
              <Form form={editForm} layout="vertical">
                <Form.Item name="title" label="Title" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item name="shortDescription" label="Short description" rules={[{ required: true }]}>
                  <Input.TextArea rows={3} />
                </Form.Item>
                <Form.Item name="detectionObjective" label="Detection objective">
                  <Input.TextArea rows={3} />
                </Form.Item>
                <Form.Item name="mappedTtps" label="Mapped TTPs (comma-separated)">
                  <Input />
                </Form.Item>
                <Form.Item name="estimatedDetectionComplexity" label="Estimated complexity">
                  <Input />
                </Form.Item>
                <Form.Item
                  name="autoEnrich"
                  label="Run AI Enrichment"
                  valuePropName="checked"
                  extra="If enabled, HEFAISTOS re-runs AI enrichment and refreshes the case details based on your edits."
                >
                  <Checkbox />
                </Form.Item>
              </Form>
            )}
          </>
        )}
      </Drawer>

      <Modal
        title="Promote to Workbench"
        open={promoteOpen}
        onCancel={() => setPromoteOpen(false)}
        onOk={() => {
          void handlePromote().catch((err) => messageApi.error(err.message || 'Promotion failed'));
        }}
        confirmLoading={promoting}
      >
        <Form form={promoteForm} layout="vertical">
          <Form.Item name="title" label="Workbench title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default WaitingRoomPage;
