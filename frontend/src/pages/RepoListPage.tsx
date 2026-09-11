import React from 'react';
import { Link } from 'react-router-dom';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { App, Alert, Card, Table, Space, Button, Typography, Modal, Form, Input, Popconfirm, Select, Radio, Divider, Switch, Tooltip, Tabs, Tag } from 'antd';
import { ClockCircleOutlined, PlusOutlined, EditOutlined, DeleteOutlined, LockOutlined } from '@ant-design/icons';

const GET_RULE_REPOSITORIES = gql`
  query GetRuleRepositories {
    me { username role }
    allRuleRepositories {
      id name url username provider apiBaseUrl verifySsl lastSync ruleCount
      autoPullEnabled autoPullSchedule nextScheduledPull
    }
  }
`;
const GET_GRAPHS = gql`
  query GetAllPlaybookGraphsForPush {
    allPlaybookGraphs { id title status }
  }
`;
const PULL_RULE_REPOSITORY = gql`
  mutation PullRuleRepository($id: ID!) {
    pullRuleRepository(id: $id) { ok message repository { id lastSync } }
  }
`;
const PUSH_PLAYBOOK_TO_GIT = gql`
  mutation PushPlaybookToGit($graphId: UUID!, $repositoryId: String!, $targetFolder: String) {
    pushPlaybookToGit(graphId: $graphId, repositoryId: $repositoryId, targetFolder: $targetFolder) { ok queuedCount message }
  }
`;
const CREATE_RULE_REPOSITORY = gql`
  mutation CreateRuleRepository($name: String!, $url: String!, $username: String, $token: String, $provider: String, $apiBaseUrl: String, $verifySsl: Boolean) {
    createRuleRepository(name: $name, url: $url, username: $username, token: $token, provider: $provider, apiBaseUrl: $apiBaseUrl, verifySsl: $verifySsl) {
      repository { id name url username provider apiBaseUrl verifySsl lastSync }
    }
  }
`;
const DELETE_RULE_REPOSITORY = gql`
  mutation DeleteRuleRepository($id: ID!) {
    deleteRuleRepository(id: $id) { ok }
  }
`;

// --- MISP Instances ---
const GET_MISP_INSTANCES = gql`
  query GetMISPInstances {
    mispInstances {
      id
      name
      url
      verifySsl
      authKeyHint
      createdAt
    }
  }
`;

const CREATE_MISP_INSTANCE = gql`
  mutation CreateMISPInstance($name: String!, $url: String!, $authKey: String!, $verifySsl: Boolean) {
    createMispInstance(name: $name, url: $url, authKey: $authKey, verifySsl: $verifySsl) {
      success
      message
      mispInstance { id name url verifySsl authKeyHint createdAt }
    }
  }
`;

const UPDATE_MISP_INSTANCE = gql`
  mutation UpdateMISPInstance($id: UUID!, $name: String, $url: String, $authKey: String, $verifySsl: Boolean) {
    updateMispInstance(id: $id, name: $name, url: $url, authKey: $authKey, verifySsl: $verifySsl) {
      success
      message
      mispInstance { id name url verifySsl authKeyHint createdAt }
    }
  }
`;

const DELETE_MISP_INSTANCE = gql`
  mutation DeleteMISPInstance($id: UUID!) {
    deleteMispInstance(id: $id) {
      success
      message
    }
  }
`;

const MISP_INSTANCE_LIMIT = 5;

interface MISPInstance {
  id: string;
  name: string;
  url: string;
  verifySsl: boolean;
  authKeyHint: string;
  createdAt: string;
}

interface MISPInstancesData { mispInstances: MISPInstance[] }

// --- MISP Instances Tab Component ---
const MISPInstancesTab: React.FC<{ role: string }> = ({ role }) => {
  const { message } = App.useApp();
  const { data, loading, refetch } = useQuery<MISPInstancesData>(GET_MISP_INSTANCES, { fetchPolicy: 'cache-and-network' });
  const [modalVisible, setModalVisible] = React.useState(false);
  const [editing, setEditing] = React.useState<MISPInstance | null>(null);
  const [form] = Form.useForm();

  const [createInstance, { loading: creating }] = useMutation(CREATE_MISP_INSTANCE, {
    onCompleted: (res) => {
      if (res.createMispInstance.success) {
        message.success('MISP instance added');
        refetch();
        setModalVisible(false);
        form.resetFields();
      } else {
        message.error(res.createMispInstance.message || 'Failed to add MISP instance');
      }
    },
  });
  const [updateInstance, { loading: updating }] = useMutation(UPDATE_MISP_INSTANCE, {
    onCompleted: (res) => {
      if (res.updateMispInstance.success) {
        message.success('MISP instance updated');
        refetch();
        setModalVisible(false);
        setEditing(null);
        form.resetFields();
      } else {
        message.error(res.updateMispInstance.message || 'Failed to update MISP instance');
      }
    },
  });
  const [deleteInstance] = useMutation(DELETE_MISP_INSTANCE, {
    onCompleted: (res) => {
      if (res.deleteMispInstance.success) {
        message.success('MISP instance deleted');
        refetch();
      } else {
        message.error(res.deleteMispInstance.message || 'Failed to delete MISP instance');
      }
    },
  });

  const canManage = role === 'ADMIN';
  const instances = data?.mispInstances || [];
  const atLimit = instances.length >= MISP_INSTANCE_LIMIT;

  const onAdd = () => {
    setEditing(null);
    form.resetFields();
    setModalVisible(true);
  };

  const onEdit = (inst: MISPInstance) => {
    setEditing(inst);
    form.setFieldsValue({ name: inst.name, url: inst.url, verifySsl: inst.verifySsl, authKey: '' });
    setModalVisible(true);
  };

  const onDelete = (id: string) => {
    deleteInstance({ variables: { id } });
  };

  const onModalOk = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        const vars: any = { id: editing.id, name: values.name, url: values.url, verifySsl: values.verifySsl };
        if (values.authKey) vars.authKey = values.authKey;
        updateInstance({ variables: vars });
      } else {
        createInstance({ variables: { name: values.name, url: values.url, authKey: values.authKey, verifySsl: values.verifySsl } });
      }
    } catch {
      // validation failed
    }
  };

  const mispColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'URL', dataIndex: 'url', key: 'url' },
    {
      title: 'Auth Key',
      dataIndex: 'authKeyHint',
      key: 'authKeyHint',
      render: (hint: string) => (
        <Space>
          <LockOutlined />
          <Typography.Text type="secondary">{hint}</Typography.Text>
        </Space>
      ),
    },
    {
      title: 'Verify SSL',
      dataIndex: 'verifySsl',
      key: 'verifySsl',
      render: (v: boolean) => <Tag color={v ? 'green' : 'orange'}>{v ? 'Yes' : 'No'}</Tag>,
    },
    ...(canManage ? [{
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: MISPInstance) => (
        <Space>
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(record)} />
          </Tooltip>
          <Popconfirm title="Delete this MISP instance?" onConfirm={() => onDelete(record.id)} okText="Delete" okButtonProps={{ danger: true }}>
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    }] : []),
  ];

  return (
    <Card
      loading={loading}
      extra={
        canManage && (
          <Tooltip title={atLimit ? `Maximum of ${MISP_INSTANCE_LIMIT} instances per organization` : 'Add MISP instance'}>
            <Button type="primary" icon={<PlusOutlined />} onClick={onAdd} disabled={atLimit}>
              Add Instance
            </Button>
          </Tooltip>
        )
      }
    >
      {!canManage && (
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          Only Admins can manage MISP instances.
        </Typography.Text>
      )}
      {atLimit && (
        <Typography.Text type="warning" style={{ display: 'block', marginBottom: 12 }}>
          Maximum of {MISP_INSTANCE_LIMIT} MISP instances reached.
        </Typography.Text>
      )}
      <Table
        rowKey="id"
        dataSource={instances}
        columns={mispColumns}
        pagination={false}
        locale={{ emptyText: 'No MISP instances configured. Add one to enable per-hunt MISP push.' }}
      />
      <Modal
        title={editing ? 'Edit MISP Instance' : 'Add MISP Instance'}
        open={modalVisible}
        onOk={onModalOk}
        onCancel={() => { setModalVisible(false); setEditing(null); form.resetFields(); }}
        confirmLoading={creating || updating}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ verifySsl: true }}>
          <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Name is required' }]}>
            <Input placeholder="e.g., Production MISP" />
          </Form.Item>
          <Form.Item name="url" label="URL" rules={[{ required: true, message: 'URL is required' }, { type: 'url', message: 'Enter a valid URL' }]}>
            <Input placeholder="https://misp.example.com" />
          </Form.Item>
          <Form.Item
            name="authKey"
            label="Auth Key"
            rules={editing ? [] : [{ required: true, message: 'Auth key is required' }]}
            extra={editing ? 'Leave blank to keep the existing key.' : undefined}
          >
            <Input.Password placeholder={editing ? '(unchanged)' : 'MISP API auth key'} />
          </Form.Item>
          <Form.Item name="verifySsl" label="Verify SSL" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

interface MeData { username: string; role: string }
interface Repo { id: string; name: string; url: string | null; username: string | null; provider?: string | null; apiBaseUrl?: string | null; verifySsl?: boolean; lastSync: string | null; ruleCount?: number; autoPullEnabled?: boolean; autoPullSchedule?: string; nextScheduledPull?: string | null }
interface GetRepositoriesData { me?: MeData | null; allRuleRepositories: Repo[] }
interface PullRepoResult { pullRuleRepository: { ok: boolean; message?: string; repository: { id: string; lastSync: string | null } } }
interface CreateRepoResult { createRuleRepository: { repository: Repo } }
interface DeleteRepoResult { deleteRuleRepository: { ok: boolean } }
interface GraphRow { id: string; title: string; status?: string }
interface GetGraphsData { allPlaybookGraphs: GraphRow[] }
interface PushResult { pushPlaybookToGit: { ok: boolean; queuedCount?: number; message?: string } }

const RepoListPage: React.FC = () => {
  const { message } = App.useApp();
  const { data, loading, error, refetch, startPolling, stopPolling } = useQuery<GetRepositoriesData>(GET_RULE_REPOSITORIES, { fetchPolicy: 'cache-and-network' });
  const { data: graphsData, loading: loadingGraphs } = useQuery<GetGraphsData>(GET_GRAPHS, { fetchPolicy: 'cache-first' });
  const [pullRepository, { loading: pulling }] = useMutation<PullRepoResult>(PULL_RULE_REPOSITORY);
  const [pushPlaybookToGit, { loading: pushing }] = useMutation<PushResult>(PUSH_PLAYBOOK_TO_GIT);
  const [createRepository, { loading: creating }] = useMutation<CreateRepoResult>(CREATE_RULE_REPOSITORY, {
    onCompleted: () => { message.success('Repository created'); refetch(); },
    onError: (err) => message.error(err.message || 'Create failed'),
  });
  const [deleteRepository, { loading: deleting }] = useMutation<DeleteRepoResult>(DELETE_RULE_REPOSITORY, {
    onCompleted: () => { message.success('Repository deleted'); refetch(); },
    onError: (err) => message.error(err.message || 'Delete failed'),
  });
  const UPDATE_RULE_REPOSITORY = gql`
    mutation UpdateRuleRepository($id: ID!, $url: String, $username: String, $token: String, $name: String, $provider: String, $apiBaseUrl: String, $verifySsl: Boolean, $autoPullEnabled: Boolean, $autoPullSchedule: String) {
      updateRuleRepository(id: $id, url: $url, username: $username, token: $token, name: $name, provider: $provider, apiBaseUrl: $apiBaseUrl, verifySsl: $verifySsl, autoPullEnabled: $autoPullEnabled, autoPullSchedule: $autoPullSchedule) {
        repository { id name url username provider apiBaseUrl verifySsl lastSync autoPullEnabled autoPullSchedule nextScheduledPull }
      }
    }
  `;
  interface UpdateRepoResult { updateRuleRepository: { repository: Repo } }
  const [updateRepository, { loading: saving }] = useMutation<UpdateRepoResult>(UPDATE_RULE_REPOSITORY, {
    onCompleted: () => { message.success('Repository updated'); refetch(); },
    onError: (err) => message.error(err.message || 'Update failed'),
  });

  const role = data?.me?.role || 'VIEWER';
  const canAdmin = role === 'ADMIN';

  // Modal state
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [editingRepo, setEditingRepo] = React.useState<Repo | null>(null);
  const [form] = Form.useForm();
  const [isPushModalOpen, setIsPushModalOpen] = React.useState(false);
  const [pushForm] = Form.useForm();
  const [targetRepoForPush, setTargetRepoForPush] = React.useState<Repo | null>(null);
  const [folderMode, setFolderMode] = React.useState<'auto' | 'preset' | 'new'>('auto');

  // Subtle polling + hint after pull
  const [isSyncing, setIsSyncing] = React.useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = React.useState<Date | null>(null);
  const pollingTimeoutRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (pollingTimeoutRef.current) {
        window.clearTimeout(pollingTimeoutRef.current);
      }
      stopPolling();
    };
  }, [stopPolling]);

  const openCreateModal = () => {
    setEditingRepo(null);
    form.resetFields();
    setIsModalOpen(true);
  };

  const openEditModal = (repo: Repo) => {
    setEditingRepo(repo);
    form.setFieldsValue({
      name: repo.name,
      url: repo.url || '',
      username: repo.username || '',
      provider: repo.provider || 'AUTO',
      apiBaseUrl: repo.apiBaseUrl || '',
      verifySsl: repo.verifySsl ?? true,
      token: '',
      autoPullEnabled: repo.autoPullEnabled || false,
      autoPullSchedule: repo.autoPullSchedule || 'DISABLED',
    });
    setIsModalOpen(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      if (editingRepo) {
        await updateRepository({ variables: { id: editingRepo.id, ...values } });
      } else {
        await createRepository({ variables: values });
      }
      setIsModalOpen(false);
      setEditingRepo(null);
      form.resetFields();
      setLastUpdatedAt(new Date());
    } catch (e) {
      // validation or mutation error already surfaced via message
    }
  };

  const handlePull = async (repoId: string) => {
    const result = await pullRepository({ variables: { id: repoId } });
    const pullResult = result.data?.pullRuleRepository;
    
    if (!pullResult?.ok) {
      message.error(pullResult?.message || 'Failed to queue pull request');
      return;
    }
    
    message.success(pullResult.message || 'Pull requested');
    setIsSyncing(true);
    startPolling(3000);
    if (pollingTimeoutRef.current) {
      window.clearTimeout(pollingTimeoutRef.current);
    }
    pollingTimeoutRef.current = window.setTimeout(async () => {
      stopPolling();
      setIsSyncing(false);
      await refetch();
      setLastUpdatedAt(new Date());
    }, 15000);
  };

  const openPushModal = (repo: Repo) => {
    setTargetRepoForPush(repo);
    pushForm.resetFields();
    pushForm.setFieldsValue({ folderMode: 'auto' });
    setFolderMode('auto');
    setIsPushModalOpen(true);
  };

  const handlePush = async () => {
    try {
      const values = await pushForm.validateFields();
      if (!targetRepoForPush) return;
      
      // Build target folder path
      let targetFolder = values.targetFolder;
      if (values.folderMode === 'new' && values.newFolderName) {
        targetFolder = values.newFolderName.trim();
      }
      
      const res = await pushPlaybookToGit({ 
        variables: { 
          graphId: values.graphId, 
          repositoryId: targetRepoForPush.id,
          targetFolder: targetFolder || undefined,
        } 
      });
      
      const pushResult = res.data?.pushPlaybookToGit;
      
      if (!pushResult?.ok) {
        message.error(pushResult?.message || 'Failed to queue push request');
        return;
      }
      
      const cnt = pushResult.queuedCount ?? 0;
      if (cnt > 0) {
        message.success(`Queued ${cnt} rule${cnt === 1 ? '' : 's'} for push`);
      } else {
        message.info(pushResult.message || 'No rules to push');
      }
      
      setIsPushModalOpen(false);
      setTargetRepoForPush(null);
      
      // Start brief polling only if rules were queued
      if (cnt > 0) {
        setIsSyncing(true);
        startPolling(3000);
        if (pollingTimeoutRef.current) {
          window.clearTimeout(pollingTimeoutRef.current);
        }
        pollingTimeoutRef.current = window.setTimeout(async () => {
          stopPolling();
          setIsSyncing(false);
          await refetch();
          setLastUpdatedAt(new Date());
        }, 15000);
      }
    } catch (e: any) {
      message.error(e?.message || 'Push failed');
    }
  };

  const updatedHint = React.useMemo(() => {
    if (isSyncing) return 'Syncing…';
    if (!lastUpdatedAt) return undefined;
    const diff = (Date.now() - lastUpdatedAt.getTime()) / 1000;
    if (diff < 30) return 'Updated just now';
    const minutes = Math.floor(diff / 60);
    if (minutes < 60) return `Updated ${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `Updated ${hours}h ago`;
  }, [isSyncing, lastUpdatedAt]);

  const columns = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'Git URL', dataIndex: 'url', key: 'url', render: (url: string | null) => url ? <a href={url} target="_blank" rel="noreferrer">{url}</a> : <Typography.Text type="secondary">N/A</Typography.Text> },
    { title: 'Username', dataIndex: 'username', key: 'username', render: (u: string | null) => u || <Typography.Text type="secondary">N/A</Typography.Text> },
    { title: 'Last Synced', dataIndex: 'lastSync', key: 'lastSync', render: (d: string | null) => d ? new Date(d).toLocaleString() : <Typography.Text type="secondary">Never</Typography.Text> },
    { title: 'Auto-Pull', dataIndex: 'autoPullEnabled', key: 'autoPull', render: (_: any, repo: Repo) => (
      repo.autoPullEnabled ? (
        <Tooltip title={`Pulls ${repo.autoPullSchedule?.replace('H', ' hours') || ''}`}>
          <Space>
            <ClockCircleOutlined style={{ color: '#52c41a' }} />
            <Typography.Text type="success">On</Typography.Text>
          </Space>
        </Tooltip>
      ) : (
        <Typography.Text type="secondary">Off</Typography.Text>
      )
    )},
    { title: 'Rules', dataIndex: 'ruleCount', key: 'ruleCount', render: (_: any, repo: Repo) => (
      <>{typeof repo.ruleCount === 'number' ? <Link to={`/rules?repo=${repo.id}`}>{repo.ruleCount}</Link> : 0}</>
    ) },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, repo: Repo) => (
        <Space>
          <Button type="primary" size="small" disabled={!canAdmin} loading={pulling || isSyncing}
            onClick={() => handlePull(repo.id)}
          >
            Pull
          </Button>
          <Button size="small" disabled={!canAdmin} loading={pushing || isSyncing}
            onClick={() => openPushModal(repo)}
          >
            Push
          </Button>
          <Button size="small" disabled={!canAdmin} loading={saving} onClick={() => openEditModal(repo)}>Edit</Button>
          <Popconfirm
            title="Delete this repository?"
            okButtonProps={{ danger: true }}
            okText="Delete"
            onConfirm={() => deleteRepository({ variables: { id: repo.id } })}
            disabled={!canAdmin}
          >
            <Button size="small" danger disabled={!canAdmin} loading={deleting}>Delete</Button>
          </Popconfirm>
          {!canAdmin && <Typography.Text type="secondary">Admin only</Typography.Text>}
        </Space>
      )
    }
  ];

  return (
    <div style={{ padding: 24 }}>
      <Tabs
        defaultActiveKey="repos"
        items={[
          {
            key: 'repos',
            label: 'Rule Repositories',
            children: (
              <>
                <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
                  <Space>
                    {updatedHint && <Typography.Text type="secondary">{updatedHint}</Typography.Text>}
                    <Button onClick={() => { refetch(); setLastUpdatedAt(new Date()); }}>Refresh</Button>
                    {canAdmin && (
                      <Button type="primary" onClick={openCreateModal}>New Repository</Button>
                    )}
                  </Space>
                </Space>
                {error && (
                  <div style={{ marginBottom: 16 }}>
                    <Typography.Text type="danger">{error.message}</Typography.Text>
                  </div>
                )}
                <Card>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="Supported Git Services"
                    description="Repositories can point to GitHub, GitLab, or Gitea (including self-hosted instances)."
                  />
                  <Table
                    rowKey="id"
                    loading={loading}
                    dataSource={data?.allRuleRepositories || []}
                    columns={columns as any}
                  />
                  <Modal
                    title={editingRepo ? 'Edit Repository' : 'New Repository'}
                    open={isModalOpen}
                    onOk={handleModalOk}
                    onCancel={() => { setIsModalOpen(false); setEditingRepo(null); }}
                    confirmLoading={saving || creating}
                    destroyOnClose
                  >
                    <Form layout="vertical" form={form} preserve={false} initialValues={{ verifySsl: true }}>
                      <Form.Item label="Name" name="name" rules={editingRepo ? [] : [{ required: true, message: 'Name is required' }]}>
                        <Input placeholder="My Rules Repo" disabled={false} />
                      </Form.Item>
                      <Form.Item label="Git URL" name="url" rules={editingRepo ? [] : [{ required: true, message: 'Git URL is required' }]}>
                        <Input placeholder="https://github.com/org/repo.git" />
                      </Form.Item>
                      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                        Supported services: GitHub, GitLab, and Gitea.
                      </Typography.Text>
                      <Form.Item label="Username" name="username">
                        <Input placeholder="git username (optional)" />
                      </Form.Item>
                      <Form.Item label="Provider" name="provider" initialValue="AUTO">
                        <Select
                          options={[
                            { value: 'AUTO', label: 'Auto-detect from URL' },
                            { value: 'GITHUB', label: 'GitHub' },
                            { value: 'GITLAB', label: 'GitLab' },
                            { value: 'GITEA', label: 'Gitea' },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item
                        label="API Base URL"
                        name="apiBaseUrl"
                        extra="Optional. Use for self-hosted providers (e.g., https://gitlab.example.com/api/v4)."
                        rules={[{ type: 'url', message: 'Enter a valid URL' }]}
                      >
                        <Input placeholder="https://gitlab.example.com/api/v4 (optional)" />
                      </Form.Item>
                      <Form.Item
                        label="Verify SSL"
                        name="verifySsl"
                        valuePropName="checked"
                        tooltip="Disable only for trusted self-signed certificates."
                      >
                        <Switch />
                      </Form.Item>
                      <Form.Item label="Token/Password" name="token">
                        <Input.Password placeholder="access token (optional)" autoComplete="new-password" />
                      </Form.Item>
                      
                      {editingRepo && (
                        <>
                          <Divider orientation="left" plain>
                            <Space>
                              <ClockCircleOutlined />
                              Scheduled Pull
                            </Space>
                          </Divider>
                          <Form.Item 
                            label="Enable Auto-Pull" 
                            name="autoPullEnabled" 
                            valuePropName="checked"
                            tooltip="When enabled, the repository will be automatically pulled at the scheduled interval"
                          >
                            <Switch />
                          </Form.Item>
                          <Form.Item 
                            label="Pull Schedule" 
                            name="autoPullSchedule"
                            tooltip="How often to automatically pull updates from this repository"
                          >
                            <Select
                              options={[
                                { value: 'DISABLED', label: 'Disabled' },
                                { value: '24H', label: 'Every 24 hours' },
                                { value: '48H', label: 'Every 48 hours' },
                                { value: '72H', label: 'Every 72 hours' },
                                { value: 'WEEKLY', label: 'Weekly' },
                              ]}
                            />
                          </Form.Item>
                          {editingRepo.nextScheduledPull && (
                            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                              Next scheduled pull: {new Date(editingRepo.nextScheduledPull).toLocaleString()}
                            </Typography.Text>
                          )}
                        </>
                      )}
                    </Form>
                  </Modal>
                  <Modal
                    title={targetRepoForPush ? `Push Workbench to ${targetRepoForPush.name}` : 'Push Workbench'}
                    open={isPushModalOpen}
                    onOk={handlePush}
                    onCancel={() => { setIsPushModalOpen(false); setTargetRepoForPush(null); }}
                    confirmLoading={pushing || isSyncing}
                    destroyOnClose
                    width={520}
                  >
                    <Form layout="vertical" form={pushForm} preserve={false}>
                      <Form.Item label="Workbench" name="graphId" rules={[{ required: true, message: 'Select a workbench to push' }]}>
                        <Select
                          placeholder={loadingGraphs ? 'Loading workbenches...' : 'Select a workbench'}
                          loading={loadingGraphs}
                          showSearch
                          optionFilterProp="label"
                          options={(graphsData?.allPlaybookGraphs || [])
                            .filter(g => ['APPROVED','DEPLOYED'].includes((g.status || '').toUpperCase()))
                            .map(g => ({ value: g.id, label: `${g.title}${g.status ? ` (${g.status})` : ''}` }))}
                        />
                      </Form.Item>
                      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                        Only workbenches in status APPROVED or DEPLOYED are eligible for push.
                      </Typography.Text>
                      
                      <Divider orientation="left" plain>Target Folder</Divider>
                      
                      <Form.Item name="folderMode" initialValue="auto">
                        <Radio.Group 
                          onChange={(e) => setFolderMode(e.target.value)}
                          value={folderMode}
                        >
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Radio value="auto">
                              <strong>Auto-organize by format</strong>
                              <Typography.Text type="secondary" style={{ display: 'block', marginLeft: 24 }}>
                              Rules will be placed in folders based on their format (rules/kql, rules/wazuh, etc.)
                              </Typography.Text>
                            </Radio>
                            <Radio value="preset">
                              <strong>Choose existing folder</strong>
                            </Radio>
                            <Radio value="new">
                              <strong>Create new folder</strong>
                            </Radio>
                          </Space>
                        </Radio.Group>
                      </Form.Item>
                      
                      {folderMode === 'preset' && (
                        <Form.Item 
                          name="targetFolder" 
                          label="Select folder"
                          rules={[{ required: folderMode === 'preset', message: 'Select a folder' }]}
                        >
                          <Select
                            placeholder="Select target folder"
                            showSearch
                            optionFilterProp="label"
                            options={[
                              { value: 'rules/kql', label: 'rules/kql (Kusto Query Language)' },
                              { value: 'rules/wazuh', label: 'rules/wazuh (Wazuh XML)' },
                              { value: 'rules/splunk', label: 'rules/splunk (Splunk SPL)' },
                              { value: 'rules/yara', label: 'rules/yara (YARA rules)' },
                              { value: 'rules/snort', label: 'rules/snort (Snort/Suricata)' },
                              { value: 'rules/other', label: 'rules/other (Other formats)' },
                              { value: 'detections', label: 'detections/' },
                              { value: '', label: '/ (repository root)' },
                            ]}
                          />
                        </Form.Item>
                      )}
                      
                      {folderMode === 'new' && (
                        <Form.Item 
                          name="newFolderName" 
                          label="New folder path"
                          rules={[{ required: folderMode === 'new', message: 'Enter a folder path' }]}
                          help="Use forward slashes for nested folders (e.g., detections/windows/process)"
                        >
                          <Input placeholder="rules/custom" />
                        </Form.Item>
                      )}
                    </Form>
                  </Modal>
                </Card>
              </>
            ),
          },
          {
            key: 'misp',
            label: 'MISP',
            children: <MISPInstancesTab role={role} />,
          },
        ]}
      />
    </div>
  );
};

export default RepoListPage;
export { RepoListPage };
