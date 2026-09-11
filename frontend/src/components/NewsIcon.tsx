import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Badge, Button } from 'antd';
import { BulbOutlined } from '@ant-design/icons';
import { NewsModal } from './NewsModal';

interface UnreadCountData {
  unreadNewsCount: number;
}

const UNREAD_NEWS_COUNT = gql`
  query UnreadNewsCount {
    unreadNewsCount
  }
`;

export const NewsIcon: React.FC = () => {
  const [modalOpen, setModalOpen] = useState(false);
  const { data, refetch } = useQuery<UnreadCountData>(UNREAD_NEWS_COUNT, {
    pollInterval: 30000,           // Poll every 30 seconds
    fetchPolicy: 'network-only',   // Always fetch fresh data
    nextFetchPolicy: 'cache-first'
  });

  // Refetch when modal opens for latest data
  useEffect(() => { 
    if (modalOpen) { 
      refetch(); 
    } 
  }, [modalOpen, refetch]);

  const unreadCount = data?.unreadNewsCount ?? 0;

  return (
    <>
      <Badge 
        count={unreadCount} 
        overflowCount={99}
        status={unreadCount > 0 ? 'processing' : undefined}
      >
        <Button 
          type="text" 
          aria-label={`News & Announcements (${unreadCount} unread)`}
          icon={<BulbOutlined />}
          onClick={() => setModalOpen(true)}
        />
      </Badge>
      <NewsModal 
        open={modalOpen} 
        onClose={() => {
          setModalOpen(false);
          refetch(); // Refresh count after modal closes
        }} 
      />
    </>
  );
};

export default NewsIcon;
