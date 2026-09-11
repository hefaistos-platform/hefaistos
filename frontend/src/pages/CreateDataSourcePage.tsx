import React, { useState, useMemo } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { useNavigate } from 'react-router-dom';
import { Input, Button, Card, Space, Alert, Breadcrumb, Typography } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import SimpleMDE from 'react-simplemde-editor';

// GraphQL mutation to create a data source
const CREATE_DATA_SOURCE_MUTATION = gql`
  mutation CreateDataSource($name: String!, $platform: String, $description: String) {
    createDataSource(name: $name, platform: $platform, description: $description) {
      dataSource { id name }
    }
  }
`;

// Types
interface CreateDataSourceData {
  createDataSource: { dataSource: { id: string } };
}
interface CreateDataSourceVars {
  name: string;
  platform?: string;
  description?: string;
}

export const CreateDataSourcePage: React.FC = () => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [platform, setPlatform] = useState('');
  const [description, setDescription] = useState('');

  // Memoized SimpleMDE options for description
  const simpleMdeOptions = useMemo(() => ({
    spellChecker: false,
    status: false,
    placeholder: 'Describe this data source: what it contains, how it\'s used, any relevant details...',
    toolbar: [
      'bold', 'italic', 'heading', '|',
      'quote', 'unordered-list', 'ordered-list', 'table', 'code', 'link', 'image', 'horizontal-rule', '|',
      'preview', 'side-by-side', 'fullscreen', 'guide'
    ] as const,
  } as const), []);

  const [createDataSource, { loading, error }] = useMutation<CreateDataSourceData, CreateDataSourceVars>(
    CREATE_DATA_SOURCE_MUTATION
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const { data } = await createDataSource({
        variables: {
          name: name.trim(),
          platform: platform.trim() || undefined,
          description: description.trim() || undefined,
        },
      });
      const id = data?.createDataSource.dataSource.id;
      if (id) navigate(`/catalog/${id}`);
      else navigate('/catalog');
    } catch (err) {
      console.error('Failed to create data source', err);
    }
  };

  return (
    <div className="knowledge-theme" style={{ padding: '24px', maxWidth: '800px', margin: '0 auto' }}>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <button onClick={() => navigate('/catalog')} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', textDecoration: 'none', padding: 0 }}>Data Catalog</button>
        </Breadcrumb.Item>
        <Breadcrumb.Item>New Data Source</Breadcrumb.Item>
      </Breadcrumb>

      <Card
        title={<Typography.Title level={3} style={{ margin: 0 }}>Create New Data Source</Typography.Title>}
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
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
              Data Source Name *
            </label>
            <Input
              placeholder="e.g., Production Database, AWS S3 Bucket"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
              Platform
            </label>
            <Input
              placeholder="e.g., Windows, Linux, AWS, Azure, Kubernetes"
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
              Description
            </label>
            <div style={{ border: '1px solid var(--hef-border)', borderRadius: '6px', overflow: 'hidden' }}>
              <SimpleMDE
                value={description}
                onChange={setDescription}
                options={simpleMdeOptions}
              />
            </div>
          </div>

          <Space style={{ marginTop: 16 }}>
            <Button
              type="primary"
              htmlType="submit"
              disabled={loading || !name.trim()}
              loading={loading}
            >
              <PixelIcon name="add" className="w-5 h-5" />
              {loading ? 'Creating...' : 'Create Data Source'}
            </Button>
            <Button onClick={() => navigate('/catalog')}>Cancel</Button>
          </Space>
        </form>
      </Card>
    </div>
  );
};
