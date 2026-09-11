import React, { useEffect, useMemo, useRef, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Modal, Input, Card, List, Typography, Space, Tag, Empty, App } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import { MarkdownRenderer, markdownToPlainText } from '../components/MarkdownRenderer';

// --- GraphQL Queries ---
const GET_ALL_KB_DATA_QUERY = gql`
  query GetAllKBData {
    me { username role isSuperuser }
    allKbCategories {
      id
      name
      description
      articles {
        id
        title
        updatedAt
        tags
        author {
          username
        }
      }
    }
  }
`;

const CREATE_KB_CATEGORY = gql`
  mutation CreateKBCategory($name: String!, $description: String) {
    createKbCategory(name: $name, description: $description) {
      category { id name description articles { id } }
    }
  }
`;

const DELETE_KB_CATEGORY = gql`
  mutation DeleteKBCategory($id: UUID!) {
    deleteKbCategory(id: $id) { ok }
  }
`;

const UPDATE_KB_CATEGORY = gql`
  mutation UpdateKBCategory($id: UUID!, $name: String, $description: String) {
    updateKbCategory(id: $id, name: $name, description: $description) {
      category { id name description }
    }
  }
`;

const EXPORT_KB_ARTICLES = gql`
  mutation ExportKBArticles {
    exportKbArticles {
      ok
      filename
      payloadJson
    }
  }
`;

const IMPORT_KB_ARTICLES = gql`
  mutation ImportKBArticles($payloadJson: String!) {
    importKbArticles(payloadJson: $payloadJson) {
      ok
      categoriesCreated
      categoriesUpdated
      articlesCreated
      articlesUpdated
    }
  }
`;

// --- TypeScript Types ---
interface KBArticle {
  id: string;
  title: string;
  updatedAt: string;
  tags?: string[];
  author: { username: string } | null;
}
interface KBCategory {
  id: string;
  name: string;
  description: string | null;
  articles: KBArticle[];
}

interface CreateKBCategoryResponse {
  createKbCategory: { category: KBCategory };
}

interface ExportKBArticlesResponse {
  exportKbArticles: {
    ok: boolean;
    filename: string;
    payloadJson: string;
  };
}

interface ImportKBArticlesResponse {
  importKbArticles: {
    ok: boolean;
    categoriesCreated: number;
    categoriesUpdated: number;
    articlesCreated: number;
    articlesUpdated: number;
  };
}

export const KnowledgeBasePage = () => {
  const navigate = useNavigate();
  const { modal, message } = App.useApp();
  const { data, loading, error, refetch } = useQuery<{ allKbCategories: KBCategory[]; me?: { username: string; role: string; isSuperuser?: boolean } | null }>(
    GET_ALL_KB_DATA_QUERY,
    {
      fetchPolicy: 'cache-and-network',
      nextFetchPolicy: 'cache-first',
      notifyOnNetworkStatusChange: true,
    }
  );

  // UI State
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [isCreateCatOpen, setIsCreateCatOpen] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatDesc, setNewCatDesc] = useState('');

  const [createCategory, { loading: creatingCat }] = useMutation<CreateKBCategoryResponse>(CREATE_KB_CATEGORY);

  const [deleteCategory, { loading: deletingCat }] = useMutation(DELETE_KB_CATEGORY, {
    onCompleted: async () => {
      await refetch();
      message.success('Category deleted');
    },
    onError: (err) => {
      message.error(err.message || 'Failed to delete category');
    }
  });

  const [updateCategory, { loading: updatingCat }] = useMutation(UPDATE_KB_CATEGORY, {
    onCompleted: async () => {
      await refetch();
      message.success('Category updated');
    },
    onError: (err) => message.error(err.message || 'Failed to update category')
  });

  const [exportKbArticles, { loading: exportingKb }] = useMutation<ExportKBArticlesResponse>(EXPORT_KB_ARTICLES);
  const [importKbArticles, { loading: importingKb }] = useMutation<ImportKBArticlesResponse>(IMPORT_KB_ARTICLES);
  const importFileInputRef = useRef<HTMLInputElement | null>(null);

  const categories = useMemo(() => data?.allKbCategories || [], [data]);
  const meRole = (data?.me?.role || '').toUpperCase();
  const isElOne = meRole === 'ELONE';
  const isSuperuser = Boolean(data?.me?.isSuperuser);
  const isAdmin = meRole === 'ADMIN';
  const canExportKb = !isElOne && (isAdmin || isSuperuser);
  const canImportKb = !isElOne && isSuperuser;

  // Ensure a category is selected when data loads
  useEffect(() => {
    if (!selectedCategoryId && categories.length > 0) {
      setSelectedCategoryId(categories[0].id);
    }
  }, [categories, selectedCategoryId]);

  const selectedCategory = useMemo(() => categories.find(c => c.id === selectedCategoryId) || null, [categories, selectedCategoryId]);

  const filteredArticles = useMemo(() => {
    if (!selectedCategory) return [] as KBArticle[];
    const q = search.trim().toLowerCase();
    const list = selectedCategory.articles.slice().sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    if (!q) return list;
    return list.filter(a => a.title.toLowerCase().includes(q));
  }, [selectedCategory, search]);

  // Tag filter options derived from selected category
  const allTags = useMemo(() => {
    const set = new Set<string>();
    selectedCategory?.articles.forEach(a => a.tags?.forEach((t: string) => set.add(t)));
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [selectedCategory]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const tagFilteredArticles = useMemo(() => {
    if (!selectedTags.length) return filteredArticles;
    return filteredArticles.filter(a => {
      const tags: string[] = a.tags || [];
      return selectedTags.every(t => tags.includes(t));
    });
  }, [filteredArticles, selectedTags]);

  // Unread tracking (client-side): mark articles updated after lastSeen per category as "New"
  const lastSeenKey = selectedCategoryId ? `kb:lastSeen:${selectedCategoryId}` : null;
  const lastSeen = useMemo(() => {
    if (!lastSeenKey) return 0;
    const raw = localStorage.getItem(lastSeenKey);
    return raw ? parseInt(raw, 10) : 0;
  }, [lastSeenKey]);
  const markAllRead = () => {
    if (lastSeenKey) localStorage.setItem(lastSeenKey, `${Date.now()}`);
  };

  // Color palette for category tiles
  const categoryColors = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
    '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
    '#F8B88B', '#AED6F1', '#F5B7B1', '#A9DFBF',
  ];
  const getCategoryColor = (index: number) => categoryColors[index % categoryColors.length];

  const handleEditCategory = (cat: KBCategory) => {
    let newName = cat.name;
    let newDesc = cat.description || '';
    modal.confirm({
      title: 'Edit Category',
      icon: null,
      className: 'knowledge-theme-modal',
      content: (
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 8 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Name</label>
            <Input defaultValue={newName} onChange={(e) => { newName = e.target.value; }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Description</label>
            <Input.TextArea rows={3} defaultValue={newDesc} onChange={(e) => { newDesc = e.target.value; }} />
          </div>
        </div>
      ),
      okText: 'Save',
      cancelText: 'Cancel',
      onOk: () => updateCategory({ variables: { id: cat.id, name: newName, description: newDesc } }),
    });
  };

  const handleDeleteCategory = (cat: KBCategory) => {
    modal.confirm({
      title: 'Delete category?',
      content: 'Articles will not be deleted; their category will be cleared.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      cancelText: 'Cancel',
      onOk: () => deleteCategory({ variables: { id: cat.id } })
    });
  };

  const handleExportKnowledgeBase = async () => {
    try {
      const res = await exportKbArticles();
      const payload = res.data?.exportKbArticles;
      if (!payload?.ok || !payload.payloadJson) {
        message.error('Export failed');
        return;
      }

      const blob = new Blob([payload.payloadJson], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = payload.filename || 'knowledge-base-export.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      message.success('Knowledge Base exported');
    } catch (err: any) {
      message.error(err?.message || 'Failed to export Knowledge Base');
    }
  };

  const handleImportFileSelection: React.ChangeEventHandler<HTMLInputElement> = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const payloadJson = await file.text();
      const res = await importKbArticles({ variables: { payloadJson } });
      const result = res.data?.importKbArticles;
      if (!result?.ok) {
        message.error('Import failed');
        return;
      }

      message.success(
        `Import completed: ${result.categoriesCreated} categories created, ${result.categoriesUpdated} categories updated, ${result.articlesCreated} articles created, ${result.articlesUpdated} articles updated.`
      );
      await refetch();
    } catch (err: any) {
      message.error(err?.message || 'Failed to import Knowledge Base');
    } finally {
      event.target.value = '';
    }
  };

  return (
    <div className="knowledge-theme">
      {error && (
        <div style={{ marginBottom: 12 }}>
          <Typography.Text type="danger">Error: {error.message}</Typography.Text>
        </div>
      )}
      <div style={{ padding: '0 24px' }}>
        {/* Categories Grid */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Typography.Title level={4} style={{ margin: 0 }}>Categories</Typography.Title>
            {(data?.me?.role === 'ADMIN' || data?.me?.role === 'VIEWER') && !isElOne && (
            <Button type="dashed" onClick={() => setIsCreateCatOpen(true)}>
              <PixelIcon name="add" className="w-4 h-4" />
              <span style={{ marginLeft: 8 }}>New Category</span>
            </Button>
            )}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', justifyContent: 'center' }}>
            {categories.map((cat, index) => (
              <Card
                key={cat.id}
                hoverable
                style={{
                  cursor: 'pointer',
                  borderLeft: `5px solid ${getCategoryColor(index)}`,
                  background: selectedCategoryId === cat.id ? 'var(--hef-bg-subtle)' : 'var(--hef-bg-surface)',
                  transition: 'all 0.3s ease',
                  width: '180px',
                  flexShrink: 0,
                }}
                onClick={() => setSelectedCategoryId(cat.id)}
              >
                <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', minHeight: 150 }}>
                  <div
                    style={{
                      width: '50px',
                      height: '50px',
                      borderRadius: '50%',
                      background: getCategoryColor(index),
                      margin: '0 auto 12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '24px',
                      fontWeight: 'bold',
                      color: 'white',
                    }}
                  >
                    {cat.articles.length}
                  </div>
                  <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>
                    {cat.name}
                  </Typography.Text>
                  {cat.description && (
                    <Typography.Text type="secondary" ellipsis={{ tooltip: markdownToPlainText(cat.description) }} style={{ fontSize: '12px', display: 'block' }}>
                      {markdownToPlainText(cat.description)}
                    </Typography.Text>
                  )}
                  {/* Bottom buttons */}
                  <div style={{ marginTop: 'auto', paddingTop: 12 }}>
                    <Space>
                      {(data?.me?.role === 'ADMIN' || data?.me?.role === 'VIEWER') && !isElOne && (
                      <Button
                        size="small"
                        loading={updatingCat}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEditCategory(cat);
                        }}
                      >
                        Edit
                      </Button>
                      )}
                      {(data?.me?.role === 'ADMIN' || data?.me?.role === 'VIEWER') && !isElOne && (
                      <Button
                        danger
                        size="small"
                        loading={deletingCat}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteCategory(cat);
                        }}
                      >
                        Delete
                      </Button>
                      )}
                    </Space>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* Articles Card */}
        <div>
          <Card
            bordered
            title={
              <Space direction="vertical" size={0}>
                <Typography.Title level={3} style={{ margin: 0 }}>{selectedCategory?.name || 'Knowledge Base'}</Typography.Title>
                {selectedCategory?.description && (
                  <MarkdownRenderer content={selectedCategory.description} variant="small" skipEmpty={false} />
                )}
              </Space>
            }
            extra={
              <Space>
                <Input.Search
                  allowClear
                  placeholder="Search articles"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ width: 240 }}
                />
                {allTags.length > 0 && (
                  <Space>
                    <Typography.Text type="secondary">Filter by tag:</Typography.Text>
                    <div>
                      {allTags.map(tag => (
                        <Tag.CheckableTag
                          key={tag}
                          checked={selectedTags.includes(tag)}
                          onChange={(checked) => {
                            setSelectedTags(prev => checked ? [...prev, tag] : prev.filter(t => t !== tag));
                          }}
                        >{tag}</Tag.CheckableTag>
                      ))}
                    </div>
                  </Space>
                )}
                <Button onClick={() => refetch()}>
                  <PixelIcon name="refresh" className="w-5 h-5" />
                  <span style={{ marginLeft: 8 }}>Refresh</span>
                </Button>
                {canExportKb && (
                  <Button onClick={handleExportKnowledgeBase} loading={exportingKb}>
                    Export
                  </Button>
                )}
                {canImportKb && (
                  <Button onClick={() => importFileInputRef.current?.click()} loading={importingKb}>
                    Import
                  </Button>
                )}
                <Button onClick={markAllRead}>
                  Mark all read
                </Button>
                {(data?.me?.role === 'ADMIN' || data?.me?.role === 'VIEWER') && !isElOne && (
                <Button type="primary" onClick={() => navigate('/kb/new')}>
                  <PixelIcon name="add" className="w-5 h-5" />
                  <span style={{ marginLeft: 8 }}>New Article</span>
                </Button>
                )}
              </Space>
            }
            loading={loading}
          >
            {!selectedCategory ? (
              <Empty description="Select a category to view articles" />
            ) : tagFilteredArticles.length === 0 ? (
              <Empty description={search || selectedTags.length ? 'No articles match your filters' : 'No articles in this category yet'} />
            ) : (
              <List
                itemLayout="vertical"
                dataSource={tagFilteredArticles}
                renderItem={(article: KBArticle) => (
                  <List.Item
                    key={article.id}
                    actions={isElOne
                      ? []
                      : [
                          <Button size="small" onClick={() => navigate(`/kb/edit/${article.id}`)} key="edit">
                            Edit
                          </Button>,
                        ]
                    }
                  >
                    <List.Item.Meta
                      title={<Link to={`/kb/article/${article.id}`}>{article.title}</Link>}
                      description={
                        <Space size={16}>
                          <Typography.Text type="secondary">By {article.author?.username || 'N/A'}</Typography.Text>
                          <Typography.Text type="secondary">Updated {new Date(article.updatedAt).toLocaleDateString()}</Typography.Text>
                          {Number(new Date(article.updatedAt)) > lastSeen && <Tag color="green">NEW</Tag>}
                          {selectedCategory && <Tag>{selectedCategory.name}</Tag>}
                          {(article.tags || []).map((t: string) => (
                            <Tag key={t} color="blue">{t}</Tag>
                          ))}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </div>
      </div>

      <Modal
        title="Create Category"
        className="knowledge-theme-modal"
        open={isCreateCatOpen}
        onCancel={() => setIsCreateCatOpen(false)}
        onOk={async () => {
          if (!newCatName.trim()) return;
          const res = await createCategory({ variables: { name: newCatName.trim(), description: newCatDesc || null } });
          setIsCreateCatOpen(false);
          setNewCatName('');
          setNewCatDesc('');
          await refetch();
          const created = res.data?.createKbCategory.category;
          if (created) setSelectedCategoryId(created.id);
        }}
        okButtonProps={{ disabled: !newCatName.trim(), loading: creatingCat }}
      >
        <div className="space-y-3">
          <div>
            <label className="block mb-1 text-sm font-medium">Name</label>
            <Input value={newCatName} onChange={(e) => setNewCatName(e.target.value)} placeholder="Category name" />
          </div>
          <div>
            <label className="block mb-1 text-sm font-medium">Description</label>
            <Input.TextArea rows={3} value={newCatDesc} onChange={(e) => setNewCatDesc(e.target.value)} placeholder="Optional description" />
          </div>
        </div>
      </Modal>
      <input
        ref={importFileInputRef}
        type="file"
        accept="application/json,.json"
        style={{ display: 'none' }}
        onChange={handleImportFileSelection}
      />
    </div>
  );
};
