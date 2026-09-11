import React, { useState, useMemo } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Table, Button, Input, Space, App, Card, Tabs } from 'antd';
import SimpleMDE from 'react-simplemde-editor';
import { createEditorOptions, MARKDOWN_PLACEHOLDERS, configureMdeInstance } from '../config/markdownConfig';
import { MarkdownRenderer } from './MarkdownRenderer';

// --- TypeScript Types ---
interface DataSourceField {
  id: string;
  fieldName: string;
  dataType: string | null;
  description: string | null;
  exampleValue: string | null;
}

interface FieldManagerProps {
  dataSourceId: string;
  fields: DataSourceField[];
  refetchQuery: any; // Query to refetch after a change
}

// --- GraphQL Mutations ---
const ADD_FIELD_MUTATION = gql`
  mutation AddDataSourceField(
    $dataSourceId: ID!, 
    $fieldName: String!, 
    $dataType: String, 
    $description: String, 
    $exampleValue: String
  ) {
    addDataSourceField(
      dataSourceId: $dataSourceId, 
      fieldName: $fieldName, 
      dataType: $dataType, 
      description: $description, 
      exampleValue: $exampleValue
    ) {
      dataSourceField { id }
    }
  }
`;

const DELETE_FIELD_MUTATION = gql`
  mutation DeleteDataSourceField($id: ID!) {
    deleteDataSourceField(id: $id) {
      ok
    }
  }
`;

// Note: We are omitting UpdateField for simplicity, using Delete + Add

export const FieldManager: React.FC<FieldManagerProps> = ({ dataSourceId, fields, refetchQuery }) => {
  const { modal, message } = App.useApp();
  // State for the "Add New" form
  const [fieldName, setFieldName] = useState('');
  const [dataType, setDataType] = useState('');
  const [description, setDescription] = useState('');
  const [exampleValue, setExampleValue] = useState('');
  const [previewTab, setPreviewTab] = useState('editor');

  // Memoized editor options
  const editorOptions = useMemo(
    () => createEditorOptions('minimal', MARKDOWN_PLACEHOLDERS.description),
    []
  );

  const [addField, { loading: addLoading }] = useMutation(ADD_FIELD_MUTATION, {
    refetchQueries: [{ query: refetchQuery, variables: { id: dataSourceId } }]
  });
  const [deleteField, { loading: deleteLoading }] = useMutation(DELETE_FIELD_MUTATION, {
    refetchQueries: [{ query: refetchQuery, variables: { id: dataSourceId } }]
  });

  const handleAddField = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await addField({
        variables: { dataSourceId, fieldName, dataType, description, exampleValue }
      });
      message.success('Field added');
      setFieldName('');
      setDataType('');
      setDescription('');
      setExampleValue('');
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
      message.error('Failed to add field');
    }
  };

  const handleDeleteField = async (fieldId: string) => {
    modal.confirm({
      title: 'Delete field?',
      content: 'This will permanently remove the field definition.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await deleteField({ variables: { id: fieldId } });
          message.success('Field deleted');
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error(e);
          message.error('Failed to delete field');
        }
      }
    });
  };

  return (
    <div>
      <h3>Data Fields</h3>
      <Table
        rowKey="id"
        dataSource={fields}
        pagination={false}
        size="small"
        columns={[
          { title: 'Field Name', dataIndex: 'fieldName' },
          { title: 'Data Type', dataIndex: 'dataType', render: (v: string | null) => v || 'N/A' },
          { title: 'Description', dataIndex: 'description', render: (v: string | null) => v || 'N/A' },
          { title: 'Example', dataIndex: 'exampleValue', render: (v: string | null) => v || 'N/A' },
          {
            title: 'Actions',
            render: (_: any, record: DataSourceField) => (
              <Button danger size="small" onClick={() => handleDeleteField(record.id)} loading={deleteLoading}>Delete</Button>
            )
          }
        ]}
        locale={{ emptyText: 'No fields documented for this data source.' }}
        style={{ marginTop: '1rem' }}
      />

      <hr style={{ margin: '2rem 0' }} />

      <h4>Add New Field</h4>
      <form onSubmit={handleAddField}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Input 
            value={fieldName} 
            onChange={(e) => setFieldName(e.target.value)} 
            placeholder="Field Name (e.g., ProcessId)" 
            required 
          />
          <Input 
            value={dataType} 
            onChange={(e) => setDataType(e.target.value)} 
            placeholder="Data Type (e.g., integer)" 
          />
          
          {/* Description with Markdown Editor */}
          <div>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 500 }}>
              Description (Markdown supported)
            </label>
            <Tabs
              activeKey={previewTab}
              onChange={setPreviewTab}
              tabBarStyle={{ marginBottom: 0 }}
              items={[
                {
                  key: 'editor',
                  label: '✏️ Editor',
                  children: (
                    <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden' }}>
                      <SimpleMDE
                        value={description}
                        onChange={setDescription}
                        options={editorOptions}
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
                      style={{ marginBottom: 16, background: '#f5f5f5', minHeight: 150 }}
                    >
                      {description.trim() ? (
                        <MarkdownRenderer content={description} variant="small" />
                      ) : (
                        <p style={{ color: '#999', fontStyle: 'italic' }}>
                          No content to preview...
                        </p>
                      )}
                    </Card>
                  ),
                },
              ]}
            />
          </div>

          <Input 
            value={exampleValue} 
            onChange={(e) => setExampleValue(e.target.value)} 
            placeholder="Example Value (e.g., 4688)" 
          />
          <Button type="primary" htmlType="submit" loading={addLoading}>
            Add Field
          </Button>
        </Space>
      </form>
    </div>
  );
};