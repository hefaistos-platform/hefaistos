/**
 * PlatformCredentials settings page.
 *
 * Allows organisation admins to configure, save, and test API credentials
 * for each supported SIEM/EDR platform (Microsoft Defender, Azure Sentinel,
 * Splunk, IBM QRadar, Wazuh).  Credentials are stored encrypted on the backend.
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  Tooltip,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { App } from 'antd';
import { useMutation, useQuery } from '@apollo/client';
import {
  GET_PLATFORM_CREDENTIALS,
  SET_PLATFORM_CREDENTIAL,
  DELETE_PLATFORM_CREDENTIAL,
  TEST_PLATFORM_CONNECTION,
  PlatformCredential,
} from '../../graphql/deployment';

const { Title, Text } = Typography;

// ---------------------------------------------------------------------------
// Platform metadata
// ---------------------------------------------------------------------------

interface PlatformMeta {
  key: string;
  label: string;
  icon: string;
  fields: FieldDef[];
}

interface FieldDef {
  name: string;
  label: string;
  placeholder?: string;
  secret?: boolean;
  required?: boolean;
  type?: string;
}

const PLATFORMS: PlatformMeta[] = [
  {
    key: 'defender',
    label: 'Microsoft Defender for Endpoint',
    icon: '🛡️',
    fields: [
      { name: 'tenant_id', label: 'Azure Tenant ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', required: true },
      { name: 'client_id', label: 'Application (Client) ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', required: true },
      { name: 'client_secret', label: 'Client Secret', secret: true, required: true },
    ],
  },
  {
    key: 'sentinel',
    label: 'Azure Sentinel',
    icon: '🔵',
    fields: [
      { name: 'tenant_id', label: 'Tenant ID', required: true },
      { name: 'client_id', label: 'Client ID', required: true },
      { name: 'client_secret', label: 'Client Secret', secret: true, required: true },
      { name: 'subscription_id', label: 'Subscription ID', required: true },
      { name: 'resource_group', label: 'Resource Group', placeholder: 'e.g., rg-sentinel-prod', required: true },
      { name: 'workspace_name', label: 'Log Analytics Workspace', placeholder: 'e.g., sentinel-workspace-prod', required: true },
    ],
  },
  {
    key: 'splunk',
    label: 'Splunk Enterprise',
    icon: '🟢',
    fields: [
      { name: 'splunk_url', label: 'Splunk URL', placeholder: 'https://splunk.example.com:8089', required: true },
      { name: 'username', label: 'Username', required: true },
      { name: 'password', label: 'Password', secret: true, required: true },
      { name: 'alert_email', label: 'Alert Email (Optional)', placeholder: 'soc@example.com', type: 'email' },
    ],
  },
  {
    key: 'qradar',
    label: 'IBM QRadar',
    icon: '🟣',
    fields: [
      { name: 'qradar_url', label: 'QRadar Console URL', placeholder: 'https://qradar.example.com', required: true },
      { name: 'sec_token', label: 'SEC Token', placeholder: 'Enter SEC authorization token', secret: true, required: true },
    ],
  },
  {
    key: 'wazuh',
    label: 'Wazuh Manager',
    icon: '🟠',
    fields: [
      { name: 'wazuh_url', label: 'Wazuh API URL', placeholder: 'https://wazuh.example.com:55000', required: true },
      { name: 'username', label: 'Username', required: true },
      { name: 'password', label: 'Password', secret: true, required: true },
    ],
  },
];

// ---------------------------------------------------------------------------
// Single platform card
// ---------------------------------------------------------------------------

interface PlatformCardProps {
  meta: PlatformMeta;
  credentials: PlatformCredential[];
  onSave: (
    platform: string,
    profileName: string,
    setDefault: boolean,
    values: Record<string, unknown>,
  ) => Promise<void>;
  onTest: (platform: string, profileName: string) => Promise<void>;
  onDelete: (platform: string, profileName: string) => Promise<void>;
  testing: boolean;
  saving: boolean;
}

const PlatformCard: React.FC<PlatformCardProps> = ({
  meta,
  credentials,
  onSave,
  onTest,
  onDelete,
  testing,
  saving,
}) => {
  const [form] = Form.useForm();
  const profileName = (Form.useWatch('profileName', form) as string | undefined)?.trim() || 'default';

  const availableProfiles = useMemo(() => {
    const sorted = [...credentials].sort((a, b) => {
      if (a.isDefault !== b.isDefault) return a.isDefault ? -1 : 1;
      return a.profileName.localeCompare(b.profileName);
    });
    return sorted.map((c) => c.profileName);
  }, [credentials]);

  const activeCredential = useMemo(
    () => credentials.find((c) => c.profileName === profileName),
    [credentials, profileName],
  );

  useEffect(() => {
    const preferredProfile = credentials.find((c) => c.isDefault)?.profileName
      || credentials[0]?.profileName
      || 'default';
    form.setFieldsValue({
      profileName: preferredProfile,
      enabled: credentials.find((c) => c.profileName === preferredProfile)?.enabled ?? true,
      setDefault: credentials.find((c) => c.profileName === preferredProfile)?.isDefault ?? false,
    });
  }, [credentials, form]);

  useEffect(() => {
    if (!activeCredential) {
      return;
    }
    form.setFieldsValue({
      enabled: activeCredential.enabled,
      setDefault: activeCredential.isDefault,
    });
  }, [activeCredential, form]);

  const statusIcon = activeCredential?.testStatus === true
    ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
    : activeCredential?.testStatus === false
      ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      : null;

  const cardTitle = (
    <Space>
      <span>{meta.icon}</span>
      <span>{meta.label}</span>
      {statusIcon}
      {activeCredential?.hasCredentials && (
        <Tag color="blue" style={{ fontSize: 11 }}>Configured</Tag>
      )}
      {activeCredential?.enabled && activeCredential?.hasCredentials && (
        <Tag color="green" style={{ fontSize: 11 }}>Enabled</Tag>
      )}
      <Tag color={activeCredential?.isDefault ? 'gold' : 'default'} style={{ fontSize: 11 }}>
        Profile: {profileName}
      </Tag>
    </Space>
  );

  const handleFinish = (values: Record<string, unknown>) => {
    const { profileName: profile, setDefault, ...rest } = values;
    onSave(
      meta.key,
      String(profile || 'default').trim() || 'default',
      Boolean(setDefault),
      rest,
    );
  };

  return (
    <Card title={cardTitle} style={{ marginBottom: 16 }}>
      {activeCredential?.lastTested && (
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
          Last tested: {new Date(activeCredential.lastTested).toLocaleString()}
          {activeCredential.testMessage && ` — ${activeCredential.testMessage}`}
        </Text>
      )}

      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        initialValues={{ enabled: true, setDefault: false, profileName: 'default' }}
      >
        <Form.Item
          name="profileName"
          label="Credential profile"
          rules={[{ required: true, message: 'Credential profile is required' }]}
        >
          <Input placeholder="default" />
        </Form.Item>
        {availableProfiles.length > 0 && (
          <Space size={[4, 4]} wrap style={{ marginBottom: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>Existing:</Text>
            {availableProfiles.map((name) => (
              <Tag
                key={name}
                color={name === profileName ? 'blue' : 'default'}
                style={{ cursor: 'pointer' }}
                onClick={() => form.setFieldsValue({ profileName: name })}
              >
                {name}
              </Tag>
            ))}
          </Space>
        )}

        <Form.Item name="enabled" label="Enable for deployment" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="setDefault" label="Set this profile as platform default" valuePropName="checked">
          <Switch />
        </Form.Item>

        {meta.fields.map((f) => (
          <Form.Item
            key={f.name}
            name={f.name}
            label={f.label}
            rules={f.required ? [{ required: true, message: `${f.label} is required` }] : []}
          >
            {f.secret ? (
              <Input.Password placeholder={f.placeholder || (activeCredential?.hasCredentials ? '(stored - enter to replace)' : '')} />
            ) : (
              <Input placeholder={f.placeholder} type={f.type} />
            )}
          </Form.Item>
        ))}

        <Space>
          <Button type="primary" htmlType="submit" loading={saving}>
            Save {meta.label} Config
          </Button>
          <Button
            onClick={() => onTest(meta.key, profileName)}
            loading={testing}
            disabled={!activeCredential?.hasCredentials}
          >
            Test Connection
          </Button>
          {activeCredential?.hasCredentials && (
            <Tooltip title="Remove stored credentials">
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={() => onDelete(meta.key, profileName)}
              >
                Remove
              </Button>
            </Tooltip>
          )}
        </Space>
      </Form>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Main PlatformCredentials page
// ---------------------------------------------------------------------------

const PlatformCredentials: React.FC = () => {
  const { message } = App.useApp();

  const { data, loading, refetch } = useQuery<{ platformCredentials: PlatformCredential[] }>(
    GET_PLATFORM_CREDENTIALS,
    { fetchPolicy: 'cache-and-network' },
  );

  const [setPlatformCredential] = useMutation(SET_PLATFORM_CREDENTIAL);
  const [deletePlatformCredential] = useMutation(DELETE_PLATFORM_CREDENTIAL);
  const [testPlatformConnection] = useMutation(TEST_PLATFORM_CONNECTION);

  const [testingPlatform, setTestingPlatform] = useState<string | null>(null);
  const [savingPlatform, setSavingPlatform] = useState<string | null>(null);

  const credMap = useMemo(() => {
    const grouped = new Map<string, PlatformCredential[]>();
    (data?.platformCredentials ?? []).forEach((credential) => {
      const list = grouped.get(credential.platform) ?? [];
      list.push(credential);
      grouped.set(credential.platform, list);
    });
    return grouped;
  }, [data?.platformCredentials]);

  const handleSave = async (
    platform: string,
    profileName: string,
    setDefault: boolean,
    values: Record<string, unknown>,
  ) => {
    const { enabled, ...credFields } = values as { enabled: boolean; [k: string]: unknown };

    // Filter out empty/blank credential fields so we don't overwrite stored values with blanks
    const filteredCreds = Object.fromEntries(
      Object.entries(credFields).filter(([, v]) => v != null && v !== ''),
    );

    const normalizedProfile = profileName || 'default';
    setSavingPlatform(`${platform}:${normalizedProfile}`);
    try {
      const result = await setPlatformCredential({
        variables: {
          platform,
          credentials: JSON.stringify(filteredCreds),
          profileName: normalizedProfile,
          setDefault,
          enabled: enabled ?? true,
        },
      });

      if (result.data?.setPlatformCredential?.success) {
        message.success('Credentials saved successfully');
        refetch();
      } else {
        message.error(result.data?.setPlatformCredential?.message || 'Save failed');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save credentials';
      message.error(msg);
    } finally {
      setSavingPlatform(null);
    }
  };

  const handleTest = async (platform: string, profileName: string) => {
    const normalizedProfile = profileName || 'default';
    setTestingPlatform(`${platform}:${normalizedProfile}`);
    try {
      const result = await testPlatformConnection({
        variables: {
          platform,
          profileName: normalizedProfile,
        },
      });
      if (result.data?.testPlatformConnection?.success) {
        message.success('Connection successful!');
      } else {
        message.error(result.data?.testPlatformConnection?.message || 'Connection failed');
      }
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection test failed';
      message.error(msg);
    } finally {
      setTestingPlatform(null);
    }
  };

  const handleDelete = async (platform: string, profileName: string) => {
    try {
      const result = await deletePlatformCredential({
        variables: {
          platform,
          profileName: profileName || 'default',
        },
      });
      if (result.data?.deletePlatformCredential?.success) {
        message.success('Credentials removed');
        refetch();
      } else {
        message.error(result.data?.deletePlatformCredential?.message || 'Delete failed');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to remove credentials';
      message.error(msg);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '48px auto' }} />;

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 0' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ marginBottom: 4 }}>Platform Credentials</Title>
        <Text type="secondary">
          Configure API credentials for SIEM/EDR platform integrations. Credentials are encrypted at rest.
        </Text>
      </div>

      <Alert
        message="Security Notice"
        description="Credentials are encrypted using AES-256 (Fernet) and stored securely. Never share API keys or tokens."
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      {PLATFORMS.map((meta) => (
        <PlatformCard
          key={meta.key}
          meta={meta}
          credentials={credMap.get(meta.key) ?? []}
          onSave={handleSave}
          onTest={handleTest}
          onDelete={handleDelete}
          testing={Boolean(testingPlatform?.startsWith(`${meta.key}:`))}
          saving={Boolean(savingPlatform?.startsWith(`${meta.key}:`))}
        />
      ))}
    </div>
  );
};

export default PlatformCredentials;
