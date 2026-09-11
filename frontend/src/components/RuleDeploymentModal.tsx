/**
 * RuleDeploymentModal
 *
 * Modal dialog for deploying an OpenTide detection rule to one or more
 * SIEM/EDR platforms (Microsoft Defender, Azure Sentinel, Splunk, IBM QRadar,
 * Wazuh) via their REST APIs.
 *
 * Features:
 * - Platform selection checkboxes (only platforms with configured credentials
 *   are shown as enabled)
 * - Per-platform results table with success/failure indicator, rule ID, and
 *   deployment message
 * - Link to configure credentials for platforms that are not yet set up
 */

import React, { useState, useEffect } from 'react';
import {
  Modal,
  Checkbox,
  Button,
  Table,
  Tag,
  Space,
  Alert,
  Spin,
  Typography,
  Tooltip,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeploymentUnitOutlined,
  InfoCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery } from '@apollo/client';
import {
  DEPLOY_OPENTIDE_RULE,
  GET_PLATFORM_CREDENTIALS,
  PlatformDeploymentResult,
  PlatformCredential,
} from '../graphql/deployment';

const { Text, Title, Paragraph } = Typography;

// ---------------------------------------------------------------------------
// Platform metadata (display names, icons, descriptions)
// ---------------------------------------------------------------------------

interface PlatformMeta {
  key: string;
  label: string;
  icon: string;
  description: string;
  requiredFormat: string;
}

const PLATFORM_META: PlatformMeta[] = [
  {
    key: 'defender',
    label: 'Microsoft Defender',
    icon: '🛡️',
    description: 'Deploys KQL custom detection rules to Defender for Endpoint.',
    requiredFormat: 'kql',
  },
  {
    key: 'sentinel',
    label: 'Azure Sentinel',
    icon: '☁️',
    description: 'Creates/updates Scheduled Query Rules in Azure Sentinel.',
    requiredFormat: 'kql',
  },
  {
    key: 'splunk',
    label: 'Splunk',
    icon: '🔍',
    description: 'Creates/updates Saved Searches (correlation rules) in Splunk.',
    requiredFormat: 'spl',
  },
  {
    key: 'qradar',
    label: 'IBM QRadar',
    icon: '🔵',
    description: 'Creates custom AQL-based detection rules in QRadar.',
    requiredFormat: 'qradar',
  },
  {
    key: 'wazuh',
    label: 'Wazuh',
    icon: '🟢',
    description: 'Uploads XML rule files to the Wazuh manager via its REST API.',
    requiredFormat: 'wazuh',
  },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RuleDeploymentModalProps {
  visible: boolean;
  ruleId: string;
  ruleTitle: string;
  /** Raw rule content (OpenTide YAML) – used to determine which platforms have data */
  ruleContent: string;
  onCancel: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const RuleDeploymentModal: React.FC<RuleDeploymentModalProps> = ({
  visible,
  ruleId,
  ruleTitle,
  ruleContent,
  onCancel,
}) => {
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [deploymentResults, setDeploymentResults] = useState<PlatformDeploymentResult[]>([]);
  const [deployed, setDeployed] = useState(false);

  // Reset state when modal opens
  useEffect(() => {
    if (visible) {
      setSelectedPlatforms([]);
      setDeploymentResults([]);
      setDeployed(false);
    }
  }, [visible]);

  // Query existing platform credentials
  const { data: credData, loading: credLoading } = useQuery<{
    platformCredentials: PlatformCredential[];
  }>(GET_PLATFORM_CREDENTIALS, { skip: !visible });

  const configuredPlatforms = new Set(
    (credData?.platformCredentials ?? [])
      .filter((c) => c.enabled)
      .map((c) => c.platform)
  );

  // Detect which platforms have content in the rule YAML (client-side hint)
  const ruleHasPlatform = (platformKey: string): boolean => {
    try {
      // Very lightweight check – just look for the platform key at top level of YAML
      return ruleContent.includes(`${platformKey}:`);
    } catch {
      return false;
    }
  };

  // Deploy mutation
  const [deployRule, { loading: deploying }] = useMutation<{
    deployOpenTideRule: {
      success: boolean;
      message: string;
      results: PlatformDeploymentResult[];
    };
  }>(DEPLOY_OPENTIDE_RULE);

  const handleDeploy = async () => {
    if (selectedPlatforms.length === 0) return;

    try {
      const { data } = await deployRule({
        variables: { ruleId, platforms: selectedPlatforms },
      });
      if (data?.deployOpenTideRule) {
        setDeploymentResults(data.deployOpenTideRule.results);
        setDeployed(true);
      }
    } catch (err: any) {
      setDeploymentResults([
        {
          platform: 'System',
          success: false,
          ruleId: null,
          message: err.message ?? 'Unexpected error during deployment.',
          errors: [],
        },
      ]);
      setDeployed(true);
    }
  };

  const togglePlatform = (key: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const overallSuccess =
    deployed && deploymentResults.length > 0 && deploymentResults.every((r) => r.success);
  const hasFailures =
    deployed && deploymentResults.some((r) => !r.success);

  // ---------------------------------------------------------------------------
  // Results table columns
  // ---------------------------------------------------------------------------
  const columns = [
    {
      title: 'Platform',
      dataIndex: 'platform',
      key: 'platform',
      render: (name: string) => {
        const meta = PLATFORM_META.find(
          (m) => m.label.toLowerCase() === name.toLowerCase() || m.key === name.toLowerCase()
        );
        return (
          <Space>
            <span>{meta?.icon ?? '🔧'}</span>
            <Text strong>{name}</Text>
          </Space>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'success',
      key: 'success',
      render: (success: boolean) =>
        success ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            Success
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="error">
            Failed
          </Tag>
        ),
    },
    {
      title: 'Rule ID',
      dataIndex: 'ruleId',
      key: 'ruleId',
      render: (id: string | null) =>
        id ? (
          <Text code copyable>
            {id}
          </Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: 'Message',
      dataIndex: 'message',
      key: 'message',
      render: (msg: string, record: PlatformDeploymentResult) => (
        <Space direction="vertical" size={0}>
          <Text>{msg}</Text>
          {record.errors && record.errors.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {record.errors.map((e, i) => (
                <li key={i}>
                  <Text type="danger" style={{ fontSize: 12 }}>
                    {e}
                  </Text>
                </li>
              ))}
            </ul>
          )}
        </Space>
      ),
    },
  ];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <Modal
      title={
        <Space>
          <DeploymentUnitOutlined style={{ color: '#1890ff' }} />
          <span>Deploy Rule to Platforms</span>
        </Space>
      }
      open={visible}
      onCancel={onCancel}
      footer={null}
      width={760}
      destroyOnClose
    >
      {/* Rule info */}
      <Paragraph>
        <Text strong>Rule: </Text>
        <Text>{ruleTitle}</Text>
      </Paragraph>

      {!deployed && (
        <>
          {/* Platform selection */}
          <Title level={5} style={{ marginBottom: 8 }}>
            Select target platforms
          </Title>

          {credLoading ? (
            <Spin size="small" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
              {PLATFORM_META.map((platform) => {
                const hasCredentials = configuredPlatforms.has(platform.key);
                const hasContent = ruleHasPlatform(platform.key);
                const isChecked = selectedPlatforms.includes(platform.key);

                return (
                  <div
                    key={platform.key}
                    style={{
                      padding: '10px 14px',
                      border: `1px solid ${isChecked ? '#1890ff' : '#d9d9d9'}`,
                      borderRadius: 8,
                      background: isChecked ? '#e6f7ff' : '#fafafa',
                      cursor: hasCredentials ? 'pointer' : 'not-allowed',
                      opacity: hasCredentials ? 1 : 0.55,
                    }}
                    onClick={() => hasCredentials && togglePlatform(platform.key)}
                  >
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Space>
                        <Checkbox
                          checked={isChecked}
                          disabled={!hasCredentials}
                          onChange={() => hasCredentials && togglePlatform(platform.key)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <span style={{ fontSize: 18 }}>{platform.icon}</span>
                        <div>
                          <Text strong>{platform.label}</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {platform.description}
                          </Text>
                        </div>
                      </Space>
                      <Space size={4}>
                        {hasContent && (
                          <Tooltip title="Rule contains platform-specific query">
                            <Tag color="blue" style={{ fontSize: 11 }}>
                              Has query
                            </Tag>
                          </Tooltip>
                        )}
                        {!hasCredentials && (
                          <Tooltip title="Configure credentials in Settings to enable this platform">
                            <Tag
                              icon={<SettingOutlined />}
                              color="warning"
                              style={{ fontSize: 11 }}
                            >
                              No credentials
                            </Tag>
                          </Tooltip>
                        )}
                      </Space>
                    </Space>
                  </div>
                );
              })}
            </div>
          )}

          {/* No credentials hint */}
          {!credLoading && configuredPlatforms.size === 0 && (
            <Alert
              type="info"
              icon={<InfoCircleOutlined />}
              showIcon
              message="No platform credentials configured"
              description={
                <>
                  Configure API credentials for each platform in{' '}
                  <strong>Settings → Platform Credentials</strong> before deploying rules.
                </>
              }
              style={{ marginBottom: 16 }}
            />
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button onClick={onCancel}>Cancel</Button>
            <Button
              type="primary"
              icon={<DeploymentUnitOutlined />}
              disabled={selectedPlatforms.length === 0}
              loading={deploying}
              onClick={handleDeploy}
            >
              Deploy to {selectedPlatforms.length || ''} platform
              {selectedPlatforms.length !== 1 ? 's' : ''}
            </Button>
          </div>
        </>
      )}

      {/* Results */}
      {deployed && (
        <>
          {overallSuccess && (
            <Alert
              type="success"
              showIcon
              message="All deployments completed successfully!"
              style={{ marginBottom: 16 }}
            />
          )}
          {hasFailures && !overallSuccess && (
            <Alert
              type="warning"
              showIcon
              message="Some deployments failed. Review the table below."
              style={{ marginBottom: 16 }}
            />
          )}

          <Table<PlatformDeploymentResult>
            dataSource={deploymentResults}
            columns={columns}
            rowKey="platform"
            pagination={false}
            size="small"
            style={{ marginBottom: 16 }}
          />

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button
              onClick={() => {
                setDeployed(false);
                setDeploymentResults([]);
                setSelectedPlatforms([]);
              }}
            >
              Deploy Again
            </Button>
            <Button type="primary" onClick={onCancel}>
              Close
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
};

export default RuleDeploymentModal;
