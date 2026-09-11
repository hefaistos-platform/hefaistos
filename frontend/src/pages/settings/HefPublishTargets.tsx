/**
 * HefPublishTargets – CRUD UI for OpenTIDE HEF Publish Targets.
 *
 * Embedded inside ``ConfigurationPage`` Platforms tab so organisation admins
 * can manage the publish profiles that pre-fill the "Publish OpenTIDE HEF"
 * section on the Workbench Detail page (Export/Import → Repository tab).
 *
 * A "publish target" stores reusable defaults: which
 * :class:`RuleRepository` to push to, the branch, the target folder, and the
 * list of default deployment platforms.  Target rows correspond 1:1 to
 * ``organizations.OpenTidePublishProfile`` records on the backend.
 */

import React, { useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  GithubOutlined,
} from '@ant-design/icons';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';

import {
  GET_HEF_PUBLISH_PROFILES,
  SET_HEF_PUBLISH_PROFILE,
  DELETE_HEF_PUBLISH_PROFILE,
  HefPublishProfile,
} from '../../graphql/hefPublishProfiles';

const { Title, Text } = Typography;

const GET_RULE_REPOSITORIES_FOR_HEF = gql`
  query GetRuleRepositoriesForHefTargets {
    allRuleRepositories {
      id
      name
      url
      provider
    }
  }
`;

interface RuleRepositoryOption {
  id: string;
  name: string;
  url: string | null;
  provider?: string | null;
}

const PLATFORM_OPTIONS = [
  { label: 'Microsoft Defender', value: 'defender' },
  { label: 'Azure Sentinel', value: 'sentinel' },
  { label: 'Splunk', value: 'splunk' },
  { label: 'IBM QRadar', value: 'qradar' },
  { label: 'Wazuh', value: 'wazuh' },
];

interface ProfileFormValues {
  name: string;
  repositoryId: string;
  branch?: string;
  targetFolder?: string;
  pushPlatformRules?: boolean;
  enabledPlatforms?: string[];
  useGraphConfiguredPlatforms?: boolean;
  kqlTargetPolicy?: 'defender' | 'sentinel' | 'both';
  enabled?: boolean;
}

const HefPublishTargets: React.FC = () => {
  const { message } = App.useApp();
  const [form] = Form.useForm<ProfileFormValues>();
  const [editing, setEditing] = useState<HefPublishProfile | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const { data: profilesData, loading: profilesLoading, refetch } = useQuery<{
    opentideHefPublishProfiles: HefPublishProfile[];
  }>(GET_HEF_PUBLISH_PROFILES, { fetchPolicy: 'cache-and-network' });

  const { data: reposData, loading: reposLoading } = useQuery<{
    allRuleRepositories: RuleRepositoryOption[];
  }>(GET_RULE_REPOSITORIES_FOR_HEF);

  const [setProfile, { loading: saving }] = useMutation(SET_HEF_PUBLISH_PROFILE);
  const [deleteProfile] = useMutation(DELETE_HEF_PUBLISH_PROFILE);

  const repositoryOptions = useMemo(
    () => reposData?.allRuleRepositories ?? [],
    [reposData],
  );

  const profiles = profilesData?.opentideHefPublishProfiles ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      branch: 'main',
      enabled: true,
      pushPlatformRules: false,
      useGraphConfiguredPlatforms: true,
      enabledPlatforms: [],
      kqlTargetPolicy: 'defender',
    });
    setModalOpen(true);
  };

  const openEdit = (profile: HefPublishProfile) => {
    setEditing(profile);
    form.setFieldsValue({
      name: profile.name,
      repositoryId: profile.repositoryId,
      branch: profile.branch || 'main',
      targetFolder: profile.targetFolder || '',
      pushPlatformRules: profile.pushPlatformRules ?? false,
      enabledPlatforms: profile.enabledPlatforms || [],
      useGraphConfiguredPlatforms: profile.useGraphConfiguredPlatforms,
      kqlTargetPolicy: profile.kqlTargetPolicy || 'defender',
      enabled: profile.enabled,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    let values: ProfileFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    try {
      const result = await setProfile({
        variables: {
          id: editing?.id,
          name: values.name,
          repositoryId: values.repositoryId,
          branch: values.branch || 'main',
          targetFolder: values.targetFolder || '',
          pushPlatformRules: values.pushPlatformRules ?? false,
          enabledPlatforms: values.enabledPlatforms ?? [],
          useGraphConfiguredPlatforms: values.useGraphConfiguredPlatforms ?? true,
          kqlTargetPolicy: values.kqlTargetPolicy ?? 'defender',
          enabled: values.enabled ?? true,
        },
      });

      if (result.data?.setOpenTidePublishProfile?.success) {
        message.success(
          editing
            ? 'HEF publish target updated'
            : 'HEF publish target created',
        );
        setModalOpen(false);
        setEditing(null);
        refetch();
      } else {
        message.error(
          result.data?.setOpenTidePublishProfile?.message || 'Save failed',
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save target';
      message.error(msg);
    }
  };

  const handleDelete = async (profile: HefPublishProfile) => {
    try {
      const result = await deleteProfile({ variables: { id: profile.id } });
      if (result.data?.deleteOpenTidePublishProfile?.success) {
        message.success('HEF publish target deleted');
        refetch();
      } else {
        message.error(
          result.data?.deleteOpenTidePublishProfile?.message || 'Delete failed',
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete target';
      message.error(msg);
    }
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, profile: HefPublishProfile) => (
        <Space>
          <strong>{text}</strong>
          {!profile.enabled && <Tag color="default">Disabled</Tag>}
        </Space>
      ),
    },
    {
      title: 'Repository',
      key: 'repository',
      render: (_: unknown, profile: HefPublishProfile) => (
        <Space size="small">
          <GithubOutlined />
          <span>{profile.repositoryName || profile.repositoryUrl || '—'}</span>
        </Space>
      ),
    },
    {
      title: 'Branch',
      dataIndex: 'branch',
      key: 'branch',
      width: 120,
    },
    {
      title: 'Target Folder',
      dataIndex: 'targetFolder',
      key: 'targetFolder',
      render: (value: string) => value || <Text type="secondary">(repo root)</Text>,
    },
    {
      title: 'Default Platforms',
      key: 'enabledPlatforms',
      render: (_: unknown, profile: HefPublishProfile) => {
        if (!profile.enabledPlatforms?.length) {
          return profile.useGraphConfiguredPlatforms ? (
            <Text type="secondary">Use workbench platforms</Text>
          ) : (
            <Text type="secondary">None</Text>
          );
        }
        return (
          <Space wrap>
            {profile.enabledPlatforms.map((p) => (
              <Tag key={p}>{p}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: 'KQL Target',
      key: 'kqlTargetPolicy',
      width: 160,
      render: (_: unknown, profile: HefPublishProfile) => {
        const value = profile.kqlTargetPolicy || 'defender';
        const labelMap: Record<string, string> = {
          defender: 'Defender',
          sentinel: 'Sentinel',
          both: 'Both',
        };
        return <Tag color="geekblue">{labelMap[value] || value}</Tag>;
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 160,
      render: (_: unknown, profile: HefPublishProfile) => (
        <Space>
          <Tooltip title="Edit">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEdit(profile)}
            />
          </Tooltip>
          <Popconfirm
            title="Delete this publish target?"
            description="Existing publish jobs that referenced it will keep their history."
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(profile)}
          >
            <Tooltip title="Delete">
              <Button type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <span>OpenTIDE HEF Publish Targets</span>
          <Tag color="blue">Admin</Tag>
        </Space>
      }
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openCreate}
          disabled={reposLoading || repositoryOptions.length === 0}
        >
          New Target
        </Button>
      }
      style={{ marginBottom: 24 }}
    >
      <Alert
        message="What is an OpenTIDE HEF Publish Target?"
        description={
          <span>
            A reusable preset that pre-fills the
            <em> Publish OpenTIDE HEF </em>
            section on the Workbench Detail page
            (Export/Import → Repository tab). It binds a repository to a
            supported Git service (GitHub, GitLab, or Gitea),
            {' '}
            default branch, target folder, and list of deployment platforms
            (Defender / Sentinel / Splunk / QRadar / Wazuh). When a publish
            runs, the workbench is compiled into TVM/DOM/MDR YAML, committed
            to the configured repository, and the resulting OpenTIDE
            rule is deployed to the selected platforms using the credentials
            configured below.
          </span>
        }
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      {profilesLoading ? (
        <Spin />
      ) : (
        <Table
          rowKey="id"
          dataSource={profiles}
          columns={columns}
          pagination={false}
          locale={{
            emptyText: repositoryOptions.length
              ? 'No HEF publish targets configured yet. Click "New Target" to create one.'
              : 'No repositories are configured yet — add one in Settings → Repositories before creating a HEF publish target.',
          }}
        />
      )}

      <Modal
        title={editing ? 'Edit HEF Publish Target' : 'New HEF Publish Target'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onOk={handleSubmit}
        confirmLoading={saving}
        okText={editing ? 'Save' : 'Create'}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            branch: 'main',
            enabled: true,
            pushPlatformRules: false,
            useGraphConfiguredPlatforms: true,
            enabledPlatforms: [],
            kqlTargetPolicy: 'defender',
          }}
        >
          <Form.Item
            name="name"
            label="Name"
            rules={[{ required: true, message: 'Name is required' }]}
            extra="A short, unique label shown in the Workbench publish dropdown."
          >
            <Input placeholder="e.g. Production – HEF main" />
          </Form.Item>

          <Form.Item
            name="repositoryId"
            label="Repository"
            rules={[{ required: true, message: 'Repository is required' }]}
            extra="Any configured repository from Settings → Repositories is eligible (GitHub, GitLab, or Gitea)."
          >
            <Select
              placeholder="Select a configured repository"
              loading={reposLoading}
              options={repositoryOptions.map((repo) => ({
                value: repo.id,
                label: `${repo.name}${repo.url ? ` (${repo.url})` : ''}${repo.provider ? ` [${repo.provider}]` : ''}`,
              }))}
            />
          </Form.Item>

          <Form.Item name="branch" label="Branch">
            <Input placeholder="main" />
          </Form.Item>

          <Form.Item
            name="targetFolder"
            label="Target Folder (optional)"
            extra="Sub-folder inside the repository where TVM/DOM/MDR YAML files will be written."
          >
            <Input placeholder="e.g. content/hefaistos" />
          </Form.Item>

          <Form.Item
            name="pushPlatformRules"
            label="Push individual platform rule files"
            valuePropName="checked"
            extra="Also save standalone rule files in kql/, splunk/, sigma/, wazuh/, and qradar/."
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="enabledPlatforms"
            label="Default Deployment Platforms"
            extra="If left empty, the workbench's configured platforms (or none) are used."
          >
            <Select mode="multiple" options={PLATFORM_OPTIONS} placeholder="Select platforms" />
          </Form.Item>

          <Form.Item
            name="useGraphConfiguredPlatforms"
            label="Fall back to workbench-configured platforms"
            valuePropName="checked"
            extra="When enabled and no default platforms are set, use the platforms configured on the workbench."
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="kqlTargetPolicy"
            label="KQL Target Policy"
            extra="How KQL platform values are resolved during publish."
          >
            <Select
              options={[
                { label: 'Defender only', value: 'defender' },
                { label: 'Sentinel only', value: 'sentinel' },
                { label: 'Defender + Sentinel', value: 'both' },
              ]}
            />
          </Form.Item>

          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default HefPublishTargets;
