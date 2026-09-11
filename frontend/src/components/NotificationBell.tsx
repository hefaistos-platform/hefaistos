import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Badge, Button, List, Popover, Space } from 'antd';
import { BellOutlined } from '@ant-design/icons';

interface HeaderNotificationItem {
  id: string;
  verb: string;
  read: boolean;
  timestamp: string;
}

interface HeaderNotificationsData {
  unreadNotificationCount: number;
  myNotifications: HeaderNotificationItem[];
}

const HEADER_NOTIFICATIONS = gql`
  query HeaderNotifications {
    unreadNotificationCount
    myNotifications {
      id
      verb
      read
      timestamp
    }
  }
`;

const MARK_ALL_READ = gql`
  mutation MarkAllNotificationsAsRead { markAllNotificationsAsRead { ok } }
`;

export const NotificationBell: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [isPageVisible, setIsPageVisible] = useState<boolean>(() => {
    if (typeof document === 'undefined') return true;
    return document.visibilityState !== 'hidden';
  });

  useEffect(() => {
    const onVisibilityChange = () => {
      setIsPageVisible(document.visibilityState !== 'hidden');
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  const { data, loading, refetch } = useQuery<HeaderNotificationsData>(HEADER_NOTIFICATIONS, {
    pollInterval: isPageVisible ? 15000 : 0,
    fetchPolicy: 'cache-and-network',
    nextFetchPolicy: 'cache-first' // After first network fetch fall back to cache for efficiency
  });
  const [markAll, { loading: marking }] = useMutation(MARK_ALL_READ, {
    onCompleted: () => refetch(),
  });

  // Refetch immediately when the popover is opened for freshest list
  useEffect(() => { if (open) { refetch(); } }, [open, refetch]);

  const unreadCount = data?.unreadNotificationCount ?? 0;

  return (
    <Popover
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      title={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <span>Notifications</span>
          <Button size="small" onClick={() => markAll()} loading={marking} disabled={loading}>
            Mark all read
          </Button>
        </Space>
      }
      content={
        <div style={{ width: 360 }}>
          <List
            size="small"
            dataSource={[...(data?.myNotifications ?? [])]
              .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
              .slice(0, 8)
            }
            locale={{ emptyText: loading ? 'Loading...' : 'No notifications' }}
            renderItem={(item) => (
              <List.Item style={{ opacity: item.read ? 0.7 : 1 }}>
                <List.Item.Meta title={item.verb} description={new Date(item.timestamp).toLocaleString()} />
              </List.Item>
            )}
          />
        </div>
      }
    >
      <Badge count={unreadCount} overflowCount={99} status={unreadCount > 0 ? 'processing' : undefined}>
        <Button type="text" aria-label={`Notifications (${unreadCount} unread)`} icon={<BellOutlined />} />
      </Badge>
    </Popover>
  );
};

export default NotificationBell;
