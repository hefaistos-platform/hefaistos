import React, { useState } from 'react';
import { Form, Input, Select, Button, Space, Row, Col, Upload, message, Badge, Tooltip, Divider } from 'antd';
import { RobotOutlined, UploadOutlined, LinkOutlined, CloudDownloadOutlined, LockOutlined } from '@ant-design/icons';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { ADVOPSReport, ADVOPSPriority, ADVOPSStatus } from '../../types/advops';

const EXTRACT_STRAIN_DATA = gql`
  mutation ExtractStrainData($fileContent: String!, $filename: String!) {
    extractStrainData(fileContent: $fileContent, filename: $filename) {
      result {
        huntId
        hypothesis
        status
        priority
        verificationSummary
        infrastructureSummary
        pivotSummary
        falsePositiveSummary
        mitreSummary
        detectionLogicSummary
        confidence
        error
      }
      providerUsed
    }
  }
`;

const EXTRACT_STRAIN_DATA_FROM_URL = gql`
  mutation ExtractStrainDataFromURL($url: String!) {
    extractStrainDataFromUrl(url: $url) {
      result {
        huntId
        hypothesis
        status
        priority
        verificationSummary
        infrastructureSummary
        pivotSummary
        falsePositiveSummary
        mitreSummary
        detectionLogicSummary
        confidence
        error
      }
      providerUsed
    }
  }
`;

interface ExtractStrainDataResult {
  extractStrainData: {
    result: {
      huntId: string;
      hypothesis: string;
      status: string;
      priority: string;
      verificationSummary: string;
      infrastructureSummary: string;
      pivotSummary: string;
      falsePositiveSummary: string;
      mitreSummary: string;
      detectionLogicSummary: string;
      confidence: string;
      error: string;
    };
    providerUsed: string;
  };
}

interface ExtractStrainDataVars {
  fileContent: string;
  filename: string;
}

interface ExtractStrainDataFromURLResult {
  extractStrainDataFromUrl: {
    result: ExtractStrainDataResult['extractStrainData']['result'];
    providerUsed: string;
  };
}

interface ExtractStrainDataFromURLVars {
  url: string;
}

const statusOptions: { label: string; value: ADVOPSStatus }[] = [
  { label: 'Idea/Hypothesis', value: 'IDEA' },
  { label: 'In Research', value: 'RESEARCH' },
  { label: 'In Development', value: 'DEVELOPMENT' },
  { label: 'Approved', value: 'APPROVED' },
  { label: 'Testing', value: 'TESTING' },
  { label: 'Deployed', value: 'DEPLOYED' },
  { label: 'Tuning/Maintenance', value: 'TUNING' },
];

const priorityOptions: { label: string; value: ADVOPSPriority }[] = [
  { label: 'Critical', value: 'CRITICAL' },
  { label: 'High', value: 'HIGH' },
  { label: 'Medium', value: 'MEDIUM' },
  { label: 'Low', value: 'LOW' },
];

export interface ADVOPSFormProps {
  initial?: Partial<ADVOPSReport>;
  submitting?: boolean;
  onSubmit: (values: Partial<ADVOPSReport>) => void;
  onCancel?: () => void;
  onPushToMISP?: () => void;
  onCreateWorkbench?: () => void;
  onToggleRemotePull?: () => void;
  remotePullEnabled?: boolean;
  togglingRemotePull?: boolean;
  workbenchLoading?: boolean;
}

export const ADVOPSForm: React.FC<ADVOPSFormProps> = ({
  initial,
  submitting,
  onSubmit,
  onCancel,
  onPushToMISP,
  onCreateWorkbench,
  onToggleRemotePull,
  remotePullEnabled,
  togglingRemotePull,
  workbenchLoading,
}) => {
  const [form] = Form.useForm<Partial<ADVOPSReport>>();
  const [extractStrain, { loading: strainLoading }] = useMutation<ExtractStrainDataResult, ExtractStrainDataVars>(EXTRACT_STRAIN_DATA);
  const [extractStrainFromUrl, { loading: urlLoading }] = useMutation<ExtractStrainDataFromURLResult, ExtractStrainDataFromURLVars>(EXTRACT_STRAIN_DATA_FROM_URL);

  // State for strAIn extraction result (shown inline instead of nested modal)
  const [strainResult, setStrainResult] = useState<ExtractStrainDataResult['extractStrainData']['result'] | null>(null);
  const [reportUrl, setReportUrl] = useState('');

  const applyStrainData = (result: any, mode: 'OVERWRITE' | 'APPEND') => {
      console.log('[strAIn] Applying data:', result, 'Mode:', mode); // Debug
      const current = form.getFieldsValue();
      const newData: any = {};
      
      // Fields that can be appended (text areas)
      const appendableFields = [
        'hypothesis',
        'verificationSummary', 'infrastructureSummary', 
        'pivotSummary', 'falsePositiveSummary', 
        'mitreSummary', 'detectionLogicSummary'
      ];
      
      // Fields that should only be overwritten (enums, IDs)
      const overwriteOnlyFields = ['huntId', 'priority', 'status'];
      
      // Special handle Status (Check case insensitive)
      if (result.status && mode === 'OVERWRITE') {
          const s = result.status.toUpperCase();
          if (['IDEA', 'RESEARCH', 'DEVELOPMENT', 'APPROVED', 'TESTING', 'DEPLOYED', 'TUNING'].includes(s)) {
             newData.status = s;
          }
      }
      
      // Handle priority (overwrite only)
      if (result.priority && mode === 'OVERWRITE') {
          const p = result.priority.toUpperCase();
          if (['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].includes(p)) {
              newData.priority = p;
          }
      }
      
      // Handle huntId (overwrite only)
      if (result.huntId && mode === 'OVERWRITE') {
          newData.huntId = result.huntId;
      }
      
      // Handle appendable fields
      appendableFields.forEach(f => {
          if (result[f]) {
              const key = f as keyof ADVOPSReport;
              if (mode === 'OVERWRITE' || !current[key]) {
                  newData[f] = result[f];
              } else {
                  // Append with newline
                  newData[f] = current[key] + '\n\n' + result[f];
              }
          }
      });
      
      console.log('[strAIn] Setting fields to:', newData); // Debug
      form.setFieldsValue(newData);
      message.success(`Data applied via strAIn (${mode})`);
  };

  const handleStrainUpload = (file: File) => {
    // Check size <= 10MB
    if (file.size > 10 * 1024 * 1024) {
      message.error({
        content: 'File exceeds 10MB limit. Please upload a smaller file.',
        duration: 5,
      });
      return Upload.LIST_IGNORE;
    }

    const msgKey = 'strain_process';
    console.log('[strAIn] Reading file:', file.name);
    message.loading({ content: 'strAIn: Reading document...', key: msgKey, duration: 0 });

    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = async () => {
       const base64 = reader.result as string;
       console.log('[strAIn] File read. Base64 len:', base64.length);
       
       message.loading({ content: 'strAIn: Analyzing with AI (this may take a minute)...', key: msgKey, duration: 0 });
       
       try {
         console.log('[strAIn] Sending mutation...');
         const { data } = await extractStrain({ variables: { fileContent: base64, filename: file.name }});
         console.log('[strAIn] Response received:', data);
         const result = data?.extractStrainData?.result;
         
         // Check for actual error (non-empty string)
         if (!result) {
           console.error('[strAIn] No result object');
           message.error({ 
             content: '❌ No result returned from AI. Please try again or check your AI settings.', 
             key: msgKey,
             duration: 6,
           });
           return;
         }
         
         if (result.error && result.error.trim() !== '') {
           console.error('[strAIn] Error in result:', result.error);
           message.error({ 
             content: `❌ ${result.error}`, 
             key: msgKey,
             duration: 8,
           });
           return;
         }
         
         console.log('[strAIn] Extraction successful, showing inline panel...');
         message.success({ content: '✅ Analysis Complete! Review extracted data below.', key: msgKey });
         
         // Store result in state to show inline panel (avoids nested modal z-index issues)
         setStrainResult(result);
       } catch (e: any) {
         const errorMessage = e.message || 'Unknown error occurred';
         console.error('[strAIn] Extraction error:', e);
         message.error({ 
           content: `❌ Extraction failed: ${errorMessage}`, 
           key: msgKey,
           duration: 8,
         });
       }
    };
    reader.onerror = () => {
        message.error({ 
          content: '❌ Failed to read file. Please try again.', 
          key: msgKey,
          duration: 5,
        });
    };
    return Upload.LIST_IGNORE; // Prevent auto upload
  };

  const handleUrlAnalysis = async () => {
    const trimmedUrl = reportUrl.trim();
    if (!trimmedUrl) {
      message.error('Please enter a URL.');
      return;
    }
    try {
      new URL(trimmedUrl);
    } catch {
      message.error('Please enter a valid URL (e.g. https://example.com/report.pdf).');
      return;
    }

    const msgKey = 'strain_url_process';
    message.loading({ content: '🔍 Fetching and analyzing report...', key: msgKey, duration: 0 });

    try {
      const { data } = await extractStrainFromUrl({ variables: { url: trimmedUrl } });
      const result = data?.extractStrainDataFromUrl?.result;

      if (!result) {
        message.error({ content: '❌ No result returned from AI. Please try again or check your AI settings.', key: msgKey, duration: 6 });
        return;
      }

      if (result.error && result.error.trim() !== '') {
        message.error({ content: `❌ ${result.error}`, key: msgKey, duration: 8 });
        return;
      }

      message.success({ content: '✅ Analysis Complete! Review extracted data below.', key: msgKey });
      setStrainResult(result);
    } catch (e: any) {
      const errorMessage = e.message || 'Unknown error occurred';
      console.error('[strAIn URL] Extraction error:', e);
      message.error({ content: `❌ URL analysis failed: ${errorMessage}`, key: msgKey, duration: 8 });
    }
  };

  // Check if this is a new hunt with auto-generated ID (has huntId but no id)
  const isAutoGeneratedHuntId = Boolean(initial?.huntId && !initial?.id);

  return (
    <Form
      layout="vertical"
      form={form}
      initialValues={{
        status: initial?.status || 'IDEA',
        priority: initial?.priority || 'MEDIUM',
        ...initial,
      }}
      onFinish={onSubmit}
    >
      {/* strAIn Bar */}
      <div className="mb-6 p-4 border border-blue-100 bg-blue-50 rounded-lg">
         <div className="flex items-center gap-3 mb-3">
            <div className="bg-white p-2 rounded-full shadow-sm text-blue-500 text-xl">
               <RobotOutlined />
            </div>
            <div>
               <h4 className="m-0 font-bold text-blue-900">strAIn Intelligence Extractor</h4>
               <p className="m-0 text-xs text-blue-600">Upload a document or paste a URL to auto-fill this hunt.</p>
            </div>
         </div>
         <Space.Compact style={{ width: '100%' }}>
           <Input
             placeholder="https://example.com/threat-report.pdf"
             value={reportUrl}
             onChange={(e) => setReportUrl(e.target.value)}
             onPressEnter={handleUrlAnalysis}
             disabled={urlLoading || strainLoading}
           />
           <Button
             type="primary"
             icon={<LinkOutlined />}
             loading={urlLoading}
             disabled={strainLoading}
             onClick={handleUrlAnalysis}
           >
             Analyze URL
           </Button>
         </Space.Compact>
         <Divider plain style={{ margin: '12px 0' }}>OR</Divider>
         <Upload beforeUpload={handleStrainUpload} showUploadList={false} accept=".pdf,.docx,.doc,.txt,.csv" maxCount={1}>
            <Tooltip title="Upload PDF/DOCX (Max 10MB)">
              <Button type="default" icon={<UploadOutlined />} loading={strainLoading} disabled={urlLoading} block>
                  Upload Document
              </Button>
            </Tooltip>
         </Upload>
      </div>

      {/* strAIn Extraction Result Panel (shown when extraction completes) */}
      {strainResult && (
        <div className="mb-6 p-4 border-2 border-green-300 bg-green-50 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h4 className="m-0 font-bold text-green-800 flex items-center gap-2">
              <RobotOutlined /> strAIn Extraction Complete
            </h4>
            <Badge 
              status={strainResult.confidence === 'High' ? 'success' : strainResult.confidence === 'Medium' ? 'warning' : 'default'} 
              text={`Confidence: ${strainResult.confidence || 'Unknown'}`} 
            />
          </div>
          
          <div className="bg-white p-3 rounded border mb-3 text-sm">
            <p className="mb-2"><strong>Hypothesis:</strong> {(strainResult.hypothesis || '').substring(0, 200)}...</p>
            <p className="mb-0">
              <strong>Extracted:</strong> {strainResult.infrastructureSummary ? strainResult.infrastructureSummary.split('\n').length : 0} IoCs, {strainResult.mitreSummary ? strainResult.mitreSummary.split('\n').length : 0} TTPs
            </p>
          </div>
          
          <Space>
            <Button 
              type="primary" 
              danger 
              onClick={() => { applyStrainData(strainResult, 'OVERWRITE'); setStrainResult(null); }}
            >
              Overwrite Form
            </Button>
            <Button 
              type="primary"
              onClick={() => { applyStrainData(strainResult, 'APPEND'); setStrainResult(null); }}
            >
              Append to Existing
            </Button>
            <Button onClick={() => setStrainResult(null)}>
              Dismiss
            </Button>
          </Space>
        </div>
      )}

      <Row gutter={24}>

        {/* Left Column */}
        <Col span={12}>
          <Form.Item 
            name="huntId" 
            label="Hunt ID" 
            rules={[{ required: true, message: 'Hunt ID is required' }]}
            tooltip={isAutoGeneratedHuntId ? "Auto-generated hunt ID for this month" : undefined}
          > 
            <Input 
              placeholder="e.g., ADV-2026-02-001" 
              disabled={isAutoGeneratedHuntId}
              style={isAutoGeneratedHuntId ? { backgroundColor: 'var(--hef-bg-subtle)', color: 'var(--hef-text-primary)', borderColor: 'var(--hef-border)' } : undefined}
            />
          </Form.Item>
          <Form.Item name="hypothesis" label="Hypothesis" rules={[{ required: true, message: 'Hypothesis is required' }]}> 
            <Input.TextArea rows={3} placeholder="What are we hunting for?" />
          </Form.Item>
          <Form.Item name="status" label="Status" rules={[{ required: true }]}> 
            <Select options={statusOptions} />
          </Form.Item>
          <Form.Item name="priority" label="Priority" rules={[{ required: true }]}> 
            <Select options={priorityOptions} />
          </Form.Item>
          <Form.Item name="verificationSummary" label="Verification Summary">
            <Input.TextArea rows={4} placeholder="Key checks or evidence" />
          </Form.Item>
        </Col>

        {/* Right Column */}
        <Col span={12}>
          <Form.Item name="infrastructureSummary" label="Infrastructure Summary" extra="Enter One Item per Line">
            <Input.TextArea rows={4} placeholder="IPs, domains, certs" />
          </Form.Item>
          <Form.Item name="pivotSummary" label="Pivot Summary">
            <Input.TextArea rows={4} placeholder="Links and pivots" />
          </Form.Item>
          <Form.Item name="falsePositiveSummary" label="False-Positive Analysis">
            <Input.TextArea rows={4} placeholder="Noise and mitigations" />
          </Form.Item>
          <Form.Item name="mitreSummary" label="MITRE Mapping" extra="Enter One Item per Line">
            <Input.TextArea rows={4} placeholder="Techniques, tactics" />
          </Form.Item>
          <Form.Item name="detectionLogicSummary" label="Detection Logic">
            <Input.TextArea rows={4} placeholder="Rules, queries, playbooks" />
          </Form.Item>
        </Col>
      </Row>

      <Space style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
        <Space>
          {initial?.id && (
            <>
              <Button
                onClick={onToggleRemotePull}
                loading={togglingRemotePull}
                disabled={!onToggleRemotePull || submitting}
                icon={remotePullEnabled ? <CloudDownloadOutlined /> : <LockOutlined />}
              >
                {remotePullEnabled ? 'Remote Pull ON' : 'Remote Pull OFF'}
              </Button>
              <Button 
                type="primary" 
                danger 
                onClick={onPushToMISP}
                disabled={submitting}
              >
                PUSH 2 MISP
              </Button>
              <Button 
                onClick={onCreateWorkbench}
                loading={workbenchLoading}
                disabled={submitting || workbenchLoading}
              >
                + Workbench
              </Button>
            </>
          )}
        </Space>
        <Space>
          {onCancel && (
            <Button onClick={onCancel} disabled={submitting || workbenchLoading}>
              Cancel
            </Button>
          )}
          <Button type="primary" htmlType="submit" loading={submitting}>
            Save
          </Button>
        </Space>
      </Space>
    </Form>
  );
};
