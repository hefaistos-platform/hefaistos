import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import {
  App,
  Card,
  Input,
  Space,
  Button,
  Typography,
  Tabs,
  Table,
  Modal,
  Form,
  Switch,
  Tooltip,
  Popconfirm,
  Tag,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, LockOutlined } from '@ant-design/icons';

// --- Git Config ---
const GET_GIT_CONFIG = gql`
  query GetGitConfig {
    me { username role }
    gitConfig: gitConfig { defaultRemote branch autoPullIntervalHours }
  }
`;

const UPDATE_GIT_CONFIG = gql`
  mutation UpdateGitConfig($defaultRemote: String, $branch: String, $autoPullIntervalHours: Int) {
    updateGitConfig(defaultRemote: $defaultRemote, branch: $branch, autoPullIntervalHours: $autoPullIntervalHours) {
      ok
      config { defaultRemote branch autoPullIntervalHours }
    }
  }
`;

const PUSH_REPOSITORY = gql`
  mutation PushRepository($remote: String, $branch: String) {
    pushRepository(remote: $remote, branch: $branch) { ok message }
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

interface MeData { username: string; role: string }
interface GitConfig { defaultRemote: string; branch: string; autoPullIntervalHours: number }
interface GetGitConfigData { me?: MeData | null; gitConfig?: GitConfig | null }
interface UpdateGitConfigResult { updateGitConfig: { ok: boolean; config: GitConfig } }
interface PushRepositoryResult { pushRepository: { ok: boolean; message?: string } }

interface MISPInstance {
  id: string;
  name: string;
  url: string;
  verifySsl: boolean;
  authKeyHint: string;
  createdAt: string;
}

interface MISPInstancesData { mispInstances: MISPInstance[] }

// --- Git Config Tab ---
const GitConfigTab: React.FC<{ role: string }> = ({ role }) => {
  const { message } = App.useApp();
  const { data, loading, error, refetch } = useQuery<GetGitConfigData>(GET_GIT_CONFIG, { fetchPolicy: 'cache-and-network' });
  const [updateGitConfig, { loading: saving }] = useMutation<UpdateGitConfigResult>(UPDATE_GIT_CONFIG, {
    onCompleted: () => { refetch(); message.success('Settings updated'); },
  });
  const [pushRepository, { loading: pushing }] = useMutation<PushRepositoryResult>(PUSH_REPOSITORY, {
    onCompleted: (res) => { message.success(res.pushRepository?.message || 'Push scheduled'); },
  });

  const canPush = role === 'ADMIN' || role === 'REVIEWER';
  const [remote, setRemote] = useState<string>(data?.gitConfig?.defaultRemote || 'origin');
  const [branch, setBranch] = useState<string>(data?.gitConfig?.branch || 'main');
  const [interval, setInterval] = useState<number>(data?.gitConfig?.autoPullIntervalHours || 12);

  return (
    <Card loading={loading}>
      {error && <Typography.Text type="danger">{error.message}</Typography.Text>}
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <div>
          <Typography.Text strong>Remote</Typography.Text>
          <Input value={remote} onChange={(e) => setRemote(e.target.value)} disabled={!canPush} />
        </div>
        <div>
          <Typography.Text strong>Branch</Typography.Text>
          <Input value={branch} onChange={(e) => setBranch(e.target.value)} disabled={!canPush} />
        </div>
        <div>
          <Typography.Text strong>Auto-PULL interval (hours)</Typography.Text>
          <Input type="number" value={interval} onChange={(e) => setInterval(parseInt(e.target.value || '0', 10))} disabled={!canPush} />
        </div>
        <Space>
          <Button type="primary" disabled={!canPush} loading={saving} onClick={() => updateGitConfig({ variables: { defaultRemote: remote, branch, autoPullIntervalHours: interval } })}>Save</Button>
          <Button type="primary" disabled={!canPush} loading={pushing} onClick={() => pushRepository({ variables: { remote, branch } })}>Push</Button>
        </Space>
        {!canPush && <Typography.Text type="secondary">Only Admin/Reviewer can edit and push repositories.</Typography.Text>}
      </Space>
    </Card>
  );
};

// --- MISP Instances Tab ---
const MISPInstancesTab: React.FC<{ role: string }> = ({ role }) => {
  const { message } = App.useApp();
  const { data, loading, refetch } = useQuery<MISPInstancesData>(GET_MISP_INSTANCES, { fetchPolicy: 'cache-and-network' });
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

  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<MISPInstance | null>(null);
  const [form] = Form.useForm();

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

  const columns = [
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
        columns={columns}
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

// --- Main Repositories Page ---
const Repositories: React.FC = () => {
  const { data } = useQuery<GetGitConfigData>(GET_GIT_CONFIG, { fetchPolicy: 'cache-and-network' });
  const role = data?.me?.role || 'VIEWER';

  return (
    <div style={{ padding: 24 }}>
      <Tabs
        defaultActiveKey="git"
        items={[
          {
            key: 'git',
            label: 'Repository Settings',
            children: <GitConfigTab role={role} />,
          },
          {
            key: 'misp',
            label: 'MISP Instances',
            children: <MISPInstancesTab role={role} />,
          },
        ]}
      />
    </div>
  );
};

export default Repositories;
