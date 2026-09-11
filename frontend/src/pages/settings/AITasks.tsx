import React, { useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Card, Modal, Space, Switch, Table, Tag, Tooltip, Typography, message, theme } from 'antd';

const { Text } = Typography;

const GET_ORG_AI_TASK_CONFIGS = gql`
  query GetOrgAiTaskConfigs {
    orgAiTaskConfigs {
      taskKey
      title
      description
      aiRequired
      enabled
      schedule
      dayOfWeek
      dayOfMonth
      runHour
      runMinute
      nextRunAt
      lastRunAt
      lastStatus
      lastMessage
      updatedAt
    }
  }
`;

const GET_ORG_AI_TASK_RUNS = gql`
  query GetOrgAiTaskRuns($limit: Int, $taskKey: String) {
    orgAiTaskRuns(limit: $limit, taskKey: $taskKey) {
      id
      taskKey
      title
      status
      trigger
      startedAt
      completedAt
      durationMs
      outputSummary
      errorMessage
      runByUsername
    }
  }
`;

const GET_RULE_REPOSITORY_RAG_HEALTH = gql`
  query GetRuleRepositoryRagHealth {
    ruleRepositoryRagHealth {
      repositoryId
      repositoryName
      ragSyncEnabled
      ragLastSyncStatus
      ragLastSynced
      ragLastSyncedTemplates
      ingestedFiles
      failedFiles
      qdrantPointCount
      qdrantStatus
      qdrantError
    }
  }
`;

const SET_ORG_AI_TASK_CONFIG = gql`
  mutation SetOrgAiTaskConfig(
    $taskKey: String!
    $enabled: Boolean
    $schedule: String
    $dayOfWeek: Int
    $dayOfMonth: Int
    $runHour: Int
    $runMinute: Int
  ) {
    setOrgAiTaskConfig(
      taskKey: $taskKey
      enabled: $enabled
      schedule: $schedule
      dayOfWeek: $dayOfWeek
      dayOfMonth: $dayOfMonth
      runHour: $runHour
      runMinute: $runMinute
    ) {
      success
      message
    }
  }
`;

const RUN_ORG_AI_TASK_NOW = gql`
  mutation RunOrgAiTaskNow($taskKey: String!) {
    runOrgAiTaskNow(taskKey: $taskKey) {
      success
      message
      run {
        id
        taskKey
        status
        trigger
        startedAt
        completedAt
        durationMs
        outputSummary
        errorMessage
      }
    }
  }
`;

interface TaskConfig {
  taskKey: string;
  title: string;
  description: string;
  aiRequired: boolean;
  enabled: boolean;
  schedule: 'DAILY' | 'WEEKLY' | 'MONTHLY';
  dayOfWeek: number;
  dayOfMonth: number;
  runHour: number;
  runMinute: number;
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  lastStatus?: 'SUCCESS' | 'FAILED' | 'SKIPPED' | null;
  lastMessage?: string | null;
}

interface TaskRun {
  id: string;
  taskKey: string;
  title: string;
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED';
  trigger: 'SCHEDULED' | 'MANUAL';
  startedAt?: string | null;
  completedAt?: string | null;
  durationMs?: number | null;
  outputSummary?: string | null;
  errorMessage?: string | null;
  runByUsername?: string | null;
}

interface RagHealthRow {
  repositoryId: string;
  repositoryName: string;
  ragSyncEnabled: boolean;
  ragLastSyncStatus?: string | null;
  ragLastSynced?: string | null;
  ragLastSyncedTemplates?: number | null;
  ingestedFiles?: number | null;
  failedFiles?: number | null;
  qdrantPointCount?: number | null;
  qdrantStatus?: string | null;
  qdrantError?: string | null;
}

const SCHEDULE_OPTIONS = [
  { value: 'DAILY', label: 'Daily' },
  { value: 'WEEKLY', label: 'Weekly' },
  { value: 'MONTHLY', label: 'Monthly' },
];

const WEEKDAY_OPTIONS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
];

const HOUR_OPTIONS = Array.from({ length: 24 }).map((_, hour) => ({
  value: hour,
  label: `${String(hour).padStart(2, '0')}:00`,
}));

const MINUTE_OPTIONS = [0, 15, 30, 45].map((minute) => ({
  value: minute,
  label: String(minute).padStart(2, '0'),
}));

const MONTH_DAY_OPTIONS = Array.from({ length: 28 }).map((_, index) => ({
  value: index + 1,
  label: `Day ${index + 1}`,
}));

const SCHEDULE_VALUES = new Set<string>(SCHEDULE_OPTIONS.map((option) => option.value));
const MINUTE_VALUES = new Set<number>(MINUTE_OPTIONS.map((option) => option.value));

const clampInt = (value: unknown, min: number, max: number, fallback: number): number => {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  const rounded = Math.round(parsed);
  if (rounded < min) return min;
  if (rounded > max) return max;
  return rounded;
};

const normalizeScheduleValue = (value: unknown): TaskConfig['schedule'] => {
  const normalized = String(value || '').toUpperCase().trim();
  if (SCHEDULE_VALUES.has(normalized)) {
    return normalized as TaskConfig['schedule'];
  }
  return 'WEEKLY';
};

const REPORT_TASK_KEYS = new Set<string>([
  'coverage_gap_digest',
  'detection_debt_snapshot',
  'executive_risk_narrative',
  'compliance_evidence_draft',
  'program_review_digest',
]);

const statusColor = (status?: string | null): string => {
  if (status === 'SUCCESS') return 'green';
  if (status === 'FAILED') return 'red';
  if (status === 'SKIPPED') return 'orange';
  return 'default';
};

const qdrantStatusColor = (status?: string | null): string => {
  if (status === 'OK') return 'green';
  if (status === 'ERROR') return 'red';
  if (status === 'DISABLED') return 'default';
  return 'orange';
};

const formatDateTime = (value?: string | null): string => (value ? new Date(value).toLocaleString() : 'N/A');

const compactText = (value?: string | null, max = 220): string => {
  const raw = (value || '').trim();
  if (!raw) return '';
  if (raw.length <= max) return raw;
  return `${raw.slice(0, max - 3)}...`;
};

const getRunOutputText = (run: TaskRun): string => (run.outputSummary || run.errorMessage || '').trim();

const sanitizeFilenamePart = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64) || 'task';

const triggerText = (value?: string | null): string => (value || 'MANUAL').toLowerCase();

const buildConfigVariables = (task: TaskConfig, patch: Partial<TaskConfig>) => {
  const merged = { ...task, ...patch };
  return {
    taskKey: task.taskKey,
    enabled: merged.enabled,
    schedule: merged.schedule,
    dayOfWeek: merged.dayOfWeek,
    dayOfMonth: merged.dayOfMonth,
    runHour: merged.runHour,
    runMinute: merged.runMinute,
  };
};

const AITasksTab: React.FC<{ canManage: boolean }> = ({ canManage }) => {
  const { token } = theme.useToken();
  const [savingTaskKey, setSavingTaskKey] = useState<string | null>(null);
  const [runningTaskKey, setRunningTaskKey] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<TaskRun | null>(null);
  const [selectedTaskOutput, setSelectedTaskOutput] = useState<{ task: TaskConfig; text: string } | null>(null);

  const outputBlockStyle: React.CSSProperties = {
    whiteSpace: 'pre-wrap',
    background: token.colorFillAlter,
    color: token.colorText,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadius,
  };

  const { data, loading, error, refetch } = useQuery<{ orgAiTaskConfigs: TaskConfig[] }>(
    GET_ORG_AI_TASK_CONFIGS,
    {
      fetchPolicy: 'cache-and-network',
      skip: !canManage,
    },
  );
  const { data: runsData, loading: runsLoading, refetch: refetchRuns } = useQuery<{ orgAiTaskRuns: TaskRun[] }>(
    GET_ORG_AI_TASK_RUNS,
    {
      variables: { limit: 40 },
      fetchPolicy: 'cache-and-network',
      skip: !canManage,
    },
  );
  const {
    data: ragHealthData,
    loading: ragHealthLoading,
    error: ragHealthError,
    refetch: refetchRagHealth,
  } = useQuery<{ ruleRepositoryRagHealth: RagHealthRow[] }>(
    GET_RULE_REPOSITORY_RAG_HEALTH,
    {
      fetchPolicy: 'cache-and-network',
      skip: !canManage,
    },
  );

  const [setOrgAiTaskConfig] = useMutation(SET_ORG_AI_TASK_CONFIG);
  const [runOrgAiTaskNow] = useMutation(RUN_ORG_AI_TASK_NOW);

  const tasks = useMemo(() => data?.orgAiTaskConfigs ?? [], [data?.orgAiTaskConfigs]);
  const runs = useMemo(() => runsData?.orgAiTaskRuns ?? [], [runsData?.orgAiTaskRuns]);
  const ragHealthRows = useMemo(() => ragHealthData?.ruleRepositoryRagHealth ?? [], [ragHealthData?.ruleRepositoryRagHealth]);

  const taskTitleMap = useMemo(() => {
    const map = new Map<string, string>();
    tasks.forEach((task) => map.set(task.taskKey, task.title));
    return map;
  }, [tasks]);

  const runTitle = (record: TaskRun): string => taskTitleMap.get(record.taskKey) || record.title || record.taskKey;

  const downloadRunOutput = (record: TaskRun) => {
    const output = getRunOutputText(record);
    if (!output) {
      message.warning('No run output is available to download.');
      return;
    }
    const startedAt = record.startedAt ? new Date(record.startedAt).toISOString().slice(0, 19).replace(/:/g, '-') : 'unknown-time';
    const filename = `${sanitizeFilenamePart(record.taskKey)}-${triggerText(record.trigger)}-${startedAt}.txt`;
    const blob = new Blob([output], { type: 'text/plain;charset=utf-8' });
    const downloadUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = downloadUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.URL.revokeObjectURL(downloadUrl);
  };

  const downloadTaskOutput = (task: TaskConfig, output: string) => {
    const startedAt = task.lastRunAt ? new Date(task.lastRunAt).toISOString().slice(0, 19).replace(/:/g, '-') : 'unknown-time';
    const filename = `${sanitizeFilenamePart(task.taskKey)}-last-message-${startedAt}.txt`;
    const blob = new Blob([output], { type: 'text/plain;charset=utf-8' });
    const downloadUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = downloadUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.URL.revokeObjectURL(downloadUrl);
  };

  const persistTaskConfig = async (task: TaskConfig, patch: Partial<TaskConfig>) => {
    setSavingTaskKey(task.taskKey);
    try {
      const response = await setOrgAiTaskConfig({
        variables: buildConfigVariables(task, patch),
      });
      const payload = response.data?.setOrgAiTaskConfig;
      if (!payload?.success) {
        message.error(payload?.message || 'Failed to save task configuration');
        return;
      }
      message.success('Task configuration saved');
      await Promise.all([refetch(), refetchRuns()]);
    } catch (e: any) {
      message.error(e?.message || 'Failed to save task configuration');
    } finally {
      setSavingTaskKey(null);
    }
  };

  const handleRunNow = async (taskKey: string) => {
    setRunningTaskKey(taskKey);
    try {
      const response = await runOrgAiTaskNow({ variables: { taskKey } });
      const payload = response.data?.runOrgAiTaskNow;
      if (!payload?.success) {
        message.error(payload?.message || 'Task execution failed');
      } else {
        message.success(payload?.message || 'Task executed');
      }
      await Promise.all([refetch(), refetchRuns()]);
    } catch (e: any) {
      message.error(e?.message || 'Task execution failed');
    } finally {
      setRunningTaskKey(null);
    }
  };

  if (!canManage) {
    return <Alert type="warning" showIcon message="Only administrators can manage AI tasks." />;
  }

  if (error) {
    return <Alert type="error" showIcon message="Failed to load AI tasks." description={error.message} />;
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Card
        loading={loading}
        title="AI Tasks"
        extra={<Button onClick={() => { refetch(); refetchRuns(); refetchRagHealth(); }}>Refresh</Button>}
      >
        <Text type="secondary">
          Enable AI-assisted operational tasks, choose cadence, and run tasks on demand.
          All schedules are stored in UTC.
        </Text>
        <div className="mt-4 space-y-4">
          {tasks.map((task) => {
            const saving = savingTaskKey === task.taskKey;
            const running = runningTaskKey === task.taskKey;
            const normalizedSchedule = normalizeScheduleValue(task.schedule);
            const normalizedDayOfWeek = clampInt(task.dayOfWeek, 0, 6, 0);
            const normalizedDayOfMonth = clampInt(task.dayOfMonth, 1, 28, 1);
            const normalizedRunHour = clampInt(task.runHour, 0, 23, 8);
            const normalizedRunMinuteRaw = clampInt(task.runMinute, 0, 59, 0);
            const normalizedRunMinute = MINUTE_VALUES.has(normalizedRunMinuteRaw)
              ? normalizedRunMinuteRaw
              : 0;
            return (
              <div key={task.taskKey} className="rounded-lg border border-gray-200 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="md:max-w-[48%]">
                    <div className="flex items-center gap-2">
                      <Text strong>{task.title}</Text>
                      {task.aiRequired ? <Tag color="blue">AI Required</Tag> : <Tag>AI Optional</Tag>}
                    </div>
                    <Text type="secondary">{task.description}</Text>
                    <div className="mt-2 text-xs text-gray-500">
                      Last run: {formatDateTime(task.lastRunAt)}{' '}
                      {task.lastStatus && <Tag color={statusColor(task.lastStatus)}>{task.lastStatus}</Tag>}
                    </div>
                    <div className="text-xs text-gray-500">Next run: {formatDateTime(task.nextRunAt)}</div>
                    {task.lastMessage && (
                      <Space direction="vertical" size={6} className="mt-2 w-full">
                        <div
                          className="p-2 text-xs"
                          style={outputBlockStyle}
                        >
                          {compactText(task.lastMessage, 420)}
                        </div>
                        <Space size={8}>
                          <Button
                            size="small"
                            onClick={() => setSelectedTaskOutput({ task, text: task.lastMessage || '' })}
                          >
                            Read
                          </Button>
                          <Button
                            size="small"
                            onClick={() => downloadTaskOutput(task, task.lastMessage || '')}
                          >
                            Download
                          </Button>
                        </Space>
                      </Space>
                    )}
                  </div>

                  <Space wrap align="start">
                    <Tooltip title="Enable or disable this task">
                      <Switch
                        checked={task.enabled}
                        loading={saving}
                        onChange={(checked) => persistTaskConfig(task, { enabled: checked })}
                      />
                    </Tooltip>
                    <select
                      className="config-auth-native-select rounded border px-2 py-1 text-sm leading-5"
                      style={{ width: 118 }}
                      value={normalizedSchedule}
                      disabled={saving}
                      onChange={(event) => persistTaskConfig(task, {
                        schedule: String(event.target.value).toUpperCase() as TaskConfig['schedule'],
                      })}
                    >
                      {SCHEDULE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                    {normalizedSchedule === 'WEEKLY' && (
                      <select
                        className="config-auth-native-select rounded border px-2 py-1 text-sm leading-5"
                        style={{ width: 128 }}
                        value={String(normalizedDayOfWeek)}
                        disabled={saving}
                        onChange={(event) => persistTaskConfig(task, {
                          dayOfWeek: clampInt(Number(event.target.value), 0, 6, normalizedDayOfWeek),
                        })}
                      >
                        {WEEKDAY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    )}
                    {normalizedSchedule === 'MONTHLY' && (
                      <select
                        className="config-auth-native-select rounded border px-2 py-1 text-sm leading-5"
                        style={{ width: 96 }}
                        value={String(normalizedDayOfMonth)}
                        disabled={saving}
                        onChange={(event) => persistTaskConfig(task, {
                          dayOfMonth: clampInt(Number(event.target.value), 1, 28, normalizedDayOfMonth),
                        })}
                      >
                        {MONTH_DAY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    )}
                    <select
                      className="config-auth-native-select rounded border px-2 py-1 text-sm leading-5"
                      style={{ width: 100 }}
                      value={String(normalizedRunHour)}
                      disabled={saving}
                      onChange={(event) => persistTaskConfig(task, {
                        runHour: clampInt(Number(event.target.value), 0, 23, normalizedRunHour),
                      })}
                    >
                      {HOUR_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                    <select
                      className="config-auth-native-select rounded border px-2 py-1 text-sm leading-5"
                      style={{ width: 88 }}
                      value={String(normalizedRunMinute)}
                      disabled={saving}
                      onChange={(event) => persistTaskConfig(task, {
                        runMinute: clampInt(Number(event.target.value), 0, 59, normalizedRunMinute),
                      })}
                    >
                      {MINUTE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                    <Button
                      type="primary"
                      loading={running}
                      disabled={saving}
                      onClick={() => handleRunNow(task.taskKey)}
                    >
                      Run Now
                    </Button>
                  </Space>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card
        title="RAG Sync Health"
        loading={ragHealthLoading}
        extra={<Button size="small" onClick={() => refetchRagHealth()}>Refresh Health</Button>}
      >
        <Text type="secondary">
          Shows each repository&apos;s last RAG sync outcome and current template point count in Qdrant.
        </Text>
        {ragHealthError ? (
          <Alert
            className="mt-3"
            type="error"
            showIcon
            message="Failed to load RAG health report."
            description={ragHealthError.message}
          />
        ) : (
          <Table
            className="mt-3"
            size="small"
            rowKey="repositoryId"
            pagination={{ pageSize: 8 }}
            scroll={{ x: 1500 }}
            dataSource={ragHealthRows}
            locale={{ emptyText: 'No repositories available.' }}
            columns={[
              {
                title: 'Repository',
                dataIndex: 'repositoryName',
                key: 'repositoryName',
                width: 220,
              },
              {
                title: 'RAG Sync',
                dataIndex: 'ragSyncEnabled',
                key: 'ragSyncEnabled',
                width: 110,
                render: (value: boolean) => <Tag color={value ? 'blue' : 'default'}>{value ? 'ENABLED' : 'DISABLED'}</Tag>,
              },
              {
                title: 'Last Sync Status',
                dataIndex: 'ragLastSyncStatus',
                key: 'ragLastSyncStatus',
                width: 140,
                render: (value: string | null | undefined) => <Tag color={statusColor(value)}>{value || 'IDLE'}</Tag>,
              },
              {
                title: 'Last Successful',
                dataIndex: 'ragLastSynced',
                key: 'ragLastSynced',
                width: 180,
                render: (value: string | null | undefined) => formatDateTime(value),
              },
              {
                title: 'Templates (Last)',
                dataIndex: 'ragLastSyncedTemplates',
                key: 'ragLastSyncedTemplates',
                width: 130,
                render: (value: number | null | undefined) => String(value ?? 0),
              },
              {
                title: 'Qdrant Points',
                dataIndex: 'qdrantPointCount',
                key: 'qdrantPointCount',
                width: 120,
                render: (value: number | null | undefined) => String(value ?? 0),
              },
              {
                title: 'Qdrant',
                dataIndex: 'qdrantStatus',
                key: 'qdrantStatus',
                width: 120,
                render: (value: string | null | undefined) => <Tag color={qdrantStatusColor(value)}>{value || 'UNKNOWN'}</Tag>,
              },
              {
                title: 'Files',
                key: 'files',
                width: 130,
                render: (_value: unknown, record: RagHealthRow) => {
                  const ingested = record.ingestedFiles ?? 0;
                  const failed = record.failedFiles ?? 0;
                  return <span>{ingested} ingested / {failed} failed</span>;
                },
              },
              {
                title: 'Error',
                dataIndex: 'qdrantError',
                key: 'qdrantError',
                ellipsis: true,
                render: (value: string | null | undefined) => {
                  const text = (value || '').trim();
                  if (!text) return <span>-</span>;
                  return (
                    <Tooltip title={text}>
                      <span>{compactText(text, 120)}</span>
                    </Tooltip>
                  );
                },
              },
            ]}
          />
        )}
      </Card>

      <Card title="Recent AI Task Runs" loading={runsLoading}>
        <Table
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1100 }}
          dataSource={runs}
          columns={[
            {
              title: 'Started',
              dataIndex: 'startedAt',
              key: 'startedAt',
              width: 190,
              render: (value: string | null | undefined) => formatDateTime(value),
            },
            {
              title: 'Task',
              dataIndex: 'taskKey',
              key: 'task',
              width: 260,
              render: (_value: string, record: TaskRun) => taskTitleMap.get(record.taskKey) || record.title || record.taskKey,
            },
            {
              title: 'Trigger',
              dataIndex: 'trigger',
              key: 'trigger',
              width: 100,
              render: (value: string) => <Tag>{value}</Tag>,
            },
            {
              title: 'Status',
              dataIndex: 'status',
              key: 'status',
              width: 110,
              render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
            },
            {
              title: 'Duration',
              dataIndex: 'durationMs',
              key: 'durationMs',
              width: 110,
              render: (value: number | null | undefined) => (value ? `${(value / 1000).toFixed(1)}s` : 'N/A'),
            },
            {
              title: 'Result',
              key: 'result',
              render: (_value: unknown, record: TaskRun) => {
                const text = getRunOutputText(record);
                const isReport = REPORT_TASK_KEYS.has(record.taskKey);
                if (!text) {
                  return <span>N/A</span>;
                }
                return (
                  <Space direction="vertical" size={4}>
                    <span>{compactText(text, isReport ? 180 : 260)}</span>
                    <Space size={8}>
                      <Button size="small" onClick={() => setSelectedRun(record)}>
                        Read
                      </Button>
                      <Button size="small" onClick={() => downloadRunOutput(record)}>
                        Download
                      </Button>
                    </Space>
                  </Space>
                );
              },
            },
          ]}
        />
      </Card>
      <Modal
        open={Boolean(selectedRun)}
        onCancel={() => setSelectedRun(null)}
        width={900}
        title={selectedRun ? `${runTitle(selectedRun)} - Full Output` : 'Task Output'}
        footer={[
          <Button
            key="download"
            onClick={() => {
              if (selectedRun) downloadRunOutput(selectedRun);
            }}
            disabled={!selectedRun || !getRunOutputText(selectedRun)}
          >
            Download
          </Button>,
          <Button key="close" type="primary" onClick={() => setSelectedRun(null)}>
            Close
          </Button>,
        ]}
      >
        {selectedRun && (
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            <Text type="secondary">
              Status: {selectedRun.status} | Trigger: {selectedRun.trigger} | Started: {formatDateTime(selectedRun.startedAt)}
            </Text>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                maxHeight: 520,
                overflowY: 'auto',
                background: token.colorFillAlter,
                color: token.colorText,
                border: `1px solid ${token.colorBorderSecondary}`,
                borderRadius: token.borderRadius,
                padding: 12,
                margin: 0,
              }}
            >
              {getRunOutputText(selectedRun) || 'No output is available for this run.'}
            </pre>
          </Space>
        )}
      </Modal>
      <Modal
        open={Boolean(selectedTaskOutput)}
        onCancel={() => setSelectedTaskOutput(null)}
        width={900}
        title={selectedTaskOutput ? `${selectedTaskOutput.task.title} - Last Output` : 'Task Output'}
        footer={[
          <Button
            key="download"
            onClick={() => {
              if (selectedTaskOutput) downloadTaskOutput(selectedTaskOutput.task, selectedTaskOutput.text);
            }}
            disabled={!selectedTaskOutput?.text}
          >
            Download
          </Button>,
          <Button key="close" type="primary" onClick={() => setSelectedTaskOutput(null)}>
            Close
          </Button>,
        ]}
      >
        {selectedTaskOutput && (
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            <Text type="secondary">
              Last run: {formatDateTime(selectedTaskOutput.task.lastRunAt)} | Next run: {formatDateTime(selectedTaskOutput.task.nextRunAt)}
            </Text>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                maxHeight: 520,
                overflowY: 'auto',
                background: token.colorFillAlter,
                color: token.colorText,
                border: `1px solid ${token.colorBorderSecondary}`,
                borderRadius: token.borderRadius,
                padding: 12,
                margin: 0,
              }}
            >
              {selectedTaskOutput.text || 'No output is available for this task.'}
            </pre>
          </Space>
        )}
      </Modal>
    </Space>
  );
};

export default AITasksTab;
