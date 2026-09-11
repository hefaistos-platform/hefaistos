import React, { useState, useMemo } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import {
  Alert,
  Table, 
  Button, 
  Modal, 
  Form, 
  Input, 
  Select, 
  DatePicker, 
  Switch, 
  Space, 
  Tag, 
  Popconfirm,
  Typography,
  message,
  Card,
  Tabs
} from 'antd';
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined,
  EyeOutlined,
  EyeInvisibleOutlined
} from '@ant-design/icons';
import SimpleMDE from 'react-simplemde-editor';
import dayjs from 'dayjs';
import { createEditorOptions, MARKDOWN_PLACEHOLDERS, configureMdeInstance } from '../config/markdownConfig';
import { MarkdownRenderer, markdownToPlainText } from '../components/MarkdownRenderer';

const { Title, Text } = Typography;

interface NewsPost {
  id: string;
  title?: string;
  content: string;
  category: string;
  priority: string;
  isPinned: boolean;
  isPublished: boolean;
  publishedAt?: string;
  expiresAt?: string;
  createdAt: string;
  author: {
    username: string;
  };
}

interface AllNewsData {
  allNews: NewsPost[];
}

interface NewsAdminAccessData {
  me?: {
    id: string;
    role?: string | null;
    isSuperuser?: boolean | null;
  } | null;
}

const ALL_NEWS_ADMIN_QUERY = gql`
  query AllNewsAdmin {
    allNews(includeExpired: true, includeUnpublished: true, limit: 1000) {
      id
      title
      content
      category
      priority
      isPinned
      isPublished
      publishedAt
      expiresAt
      createdAt
      author {
        username
      }
    }
  }
`;

const NEWS_SETTINGS_QUERY = gql`
  query NewsSettings {
    newsSettings
  }
`;

const NEWS_ADMIN_ACCESS_QUERY = gql`
  query NewsAdminAccess {
    me {
      id
      role
      isSuperuser
    }
  }
`;

const SET_NEWS_SETTINGS = gql`
  mutation SetNewsSettings($digestEnabled: Boolean!, $digestDay: String, $digestHour: Int) {
    setNewsSettings(digestEnabled: $digestEnabled, digestDay: $digestDay, digestHour: $digestHour)
  }
`;

const SEND_NEWS_DIGEST = gql`
  mutation SendNewsDigest($limit: Int) {
    sendNewsDigest(limit: $limit)
  }
`;

const CREATE_NEWS_POST = gql`
  mutation CreateNewsPost(
    $title: String
    $content: String!
    $category: String!
    $priority: String!
    $isPinned: Boolean
    $expiresAt: DateTime
  ) {
    createNewsPost(
      title: $title
      content: $content
      category: $category
      priority: $priority
      isPinned: $isPinned
      expiresAt: $expiresAt
    ) {
      success
      newsPost {
        id
        title
        content
      }
    }
  }
`;

const UPDATE_NEWS_POST = gql`
  mutation UpdateNewsPost(
    $id: UUID!
    $title: String
    $content: String
    $category: String
    $priority: String
    $isPinned: Boolean
    $expiresAt: DateTime
  ) {
    updateNewsPost(
      id: $id
      title: $title
      content: $content
      category: $category
      priority: $priority
      isPinned: $isPinned
      expiresAt: $expiresAt
    ) {
      success
      newsPost {
        id
        title
        content
      }
    }
  }
`;

const PUBLISH_NEWS_POST = gql`
  mutation PublishNewsPost($id: UUID!) {
    publishNewsPost(id: $id) {
      success
    }
  }
`;

const UNPUBLISH_NEWS_POST = gql`
  mutation UnpublishNewsPost($id: UUID!) {
    unpublishNewsPost(id: $id) {
      success
    }
  }
`;

const DELETE_NEWS_POST = gql`
  mutation DeleteNewsPost($id: UUID!) {
    deleteNewsPost(id: $id) {
      success
    }
  }
`;

const CATEGORY_OPTIONS = [
  { label: '🔄 Update', value: 'UPDATE' },
  { label: '⚠️ Outage', value: 'OUTAGE' },
  { label: '🚀 Feature', value: 'FEATURE' },
  { label: '🔧 Maintenance', value: 'MAINTENANCE' },
  { label: '📢 Announcement', value: 'ANNOUNCEMENT' },
  { label: '🔒 Security', value: 'SECURITY' }
];

const PRIORITY_OPTIONS = [
  { label: 'Low', value: 'LOW' },
  { label: 'Medium', value: 'MEDIUM' },
  { label: 'High', value: 'HIGH' },
  { label: 'Urgent', value: 'URGENT' }
];

export const AdminNewsPage: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingPost, setEditingPost] = useState<NewsPost | null>(null);
  const [previewContent, setPreviewContent] = useState('');
  const [contentTab, setContentTab] = useState('editor');
  const [form] = Form.useForm();

  // Memoized editor options
  const contentEditorOptions = useMemo(
    () => createEditorOptions('standard', MARKDOWN_PLACEHOLDERS.content),
    []
  );

  const { data: accessData, loading: accessLoading } = useQuery<NewsAdminAccessData>(NEWS_ADMIN_ACCESS_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const normalizedRole = (accessData?.me?.role || '').toUpperCase();
  const isBotAuditor = normalizedRole === 'BOT_AUDITOR_ORG' || normalizedRole === 'BOT_AUDITOR_GLOBAL';
  const canManage = normalizedRole === 'ADMIN' || normalizedRole === 'SUPERADMIN' || Boolean(accessData?.me?.isSuperuser);
  const canView = canManage || isBotAuditor;

  const { data, loading, refetch } = useQuery<AllNewsData>(ALL_NEWS_ADMIN_QUERY);
  interface NewsSettingsData { newsSettings: any }
  const { data: settingsData, refetch: refetchSettings } = useQuery<NewsSettingsData>(NEWS_SETTINGS_QUERY);
  type SetNewsSettingsPayload = { setNewsSettings: any };
  type SendNewsDigestPayload = { sendNewsDigest: boolean };
  const [setSettings] = useMutation<SetNewsSettingsPayload>(SET_NEWS_SETTINGS, { onCompleted: () => refetchSettings() });
  const [sendDigest] = useMutation<SendNewsDigestPayload, { limit: number }>(SEND_NEWS_DIGEST);

  const [createNews, { loading: creating }] = useMutation(CREATE_NEWS_POST, {
    refetchQueries: [{ query: ALL_NEWS_ADMIN_QUERY }],
    onCompleted: () => {
      message.success('News post created successfully');
      setIsModalOpen(false);
      form.resetFields();
      refetch();
    },
    onError: (error) => message.error(`Error: ${error.message}`)
  });

  const [updateNews, { loading: updating }] = useMutation(UPDATE_NEWS_POST, {
    refetchQueries: [{ query: ALL_NEWS_ADMIN_QUERY }],
    onCompleted: () => {
      message.success('News post updated successfully');
      setIsModalOpen(false);
      setEditingPost(null);
      form.resetFields();
      refetch();
    },
    onError: (error) => message.error(`Error: ${error.message}`)
  });

  const [publishNews] = useMutation(PUBLISH_NEWS_POST, {
    onCompleted: () => {
      message.success('News post published');
      refetch();
    },
    onError: (error) => message.error(`Error: ${error.message}`)
  });

  const [unpublishNews] = useMutation(UNPUBLISH_NEWS_POST, {
    onCompleted: () => {
      message.success('News post unpublished');
      refetch();
    },
    onError: (error) => message.error(`Error: ${error.message}`)
  });

  const [deleteNews] = useMutation(DELETE_NEWS_POST, {
    onCompleted: () => {
      message.success('News post deleted');
      refetch();
    },
    onError: (error) => message.error(`Error: ${error.message}`)
  });

  const handleCreate = () => {
    if (!canManage) return;
    setEditingPost(null);
    form.resetFields();
    setPreviewContent('');
    setContentTab('editor');
    form.setFieldsValue({
      category: 'ANNOUNCEMENT',
      priority: 'MEDIUM',
      isPinned: false,
      expiresAt: dayjs().add(180, 'days')
    });
    setIsModalOpen(true);
  };

  const parsedSettings = (() => {
    const raw = settingsData?.newsSettings as any;
    if (!raw) return undefined;
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch { return undefined; }
    }
    return raw;
  })();
  const digestEnabled = parsedSettings?.digestEnabled ?? true;

  const toggleDigest = async () => {
    if (!canManage) return;
    try {
      await setSettings({ variables: { digestEnabled: !digestEnabled } });
      message.success(`Digest ${!digestEnabled ? 'enabled' : 'disabled'}`);
    } catch (e: any) {
      message.error(`Error toggling digest: ${e.message}`);
    }
  };

  const sendDigestNow = async () => {
    if (!canManage) return;
    try {
      const { data } = await sendDigest({ variables: { limit: 20 } });
      if (data?.sendNewsDigest) {
        message.success('Triggered digest send');
      } else {
        message.error('Server reported failure sending digest');
      }
    } catch (e: any) {
      message.error(`Error sending digest: ${e.message}`);
    }
  };

  const handleEdit = (post: NewsPost) => {
    if (!canManage) return;
    setEditingPost(post);
    form.setFieldsValue({
      title: post.title,
      content: post.content,
      category: post.category,
      priority: post.priority,
      isPinned: post.isPinned,
      expiresAt: post.expiresAt ? dayjs(post.expiresAt) : dayjs().add(180, 'days')
    });
    setPreviewContent(post.content);
    setIsModalOpen(true);
  };

  const handleSubmit = async () => {
    if (!canManage) return;
    try {
      const values = await form.validateFields();
      const variables = {
        ...values,
        expiresAt: values.expiresAt?.toISOString()
      };

      if (editingPost) {
        await updateNews({ variables: { id: editingPost.id, ...variables } });
      } else {
        await createNews({ variables });
      }
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  const handlePublishToggle = async (post: NewsPost) => {
    if (!canManage) return;
    if (post.isPublished) {
      await unpublishNews({ variables: { id: post.id } });
    } else {
      await publishNews({ variables: { id: post.id } });
    }
  };

  const handleDelete = async (id: string) => {
    if (!canManage) return;
    await deleteNews({ variables: { id } });
  };

  const columns = [
    {
      title: 'Status',
      dataIndex: 'isPublished',
      key: 'status',
      width: 100,
      render: (isPublished: boolean) => (
        <Tag color={isPublished ? 'green' : 'orange'} icon={!isPublished ? '📝' : undefined}>
          {isPublished ? 'Published' : 'Draft'}
        </Tag>
      )
    },
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      render: (title: string, record: NewsPost) => (
        <Space direction="vertical" size={0}>
          <Text strong>{title || 'Untitled'}</Text>
          {record.isPinned && <Tag color="blue">📌 Pinned</Tag>}
        </Space>
      )
    },
    {
      title: 'Content',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      width: 300,
      render: (content: string) => {
        const previewText = markdownToPlainText(content);
        return (
          <Text ellipsis={{ tooltip: previewText }} style={{ maxWidth: 280 }}>
            {previewText}
          </Text>
        );
      }
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      width: 140,
      render: (category: string) => {
        const emoji = { 
          UPDATE: '🔄', 
          OUTAGE: '⚠️', 
          FEATURE: '🚀', 
          MAINTENANCE: '🔧', 
          ANNOUNCEMENT: '📢', 
          SECURITY: '🔒' 
        }[category];
        return <Tag>{emoji} {category}</Tag>;
      }
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      key: 'priority',
      width: 100,
      render: (priority: string) => {
        const colors: Record<string, string> = {
          LOW: 'default',
          MEDIUM: 'blue',
          HIGH: 'orange',
          URGENT: 'red'
        };
        return <Tag color={colors[priority]}>{priority}</Tag>;
      }
    },
    {
      title: 'Published',
      dataIndex: 'publishedAt',
      key: 'publishedAt',
      width: 140,
      render: (date: string) => date ? dayjs(date).format('MMM D, YYYY') : '-'
    },
    {
      title: 'Expires',
      dataIndex: 'expiresAt',
      key: 'expiresAt',
      width: 140,
      render: (date: string) => date ? dayjs(date).format('MMM D, YYYY') : '-'
    },
    {
      title: 'Author',
      dataIndex: ['author', 'username'],
      key: 'author',
      width: 120
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: any, record: NewsPost) => (
        <Space size="small">
          <Button
            type="text"
            size="small"
            icon={record.isPublished ? <EyeInvisibleOutlined /> : <EyeOutlined />}
            onClick={() => handlePublishToggle(record)}
            title={record.isPublished ? 'Unpublish' : 'Publish'}
            disabled={!canManage}
          />
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
            disabled={!canManage}
          />
          <Popconfirm
            title="Delete this news post?"
            onConfirm={() => handleDelete(record.id)}
            okText="Yes"
            cancelText="No"
            disabled={!canManage}
          >
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={!canManage}
            />
          </Popconfirm>
        </Space>
      )
    }
  ];

  if (!accessLoading && accessData?.me && !canView) {
    return (
      <div style={{ padding: '24px' }}>
        <Alert
          type="error"
          showIcon
          message="Forbidden"
          description="You need ADMIN or BOT_AUDITOR role to access News Management."
        />
      </div>
    );
  }

  return (
    <div className="news-admin-theme" style={{ padding: '24px' }}>
      <Card>
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {isBotAuditor && (
            <Alert
              type="warning"
              showIcon
              message="Read-only bot auditor mode"
              description="You can inspect news content and history, but create/edit/publish actions are disabled."
            />
          )}
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Title level={2} style={{ margin: 0 }}>
              📰 News Management
            </Title>
            <Space>
              <Button
                onClick={toggleDigest}
                disabled={!canManage}
              >
                {digestEnabled ? 'Disable Digest' : 'Enable Digest'}
              </Button>
              <Button onClick={sendDigestNow} disabled={!canManage}>Send Digest Now</Button>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreate}
                disabled={!canManage}
              >
                Create News Post
              </Button>
            </Space>
          </Space>

          <Table
            dataSource={data?.allNews}
            columns={columns}
            loading={loading}
            rowKey="id"
            pagination={{ pageSize: 20 }}
          />
        </Space>
      </Card>

      <Modal
        title={editingPost ? 'Edit News Post' : 'Create News Post'}
        open={isModalOpen}
        className="news-admin-theme"
        onCancel={() => {
          setIsModalOpen(false);
          setEditingPost(null);
          form.resetFields();
          setPreviewContent('');
        }}
        onOk={handleSubmit}
        confirmLoading={creating || updating}
        okButtonProps={{ disabled: !canManage }}
        width={900}
      >
        <Form
          form={form}
          layout="vertical"
          disabled={!canManage}
          initialValues={{
            category: 'ANNOUNCEMENT',
            priority: 'MEDIUM',
            isPinned: false
          }}
        >
          <Form.Item
            name="title"
            label="Title (optional)"
            rules={[{ max: 200, message: 'Title must be 200 characters or less' }]}
          >
            <Input placeholder="Optional title for the news post" />
          </Form.Item>

          <Form.Item
            name="content"
            hidden
            rules={[
              { required: true, message: 'Content is required' },
              { max: 500, message: 'Content must be 500 characters or less' }
            ]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            label={
              <Space>
                <span>Content (Markdown supported)</span>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {previewContent.length}/500
                </Text>
              </Space>
            }
            required
          >
            <Tabs
              activeKey={contentTab}
              onChange={setContentTab}
              tabBarStyle={{ marginBottom: 0 }}
              items={[
                {
                  key: 'editor',
                  label: '✏️ Editor',
                  children: (
                    <div style={{ border: '1px solid var(--hef-border)', borderRadius: '6px', overflow: 'hidden' }}>
                      <SimpleMDE
                        value={previewContent}
                        onChange={(val) => {
                          setPreviewContent(val);
                          form.setFieldValue('content', val);
                        }}
                        options={contentEditorOptions}
                        getMdeInstance={configureMdeInstance}
                      />
                    </div>
                  ),
                },
                {
                  key: 'preview',
                  label: '👁️ Preview',
                  children: (
                    <Card
                      size="small"
                      style={{ marginBottom: 16, background: 'var(--hef-bg-subtle)', minHeight: 300, borderColor: 'var(--hef-border)' }}
                    >
                      {previewContent.trim() ? (
                        <MarkdownRenderer content={previewContent} variant="small" />
                      ) : (
                        <p style={{ color: 'var(--hef-text-muted)', fontStyle: 'italic' }}>
                          No content to preview...
                        </p>
                      )}
                    </Card>
                  ),
                },
              ]}
            />
          </Form.Item>

          <Space style={{ width: '100%' }} size="large">
            <Form.Item
              name="category"
              label="Category"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <Select options={CATEGORY_OPTIONS} />
            </Form.Item>

            <Form.Item
              name="priority"
              label="Priority"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <Select options={PRIORITY_OPTIONS} />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size="large">
            <Form.Item
              name="expiresAt"
              label="Expires At"
              tooltip="News will auto-hide after this date (default: 180 days)"
            >
              <DatePicker showTime />
            </Form.Item>

            <Form.Item
              name="isPinned"
              label="Pin to Top"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default AdminNewsPage;
