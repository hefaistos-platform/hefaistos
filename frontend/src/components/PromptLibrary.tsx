import React, { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@apollo/client';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Input,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { MarkdownRenderer } from './MarkdownRenderer';
import {
  AIPrompt,
  EXECUTE_AI_PROMPT,
  EXPORT_AI_PROMPT_RESULT_PDF,
  GET_AI_PROMPTS,
} from '../graphql/mgmtAIPrompts';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type ExecutionPayload = {
  success: boolean;
  message?: string;
  resultMarkdown?: string;
  renderedPrompt?: string;
  providerUsed?: string;
};

function downloadBase64File(fileData: string, filename: string, contentType: string) {
  const binary = atob(fileData);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const PromptLibrary: React.FC = () => {
  const { data, loading } = useQuery<{ aiPrompts: AIPrompt[] }>(GET_AI_PROMPTS);
  const [executePrompt, { loading: executing }] = useMutation<{
    executeAiPrompt: ExecutionPayload;
  }>(EXECUTE_AI_PROMPT);
  const [exportPdf, { loading: exportingPdf }] = useMutation<{
    exportAiPromptResultPdf: {
      success: boolean;
      message?: string;
      fileData?: string;
      filename?: string;
      contentType?: string;
    };
  }>(EXPORT_AI_PROMPT_RESULT_PDF);

  const prompts = useMemo(() => data?.aiPrompts ?? [], [data?.aiPrompts]);
  const [customInput, setCustomInput] = useState('');
  const [selectedPrompt, setSelectedPrompt] = useState<AIPrompt | null>(null);
  const [result, setResult] = useState<ExecutionPayload | null>(null);

  const promptsByCategory = useMemo(() => {
    const grouped = new Map<string, AIPrompt[]>();
    prompts.forEach((prompt) => {
      if (!grouped.has(prompt.category)) grouped.set(prompt.category, []);
      grouped.get(prompt.category)?.push(prompt);
    });
    return Array.from(grouped.entries()).map(([category, items]) => ({
      category,
      items: [...items].sort((a, b) => a.order - b.order),
    }));
  }, [prompts]);

  const handleExecutePrompt = async (prompt: AIPrompt) => {
    setSelectedPrompt(prompt);
    try {
      const res = await executePrompt({
        variables: {
          promptId: prompt.id,
          customInput: customInput.trim() || null,
          customContext: null,
        },
      });
      const payload = res.data?.executeAiPrompt;
      if (!payload) {
        message.error('Prompt execution failed.');
        return;
      }
      setResult(payload);
      if (!payload.success) {
        message.error(payload.message || 'Prompt execution failed.');
        return;
      }
      message.success('Prompt executed successfully.');
    } catch (err: any) {
      message.error(err?.message || 'Prompt execution failed.');
    }
  };

  const handleSaveAsPdf = async () => {
    if (!selectedPrompt || !result?.resultMarkdown) return;
    try {
      const res = await exportPdf({
        variables: {
          title: `${selectedPrompt.title} - ${new Date().toISOString().slice(0, 10)}`,
          resultMarkdown: result.resultMarkdown,
        },
      });
      const payload = res.data?.exportAiPromptResultPdf;
      if (!payload?.success || !payload.fileData || !payload.filename || !payload.contentType) {
        message.error(payload?.message || 'PDF export failed.');
        return;
      }
      downloadBase64File(payload.fileData, payload.filename, payload.contentType);
      message.success('PDF downloaded.');
    } catch (err: any) {
      message.error(err?.message || 'PDF export failed.');
    }
  };

  return (
    <div style={{ padding: '0 4px' }}>
      <Paragraph type="secondary">
        Prompt library for management insights, threat hunting prioritization, compliance reporting,
        and operational planning.
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Text strong>Optional prompt context</Text>
        <TextArea
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          rows={3}
          placeholder="Add additional constraints, assumptions, or business context."
          style={{ marginTop: 8 }}
        />
      </Card>

      {loading ? (
        <Spin tip="Loading prompts..." />
      ) : prompts.length === 0 ? (
        <Empty description="No prompts available." />
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          {promptsByCategory.map(({ category, items }) => (
            <Card key={category} title={category.replace(/_/g, ' ')} size="small">
              <Row gutter={[12, 12]}>
                {items.map((prompt) => (
                  <Col xs={24} md={12} key={prompt.id}>
                    <Card size="small">
                      <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <Text strong>{prompt.title}</Text>
                          <Tag color={prompt.requiredRole === 'ADMIN' ? 'gold' : 'blue'}>
                            {prompt.requiredRole}
                          </Tag>
                        </div>
                        <Paragraph style={{ marginBottom: 0 }} type="secondary">
                          {prompt.description}
                        </Paragraph>
                        <Button
                          type="primary"
                          icon={<PlayCircleOutlined />}
                          loading={executing && selectedPrompt?.id === prompt.id}
                          onClick={() => handleExecutePrompt(prompt)}
                          block
                        >
                          Execute Prompt
                        </Button>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          ))}
        </Space>
      )}

      <Divider />
      <Title level={5}>Prompt Result</Title>
      {!result?.resultMarkdown ? (
        <Alert type="info" showIcon message="Execute a prompt to view AI output." />
      ) : (
        <Card
          size="small"
          extra={(
            <Space>
              {result.providerUsed && <Tag>{result.providerUsed}</Tag>}
              <Button
                icon={<DownloadOutlined />}
                onClick={handleSaveAsPdf}
                loading={exportingPdf}
              >
                Save Result as PDF
              </Button>
            </Space>
          )}
        >
          {result.message && !result.success && (
            <Alert type="error" showIcon message={result.message} style={{ marginBottom: 12 }} />
          )}
          <MarkdownRenderer content={result.resultMarkdown} variant="default" />
        </Card>
      )}
    </div>
  );
};

export default PromptLibrary;
