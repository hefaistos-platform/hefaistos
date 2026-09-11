import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { FieldManager } from '../components/FieldManager';
import { Input, Button, Card, Space, Alert, Breadcrumb, Typography, Divider, App } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import SimpleMDE from 'react-simplemde-editor';

// Define the comprehensive GraphQL query
const GET_DATA_SOURCE_DETAILS_QUERY = gql`
  query GetDataSourceDetails($id: ID!) {
    dataSource(id: $id) {
      id
      name
      platform
      description
      fields {
        id
        fieldName
        dataType
        description
        exampleValue
      }
    }
  }
`;

// Update mutation
const UPDATE_DATA_SOURCE_MUTATION = gql`
  mutation UpdateDataSource($id: ID!, $name: String, $platform: String, $description: String) {
    updateDataSource(id: $id, name: $name, platform: $platform, description: $description) {
      dataSource {
        id
        name
        platform
        description
      }
    }
  }
`;

// Delete mutation
const DELETE_DATA_SOURCE_MUTATION = gql`
  mutation DeleteDataSource($id: ID!) {
    deleteDataSource(id: $id) {
      ok
    }
  }
`;

// --- TypeScript Types ---
interface DataSourceField {
  id: string;
  fieldName: string;
  dataType: string | null;
  description: string | null;
  exampleValue: string | null;
}

interface DataSourceDetails {
  id: string;
  name: string;
  platform: string | null;
  description: string | null;
  fields: DataSourceField[];
}

interface GetDataSourceData {
  dataSource: DataSourceDetails;
}

interface GetDataSourceVars {
  id: string;
}

export const DataSourceDetailPage = () => {
  const { dataSourceId } = useParams<{ dataSourceId: string }>();
  const navigate = useNavigate();
  const { modal } = App.useApp();

  const { data, loading, error } = useQuery<GetDataSourceData, GetDataSourceVars>(
    GET_DATA_SOURCE_DETAILS_QUERY,
    { variables: { id: dataSourceId! }, skip: !dataSourceId }
  );

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState('');
  const [platform, setPlatform] = useState('');
  const [description, setDescription] = useState('');

  // Memoized SimpleMDE options for description
  const simpleMdeOptions = useMemo(() => ({
    spellChecker: false,
    status: false,
    placeholder: 'Describe this data source...',
    toolbar: [
      'bold', 'italic', 'heading', '|',
      'quote', 'unordered-list', 'ordered-list', 'table', 'code', 'link', 'image', 'horizontal-rule', '|',
      'preview', 'side-by-side', 'fullscreen', 'guide'
    ] as const,
  } as const), []);

  const [updateDataSource, { loading: updateLoading, error: updateError }] = useMutation(
    UPDATE_DATA_SOURCE_MUTATION,
    { refetchQueries: [{ query: GET_DATA_SOURCE_DETAILS_QUERY, variables: { id: dataSourceId } }] }
  );

  const [deleteDataSource, { loading: deleteLoading }] = useMutation(DELETE_DATA_SOURCE_MUTATION, {
    onCompleted: () => {
      navigate('/catalog');
    },
    onError: (err) => {
      modal.error({
        title: 'Failed to delete',
        content: err.message,
      });
    }
  });

  useEffect(() => {
    if (data?.dataSource) {
      setName(data.dataSource.name);
      setPlatform(data.dataSource.platform || '');
      setDescription(data.dataSource.description || '');
    }
  }, [data, isEditing]);

  const handleSave = async () => {
    if (!dataSourceId || !name.trim()) return;
    try {
      await updateDataSource({ variables: { id: dataSourceId, name, platform, description } });
      setIsEditing(false);
    } catch (e) {
      console.error(e);
    }
  };

  const handleDelete = () => {
    modal.confirm({
      title: 'Are you sure you want to delete this data source?',
      content: 'This action cannot be undone.',
      okText: 'Yes, Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: () => {
        deleteDataSource({ variables: { id: dataSourceId } });
      },
    });
  };

  if (!dataSourceId) return (
    <div style={{ padding: '24px', textAlign: 'center' }}>
      <Typography.Text type="danger">Invalid Data Source URL.</Typography.Text>
    </div>
  );

  if (loading) return (
    <div style={{ padding: '24px', textAlign: 'center' }}>
      <Typography.Text>Loading data source...</Typography.Text>
    </div>
  );

  if (error) return (
    <div style={{ padding: '24px' }}>
      <Alert message="Error" description={error.message} type="error" />
    </div>
  );

  if (!data || !data.dataSource) return (
    <div style={{ padding: '24px', textAlign: 'center' }}>
      <Typography.Text>Data source not found.</Typography.Text>
    </div>
  );

  const { dataSource } = data;
  const fields = Array.isArray(dataSource.fields) ? dataSource.fields : [];

  return (
    <div style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item>
          <button onClick={() => navigate('/catalog')} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', textDecoration: 'none', padding: 0 }}>Data Catalog</button>
        </Breadcrumb.Item>
        <Breadcrumb.Item>{dataSource.name}</Breadcrumb.Item>
      </Breadcrumb>

      {updateError && (
        <Alert
          message="Error"
          description={updateError.message}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      <Card bordered style={{ marginBottom: 24 }}>
        {isEditing ? (
          <form onSubmit={(e) => { e.preventDefault(); handleSave(); }} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <Typography.Title level={3} style={{ margin: 0 }}>Edit Data Source</Typography.Title>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
                Name *
              </label>
              <Input
                placeholder="Data source name"
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
                placeholder="e.g., Windows, Linux, AWS, Azure"
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
                Description
              </label>
              <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden' }}>
                <SimpleMDE
                  value={description}
                  onChange={setDescription}
                  options={simpleMdeOptions}
                />
              </div>
            </div>

            <Space style={{ marginTop: 8 }}>
              <Button type="primary" htmlType="submit" disabled={updateLoading || !name.trim()} loading={updateLoading}>
                <PixelIcon name="save" className="w-5 h-5" />
                Save Changes
              </Button>
              <Button onClick={() => setIsEditing(false)}>Cancel</Button>
            </Space>
          </form>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 16 }}>
              <div>
                <Typography.Title level={2} style={{ margin: 0, marginBottom: 8 }}>{dataSource.name}</Typography.Title>
                {dataSource.platform && (
                  <Typography.Text type="secondary">
                    <strong>Platform:</strong> {dataSource.platform}
                  </Typography.Text>
                )}
              </div>
              <Space>
                <Button onClick={() => setIsEditing(true)}>
                  <PixelIcon name="edit" className="w-5 h-5" />
                  Edit Metadata
                </Button>
                <Button danger onClick={handleDelete} loading={deleteLoading}>
                  <PixelIcon name="trash" className="w-5 h-5" />
                  Delete
                </Button>
              </Space>
            </div>

            <Divider />

            {dataSource.description ? (
              <div style={{ marginBottom: 16 }}>
                <MarkdownRenderer content={dataSource.description} variant="small" skipEmpty={false} />
              </div>
            ) : (
              <Typography.Text type="secondary" style={{ marginBottom: 16, display: 'block' }}>
                No description provided.
              </Typography.Text>
            )}
          </>
        )}
      </Card>

      {!isEditing && (
        <Card title={<Typography.Title level={4} style={{ margin: 0 }}>Fields</Typography.Title>} bordered>
          <FieldManager
            dataSourceId={dataSource.id}
            fields={fields}
            refetchQuery={GET_DATA_SOURCE_DETAILS_QUERY}
          />
        </Card>
      )}
    </div>
  );
};