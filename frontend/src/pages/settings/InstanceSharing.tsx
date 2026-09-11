import React, { useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  KeyOutlined,
  LinkOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';

const { Text, Title } = Typography;

const GET_INSTANCE_SHARING = gql`
  query GetInstanceSharing {
    hefaistosInstanceIdentity {
      instanceId
      updatedAt
    }
    hefaistosRemotePeers {
      id
      name
      remoteUrl
      remoteInstanceId
      defaultScope
      autoPullEnabled
      autoPullSchedule
      nextAutoPullAt
      verifySsl
      allowSelfSigned
      tlsCertFingerprint
      enabled
      hasApiKey
      lastSyncAt
      lastSyncStatus
      lastSyncMessage
      createdAt
      updatedAt
    }
    hefaistosInboundShareKeys {
      id
      name
      keyHint
      allowedScopes
      enforceTagFilter
      requiredTags
      isActive
      expiresAt
      lastUsedAt
      createdAt
      updatedAt
    }
    hefaistosPullJobs(limit: 30) {
      id
      peerId
      peerName
      requestedScope
      status
      summary
      message
      startedAt
      completedAt
      triggeredByUsername
    }
  }
`;

const SET_REMOTE_PEER = gql`
  mutation SetHefaistosRemotePeer(
    $id: UUID
    $name: String!
    $remoteUrl: String!
    $remoteInstanceId: UUID!
    $apiKey: String
    $defaultScope: String
    $autoPullEnabled: Boolean
    $autoPullSchedule: String
    $verifySsl: Boolean
    $allowSelfSigned: Boolean
    $tlsCertFingerprint: String
    $enabled: Boolean
  ) {
    setHefaistosRemotePeer(
      id: $id
      name: $name
      remoteUrl: $remoteUrl
      remoteInstanceId: $remoteInstanceId
      apiKey: $apiKey
      defaultScope: $defaultScope
      autoPullEnabled: $autoPullEnabled
      autoPullSchedule: $autoPullSchedule
      verifySsl: $verifySsl
      allowSelfSigned: $allowSelfSigned
      tlsCertFingerprint: $tlsCertFingerprint
      enabled: $enabled
    ) {
      success
      message
      peer { id }
    }
  }
`;

const DELETE_REMOTE_PEER = gql`
  mutation DeleteHefaistosRemotePeer($id: UUID!) {
    deleteHefaistosRemotePeer(id: $id) {
      success
      message
    }
  }
`;

const CREATE_INBOUND_KEY = gql`
  mutation CreateHefaistosInboundShareKey(
    $name: String!
    $allowedScopes: [String]!
    $enforceTagFilter: Boolean
    $requiredTags: [String]
    $expiresAt: DateTime
  ) {
    createHefaistosInboundShareKey(
      name: $name
      allowedScopes: $allowedScopes
      enforceTagFilter: $enforceTagFilter
      requiredTags: $requiredTags
      expiresAt: $expiresAt
    ) {
      success
      message
      rawApiKey
      key { id }
    }
  }
`;

const REVOKE_INBOUND_KEY = gql`
  mutation RevokeHefaistosInboundShareKey($id: UUID!) {
    revokeHefaistosInboundShareKey(id: $id) {
      success
      message
      key { id isActive }
    }
  }
`;

const PULL_FROM_REMOTE = gql`
  mutation PullFromRemoteHefaistos($peerId: UUID!, $scope: String) {
    pullFromRemoteHefaistos(peerId: $peerId, scope: $scope) {
      success
      message
      job { id status completedAt }
    }
  }
`;

interface RemotePeer {
  id: string;
  name: string;
  remoteUrl: string;
  remoteInstanceId: string;
  defaultScope: 'WORKBENCH' | 'RULES' | 'ACH' | 'ADVOPS' | 'ALL';
  autoPullEnabled: boolean;
  autoPullSchedule: 'DAILY' | 'WEEKLY';
  nextAutoPullAt?: string | null;
  verifySsl: boolean;
  allowSelfSigned: boolean;
  tlsCertFingerprint: string;
  enabled: boolean;
  hasApiKey: boolean;
  lastSyncAt?: string | null;
  lastSyncStatus?: string | null;
  lastSyncMessage?: string | null;
}

interface InboundShareKey {
  id: string;
  name: string;
  keyHint: string;
  allowedScopes: string[];
  enforceTagFilter: boolean;
  requiredTags: string[];
  isActive: boolean;
  expiresAt?: string | null;
  lastUsedAt?: string | null;
}

interface PullJob {
  id: string;
  peerName?: string | null;
  requestedScope: string;
  status: string;
  message?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  triggeredByUsername?: string | null;
}

const scopeOptions = [
  { label: 'Workbench', value: 'WORKBENCH' },
  { label: 'Rules', value: 'RULES' },
  { label: 'ACH', value: 'ACH' },
  { label: 'ADVOPS', value: 'ADVOPS' },
  { label: 'All', value: 'ALL' },
];
const autoPullScheduleOptions = [
  { label: 'Daily', value: 'DAILY' },
  { label: 'Weekly', value: 'WEEKLY' },
];

const statusColor = (status?: string | null): string => {
  if (status === 'COMPLETED') return 'green';
  if (status === 'FAILED') return 'red';
  if (status === 'PROCESSING') return 'blue';
  if (status === 'QUEUED') return 'gold';
  return 'default';
};

const fmtDate = (value?: string | null): string => (value ? new Date(value).toLocaleString() : '—');

const InstanceSharing: React.FC = () => {
  const { message } = App.useApp();
  const [peerModalOpen, setPeerModalOpen] = useState(false);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string>('');
  const [editingPeer, setEditingPeer] = useState<RemotePeer | null>(null);
  const [peerForm] = Form.useForm();
  const [keyForm] = Form.useForm();

  const { data, loading, refetch } = useQuery(GET_INSTANCE_SHARING, {
    fetchPolicy: 'cache-and-network',
  });

  const [setRemotePeer, { loading: savingPeer }] = useMutation(SET_REMOTE_PEER);
  const [deleteRemotePeer] = useMutation(DELETE_REMOTE_PEER);
  const [createInboundKey, { loading: creatingKey }] = useMutation(CREATE_INBOUND_KEY);
  const [revokeInboundKey] = useMutation(REVOKE_INBOUND_KEY);
  const [pullFromRemote, { loading: pulling }] = useMutation(PULL_FROM_REMOTE);

  const peers: RemotePeer[] = useMemo(() => data?.hefaistosRemotePeers || [], [data?.hefaistosRemotePeers]);
  const inboundKeys: InboundShareKey[] = useMemo(
    () => data?.hefaistosInboundShareKeys || [],
    [data?.hefaistosInboundShareKeys],
  );
  const pullJobs: PullJob[] = useMemo(() => data?.hefaistosPullJobs || [], [data?.hefaistosPullJobs]);
  const instanceId: string = data?.hefaistosInstanceIdentity?.instanceId || '';

  const onOpenCreatePeer = () => {
    setEditingPeer(null);
    peerForm.resetFields();
    peerForm.setFieldsValue({
      defaultScope: 'ALL',
      autoPullEnabled: false,
      autoPullSchedule: 'DAILY',
      verifySsl: true,
      allowSelfSigned: false,
      enabled: true,
    });
    setPeerModalOpen(true);
  };

  const onOpenEditPeer = (peer: RemotePeer) => {
    setEditingPeer(peer);
    peerForm.setFieldsValue({
      name: peer.name,
      remoteUrl: peer.remoteUrl,
      remoteInstanceId: peer.remoteInstanceId,
      apiKey: '',
      defaultScope: peer.defaultScope,
      autoPullEnabled: peer.autoPullEnabled,
      autoPullSchedule: peer.autoPullSchedule,
      verifySsl: peer.verifySsl,
      allowSelfSigned: peer.allowSelfSigned,
      tlsCertFingerprint: peer.tlsCertFingerprint,
      enabled: peer.enabled,
    });
    setPeerModalOpen(true);
  };

  const onSavePeer = async () => {
    try {
      const values = await peerForm.validateFields();
      const variables: Record<string, unknown> = {
        name: values.name,
        remoteUrl: values.remoteUrl,
        remoteInstanceId: values.remoteInstanceId,
        defaultScope: values.defaultScope,
        autoPullEnabled: values.autoPullEnabled,
        autoPullSchedule: values.autoPullSchedule,
        verifySsl: values.verifySsl,
        allowSelfSigned: values.allowSelfSigned,
        tlsCertFingerprint: values.tlsCertFingerprint || '',
        enabled: values.enabled,
      };
      if (editingPeer) variables.id = editingPeer.id;
      if (values.apiKey) variables.apiKey = values.apiKey;
      const result = await setRemotePeer({ variables });
      const payload = result.data?.setHefaistosRemotePeer;
      if (!payload?.success) {
        message.error(payload?.message || 'Failed to save remote peer');
        return;
      }
      message.success(payload.message || 'Remote peer saved');
      setPeerModalOpen(false);
      setEditingPeer(null);
      peerForm.resetFields();
      refetch();
    } catch (err: any) {
      message.error(err?.message || 'Failed to save remote peer');
    }
  };

  const onDeletePeer = async (peerId: string) => {
    const result = await deleteRemotePeer({ variables: { id: peerId } });
    const payload = result.data?.deleteHefaistosRemotePeer;
    if (!payload?.success) {
      message.error(payload?.message || 'Failed to delete remote peer');
      return;
    }
    message.success(payload.message || 'Remote peer deleted');
    refetch();
  };

  const onPullPeer = async (peer: RemotePeer) => {
    const result = await pullFromRemote({ variables: { peerId: peer.id, scope: peer.defaultScope } });
    const payload = result.data?.pullFromRemoteHefaistos;
    if (!payload?.success) {
      message.error(payload?.message || 'Pull failed');
      refetch();
      return;
    }
    message.success(payload.message || 'Pull completed');
    refetch();
  };

  const onCreateInboundKey = async () => {
    try {
      const values = await keyForm.validateFields();
      const result = await createInboundKey({
        variables: {
          name: values.name,
          allowedScopes: values.allowedScopes,
          enforceTagFilter: Boolean(values.enforceTagFilter),
          requiredTags: values.requiredTags || [],
          expiresAt: values.expiresAt ? values.expiresAt.toISOString() : null,
        },
      });
      const payload = result.data?.createHefaistosInboundShareKey;
      if (!payload?.success) {
        message.error(payload?.message || 'Failed to create share key');
        return;
      }
      setGeneratedKey(payload.rawApiKey || '');
      message.success(payload.message || 'Share key created');
      refetch();
      keyForm.resetFields();
    } catch (err: any) {
      message.error(err?.message || 'Failed to create share key');
    }
  };

  const onRevokeKey = async (keyId: string) => {
    const result = await revokeInboundKey({ variables: { id: keyId } });
    const payload = result.data?.revokeHefaistosInboundShareKey;
    if (!payload?.success) {
      message.error(payload?.message || 'Failed to revoke share key');
      return;
    }
    message.success(payload.message || 'Share key revoked');
    refetch();
  };

  const peerColumns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (value: string, record: RemotePeer) => (
        <Space>
          <LinkOutlined />
          <strong>{value}</strong>
          {!record.enabled && <Tag>Disabled</Tag>}
        </Space>
      ),
    },
    { title: 'Remote URL', dataIndex: 'remoteUrl', key: 'remoteUrl' },
    { title: 'Instance ID', dataIndex: 'remoteInstanceId', key: 'remoteInstanceId' },
    {
      title: 'Scope',
      dataIndex: 'defaultScope',
      key: 'defaultScope',
      render: (scope: string) => <Tag>{scope}</Tag>,
    },
    {
      title: 'Auto Pull',
      key: 'autoPull',
      render: (_: unknown, record: RemotePeer) => (
        <Space direction="vertical" size={0}>
          {record.autoPullEnabled ? (
            <>
              <Tag color="blue">{record.autoPullSchedule}</Tag>
              <Text type="secondary">Next: {fmtDate(record.nextAutoPullAt)}</Text>
            </>
          ) : (
            <Tag>Off</Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'API Key',
      dataIndex: 'hasApiKey',
      key: 'hasApiKey',
      render: (hasApiKey: boolean) => <Tag color={hasApiKey ? 'green' : 'orange'}>{hasApiKey ? 'Configured' : 'Missing'}</Tag>,
    },
    {
      title: 'Last Pull',
      key: 'lastPull',
      render: (_: unknown, record: RemotePeer) => (
        <Space direction="vertical" size={0}>
          <Text>{fmtDate(record.lastSyncAt)}</Text>
          {record.lastSyncStatus && <Tag color={statusColor(record.lastSyncStatus)}>{record.lastSyncStatus}</Tag>}
        </Space>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: RemotePeer) => (
        <Space>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => onPullPeer(record)}
            disabled={!record.enabled || !record.hasApiKey}
            loading={pulling}
          >
            Pull
          </Button>
          <Button onClick={() => onOpenEditPeer(record)}>Edit</Button>
          <Popconfirm title="Delete this remote peer?" onConfirm={() => onDeletePeer(record.id)}>
            <Button danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const keyColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Key Hint', dataIndex: 'keyHint', key: 'keyHint' },
    {
      title: 'Scopes',
      dataIndex: 'allowedScopes',
      key: 'allowedScopes',
      render: (scopes: string[]) => (
        <Space wrap>
          {(scopes || []).map((scope) => <Tag key={scope}>{scope}</Tag>)}
        </Space>
      ),
    },
    {
      title: 'Tag Policy',
      key: 'tagPolicy',
      render: (_: unknown, record: InboundShareKey) => (
        <Space wrap>
          <Tag color={record.enforceTagFilter ? 'blue' : 'default'}>
            {record.enforceTagFilter ? 'Tag Filter On' : 'Tag Filter Off'}
          </Tag>
          {record.enforceTagFilter && (record.requiredTags || []).map((tag) => (
            <Tag key={`${record.id}-${tag}`} color="purple">
              {tag}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'isActive',
      key: 'isActive',
      render: (isActive: boolean) => <Tag color={isActive ? 'green' : 'default'}>{isActive ? 'Active' : 'Revoked'}</Tag>,
    },
    { title: 'Expires', dataIndex: 'expiresAt', key: 'expiresAt', render: (value: string) => fmtDate(value) },
    { title: 'Last Used', dataIndex: 'lastUsedAt', key: 'lastUsedAt', render: (value: string) => fmtDate(value) },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: InboundShareKey) => (
        <Popconfirm title="Revoke this key?" onConfirm={() => onRevokeKey(record.id)} disabled={!record.isActive}>
          <Button danger disabled={!record.isActive}>Revoke</Button>
        </Popconfirm>
      ),
    },
  ];

  const jobColumns = [
    { title: 'Started', dataIndex: 'startedAt', key: 'startedAt', render: (value: string) => fmtDate(value) },
    { title: 'Peer', dataIndex: 'peerName', key: 'peerName' },
    { title: 'Scope', dataIndex: 'requestedScope', key: 'requestedScope', render: (scope: string) => <Tag>{scope}</Tag> },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (status: string) => <Tag color={statusColor(status)}>{status}</Tag> },
    { title: 'Message', dataIndex: 'message', key: 'message', render: (value: string) => value || '—' },
    { title: 'Completed', dataIndex: 'completedAt', key: 'completedAt', render: (value: string) => fmtDate(value) },
  ];

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Alert
        type="info"
        showIcon
        message="PULL-only design"
        description="Remote sharing endpoints are read-only. Pull operations never modify the remote HEFAISTOS instance. Export eligibility is default-deny and now requires explicit per-item remote-pull enablement; optional key-level tag filtering further restricts Workbench/Rules export."
      />

      <Card loading={loading}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Title level={4} style={{ margin: 0 }}>Local Instance Identity</Title>
          <Text type="secondary">Share this UUID v5 with trusted remote parties so they can verify your instance.</Text>
          <Space>
            <Input value={instanceId} readOnly style={{ minWidth: 520 }} />
            <Button
              icon={<CopyOutlined />}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(instanceId || '');
                  message.success('Instance ID copied');
                } catch {
                  message.error('Failed to copy instance ID');
                }
              }}
            >
              Copy
            </Button>
          </Space>
        </Space>
      </Card>

      <Card
        title="Remote Peers (PULL Sources)"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={onOpenCreatePeer}>Add Peer</Button>}
        loading={loading}
      >
        <Table
          rowKey="id"
          dataSource={peers}
          columns={peerColumns}
          pagination={false}
          locale={{ emptyText: 'No remote peers configured yet.' }}
        />
      </Card>

      <Card
        title="Inbound API Keys (What others can PULL from this instance)"
        extra={<Button icon={<KeyOutlined />} onClick={() => { setGeneratedKey(''); setKeyModalOpen(true); }}>Create Key</Button>}
        loading={loading}
      >
        <Table
          rowKey="id"
          dataSource={inboundKeys}
          columns={keyColumns}
          pagination={false}
          locale={{ emptyText: 'No inbound share keys configured.' }}
        />
      </Card>

      <Card title="Pull Job History" loading={loading}>
        <Table
          rowKey="id"
          dataSource={pullJobs}
          columns={jobColumns}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: 'No pull jobs yet.' }}
        />
      </Card>

      <Modal
        title={editingPeer ? 'Edit Remote Peer' : 'Add Remote Peer'}
        open={peerModalOpen}
        onCancel={() => { setPeerModalOpen(false); setEditingPeer(null); }}
        onOk={onSavePeer}
        okText={editingPeer ? 'Save' : 'Create'}
        confirmLoading={savingPeer}
      >
        <Form form={peerForm} layout="vertical">
          <Form.Item name="name" label="Peer Name" rules={[{ required: true, message: 'Peer name is required' }]}>
            <Input placeholder="e.g. PROD HEFAISTOS" />
          </Form.Item>
          <Form.Item name="remoteUrl" label="Remote URL" rules={[{ required: true, message: 'Remote URL is required' }, { type: 'url', message: 'Enter a valid URL' }]}>
            <Input placeholder="https://remote-hefaistos.example.com" />
          </Form.Item>
          <Form.Item name="remoteInstanceId" label="Remote Instance ID (UUID v5)" rules={[{ required: true, message: 'Remote instance ID is required' }]}>
            <Input placeholder="xxxxxxxx-xxxx-5xxx-xxxx-xxxxxxxxxxxx" />
          </Form.Item>
          <Form.Item
            name="apiKey"
            label={editingPeer ? 'Remote API Key (leave blank to keep current)' : 'Remote API Key'}
            rules={editingPeer ? [] : [{ required: true, message: 'Remote API key is required' }]}
          >
            <Input.Password placeholder="hefshare_..." />
          </Form.Item>
          <Form.Item name="defaultScope" label="Default Pull Scope" rules={[{ required: true, message: 'Select default scope' }]}>
            <Select options={scopeOptions} />
          </Form.Item>
          <Form.Item name="autoPullEnabled" label="Enable Auto Pull" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item shouldUpdate={(prev, curr) => prev.autoPullEnabled !== curr.autoPullEnabled} noStyle>
            {({ getFieldValue }) => (
              <Form.Item
                name="autoPullSchedule"
                label="Auto Pull Schedule"
                rules={getFieldValue('autoPullEnabled') ? [{ required: true, message: 'Select auto pull schedule' }] : []}
              >
                <Select
                  options={autoPullScheduleOptions}
                  disabled={!getFieldValue('autoPullEnabled')}
                />
              </Form.Item>
            )}
          </Form.Item>
          <Form.Item name="verifySsl" label="Verify TLS Certificate" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="allowSelfSigned" label="Allow Self-Signed Certificate" valuePropName="checked">
            <Switch
              onChange={(checked) => {
                if (checked) {
                  peerForm.setFieldValue('verifySsl', false);
                }
              }}
            />
          </Form.Item>
          <Form.Item name="tlsCertFingerprint" label="Pinned TLS Fingerprint (SHA-256, optional)">
            <Input placeholder="ABCD1234... (64 hex chars)" />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Create Inbound Share Key"
        open={keyModalOpen}
        onCancel={() => { setKeyModalOpen(false); setGeneratedKey(''); keyForm.resetFields(); }}
        onOk={onCreateInboundKey}
        okText="Create Key"
        confirmLoading={creatingKey}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Form form={keyForm} layout="vertical">
            <Form.Item name="name" label="Key Name" rules={[{ required: true, message: 'Key name is required' }]}>
              <Input placeholder="e.g. STAGING pull key" />
            </Form.Item>
            <Form.Item
              name="allowedScopes"
              label="Allowed Pull Scopes"
              rules={[{ required: true, message: 'Select at least one scope' }]}
              initialValue={['ALL']}
            >
              <Select mode="multiple" options={scopeOptions} />
            </Form.Item>
            <Form.Item
              name="enforceTagFilter"
              label="Enforce Tag Filter (Workbench/Rules)"
              valuePropName="checked"
              initialValue={false}
            >
              <Switch />
            </Form.Item>
            <Form.Item shouldUpdate={(prev, curr) => prev.enforceTagFilter !== curr.enforceTagFilter} noStyle>
              {({ getFieldValue }) => (
                <Form.Item
                  name="requiredTags"
                  label="Required Tags"
                  rules={getFieldValue('enforceTagFilter') ? [{ required: true, message: 'Add at least one required tag' }] : []}
                  initialValue={['PULL']}
                >
                  <Select
                    mode="tags"
                    tokenSeparators={[',', ' ']}
                    placeholder="e.g. PULL"
                    disabled={!getFieldValue('enforceTagFilter')}
                  />
                </Form.Item>
              )}
            </Form.Item>
            <Form.Item name="expiresAt" label="Expiration (optional)">
              <DatePicker showTime style={{ width: '100%' }} />
            </Form.Item>
          </Form>

          {generatedKey && (
            <Alert
              type="warning"
              showIcon
              message="Copy this key now"
              description={
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text code copyable>{generatedKey}</Text>
                  <Text type="secondary">This raw key is shown only once.</Text>
                </Space>
              }
            />
          )}
        </Space>
      </Modal>
    </Space>
  );
};

export default InstanceSharing;
