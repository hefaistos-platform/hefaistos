import React, { useState, useMemo } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Modal, Input, Select, message, Button as AntButton, Card, Space, Tabs } from 'antd';
import SimpleMDE from 'react-simplemde-editor';
import { createEditorOptions, MARKDOWN_PLACEHOLDERS, configureMdeInstance } from '../config/markdownConfig';
import { MarkdownRenderer } from './MarkdownRenderer';

const { TextArea } = Input;

// GraphQL Mutation
const CREATE_PAIN_POINT = gql`
  mutation CreatePainPoint($subject: String!, $description: String!, $priority: String!) {
    createPainPoint(subject: $subject, description: $description, priority: $priority) {
      painPoint {
        id
        subject
        description
        priority
        author {
          id
          username
        }
        createdAt
      }
      success
      message
    }
  }
`;

// TypeScript interfaces for mutation response
interface CreatePainPointData {
  createPainPoint: {
    painPoint: {
      id: string;
      subject: string;
      description: string;
      priority: string;
      author: {
        id: string;
        username: string;
      };
      createdAt: string;
    } | null;
    success: boolean;
    message: string;
  };
}

interface CreatePainPointVars {
  subject: string;
  description: string;
  priority: string;
}

interface NewPainPointModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const NewPainPointModal: React.FC<NewPainPointModalProps> = ({
  visible,
  onClose,
  onSuccess,
}) => {
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [previewTab, setPreviewTab] = useState('editor');

  // Memoized editor options
  const editorOptions = useMemo(
    () => createEditorOptions('standard', MARKDOWN_PLACEHOLDERS.details),
    []
  );

  const [createPainPoint, { loading }] = useMutation<CreatePainPointData, CreatePainPointVars>(CREATE_PAIN_POINT, {
    onCompleted: (data) => {
      if (data.createPainPoint.success) {
        message.success('Pain point created! We will look into it soon! 🎯');
        resetForm();
        onSuccess();
      } else {
        message.error(data.createPainPoint.message);
      }
    },
    onError: (error) => {
      message.error('Error creating pain point');
      console.error(error);
    },
  });

  const resetForm = () => {
    setSubject('');
    setDescription('');
    setPriority('MEDIUM');
  };

  const handleSubmit = async () => {
    if (!subject.trim()) {
      message.error('Please enter a subject');
      return;
    }

    if (!description.trim()) {
      message.error('Please enter a description');
      return;
    }

    if (subject.length > 80) {
      message.error('Subject must be 80 characters or less');
      return;
    }

    await createPainPoint({
      variables: {
        subject: subject.trim(),
        description: description.trim(),
        priority,
      },
    });
  };

  const characterCount = subject.length;

  return (
    <Modal
      title="📝 Create New Pain Point"
      open={visible}
      onCancel={onClose}
      footer={[
        <AntButton key="cancel" onClick={onClose} disabled={loading}>
          Cancel
        </AntButton>,
        <AntButton
          key="submit"
          type="primary"
          loading={loading}
          onClick={handleSubmit}
        >
          Submit Pain
        </AntButton>,
      ]}
      width={600}
      className="new-pain-modal pain-theme-modal"
    >
      <div className="pain-form">
        <div className="form-group">
          <label htmlFor="subject">Subject (max 80 characters)</label>
          <div className="input-with-counter">
            <Input
              id="subject"
              placeholder="e.g., Dashboard performance is slow"
              value={subject}
              onChange={(e) => setSubject(e.target.value.slice(0, 80))}
              maxLength={80}
            />
            <span className="character-count">{characterCount}/80</span>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="description">Description (Markdown supported)</label>
          <Tabs
            activeKey={previewTab}
            onChange={setPreviewTab}
            tabBarStyle={{ marginBottom: 0 }}
            items={[
              {
                key: 'editor',
                label: '✏️ Editor',
                children: (
                  <div style={{ border: '1px solid var(--hef-border)', borderRadius: '6px', overflow: 'hidden' }}>
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
                    style={{ marginBottom: 16, background: 'var(--hef-bg-subtle)', minHeight: 200, borderColor: 'var(--hef-border)' }}
                  >
                    {description.trim() ? (
                      <MarkdownRenderer content={description} variant="small" />
                    ) : (
                      <p style={{ color: 'var(--hef-text-muted)', fontStyle: 'italic' }}>
                        No content to preview. Start typing in the editor tab...
                      </p>
                    )}
                  </Card>
                ),
              },
            ]}
          />
          <span className="help-text" style={{ marginTop: 8, display: 'block' }}>
            {description.length}/2000 characters
          </span>
        </div>

        <div className="form-group">
          <label htmlFor="priority">Priority</label>
          <Select
            id="priority"
            value={priority}
            onChange={setPriority}
            options={[
              {
                label: '🟢 Low - Nice to have',
                value: 'LOW',
              },
              {
                label: '🟡 Medium - Should fix',
                value: 'MEDIUM',
              },
              {
                label: '🔴 High - Urgent fix needed',
                value: 'HIGH',
              },
            ]}
          />
        </div>

        <div className="pain-tips">
          <h4>💡 Tips for better PAINs:</h4>
          <ul>
            <li>Be specific and clear about the problem</li>
            <li>Include steps to reproduce if it's a bug</li>
            <li>Mention the impact on your workflow</li>
            <li>Suggest a solution if you have one</li>
            <li>Set appropriate priority</li>
          </ul>
        </div>
      </div>
    </Modal>
  );
};

export default NewPainPointModal;
