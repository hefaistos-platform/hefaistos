import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Modal, List, Tag, Button, Space, Select, Typography, Empty } from 'antd';
import { 
  CloseOutlined, 
  CheckOutlined,
  PushpinOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { MarkdownRenderer } from './MarkdownRenderer';

dayjs.extend(relativeTime);

const { Text, Title } = Typography;

interface NewsPost {
  id: string;
  title?: string;
  content: string;
  category: string;
  priority: string;
  isPinned: boolean;
  publishedAt: string;
  isRead: boolean;
  isActive: boolean;
  author: {
    username: string;
  };
}

interface AllNewsData {
  allNews: NewsPost[];
}

interface UnreadCountData {
  unreadNewsCount: number;
}

const ALL_NEWS_QUERY = gql`
  query AllNews($category: String, $includeExpired: Boolean) {
    allNews(category: $category, includeExpired: $includeExpired) {
      id
      title
      content
      category
      priority
      isPinned
      publishedAt
      isRead
      isActive
      author {
        username
      }
    }
  }
`;

const MARK_NEWS_AS_READ = gql`
  mutation MarkNewsAsRead($newsId: UUID!) {
    markNewsAsRead(newsId: $newsId) {
      success
      unreadCount
    }
  }
`;

const MARK_ALL_NEWS_AS_READ = gql`
  mutation MarkAllNewsAsRead {
    markAllNewsAsRead {
      success
      markedCount
    }
  }
`;

// Category emoji mapping
const CATEGORY_EMOJI: Record<string, string> = {
  'UPDATE': '🔄',
  'OUTAGE': '⚠️',
  'FEATURE': '🚀',
  'MAINTENANCE': '🔧',
  'ANNOUNCEMENT': '📢',
  'SECURITY': '🔒'
};

// Priority color mapping
const PRIORITY_COLORS: Record<string, string> = {
  'LOW': 'default',
  'MEDIUM': 'blue',
  'HIGH': 'orange',
  'URGENT': 'red'
};

interface NewsModalProps {
  open: boolean;
  onClose: () => void;
}

export const NewsModal: React.FC<NewsModalProps> = ({ open, onClose }) => {
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(undefined);
  
  const { data, loading, refetch } = useQuery<AllNewsData>(ALL_NEWS_QUERY, {
    variables: { 
      category: selectedCategory,
      includeExpired: false 
    },
    skip: !open,
    fetchPolicy: 'network-only'
  });

  const [markAsRead] = useMutation(MARK_NEWS_AS_READ, {
    refetchQueries: ['AllNews', 'UnreadNewsCount']
  });

  const [markAllAsRead, { loading: markingAll }] = useMutation(MARK_ALL_NEWS_AS_READ, {
    refetchQueries: ['AllNews', 'UnreadNewsCount'],
    onCompleted: () => refetch()
  });

  const handleMarkAsRead = async (newsId: string, isRead: boolean) => {
    if (!isRead) {
      await markAsRead({ variables: { newsId } });
    }
  };

  const handleMarkAllRead = async () => {
    await markAllAsRead();
  };

  // Sort: pinned first, then by date descending
  const sortedNews = [...(data?.allNews ?? [])]
    .filter(post => post.isActive)
    .sort((a, b) => {
      if (a.isPinned && !b.isPinned) return -1;
      if (!a.isPinned && b.isPinned) return 1;
      return new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime();
    });

  const categories = [
    { label: 'All', value: undefined },
    { label: '🔄 Updates', value: 'UPDATE' },
    { label: '⚠️ Outages', value: 'OUTAGE' },
    { label: '🚀 Features', value: 'FEATURE' },
    { label: '🔧 Maintenance', value: 'MAINTENANCE' },
    { label: '📢 Announcements', value: 'ANNOUNCEMENT' },
    { label: '🔒 Security', value: 'SECURITY' }
  ];

  return (
    <Modal
      title={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>
            📰 News & Announcements
          </Title>
          <Button 
            size="small" 
            icon={<CheckOutlined />}
            onClick={handleMarkAllRead}
            loading={markingAll}
            disabled={loading || sortedNews.length === 0}
          >
            Mark all read
          </Button>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
      bodyStyle={{ maxHeight: '70vh', overflowY: 'auto' }}
      closeIcon={<CloseOutlined />}
    >
      <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
        <Space>
          <Text>Filter:</Text>
          <Select
            style={{ width: 200 }}
            value={selectedCategory}
            onChange={setSelectedCategory}
            options={categories}
          />
          <Button 
            icon={<ReloadOutlined />} 
            onClick={() => refetch()}
            size="small"
          >
            Refresh
          </Button>
        </Space>
      </Space>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Text type="secondary">Loading news...</Text>
        </div>
      ) : sortedNews.length === 0 ? (
        <Empty 
          description="No news to display"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <List
          dataSource={sortedNews}
          renderItem={(post) => (
            <List.Item
              key={post.id}
              style={{
                opacity: post.isRead ? 0.6 : 1,
                borderLeft: post.isPinned ? '4px solid #1677ff' : undefined,
                paddingLeft: post.isPinned ? 12 : 16,
                background: post.isRead ? '#fafafa' : '#ffffff',
                transition: 'all 0.2s',
                cursor: 'pointer'
              }}
              onClick={() => handleMarkAsRead(post.id, post.isRead)}
            >
              <List.Item.Meta
                title={
                  <Space>
                    {post.isPinned && (
                      <PushpinOutlined style={{ color: '#1677ff' }} />
                    )}
                    <span>
                      {CATEGORY_EMOJI[post.category]} {post.title || 'News Update'}
                    </span>
                    <Tag color={PRIORITY_COLORS[post.priority]}>
                      {post.priority}
                    </Tag>
                    {!post.isRead && (
                      <Tag color="blue">NEW</Tag>
                    )}
                  </Space>
                }
                description={
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ 
                      fontSize: 14, 
                      lineHeight: 1.6,
                      marginTop: 8 
                    }}>
                      <MarkdownRenderer content={post.content} variant="small" />
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      Posted by {post.author.username} · {dayjs(post.publishedAt).fromNow()}
                    </Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Modal>
  );
};

export default NewsModal;
