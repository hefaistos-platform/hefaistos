import React, { useState, useEffect, useMemo } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Input, Select, Card, Space, Alert, Breadcrumb, Typography, Modal } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import SimpleMDE from 'react-simplemde-editor';

// 1. Query to get the article's current data
const GET_KB_ARTICLE_QUERY = gql`
  query GetKBArticle($id: UUID!) {
    kbArticle(id: $id) {
      id
      title
      content
      category {
        id
        name
      }
    }
  }
`;

// 2. Query to get all categories for the dropdown
const GET_KB_CATEGORIES_QUERY = gql`
  query GetKBCategories {
    allKbCategories {
      id
      name
    }
  }
`;

// 3. Mutation to update the article
const UPDATE_KB_ARTICLE_MUTATION = gql`
  mutation UpdateKBArticle($id: UUID!, $title: String, $content: String, $categoryId: UUID) {
    updateKbArticle(id: $id, title: $title, content: $content, categoryId: $categoryId) {
      article {
        id
        title
        content
      }
    }
  }
`;

const REFRESH_KB_DATA_QUERY = gql`
  query GetAllKBData {
    allKbCategories {
      id
      name
      description
      articles {
        id
        title
        updatedAt
        author { username }
      }
    }
  }
`;

const GET_ME_ROLE_QUERY = gql`
  query GetMeRole {
    me {
      role
    }
  }
`;

// Mutation to delete the article
const DELETE_KB_ARTICLE_MUTATION = gql`
  mutation DeleteKBArticle($id: UUID!) {
    deleteKbArticle(id: $id) {
      ok
    }
  }
`;

// --- TypeScript Types ---
interface KBCategory {
  id: string;
  name: string;
}

interface GetCategoriesData {
  allKbCategories: KBCategory[];
}

interface KBArticleDetails {
  id: string;
  title: string;
  content: string;
  category: { id: string; name: string } | null;
}

interface GetArticleData {
  kbArticle: KBArticleDetails | null;
}

interface UpdateKBArticleResponse {
  updateKbArticle: {
    article: KBArticleDetails;
  };
}

export const EditKBArticlePage: React.FC = () => {
  const { articleId } = useParams<{ articleId: string }>();
  const navigate = useNavigate();
  const { data: accessData, loading: accessLoading } = useQuery<{ me?: { role: string } | null }>(GET_ME_ROLE_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const isElOne = (accessData?.me?.role || '').toUpperCase() === 'ELONE';

  // Form State
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [categoryId, setCategoryId] = useState<string | null>(null);

  // API Hooks
  const { data: categoriesData, loading: categoriesLoading } = useQuery<GetCategoriesData>(GET_KB_CATEGORIES_QUERY);
  const { data: articleData, loading: articleLoading } = useQuery<GetArticleData>(
    GET_KB_ARTICLE_QUERY,
    { variables: { id: articleId } }
  );

  const [updateArticle, { loading: updateLoading, error: updateError }] = useMutation<UpdateKBArticleResponse>(
    UPDATE_KB_ARTICLE_MUTATION
  );

  const [deleteArticle, { loading: deleteLoading, error: deleteError }] = useMutation(DELETE_KB_ARTICLE_MUTATION);

  useEffect(() => {
    if (!accessLoading && isElOne) {
      navigate('/kb', { replace: true });
    }
  }, [accessLoading, isElOne, navigate]);

  // Shared SimpleMDE options - memoized with placeholder
  const simpleMdeOptions = useMemo(() => ({
    spellChecker: false,
    status: false,
    placeholder: 'Update your article content…',
    toolbar: [
      'bold', 'italic', 'heading', '|',
      'quote', 'unordered-list', 'ordered-list', 'table', 'code', 'link', 'image', 'horizontal-rule', '|',
      'preview', 'side-by-side', 'fullscreen', 'guide'
    ] as const,
  } as const), []);

  // Populate form when article data loads
  useEffect(() => {
    if (articleData?.kbArticle) {
      setTitle(articleData.kbArticle.title);
      setContent(articleData.kbArticle.content);
      setCategoryId(articleData.kbArticle.category?.id || null);
    }
  }, [articleData]);

  if (isElOne) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await updateArticle({
        variables: {
          id: articleId,
          title,
          content,
          categoryId: categoryId || undefined,
        },
        refetchQueries: [{ query: REFRESH_KB_DATA_QUERY }],
        awaitRefetchQueries: true,
      });
      navigate(`/kb/article/${articleId}`);
    } catch (e) {
      console.error('Failed to update article:', e);
    }
  };

  const handleDelete = async () => {
    Modal.confirm({
      title: 'Delete Article',
      content: 'Are you sure you want to delete this article permanently? This action cannot be undone.',
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await deleteArticle({
            variables: { id: articleId },
            refetchQueries: [{ query: REFRESH_KB_DATA_QUERY }],
            awaitRefetchQueries: true,
          });
          navigate('/kb');
        } catch (e) {
          console.error('Failed to delete article:', e);
        }
      },
    });
  };

  if (articleLoading) {
    return (
      <div style={{ padding: '24px', textAlign: 'center' }}>
        <Typography.Text>Loading article...</Typography.Text>
      </div>
    );
  }

  return (
    <div className="knowledge-theme" style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <button onClick={() => navigate('/kb')} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', textDecoration: 'none', padding: 0 }}>Knowledge Base</button>
        </Breadcrumb.Item>
        <Breadcrumb.Item>
          <button onClick={() => navigate(`/kb/article/${articleId}`)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', textDecoration: 'none', padding: 0 }}>{articleData?.kbArticle?.title || 'Article'}</button>
        </Breadcrumb.Item>
        <Breadcrumb.Item>Edit</Breadcrumb.Item>
      </Breadcrumb>

      <Card
        title={<Typography.Title level={3} style={{ margin: 0 }}>Edit Article</Typography.Title>}
        bordered
        style={{ marginBottom: 24 }}
      >
        {(updateError || deleteError) && (
          <Alert
            message="Error"
            description={updateError?.message || deleteError?.message}
            type="error"
            showIcon
            closable
            style={{ marginBottom: 16 }}
          />
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
                Article Title *
              </label>
              <Input
                placeholder="Enter article title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
                Category
              </label>
              <Select
                placeholder="Select a category"
                value={categoryId || undefined}
                onChange={(value) => setCategoryId(value || null)}
                disabled={categoriesLoading}
                options={categoriesData?.allKbCategories.map((cat) => ({
                  label: cat.name,
                  value: cat.id,
                })) || []}
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
              Content (Markdown) *
            </label>
            <div style={{ border: '1px solid var(--hef-border)', borderRadius: '6px', overflow: 'hidden' }}>
              <SimpleMDE
                value={content}
                onChange={setContent}
                options={simpleMdeOptions}
              />
            </div>
          </div>

          <Space style={{ marginTop: 16, justifyContent: 'space-between', width: '100%' }}>
            <div>
              <Button
                type="primary"
                htmlType="submit"
                disabled={updateLoading || !title.trim()}
                loading={updateLoading}
              >
                <PixelIcon name="save" className="w-5 h-5" />
                {updateLoading ? 'Saving...' : 'Save Changes'}
              </Button>
              <Button onClick={() => navigate(`/kb/article/${articleId}`)} style={{ marginLeft: 8 }}>
                Cancel
              </Button>
            </div>
            <Button danger onClick={handleDelete} disabled={deleteLoading} loading={deleteLoading}>
              <PixelIcon name="delete" className="w-5 h-5" />
              {deleteLoading ? 'Deleting...' : 'Delete Article'}
            </Button>
          </Space>
        </form>
      </Card>
    </div>
  );
};

export default EditKBArticlePage;
