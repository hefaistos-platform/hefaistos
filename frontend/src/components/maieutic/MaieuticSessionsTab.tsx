import React, { useEffect, useMemo, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Link, useNavigate } from 'react-router-dom';
import {
  Alert, Button, Collapse, Descriptions, Drawer, Form, Input, Modal, Popconfirm, Space, Switch, Table, Tag,
  Tooltip, Typography, message,
} from 'antd';
import { DeleteOutlined, EyeOutlined, LockOutlined, PlusOutlined } from '@ant-design/icons';
import { TlpBadge } from '../ui/TlpBadge';
import { TlpSelect } from '../ui/TlpSelect';

const { Text, Paragraph } = Typography;

export const MAIEUTIC_STAGE_COUNT = 6;

const ME_QUERY = gql`
  query MaieuticTabMe { me { id role isSuperuser } }
`;

const DRAFTS_QUERY = gql`
  query MaieuticDrafts {
    maieuticDrafts {
      id name status currentStage outcome createdWorkbenchId finishedAt allowRemotePull
      tlpClassification importedFrom isLocked createdAt updatedAt
    }
  }
`;

const DRAFT_QUERY = gql`
  query MaieuticDraft($id: UUID!) {
    maieuticDraft(id: $id) {
      id name status currentStage spec outcome createdWorkbenchId finishedAt allowRemotePull
      tlpClassification importedFrom isLocked createdAt updatedAt
    }
  }
`;

const ADMIN_INDEX_QUERY = gql`
  query MaieuticAdminIndex {
    maieuticAdminIndex {
      id name authorUsername organizationName status outcome currentStage tlpClassification
      allowRemotePull createdAt updatedAt finishedAt
    }
  }
`;

const CREATE_MUTATION = gql`
  mutation CreateMaieuticDraft($name: String, $tlp: String) {
    createMaieuticDraft(name: $name, tlpClassification: $tlp) { draft { id name } }
  }
`;

const SHARE_MUTATION = gql`
  mutation SetMaieuticDraftSharing($id: UUID!, $allow: Boolean!) {
    setMaieuticDraftSharing(draftId: $id, allowRemotePull: $allow) { draft { id allowRemotePull } }
  }
`;

const DELETE_MUTATION = gql`
  mutation DeleteMaieuticDraft($id: UUID!) { deleteMaieuticDraft(draftId: $id) { ok } }
`;

interface DraftRow {
  id: string;
  name: string;
  status: 'IN_PROGRESS' | 'FINISHED';
  currentStage: number;
  outcome: string;
  createdWorkbenchId: string | null;
  finishedAt: string | null;
  allowRemotePull: boolean;
  tlpClassification: string;
  importedFrom: string;
  isLocked: boolean;
  createdAt: string;
  updatedAt: string;
}

interface AdminRow {
  id: string;
  name: string;
  authorUsername: string | null;
  organizationName: string;
  status: string;
  outcome: string;
  currentStage: number;
  tlpClassification: string;
  allowRemotePull: boolean;
  createdAt: string;
  updatedAt: string;
  finishedAt: string | null;
}

export const OUTCOME_LABELS: Record<string, string> = {
  WORKBENCH_WITH_RULE: 'Workbench created, rule generation started',
  WORKBENCH_WITHOUT_RULE: 'Workbench created without a rule',
};

export function statusTag(status: string) {
  return status === 'FINISHED'
    ? <Tag icon={<LockOutlined />} color="default">Finished · locked</Tag>
    : <Tag color="processing">In progress</Tag>;
}

const fmt = (value?: string | null) => (value ? new Date(value).toLocaleString() : '–');

interface MaieuticSessionsTabProps {
  openCreateSignal?: number;
}

export const MaieuticSessionsTab: React.FC<MaieuticSessionsTabProps> = ({ openCreateSignal = 0 }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [form] = Form.useForm();

  const { data: meData } = useQuery(ME_QUERY);
  const role = String(meData?.me?.role || '').toUpperCase();
  const isAdminView = role === 'ADMIN' || Boolean(meData?.me?.isSuperuser);

  const { data, loading, error, refetch } = useQuery(DRAFTS_QUERY, { fetchPolicy: 'network-only' });
  const { data: adminData, refetch: refetchAdmin } = useQuery(ADMIN_INDEX_QUERY, {
    skip: !isAdminView,
    fetchPolicy: 'network-only',
  });
  const { data: detailData, loading: detailLoading } = useQuery(DRAFT_QUERY, {
    variables: { id: openId },
    skip: !openId,
    fetchPolicy: 'network-only',
  });

  const [createDraft, { loading: creating }] = useMutation(CREATE_MUTATION);
  const [setSharing] = useMutation(SHARE_MUTATION);
  const [deleteDraft] = useMutation(DELETE_MUTATION);

  const rows: DraftRow[] = data?.maieuticDrafts ?? [];
  const mine = useMemo(() => new Set(rows.map((r) => r.id)), [rows]);
  const othersMetadata: AdminRow[] = useMemo(
    () => (adminData?.maieuticAdminIndex ?? []).filter((r: AdminRow) => !mine.has(r.id)),
    [adminData, mine],
  );

  const refreshAll = () => { refetch(); if (isAdminView) refetchAdmin(); };

  useEffect(() => {
    if (openCreateSignal > 0) {
      setCreateOpen(true);
    }
  }, [openCreateSignal]);

  const onCreate = async (values: { name?: string; tlp?: string }) => {
    try {
      const res = await createDraft({ variables: { name: values.name || null, tlp: values.tlp || 'UNCLEAR' } });
      setCreateOpen(false);
      form.resetFields();
      const id = res.data?.createMaieuticDraft?.draft?.id;
      if (id) { navigate(`/maieutics/${id}`); return; }
      refreshAll();
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Could not create session');
    }
  };

  const onDelete = async (id: string) => {
    try {
      await deleteDraft({ variables: { id } });
      if (openId === id) setOpenId(null);
      refreshAll();
      messageApi.success('Session deleted. A Workbench created from it is not affected.');
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Delete failed');
    }
  };

  const onShare = async (id: string, allow: boolean) => {
    try {
      await setSharing({ variables: { id, allow } });
      refreshAll();
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Could not change sharing');
    }
  };

  const deleteButton = (id: string, finished: boolean) => (
    <Popconfirm
      title="Delete this session?"
      description={finished
        ? 'The finished record is removed. The Workbench created from it stays. Copies already pulled by peers are not recalled.'
        : 'Your answers in this session are lost.'}
      okText="Delete"
      okButtonProps={{ danger: true }}
      onConfirm={() => onDelete(id)}
    >
      <Button size="small" danger icon={<DeleteOutlined />}>Delete</Button>
    </Popconfirm>
  );

  const columns = [
    {
      title: 'Session',
      key: 'name',
      render: (_: unknown, r: DraftRow) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.name}</Text>
          {r.importedFrom && <Text type="secondary" style={{ fontSize: 12 }}>Imported from {r.importedFrom}</Text>}
        </Space>
      ),
    },
    { title: 'Status', key: 'status', render: (_: unknown, r: DraftRow) => statusTag(r.status) },
    {
      title: 'Stage',
      key: 'stage',
      render: (_: unknown, r: DraftRow) => (r.status === 'FINISHED' ? 'Done' : `${r.currentStage} of ${MAIEUTIC_STAGE_COUNT}`),
    },
    { title: 'TLP', key: 'tlp', render: (_: unknown, r: DraftRow) => <TlpBadge classification={r.tlpClassification} /> },
    {
      title: 'Outcome',
      key: 'outcome',
      render: (_: unknown, r: DraftRow) => (r.outcome ? OUTCOME_LABELS[r.outcome] ?? r.outcome : '–'),
    },
    { title: 'Updated', key: 'updated', render: (_: unknown, r: DraftRow) => fmt(r.updatedAt) },
    {
      title: 'Share',
      key: 'share',
      render: (_: unknown, r: DraftRow) => {
        if (r.status !== 'FINISHED' || r.importedFrom) {
          return (
            <Tooltip title={r.importedFrom ? 'Imported sessions cannot be shared again.' : 'Only finished sessions can be shared.'}>
              <Switch size="small" disabled checked={false} />
            </Tooltip>
          );
        }
        return (
          <Tooltip title="Let trusted peers pull this finished session through Instance Sharing. They need a key that allows Maieutic sessions (or All) and your TLP limit must allow it. Your design and answers are sent; the Workbench is not.">
            <Switch size="small" checked={r.allowRemotePull} onChange={(v) => onShare(r.id, v)} />
          </Tooltip>
        );
      },
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, r: DraftRow) => (
        <Space>
          {r.status === 'IN_PROGRESS' ? (
            <Button size="small" type="primary" onClick={() => navigate(`/maieutics/${r.id}`)}>Continue</Button>
          ) : (
            <Button size="small" icon={<EyeOutlined />} onClick={() => setOpenId(r.id)}>Open</Button>
          )}
          {deleteButton(r.id, r.status === 'FINISHED')}
        </Space>
      ),
    },
  ];

  const detail: DraftRow & { spec?: unknown } | null = detailData?.maieuticDraft ?? null;

  return (
    <div data-testid="maieutic-sessions-tab">
      {contextHolder}
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="Maieutics: guided design from an idea to a Workbench and a rule"
          description={
            <>
              Only you can see your sessions. When you create a Workbench from a session, the session is locked
              permanently and stays here as the record of how it was designed. Edit the Workbench, not the session.
              <br />
              <Text type="secondary">
                Work through the six stages and create the Workbench, with or without a generated rule.
                You can start a Maieutic session here or from the Workbench Hub action bar.
              </Text>
            </>
          }
        />
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>New session</Button>
        </Space>
        <Table<DraftRow>
          rowKey="id"
          size="middle"
          loading={loading}
          dataSource={rows}
          columns={columns}
          pagination={{ pageSize: 15, hideOnSinglePage: true }}
          locale={{ emptyText: 'No Maieutic sessions yet.' }}
        />
        {error && <Text type="danger">{error.message}</Text>}

        {isAdminView && othersMetadata.length > 0 && (
          <Collapse
            items={[{
              key: 'admin',
              label: `Sessions of other users (metadata only, ${othersMetadata.length})`,
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text type="secondary">
                    Administrators can see that a session exists and delete it, but cannot read its content.
                  </Text>
                  <Table<AdminRow>
                    rowKey="id"
                    size="small"
                    dataSource={othersMetadata}
                    pagination={{ pageSize: 10, hideOnSinglePage: true }}
                    columns={[
                      { title: 'Title', dataIndex: 'name', key: 'name' },
                      { title: 'Author', dataIndex: 'authorUsername', key: 'author', render: (v: string | null) => v ?? '–' },
                      { title: 'Organization', dataIndex: 'organizationName', key: 'org' },
                      { title: 'Status', key: 'status', render: (_: unknown, r: AdminRow) => statusTag(r.status) },
                      { title: 'TLP', key: 'tlp', render: (_: unknown, r: AdminRow) => <TlpBadge classification={r.tlpClassification} /> },
                      { title: 'Updated', key: 'updated', render: (_: unknown, r: AdminRow) => fmt(r.updatedAt) },
                      { title: '', key: 'actions', render: (_: unknown, r: AdminRow) => deleteButton(r.id, r.status === 'FINISHED') },
                    ]}
                  />
                </Space>
              ),
            }]}
          />
        )}
      </Space>

      <Modal
        title="New Maieutic session"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText="Create"
        confirmLoading={creating}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={onCreate} initialValues={{ tlp: 'UNCLEAR' }}>
          <Form.Item name="name" label="Working title" extra="You can change it later while the session is in progress.">
            <Input placeholder="e.g. LSASS credential access" maxLength={255} />
          </Form.Item>
          <Form.Item name="tlp" label="TLP classification" extra="Locked when the session finishes, so choose it now.">
            <TlpSelect />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={detail?.name ?? 'Session'}
        open={Boolean(openId)}
        onClose={() => setOpenId(null)}
        width={620}
        loading={detailLoading}
      >
        {detail && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {detail.isLocked ? (
              <Alert
                type="success"
                showIcon
                icon={<LockOutlined />}
                message="Finished and locked"
                description="This record cannot be changed. Edit the Workbench created from it instead."
              />
            ) : (
              <Alert
                type="warning"
                showIcon
                message="In progress"
                description="Use Continue in the list to keep working on it."
              />
            )}
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Status">{statusTag(detail.status)}</Descriptions.Item>
              <Descriptions.Item label="Stage">
                {detail.isLocked ? 'Done' : `${detail.currentStage} of ${MAIEUTIC_STAGE_COUNT}`}
              </Descriptions.Item>
              <Descriptions.Item label="TLP"><TlpBadge classification={detail.tlpClassification} /></Descriptions.Item>
              <Descriptions.Item label="Outcome">{detail.outcome ? OUTCOME_LABELS[detail.outcome] ?? detail.outcome : '–'}</Descriptions.Item>
              <Descriptions.Item label="Created">{fmt(detail.createdAt)}</Descriptions.Item>
              <Descriptions.Item label="Finished">{fmt(detail.finishedAt)}</Descriptions.Item>
              <Descriptions.Item label="Workbench">
                {detail.createdWorkbenchId
                  ? <Link to={`/playbooks/${detail.createdWorkbenchId}`}>Open Workbench</Link>
                  : '–'}
              </Descriptions.Item>
            </Descriptions>
            <Collapse
              items={[{
                key: 'spec',
                label: 'Recorded content (read-only)',
                children: (
                  <Paragraph>
                    <pre style={{ maxHeight: 360, overflow: 'auto', fontSize: 12 }}>
                      {JSON.stringify(detail.spec ?? {}, null, 2)}
                    </pre>
                  </Paragraph>
                ),
              }]}
            />
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default MaieuticSessionsTab;
