import React, { useEffect, useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { useMutation } from '@apollo/client/react';
import { useNavigate } from 'react-router-dom';
import { Button, Input, Select, Card, Space, Alert, Breadcrumb, Typography } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import SimpleMDE from 'react-simplemde-editor';

// --- GraphQL Queries and Mutations ---

const GET_KB_CATEGORIES_QUERY = gql`
  query GetKBCategories {
    allKbCategories {
      id
      name
    }
  }
`;

const CREATE_KB_ARTICLE_MUTATION = gql`
  mutation CreateKBArticle($title: String!, $content: String!, $categoryId: UUID, $tags: [String]) {
    createKbArticle(title: $title, content: $content, categoryId: $categoryId, tags: $tags) {
      article {
        id
        title
        tags
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

// --- TypeScript Types ---
interface KBCategory {
  id: string;
  name: string;
}
interface GetCategoriesData {
  allKbCategories: KBCategory[];
}
interface CreateKBArticleResponse {
  createKbArticle: {
    article: {
      id: string;
      title: string;
    };
  };
}

export const CreateKBArticlePage = () => {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const navigate = useNavigate();
  const { data: accessData, loading: accessLoading } = useQuery<{ me?: { role: string } | null }>(GET_ME_ROLE_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const isElOne = (accessData?.me?.role || '').toUpperCase() === 'ELONE';

  useEffect(() => {
    if (!accessLoading && isElOne) {
      navigate('/kb', { replace: true });
    }
  }, [accessLoading, isElOne, navigate]);

  // Shared SimpleMDE options - memoized with placeholder
  const simpleMdeOptions = useMemo(() => ({
    spellChecker: false,
    status: false,
    placeholder: 'Write your article content in Markdown…',
    toolbar: [
      'bold', 'italic', 'heading', '|',
      'quote', 'unordered-list', 'ordered-list', 'table', 'code', 'link', 'image', 'horizontal-rule', '|',
      'preview', 'side-by-side', 'fullscreen', 'guide'
    ] as const,
  } as const), []);

  const { data: categoriesData, loading: categoriesLoading } = useQuery<GetCategoriesData>(GET_KB_CATEGORIES_QUERY);

  const [createKbArticle, { loading: createLoading, error }] = useMutation<CreateKBArticleResponse>(CREATE_KB_ARTICLE_MUTATION);

  if (isElOne) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const result = await createKbArticle({
        variables: {
          title,
          content,
          categoryId: categoryId || undefined,
          tags: tags.length > 0 ? tags : undefined,
        },
        refetchQueries: [{ query: REFRESH_KB_DATA_QUERY }],
        awaitRefetchQueries: true,
      });

      if (result.data && result.data.createKbArticle.article) {
        navigate(`/kb/article/${result.data.createKbArticle.article.id}`);
      }
    } catch (e) {
      console.error('Failed to create article:', e);
    }
  };

  return (
    <div className="knowledge-theme" style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <button onClick={() => navigate('/kb')} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', textDecoration: 'none', padding: 0 }}>Knowledge Base</button>
        </Breadcrumb.Item>
        <Breadcrumb.Item>New Article</Breadcrumb.Item>
      </Breadcrumb>

      <Card
        title={<Typography.Title level={3} style={{ margin: 0 }}>Create New Article</Typography.Title>}
        bordered
        style={{ marginBottom: 24 }}
      >
        {error && (
          <Alert
            message="Error"
            description={error.message}
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
              Tags
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
              {tags.map((tag, index) => (
                <span
                  key={index}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '4px 8px',
                    backgroundColor: '#e6f7ff',
                    border: '1px solid #91d5ff',
                    borderRadius: '4px',
                    fontSize: '12px',
                  }}
                >
                  {tag}
                  <button
                    type="button"
                    onClick={() => setTags(tags.filter((_, i) => i !== index))}
                    style={{
                      marginLeft: '4px',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: '#1890ff',
                      padding: '0 2px',
                    }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <Input
              placeholder="Type a tag and press Enter"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  const newTag = tagInput.trim();
                  if (newTag && !tags.includes(newTag)) {
                    setTags([...tags, newTag]);
                  }
                  setTagInput('');
                }
              }}
              style={{ maxWidth: '300px' }}
            />
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

          <Space style={{ marginTop: 16 }}>
            <Button
              type="primary"
              htmlType="submit"
              disabled={createLoading || !title.trim()}
              loading={createLoading}
            >
              <PixelIcon name="add" className="w-5 h-5" />
              {createLoading ? 'Creating...' : 'Create Article'}
            </Button>
            <Button onClick={() => navigate('/kb')}>Cancel</Button>
          </Space>
        </form>
      </Card>
    </div>
  );
};
