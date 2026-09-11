/**
 * (c) 2026 M3C4N1SM0 & All kinds of AI Bots
 */
import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, gql } from '@apollo/client';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { solarizedlight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button, Space, message, Modal, Input } from 'antd';
import { DeleteOutlined, EditOutlined, SaveOutlined, DeploymentUnitOutlined } from '@ant-design/icons';
import { RuleConversionModal } from '../components/RuleConversionModal';
import { RuleDeploymentModal } from '../components/RuleDeploymentModal';
import { useTheme } from '../context/ThemeContext';

// Define the GraphQL query to fetch a single rule
const GET_RULE_QUERY = gql`
  query GetRule($id: ID!) {
    rule(id: $id) {
      id
      title
      description
      status
      author
      rawContent
      format
    }
  }
`;

const DELETE_RULE_MUTATION = gql`
  mutation DeleteDetectionRule($ruleId: UUID!) {
    deleteDetectionRule(ruleId: $ruleId) {
      success
      message
    }
  }
`;

const UPDATE_RULE_MUTATION = gql`
  mutation UpdateDetectionRule($ruleId: ID!, $rawContent: String!) {
    updateDetectionRule(ruleId: $ruleId, rawContent: $rawContent) {
      success
      message
      rule {
        id
        title
        description
        status
        author
        rawContent
        format
      }
    }
  }
`;

const CURRENT_USER_QUERY = gql`
  query CurrentUser {
    me {
      id
      username
      role
    }
  }
`;

// Define the TypeScript types
interface RuleDetail {
  id: string;
  title: string;
  description: string | null;
  status: string | null;
  author: string | null;
  rawContent: string;
  format: string;
}

interface CurrentUser {
  id: string;
  username: string;
  role: string;
}

interface GetRuleData {
  rule: RuleDetail;
}

interface GetRuleVars {
  id: string;
}

export const RuleDetailPage = () => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const darkSyntaxStyle = {
    ...oneDark,
    'code[class*="language-"]': {
      ...oneDark['code[class*="language-"]'],
      textShadow: 'none',
      background: 'transparent',
    },
    'pre[class*="language-"]': {
      ...oneDark['pre[class*="language-"]'],
      textShadow: 'none',
      background: 'transparent',
    },
  };
  const { ruleId } = useParams<{ ruleId: string }>();
  const navigate = useNavigate();
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [conversionModalVisible, setConversionModalVisible] = useState(false);
  const [deploymentModalVisible, setDeploymentModalVisible] = useState(false);
  const [editedContent, setEditedContent] = useState('');
  const [deleting, setDeleting] = useState(false);

  const { data, loading, error } = useQuery<GetRuleData, GetRuleVars>(
    GET_RULE_QUERY,
    {
      variables: { id: ruleId! },
    }
  );

  const { data: currentUserData } = useQuery<{ me: CurrentUser }>(CURRENT_USER_QUERY);
  const [deleteRule] = useMutation(DELETE_RULE_MUTATION);
  const [updateRule, { loading: saving }] = useMutation(UPDATE_RULE_MUTATION);

  if (loading) return <p>Loading rule details...</p>;
  if (error) return <p style={{ color: 'var(--hef-danger-text)' }}>Error fetching rule: {error.message}</p>;
  if (!data ||!data.rule) return <p>Rule not found.</p>;

  const { rule } = data;
  const fileName = `${(rule.title || 'rule').replace(/[^a-z0-9-_]+/gi, '_')}.yml`;

  const handleCopy = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(rule.rawContent || '');
      } else {
        const ta = document.createElement('textarea');
        ta.value = rule.rawContent || '';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      message.success('YAML copied to clipboard');
    } catch (e: any) {
      message.error(`Copy failed: ${e?.message || e}`);
    }
  };

  const handleDownload = () => {
    try {
      const blob = new Blob([rule.rawContent || ''], { type: 'text/yaml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(`Download failed: ${e?.message || e}`);
    }
  };

  const handleEdit = () => {
    setEditedContent(rule.rawContent);
    setEditModalVisible(true);
  };

  const handleEditSave = async () => {
    try {
      const { data: result } = await updateRule({
        variables: { ruleId: rule.id, rawContent: editedContent },
        refetchQueries: [{ query: GET_RULE_QUERY, variables: { id: ruleId! } }],
      });
      if (result?.updateDetectionRule?.success) {
        message.success(result.updateDetectionRule.message || 'Rule saved successfully');
        setEditModalVisible(false);
      } else {
        message.error(result?.updateDetectionRule?.message || 'Failed to save rule');
      }
    } catch (err: any) {
      message.error(err.message || 'Error saving rule');
    }
  };

  const canDeleteRule = () => {
    const currentUser = currentUserData?.me;
    if (!currentUser) return false;
    const isOwner = rule.author && rule.author === currentUser.username;
    const isAdmin = currentUser.role === 'ADMIN' || currentUser.role === 'SUPERADMIN';
    return !!(isOwner || isAdmin);
  };

  const handleDeleteRule = () => {
    Modal.confirm({
      title: 'Delete Detection Rule',
      content: `Are you sure you want to delete the rule "${rule.title}"? This action cannot be undone.`,
      okText: 'Delete',
      okType: 'danger',
      onOk: async () => {
        try {
          setDeleting(true);
          const { data: result } = await deleteRule({ variables: { ruleId: rule.id } });
          if (result?.deleteDetectionRule?.success) {
            message.success(result.deleteDetectionRule.message || 'Rule deleted successfully');
            navigate('/rules');
          } else {
            message.error(result?.deleteDetectionRule?.message || 'Failed to delete rule');
          }
        } catch (err: any) {
          message.error(err.message || 'Error deleting rule');
        } finally {
          setDeleting(false);
        }
      },
    });
  };

  return (
    <div style={{ padding: 24, color: 'var(--hef-text-primary)' }}>
      <h2>{rule.title}</h2>
      <p><strong>Status:</strong> {rule.status || 'N/A'}</p>
      <p><strong>Author:</strong> {rule.author || 'N/A'}</p>
      <p style={{ color: 'var(--hef-text-secondary)' }}>{rule.description || 'No description available.'}</p>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 16 }}>
        <h3 style={{ margin: 0 }}>Raw Rule Content</h3>
        <Space>
          {rule?.format === 'OPENTIDE' && (
            <Button
              type="primary"
              icon={<DeploymentUnitOutlined />}
              onClick={() => setDeploymentModalVisible(true)}
            >
              Deploy
            </Button>
          )}
          <Button 
            type="primary" 
            icon={<EditOutlined />} 
            onClick={handleEdit}
          >
            Edit
          </Button>
          {canDeleteRule() && (
            <Button
              danger
              icon={<DeleteOutlined />}
              loading={deleting}
              onClick={handleDeleteRule}
            >
              Delete
            </Button>
          )}
          <Button size="small" onClick={handleCopy}>
            Copy
          </Button>
          <Button size="small" onClick={handleDownload}>
            Download
          </Button>
        </Space>
      </div>
      <SyntaxHighlighter
        language="yaml"
        style={isDark ? darkSyntaxStyle : solarizedlight}
        customStyle={{
          maxHeight: '600px',
          overflowY: 'auto',
          border: '1px solid var(--hef-border)',
          borderRadius: 8,
          background: isDark ? '#0f172a' : '#f8fafc',
        }}
      >
        {rule.rawContent}
      </SyntaxHighlighter>

      {/* Edit Modal */}
      <Modal
        title="Edit Rule"
        open={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        onOk={handleEditSave}
        okText="Save"
        okButtonProps={{ icon: <SaveOutlined />, loading: saving }}
        width={800}
      >
        <Input.TextArea
          value={editedContent}
          onChange={(e) => setEditedContent(e.target.value)}
          rows={15}
          style={{ fontFamily: 'monospace', fontSize: 12 }}
        />
      </Modal>

      {/* Conversion Modal */}
      <RuleConversionModal
        visible={conversionModalVisible}
        ruleId={rule?.id}
        ruleTitle={rule?.title}
        originalFormat={rule?.format}
        onCancel={() => setConversionModalVisible(false)}
      />

      {/* Deployment Modal */}
      <RuleDeploymentModal
        visible={deploymentModalVisible}
        ruleId={rule?.id}
        ruleTitle={rule?.title}
        ruleContent={rule?.rawContent ?? ''}
        onCancel={() => setDeploymentModalVisible(false)}
      />
    </div>
  );
};
