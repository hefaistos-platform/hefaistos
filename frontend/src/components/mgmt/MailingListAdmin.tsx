import React, { useState } from 'react';
import { useMutation, useQuery } from '@apollo/client';
import {
  Alert,
  Button,
  Card,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { MailOutlined, UserDeleteOutlined } from '@ant-design/icons';
import {
  GET_MAILING_LIST,
  UPDATE_MAILING_LIST_MEMBER,
  MailingListMember,
} from '../../graphql/mgmtAIPrompts';

const { Paragraph, Text, Title } = Typography;

export const MailingListAdmin: React.FC = () => {
  const { data, loading, error, refetch } = useQuery<{ mailingListMembers: MailingListMember[] }>(
    GET_MAILING_LIST,
  );
  const [updateMember] = useMutation(UPDATE_MAILING_LIST_MEMBER);
  const [updatingUsername, setUpdatingUsername] = useState<string | null>(null);

  const members = data?.mailingListMembers ?? [];

  const handleToggle = async (member: MailingListMember, subscribe: boolean) => {
    setUpdatingUsername(member.username);
    try {
      const res = await updateMember({
        variables: { username: member.username, subscribe },
      });
      const payload = res.data?.updateMailingListMember;
      if (payload?.success) {
        message.success(payload.message || 'Mailing list updated.');
        refetch();
      } else {
        message.error(payload?.message || 'Update failed.');
      }
    } catch (err: any) {
      message.error(err?.message || 'Update failed.');
    } finally {
      setUpdatingUsername(null);
    }
  };

  const columns = [
    {
      title: 'Username',
      dataIndex: 'username',
      key: 'username',
      render: (username: string) => <Text strong>{username}</Text>,
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: 'Role',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color={role === 'ADMIN' ? 'gold' : 'blue'}>{role}</Tag>
      ),
    },
    {
      title: 'Subscribed',
      dataIndex: 'isSubscribed',
      key: 'isSubscribed',
      render: (isSubscribed: boolean, record: MailingListMember) => (
        <Switch
          checked={isSubscribed}
          loading={updatingUsername === record.username}
          onChange={(checked) => handleToggle(record, checked)}
          checkedChildren="On"
          unCheckedChildren="Off"
        />
      ),
    },
    {
      title: 'Subscribed At',
      dataIndex: 'subscribedAt',
      key: 'subscribedAt',
      render: (val: string) => val ? new Date(val).toLocaleDateString() : '—',
    },
    {
      title: 'Removed At',
      dataIndex: 'unsubscribedAt',
      key: 'unsubscribedAt',
      render: (val: string | null) => val ? new Date(val).toLocaleDateString() : '—',
    },
    {
      title: 'Action',
      key: 'action',
      render: (_: unknown, record: MailingListMember) =>
        record.isSubscribed ? (
          <Button
            danger
            size="small"
            icon={<UserDeleteOutlined />}
            loading={updatingUsername === record.username}
            onClick={() => handleToggle(record, false)}
          >
            Remove
          </Button>
        ) : (
          <Button
            size="small"
            icon={<MailOutlined />}
            loading={updatingUsername === record.username}
            onClick={() => handleToggle(record, true)}
          >
            Re-subscribe
          </Button>
        ),
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        <MailOutlined /> Monthly Report Mailing List
      </Title>
      <Paragraph type="secondary">
        Admin and Reviewer users are automatically subscribed when their account is created.
        You can manually remove or re-subscribe users below. Reports are sent on the 1st of each
        month via the <Text code>send_monthly_reports</Text> management command.
      </Paragraph>

      {error && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="Failed to load mailing list"
          description={error.message}
        />
      )}

      <Card>
        {loading ? (
          <Spin tip="Loading mailing list..." />
        ) : members.length === 0 ? (
          <Alert
            type="info"
            showIcon
            message="No mailing list entries yet. Admin and Reviewer users are auto-subscribed on login or role change."
          />
        ) : (
          <Table<MailingListMember>
            dataSource={members}
            columns={columns}
            rowKey="id"
            size="small"
            pagination={false}
          />
        )}
      </Card>

      <Space style={{ marginTop: 16 }}>
        <Button onClick={() => refetch()}>Refresh</Button>
      </Space>
    </div>
  );
};

export default MailingListAdmin;
