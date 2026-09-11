import React, { useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

const GET_ACCESS_QUERY = gql`
  query GetLogsAccess {
    me {
      id
      role
      isSuperuser
      isStaff
    }
  }
`;

const GET_MCS_SECURITY_LOGS = gql`
  query GetMcsSecurityLogs($limit: Int, $offset: Int, $level: String, $action: String, $search: String) {
    mcsSecurityLogs(limit: $limit, offset: $offset, level: $level, action: $action, search: $search) {
      total
      logs {
        id
        timestamp
        level
        logger
        message
        action
        outcome
        reason
        eventCode
        userId
        userName
        sourceIp
        requestMethod
        urlPath
        serviceName
      }
    }
  }
`;

interface AccessData {
  me?: {
    id: string;
    role?: string | null;
    isSuperuser?: boolean | null;
    isStaff?: boolean | null;
  } | null;
}

interface SecurityLogItem {
  id: string;
  timestamp?: string | null;
  level?: string | null;
  logger?: string | null;
  message?: string | null;
  action?: string | null;
  outcome?: string | null;
  reason?: string | null;
  eventCode?: string | null;
  userId?: string | null;
  userName?: string | null;
  sourceIp?: string | null;
  requestMethod?: string | null;
  urlPath?: string | null;
  serviceName?: string | null;
}

interface LogsQueryData {
  mcsSecurityLogs: {
    total: number;
    logs: SecurityLogItem[];
  };
}

interface LogsQueryVars {
  limit: number;
  offset: number;
  level?: string;
  action?: string;
  search?: string;
}

const PAGE_SIZE_OPTIONS = ['25', '50', '100'];

const levelColor = (level?: string | null): string => {
  const normalized = (level || '').toLowerCase();
  if (normalized === 'critical') return 'red';
  if (normalized === 'error') return 'volcano';
  if (normalized === 'warning') return 'gold';
  return 'blue';
};

const formatTime = (value?: string | null): string => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

export const LogsPage: React.FC = () => {
  const [level, setLevel] = useState<string | undefined>(undefined);
  const [action, setAction] = useState<string>('');
  const [search, setSearch] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(50);

  const { data: accessData, loading: accessLoading } = useQuery<AccessData>(GET_ACCESS_QUERY, {
    fetchPolicy: 'cache-and-network',
  });

  const role = (accessData?.me?.role || '').toUpperCase();
  const isBotAuditor = role === 'BOT_AUDITOR_ORG' || role === 'BOT_AUDITOR_GLOBAL';
  const isAdmin = useMemo(() => {
    return role === 'ADMIN' || Boolean(accessData?.me?.isSuperuser) || Boolean(accessData?.me?.isStaff);
  }, [accessData?.me?.isStaff, accessData?.me?.isSuperuser, role]);
  const hasLogsAccess = isAdmin || isBotAuditor;

  const variables: LogsQueryVars = useMemo(
    () => ({
      limit: pageSize,
      offset: (page - 1) * pageSize,
      level: level || undefined,
      action: action.trim() || undefined,
      search: search.trim() || undefined,
    }),
    [action, level, page, pageSize, search]
  );

  const {
    data,
    loading,
    error,
    refetch,
  } = useQuery<LogsQueryData, LogsQueryVars>(GET_MCS_SECURITY_LOGS, {
    variables,
    skip: !hasLogsAccess,
    fetchPolicy: 'network-only',
    notifyOnNetworkStatusChange: true,
  });

  const rows = data?.mcsSecurityLogs?.logs || [];
  const total = data?.mcsSecurityLogs?.total || 0;

  const columns: ColumnsType<SecurityLogItem> = [
    {
      title: 'Time (UTC/local)',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 210,
      render: (value: string | null | undefined) => formatTime(value),
    },
    {
      title: 'Level',
      dataIndex: 'level',
      key: 'level',
      width: 110,
      render: (value: string | null | undefined) => (
        <Tag color={levelColor(value)}>{(value || 'unknown').toUpperCase()}</Tag>
      ),
    },
    {
      title: 'Action',
      dataIndex: 'action',
      key: 'action',
      width: 210,
      render: (value: string | null | undefined) => <Text code>{value || '-'}</Text>,
    },
    {
      title: 'Event Code',
      dataIndex: 'eventCode',
      key: 'eventCode',
      width: 190,
      render: (value: string | null | undefined) => <Text code>{value || '-'}</Text>,
    },
    {
      title: 'User',
      key: 'user',
      width: 180,
      render: (_: unknown, row: SecurityLogItem) => row.userName || row.userId || '-',
    },
    {
      title: 'Source IP',
      dataIndex: 'sourceIp',
      key: 'sourceIp',
      width: 160,
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: 'Service / Logger',
      key: 'logger',
      width: 220,
      render: (_: unknown, row: SecurityLogItem) =>
        [row.serviceName || '-', row.logger || '-'].join(' / '),
    },
    {
      title: 'Message',
      dataIndex: 'message',
      key: 'message',
      render: (value: string | null | undefined) => value || '-',
    },
  ];

  if (accessLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <Spin size="large" tip="Checking access..." />
      </div>
    );
  }

  if (!hasLogsAccess) {
    return (
      <div style={{ padding: 32 }}>
        <Alert
          type="error"
          showIcon
          message="Forbidden"
          description="You need ADMIN or BOT_AUDITOR role to access centralized security logs."
        />
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 1600, margin: '0 auto' }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {isBotAuditor && (
          <Alert
            type="warning"
            showIcon
            message="Read-only bot auditor mode"
            description="Log viewing is allowed for evaluation. Write operations remain blocked."
          />
        )}
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            Centralized Security Logs
          </Title>
          <Text type="secondary">
            Displaying MCS security events from the last 72 hours (3 days).
          </Text>
        </div>

        <Card>
          <Space wrap>
            <Select
              allowClear
              value={level}
              placeholder="Level"
              style={{ width: 170 }}
              onChange={(value) => {
                setLevel(value);
                setPage(1);
              }}
              options={[
                { value: 'informational', label: 'Informational' },
                { value: 'warning', label: 'Warning' },
                { value: 'error', label: 'Error' },
                { value: 'critical', label: 'Critical' },
              ]}
            />
            <Input
              value={action}
              onChange={(event) => {
                setAction(event.target.value);
                setPage(1);
              }}
              style={{ width: 240 }}
              placeholder="Filter by event action"
            />
            <Input.Search
              allowClear
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onSearch={() => setPage(1)}
              style={{ width: 320 }}
              placeholder="Search message, user, code, IP..."
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => refetch(variables)}
              loading={loading}
            >
              Refresh
            </Button>
          </Space>
        </Card>

        {error && (
          <Alert
            type="error"
            showIcon
            message="Failed to load logs"
            description={error.message}
          />
        )}

        <Table<SecurityLogItem>
          rowKey={(row) => row.id}
          columns={columns}
          dataSource={rows}
          loading={loading}
          size="small"
          scroll={{ x: 1400 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: PAGE_SIZE_OPTIONS,
            showTotal: (count) => `Total events: ${count}`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
        />
      </Space>
    </div>
  );
};

export default LogsPage;
