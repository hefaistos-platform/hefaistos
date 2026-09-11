import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Card, Button, Input, Form, Select, Alert, Typography, Space, Modal, message, Popconfirm, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, CloudDownloadOutlined, CopyOutlined, DeleteOutlined, LockOutlined } from '@ant-design/icons';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface DataSourceType {
  id: string;
  name: string;
}

interface MitreTechniqueType {
  id: string;
  techniqueId: string;
  name: string;
  description: string;
}

interface HypothesisType {
  id: string;
  content: string;
  sequence: number;
  mitreTechnique: MitreTechniqueType | null;
}

interface EvidenceType {
  id: string;
  content: string;
  credibility: string;
  sequence: number;
  dataSource: DataSourceType | null;
  logReference: string | null;
}

interface MatrixCellType {
  id: string;
  hypothesis: { id: string };
  evidence: { id: string };
  score: string;
}

interface ACHAnalysisType {
  id: string;
  title: string;
  description: string;
  status: 'RESEARCH' | 'FINISHED' | 'APPROVED';
  savedAsTemplate: boolean;
  allowRemotePull: boolean;
  owner: { id: string; username: string };
  hypotheses: HypothesisType[];
  evidenceItems: EvidenceType[];
  matrixCells: MatrixCellType[];
  scores: string;
}

interface AiSettingsType {
  preferredModel: string;
  hasOpenai: boolean;
  hasGemini: boolean;
  hasClaude: boolean;
  hasOllama: boolean;
  useOrgAi: boolean;
  effectivePreferredModel: string;
}

interface GetACHAnalysisData {
  achAnalysis: ACHAnalysisType | null;
  allDataSources: DataSourceType[];
  mitreAttackTechniques: MitreTechniqueType[];
  me: { id: string; username: string } | null;
}

interface GetMyAiSettingsData {
  myAiSettings?: AiSettingsType | null;
}

interface BiasCheckResult {
  isBiased: boolean;
  warningMessage: string;
  reasoning: string;
}

interface CheckBiasResponse {
  checkAchBias: {
    result: BiasCheckResult | null;
  };
}

interface CreatePlaybookGraphResponse {
  createPlaybookGraphFromHypothesis: {
    playbookGraph: {
      id: string;
      title: string;
    };
    ok: boolean;
  };
}

interface GeneratedEvidence {
  content: string;
  credibility: string;
}

interface GenerateContentResponse {
  generateAchContent: {
    result: {
      hypotheses: string[];
      evidence: GeneratedEvidence[];
    };
  };
}

interface CloneAchAnalysisResponse {
  cloneAchAnalysis: {
    analysis: { id: string } | null;
  } | null;
}

const GET_ACH_ANALYSIS = gql`
  query GetACHAnalysis($id: UUID!) {
    achAnalysis(id: $id) {
      id
      title
      description
      status
      savedAsTemplate
      allowRemotePull
      owner { id username }
      hypotheses {
        id
        content
        sequence
        mitreTechnique { id techniqueId name description }
        similarWorkbenchCount
        similarWorkbenches {
          id
          title
          status
          updatedAt
          author { username }
          mitreTechnique { techniqueId name }
        }
      }
      evidenceItems {
        id
        content
        credibility
        sequence
        dataSource { id name }
        logReference
      }
      matrixCells {
        id
        hypothesis { id }
        evidence { id }
        score
      }
      scores
    }
    allDataSources {
      id
      name
    }
    mitreAttackTechniques {
      id
      techniqueId
      name
      description
    }
    me { id username }
  }
`;

const GET_MY_AI_SETTINGS = gql`
  query GetMyAISettings {
    myAiSettings { preferredModel hasOpenai hasGemini hasClaude hasOllama useOrgAi effectivePreferredModel }
  }
`;

const ADD_HYPOTHESIS = gql`
  mutation AddHypothesis($analysisId: UUID!, $content: String!, $mitreTechniqueId: UUID) {
    addHypothesis(analysisId: $analysisId, content: $content, mitreTechniqueId: $mitreTechniqueId) {
      hypothesis {
        id
        content
        mitreTechnique { id techniqueId name }
      }
    }
  }
`;

const ADD_EVIDENCE = gql`
  mutation AddEvidence($analysisId: UUID!, $content: String!, $credibility: String, $dataSourceId: ID, $logReference: String) {
    addEvidence(analysisId: $analysisId, content: $content, credibility: $credibility, dataSourceId: $dataSourceId, logReference: $logReference) {
      evidence {
        id
        content
        credibility
      }
    }
  }
`;

const UPDATE_HYPOTHESIS = gql`
  mutation UpdateHypothesis($hypothesisId: ID!, $content: String!, $mitreTechniqueId: UUID) {
    updateHypothesis(hypothesisId: $hypothesisId, content: $content, mitreTechniqueId: $mitreTechniqueId) {
      hypothesis {
        id
        content
        mitreTechnique { id techniqueId name description }
      }
    }
  }
`;

const DELETE_HYPOTHESIS = gql`
  mutation DeleteHypothesis($hypothesisId: ID!) {
    deleteHypothesis(hypothesisId: $hypothesisId) { ok }
  }
`;

const UPDATE_EVIDENCE = gql`
  mutation UpdateEvidence($evidenceId: ID!, $content: String!, $credibility: String, $dataSourceId: ID, $logReference: String) {
    updateEvidence(evidenceId: $evidenceId, content: $content, credibility: $credibility, dataSourceId: $dataSourceId, logReference: $logReference) {
      evidence {
        id
        content
        credibility
        dataSource { id name }
        logReference
      }
    }
  }
`;

const DELETE_EVIDENCE = gql`
  mutation DeleteEvidence($evidenceId: ID!) {
    deleteEvidence(evidenceId: $evidenceId) { ok }
  }
`;

const CREATE_PLAYBOOK_GRAPH_FROM_HYPOTHESIS = gql`
  mutation CreatePlaybookGraphFromHypothesis($hypothesisId: ID!) {
    createPlaybookGraphFromHypothesis(hypothesisId: $hypothesisId) {
      playbookGraph { id title }
      ok
    }
  }
`;

const CHECK_BIAS = gql`
  mutation CheckACHBias($hypothesisContent: String!, $evidenceContent: String!, $score: String!, $otherHypotheses: [String]!) {
    checkAchBias(hypothesisContent: $hypothesisContent, evidenceContent: $evidenceContent, score: $score, otherHypotheses: $otherHypotheses) {
      result {
        isBiased
        warningMessage
        reasoning
      }
    }
  }
`;

const UPDATE_MATRIX_CELL = gql`
  mutation UpdateMatrixCell($hypothesisId: ID!, $evidenceId: ID!, $score: String!) {
    updateMatrixCell(hypothesisId: $hypothesisId, evidenceId: $evidenceId, score: $score) {
      cell {
        id
        score
      }
    }
  }
`;

const GENERATE_ACH_CONTENT = gql`
  mutation GenerateACHContent($description: String!) {
    generateAchContent(description: $description) {
      result {
        hypotheses
        evidence {
          content
          credibility
        }
      }
    }
  }
`;

const SAVE_ACH_AS_TEMPLATE = gql`
  mutation SaveACHAsTemplate($analysis_id: UUID!, $title: String!, $description: String) {
    saveAchAsTemplate(analysisId: $analysis_id, title: $title, description: $description) {
      template { id title }
    }
  }
`;

const DELETE_ACH_ANALYSIS = gql`
  mutation DeleteAchAnalysis($analysisId: UUID!) {
    deleteAchAnalysis(analysisId: $analysisId) { ok }
  }
`;

const UPDATE_ACH_STATUS = gql`
  mutation UpdateAchStatus($analysisId: UUID!, $status: String!) {
    updateAchStatus(analysisId: $analysisId, status: $status) {
      analysis { id status }
    }
  }
`;

const CLONE_ACH_ANALYSIS = gql`
  mutation CloneAchAnalysis($analysisId: UUID!) {
    cloneAchAnalysis(analysisId: $analysisId) {
      analysis { id title }
    }
  }
`;

const SET_ACH_REMOTE_PULL = gql`
  mutation SetAchRemotePull($analysisId: UUID!, $enabled: Boolean!) {
    setAchRemotePull(analysisId: $analysisId, enabled: $enabled) {
      success
      message
      analysis { id allowRemotePull }
    }
  }
`;

const SCORE_OPTIONS = [
  { value: 'CC', label: 'Very Consistent (CC)', color: 'bg-green-900 text-green-100' },
  { value: 'C', label: 'Consistent (C)', color: 'bg-green-800 text-green-100' },
  { value: 'N', label: 'Neutral (N)', color: 'bg-gray-700 text-gray-300' },
  { value: 'I', label: 'Inconsistent (I)', color: 'bg-red-800 text-red-100' },
  { value: 'II', label: 'Very Inconsistent (II)', color: 'bg-red-900 text-red-100' },
];

export const ACHDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { data, loading, error, refetch } = useQuery<GetACHAnalysisData>(GET_ACH_ANALYSIS, { variables: { id } });
  const { data: aiSettingsData } = useQuery<GetMyAiSettingsData>(GET_MY_AI_SETTINGS, { fetchPolicy: 'cache-and-network' });
  
  const [addHypothesis] = useMutation(ADD_HYPOTHESIS);
  const [addEvidence] = useMutation(ADD_EVIDENCE);
  const [updateHypothesis] = useMutation(UPDATE_HYPOTHESIS);
  const [deleteHypothesis] = useMutation(DELETE_HYPOTHESIS);
  const [updateEvidence] = useMutation(UPDATE_EVIDENCE);
  const [deleteEvidence] = useMutation(DELETE_EVIDENCE);
  const [createPlaybookGraphFromHypothesis] = useMutation<CreatePlaybookGraphResponse>(CREATE_PLAYBOOK_GRAPH_FROM_HYPOTHESIS);
  const [updateCell] = useMutation(UPDATE_MATRIX_CELL);
  const [checkBias] = useMutation<CheckBiasResponse>(CHECK_BIAS);
  const [generateContent, { loading: generating }] = useMutation<GenerateContentResponse>(GENERATE_ACH_CONTENT);
  const [saveTemplate, { loading: savingTpl }] = useMutation(SAVE_ACH_AS_TEMPLATE);
  const [deleteAnalysis] = useMutation(DELETE_ACH_ANALYSIS);
  const [updateStatus] = useMutation(UPDATE_ACH_STATUS);
  const [cloneAnalysis, { loading: cloningAnalysis }] = useMutation<CloneAchAnalysisResponse>(CLONE_ACH_ANALYSIS);
  const [setAchRemotePull, { loading: togglingRemotePull }] = useMutation(SET_ACH_REMOTE_PULL);

  const [newHypothesis, setNewHypothesis] = useState('');
  const [newHypothesisTTP, setNewHypothesisTTP] = useState<string | undefined>(undefined);
  const [newEvidence, setNewEvidence] = useState('');
  const [newEvidenceCred, setNewEvidenceCred] = useState('MEDIUM');
  const [newEvidenceDS, setNewEvidenceDS] = useState('');
  const [newEvidenceLog, setNewEvidenceLog] = useState('');
  
  const [editingHypothesis, setEditingHypothesis] = useState<{ id: string; content: string; mitreTechniqueId?: string | null } | null>(null);
  const [editingEvidence, setEditingEvidence] = useState<{ id: string; content: string; credibility: string; dataSourceId: string; logReference: string } | null>(null);
  
  const [aiPrompt, setAiPrompt] = useState('');
  const [showAiModal, setShowAiModal] = useState(false);
  const [biasWarning, setBiasWarning] = useState<{msg: string, reasoning: string} | null>(null);
  const [aiHint, setAiHint] = useState<string | null>(null);
  const [showSaveTplModal, setShowSaveTplModal] = useState(false);
  const [saveTplTitle, setSaveTplTitle] = useState('');
  const [saveTplDesc, setSaveTplDesc] = useState('');
  const [workbenchModal, setWorkbenchModal] = useState<{ open: boolean; hypothesis: string; items: any[] }>({ open: false, hypothesis: '', items: [] });
  const [devilsAdvocateResult, setDevilsAdvocateResult] = useState<{msg: string, reasoning: string} | null>(null);
  const [loadingDevilsAdvocate, setLoadingDevilsAdvocate] = useState(false);
  const [devilsAdvocateProgress, setDevilsAdvocateProgress] = useState<string>('');
  const [cellOverrides, setCellOverrides] = useState<Record<string, string>>({});
  const navigate = useNavigate();

  if (loading) return <div style={{ padding: 24 }}>Loading...</div>;
  if (error) return <div style={{ padding: 24 }}><Text type="danger">Error: {error.message}</Text></div>;

  const analysis = data?.achAnalysis;
  if (!analysis) return <div style={{ padding: 24 }}><Text>Analysis not found</Text></div>;

  const myAiSettings = aiSettingsData?.myAiSettings;
  const isDarkTheme = typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'dark';
  const hasPersonalAiProvider = Boolean(
    myAiSettings?.hasGemini ||
    myAiSettings?.hasOpenai ||
    myAiSettings?.hasClaude ||
    myAiSettings?.hasOllama
  );
  const hasConfiguredAi = myAiSettings?.useOrgAi
    ? Boolean(myAiSettings.effectivePreferredModel)
    : hasPersonalAiProvider;
  const effectiveModelName = myAiSettings?.effectivePreferredModel || myAiSettings?.preferredModel || '';
  const modelTagColor = !myAiSettings
    ? 'default'
    : myAiSettings.hasOllama
      ? 'orange'
      : myAiSettings.hasGemini
        ? 'green'
        : myAiSettings.hasOpenai
          ? 'blue'
          : myAiSettings.hasClaude
            ? 'purple'
            : 'default';
  const scores = JSON.parse(analysis.scores || '{}');

  const handleAddHypothesis = async (values?: any) => {
    try {
      console.log('[ACH] AddHypothesis onFinish values:', values);
      console.log('[ACH] AddHypothesis current input:', newHypothesis, 'TTP:', newHypothesisTTP);
      if (!newHypothesis.trim()) {
        console.warn('[ACH] AddHypothesis: empty input, skipping');
        return;
      }
      await addHypothesis({ variables: { analysisId: id, content: newHypothesis, mitreTechniqueId: newHypothesisTTP } });
      setNewHypothesis('');
      setNewHypothesisTTP(undefined);
      await refetch();
      console.log('[ACH] AddHypothesis: success');
    } catch (err) {
      console.error('[ACH] AddHypothesis error:', err);
    }
  };

  const handleAddEvidence = async (values?: any) => {
    try {
      console.log('[ACH] AddEvidence onFinish values:', values);
      console.log('[ACH] AddEvidence current input:', { newEvidence, newEvidenceCred, newEvidenceDS, newEvidenceLog });
      if (!newEvidence.trim()) {
        console.warn('[ACH] AddEvidence: empty input, skipping');
        return;
      }
      await addEvidence({ 
        variables: { 
          analysisId: id, 
          content: newEvidence, 
          credibility: newEvidenceCred,
          dataSourceId: newEvidenceDS || null,
          logReference: newEvidenceLog || null
        } 
      });
      setNewEvidence('');
      setNewEvidenceDS('');
      setNewEvidenceLog('');
      await refetch();
      console.log('[ACH] AddEvidence: success');
    } catch (err) {
      console.error('[ACH] AddEvidence error:', err);
    }
  };

  const handleUpdateHypothesis = async () => {
    if (!editingHypothesis || !editingHypothesis.content.trim()) return;
    try {
      await updateHypothesis({ variables: { hypothesisId: editingHypothesis.id, content: editingHypothesis.content, mitreTechniqueId: editingHypothesis.mitreTechniqueId || null } });
      setEditingHypothesis(null);
      await refetch();
      message.success('Hypothesis updated');
    } catch (err: any) {
      message.error(err.message || 'Failed to update hypothesis');
    }
  };

  const handleDeleteHypothesis = async (hypothesisId: string) => {
    try {
      await deleteHypothesis({ variables: { hypothesisId } });
      await refetch();
      message.success('Hypothesis deleted');
    } catch (err: any) {
      message.error(err.message || 'Failed to delete hypothesis');
    }
  };

  const handleUpdateEvidence = async () => {
    if (!editingEvidence || !editingEvidence.content.trim()) return;
    try {
      await updateEvidence({ 
        variables: { 
          evidenceId: editingEvidence.id, 
          content: editingEvidence.content, 
          credibility: editingEvidence.credibility,
          dataSourceId: editingEvidence.dataSourceId || null,
          logReference: editingEvidence.logReference || null
        } 
      });
      setEditingEvidence(null);
      await refetch();
      message.success('Evidence updated');
    } catch (err: any) {
      message.error(err.message || 'Failed to update evidence');
    }
  };

  const handleDeleteEvidence = async (evidenceId: string) => {
    try {
      await deleteEvidence({ variables: { evidenceId } });
      await refetch();
      message.success('Evidence deleted');
    } catch (err: any) {
      message.error(err.message || 'Failed to delete evidence');
    }
  };

  const handleCreateWorkbench = async (hypothesisId: string) => {
    try {
      const result = await createPlaybookGraphFromHypothesis({ variables: { hypothesisId } });
      if (result.data?.createPlaybookGraphFromHypothesis.ok) {
        const workbenchId = result.data.createPlaybookGraphFromHypothesis.playbookGraph.id;
        message.success('Workbench created successfully');
        navigate(`/playbooks/${workbenchId}`);
      }
    } catch (err: any) {
      message.error(err.message || 'Failed to create workbench');
    }
  };

  const getCellKey = (hId: string, eId: string) => `${hId}::${eId}`;

  const handleCellChange = async (hId: string, eId: string, score: string) => {
    const key = getCellKey(hId, eId);
    const previous = cellOverrides[key];
    setCellOverrides((prev) => ({ ...prev, [key]: score }));
    try {
      await updateCell({ variables: { hypothesisId: hId, evidenceId: eId, score } });
      await refetch();
    } catch (err: any) {
      setCellOverrides((prev) => {
        const next = { ...prev };
        if (previous) next[key] = previous;
        else delete next[key];
        return next;
      });
      message.error(err?.message || 'Failed to update matrix cell score');
    }
  };

  const handleAskDevilsAdvocate = async () => {
    if (analysis.hypotheses.length === 0 || analysis.evidenceItems.length === 0) {
      message.warning('Add hypotheses and evidence before analyzing');
      return;
    }
    
    setLoadingDevilsAdvocate(true);
    setDevilsAdvocateProgress('Starting Devils Advocate analysis...');
    
    try {
      // Create list of all pairs to analyze
      const pairs = [];
      for (const evidence of analysis.evidenceItems) {
        for (const hypothesis of analysis.hypotheses) {
          pairs.push({ evidence, hypothesis });
        }
      }
      
      const totalPairs = pairs.length;
      const analysisInsights: Array<{hypothesis: string, evidence: string, warning: string, reasoning: string}> = [];
      
      // Process in batches of 3 concurrent requests
      const batchSize = 3;
      for (let i = 0; i < pairs.length; i += batchSize) {
        const batch = pairs.slice(i, Math.min(i + batchSize, pairs.length));
        
        // Update progress
        setDevilsAdvocateProgress(`Analyzing ${i + 1}-${Math.min(i + batchSize, totalPairs)} of ${totalPairs} hypothesis-evidence pairs...`);
        
        // Process batch in parallel
        const batchResults = await Promise.allSettled(
          batch.map(async (pair) => {
            const score = getCellScore(pair.hypothesis.id, pair.evidence.id);
            const others = analysis.hypotheses.filter((x) => x.id !== pair.hypothesis.id).map((x) => x.content);
            
            try {
              const res = await checkBias({
                variables: {
                  hypothesisContent: pair.hypothesis.content,
                  evidenceContent: pair.evidence.content,
                  score,
                  otherHypotheses: others
                }
              });
              const result = res.data?.checkAchBias.result;
              if (result && result.isBiased) {
                return {
                  hypothesis: pair.hypothesis.content,
                  evidence: pair.evidence.content,
                  warning: result.warningMessage,
                  reasoning: result.reasoning
                };
              }
              return null;
            } catch (err) {
              console.error("Individual bias check failed", err);
              return null;
            }
          })
        );
        
        // Collect successful results
        batchResults.forEach((result) => {
          if (result.status === 'fulfilled' && result.value) {
            analysisInsights.push(result.value);
          }
        });
      }
      
      setDevilsAdvocateProgress('');
      
      if (analysisInsights.length === 0) {
        setDevilsAdvocateResult({ 
          msg: 'No significant biases detected', 
          reasoning: 'The analysis appears balanced across hypotheses and evidence.' 
        });
      } else {
        const summary = `Found ${analysisInsights.length} potential bias issue(s) in your analysis`;
        const details = analysisInsights.map(i => 
          `• ${i.hypothesis}\n  Evidence: "${i.evidence}"\n  ${i.warning}`
        ).join('\n\n');
        setDevilsAdvocateResult({ 
          msg: summary, 
          reasoning: details 
        });
      }
    } catch (err) {
      console.error("Devils Advocate analysis failed", err);
      message.error('Failed to analyze with Devils Advocate');
      setDevilsAdvocateProgress('');
    } finally {
      setLoadingDevilsAdvocate(false);
    }
  };

  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) return;
    try {
      const res = await generateContent({ variables: { description: aiPrompt } });
      const result = res.data?.generateAchContent.result;
      
      if (result) {
        // Auto-add generated content
        for (const h of result.hypotheses) {
          await addHypothesis({ variables: { analysisId: id, content: h } });
        }
        for (const e of result.evidence) {
          await addEvidence({ variables: { analysisId: id, content: e.content, credibility: e.credibility } });
        }
      }
      
      setShowAiModal(false);
      setAiPrompt('');
      refetch();
    } catch (err) {
      console.error("AI Generation failed", err);
      setAiHint('AI not configured or selected model unsupported. Set keys and model in Profile.');
      message.error('AI Generation failed. Please configure AI in your Profile.');
    }
  };

  const handleSaveAsTemplate = async () => {
    try {
      const title = saveTplTitle.trim();
      if (!title) { message.warning('Template title is required'); return; }
      await saveTemplate({ 
        variables: { analysis_id: id, title, description: saveTplDesc || null },
        refetchQueries: ['GetACHData', 'GetACHAnalysis'],
        awaitRefetchQueries: true,
      });
      setShowSaveTplModal(false);
      setSaveTplTitle('');
      setSaveTplDesc('');
      message.success('Template saved');
      await refetch();
      Modal.confirm({
        title: 'Template Saved',
        content: 'Your template is ready to use when creating a new analysis.',
        okText: 'Go to Create',
        cancelText: 'Close',
        onOk: () => navigate('/tools/ach'),
      });
    } catch (err: any) {
      console.error('Save template failed', err);
      message.error(err?.message || 'Failed to save template');
    }
  };

  const openWorkbenchModal = (h: any) => {
    setWorkbenchModal({
      open: true,
      hypothesis: h.content,
      items: h.similarWorkbenches || [],
    });
  };

  const handleCloneAnalysis = async () => {
    try {
      const res = await cloneAnalysis({ variables: { analysisId: id } });
      const newId = res.data?.cloneAchAnalysis?.analysis?.id;
      if (newId) {
        message.success('Analysis cloned');
        navigate(`/ach/${newId}`);
      } else {
        message.error('Failed to clone analysis');
      }
    } catch (err: any) {
      message.error(err?.message || 'Failed to clone analysis');
    }
  };

  const handleToggleRemotePull = async () => {
    try {
      const result = await setAchRemotePull({
        variables: { analysisId: id, enabled: !analysis.allowRemotePull },
      });
      const payload = result.data?.setAchRemotePull;
      if (!payload?.success) {
        message.error(payload?.message || 'Failed to update remote pull access');
        return;
      }
      message.success(payload.message || 'Remote pull access updated');
      await refetch();
    } catch (err: any) {
      message.error(err?.message || 'Failed to update remote pull access');
    }
  };

  const getCellScore = (hId: string, eId: string) => {
    const override = cellOverrides[getCellKey(hId, eId)];
    if (override) return override;
    const cell = analysis.matrixCells.find((c) => c.hypothesis.id === hId && c.evidence.id === eId);
    return cell?.score || 'N';
  };

  return (
    <div className="ach-theme" style={{ padding: 24, background: 'var(--hef-bg-page)', color: 'var(--hef-text-primary)' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <Link to="/tools/ach">
            <Button icon={<ArrowLeftOutlined />}>Back</Button>
          </Link>
          <Title level={3} style={{ margin: 0, color: 'var(--hef-text-primary)' }}>{analysis.title}</Title>
          {analysis.savedAsTemplate && (
            <Tag color="purple" icon={<span>⭐</span>}>Template</Tag>
          )}
        </Space>
        <Space wrap>
          {myAiSettings && effectiveModelName && (
            <Tooltip title={myAiSettings.useOrgAi ? 'AI model is managed by your organization settings' : 'AI model is managed by your profile settings'}>
              <Tag color={modelTagColor} style={{ margin: 0, lineHeight: '30px' }}>
                Model: {effectiveModelName}
              </Tag>
            </Tooltip>
          )}
          {!analysis.savedAsTemplate && (
            <Button 
              onClick={() => setShowSaveTplModal(true)}
            >
              Save as Template
            </Button>
          )}
          <Button 
            type="primary"
            onClick={() => setShowAiModal(true)}
            style={{ background: '#722ed1' }}
          >
            ✨ AI Assistant
          </Button>
          <Button 
            onClick={handleAskDevilsAdvocate}
            loading={loadingDevilsAdvocate}
            style={{ marginLeft: 8 }}
          >
            🤔 Devils Advocate
          </Button>
          {data?.me?.id && analysis.owner?.id === data.me.id && (
          <>
            <Button
              icon={analysis.allowRemotePull ? <CloudDownloadOutlined /> : <LockOutlined />}
              loading={togglingRemotePull}
              onClick={handleToggleRemotePull}
            >
              {analysis.allowRemotePull ? 'Remote Pull ON' : 'Remote Pull OFF'}
            </Button>
            <Button 
              onClick={async () => {
                const nextStatus = analysis.status === 'FINISHED' ? 'RESEARCH' : 'FINISHED';
                try {
                  await updateStatus({ variables: { analysisId: id, status: nextStatus } });
                  message.success(`Status updated to ${nextStatus}`);
                  refetch();
                } catch (err: any) {
                  message.error(err?.message || 'Failed to update status');
                }
              }}
            >
              {analysis.status === 'FINISHED' ? 'Mark Research' : 'Mark Finished'}
            </Button>
            <Tooltip title="Clone analysis">
              <Button 
                type="text" 
                icon={<CopyOutlined />} 
                onClick={handleCloneAnalysis} 
                loading={cloningAnalysis}
              />
            </Tooltip>
            <Tooltip title="Delete analysis">
              <Popconfirm
                title="Delete analysis?"
                description="This will permanently delete this ACH matrix."
                okText="Delete"
                okButtonProps={{ danger: true }}
                cancelText="Cancel"
                onConfirm={async () => {
                  try {
                    await deleteAnalysis({ variables: { analysisId: id } });
                    message.success('Analysis deleted');
                    navigate('/tools/ach');
                  } catch (err: any) {
                    console.error(err);
                    message.error(err?.message || 'Failed to delete');
                  }
                }}
              >
                <Button type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Tooltip>
          </>
          )}
        </Space>
      </Space>

      {aiHint && (
        <Alert
          message="AI Assistant Not Configured"
          description={<>
            <div>{aiHint}</div>
            <div style={{ marginTop: 8 }}>
              Go to <Link to="/profile">Profile</Link> to add API keys and select your model.
            </div>
          </>}
          type="info"
          showIcon
          closable
          onClose={() => setAiHint(null)}
          style={{ marginBottom: 16 }}
        />
      )}
      {analysis.description && (
        <div style={{ marginBottom: 16 }}>
          <MarkdownRenderer content={analysis.description} variant="small" skipEmpty={false} />
        </div>
      )}

      {biasWarning && (
        <Alert
          message="⚠️ Devil's Advocate Warning"
          description={
            <>
              <div>{biasWarning.msg}</div>
              <div style={{ fontSize: 12, fontStyle: 'italic', marginTop: 8, opacity: 0.8 }}>{biasWarning.reasoning}</div>
            </>
          }
          type="warning"
          closable
          onClose={() => setBiasWarning(null)}
          style={{ marginBottom: 16 }}
        />
      )}

      {devilsAdvocateProgress && (
        <Alert
          message="🤔 Devils Advocate Analysis in Progress"
          description={devilsAdvocateProgress}
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Matrix */}
      <Card style={{ marginBottom: 16, overflow: 'auto', background: 'var(--hef-bg-surface)', borderColor: 'var(--hef-border)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ padding: 16, borderBottom: '1px solid var(--hef-border)', borderRight: '1px solid var(--hef-border)', textAlign: 'left', minWidth: 300, background: 'var(--hef-bg-subtle)', position: 'sticky', left: 0, zIndex: 10, color: 'var(--hef-text-primary)' }}>
                Evidence / Hypotheses
              </th>
              {analysis.hypotheses.map((h: any) => {
                const score = scores[h.id] || 0;
                let categoryColor = isDarkTheme ? '#2f1f1f' : '#fafafa';
                let categoryBadgeColor = isDarkTheme ? '#a61d24' : '#ff7875';
                let categoryLabel = 'Eliminated';
                let categoryEmoji = '🔴';
                
                if (score <= 3) {
                  categoryColor = isDarkTheme ? '#1d3122' : '#f6ffed';
                  categoryBadgeColor = isDarkTheme ? '#2f8f4e' : '#85ce61';
                  categoryLabel = 'Most Likely';
                  categoryEmoji = '🟢';
                } else if (score <= 10) {
                  categoryColor = isDarkTheme ? '#352c16' : '#fffbe6';
                  categoryBadgeColor = isDarkTheme ? '#b8841a' : '#ffc53d';
                  categoryLabel = 'Plausible';
                  categoryEmoji = '🟡';
                }
                
                // Visual bar: proportional to score
                const maxScore = Math.max(...(Object.values(scores as Record<string, number>) as number[]), 30);
                const barLength = score === 0 ? 1 : Math.min(Math.floor((score / maxScore) * 32) + 1, 32);
                const visualBar = '█'.repeat(barLength);
                
                return (
                  <th key={h.id} style={{ padding: 16, borderBottom: '1px solid var(--hef-border)', textAlign: 'left', minWidth: 200, background: categoryColor, verticalAlign: 'top', color: 'var(--hef-text-primary)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>
                        <MarkdownRenderer content={h.content} variant="small" skipEmpty={false} />
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginLeft: 8 }}>
                        <Button
                          type="text"
                          size="small"
                          icon={<span style={{ fontSize: 14 }}>✏️</span>}
                          onClick={() => setEditingHypothesis({ id: h.id, content: h.content, mitreTechniqueId: h.mitreTechnique?.id || null })}
                          style={{ padding: 0, height: 'auto' }}
                          title="Edit Hypothesis"
                        />
                        <Button
                          type="text"
                          size="small"
                          icon={<span style={{ fontSize: 14, color: '#52c41a' }}>+</span>}
                          onClick={() => handleCreateWorkbench(h.id)}
                          style={{ padding: 0, height: 'auto' }}
                          title="CREATE WORKBENCH"
                        />
                        <Popconfirm
                          title="Delete this hypothesis?"
                          onConfirm={() => handleDeleteHypothesis(h.id)}
                          okText="Delete"
                          cancelText="Cancel"
                        >
                          <Button
                            type="text"
                            size="small"
                            icon={<span style={{ fontSize: 14, color: '#ff4d4f' }}>✖</span>}
                            style={{ padding: 0, height: 'auto' }}
                            title="Delete Hypothesis"
                          />
                        </Popconfirm>
                      </div>
                    </div>
                    {h.mitreTechnique && (
                      <div style={{ marginBottom: 8, fontSize: 11, color: '#1890ff', fontWeight: 'bold' }}>
                        🎯 {h.mitreTechnique.techniqueId}: {h.mitreTechnique.name}
                      </div>
                    )}
                    <div style={{ marginBottom: 8 }}>
                      <Tooltip title="Matches workbenches that use the same MITRE technique/subtechnique as this hypothesis">
                        <Button
                          size="small"
                          type="default"
                          onClick={() => openWorkbenchModal(h)}
                          disabled={!h.similarWorkbenchCount}
                        >
                          Workbenches: {h.similarWorkbenchCount || 0}
                        </Button>
                      </Tooltip>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 12, fontWeight: 'bold', color: '#1890ff', marginBottom: 8 }}>
                      Score: {score}
                    </div>
                    <div style={{ marginBottom: 8, fontSize: 11, fontFamily: 'monospace', color: 'var(--hef-text-muted)' }}>
                      {visualBar}
                    </div>
                    <div style={{ 
                      display: 'inline-block',
                      padding: '4px 8px', 
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 'bold',
                      background: categoryBadgeColor,
                      color: '#fff'
                    }}>
                      {categoryEmoji} {categoryLabel}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {analysis.evidenceItems.map((e: any) => (
              <tr key={e.id} style={{ background: 'var(--hef-bg-surface)' }}>
                <td style={{ padding: 16, borderBottom: '1px solid var(--hef-border)', borderRight: '1px solid var(--hef-border)', background: 'var(--hef-bg-subtle)', position: 'sticky', left: 0, zIndex: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div style={{ fontSize: 14, flex: 1 }}>
                      <MarkdownRenderer content={e.content} variant="small" skipEmpty={false} />
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginLeft: 8 }}>
                      <Button
                        type="text"
                        size="small"
                        icon={<span style={{ fontSize: 14 }}>✏️</span>}
                        onClick={() => setEditingEvidence({ 
                          id: e.id, 
                          content: e.content, 
                          credibility: e.credibility,
                          dataSourceId: e.dataSource?.id || '',
                          logReference: e.logReference || ''
                        })}
                        style={{ padding: 0, height: 'auto' }}
                      />
                      <Popconfirm
                        title="Delete this evidence?"
                        onConfirm={() => handleDeleteEvidence(e.id)}
                        okText="Delete"
                        cancelText="Cancel"
                      >
                        <Button
                          type="text"
                          size="small"
                          icon={<span style={{ fontSize: 14, color: '#ff4d4f' }}>✖</span>}
                          style={{ padding: 0, height: 'auto' }}
                        />
                      </Popconfirm>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                    <span style={{ 
                      fontSize: 12, 
                      padding: '2px 8px', 
                      borderRadius: 4,
                      background: e.credibility === 'HIGH' ? '#f6ffed' : e.credibility === 'MEDIUM' ? '#fffbe6' : '#fff1f0',
                      border: `1px solid ${e.credibility === 'HIGH' ? '#b7eb8f' : e.credibility === 'MEDIUM' ? '#ffe58f' : '#ffccc7'}`,
                      color: e.credibility === 'HIGH' ? '#52c41a' : e.credibility === 'MEDIUM' ? '#faad14' : '#f5222d'
                    }}>
                      {e.credibility} Credibility
                    </span>
                    {e.dataSource && (
                      <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 4, background: '#e6f7ff', border: '1px solid #91d5ff', color: '#1890ff' }}>
                        Source: {e.dataSource.name}
                      </span>
                    )}
                    {e.logReference && (
                      <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 4, background: '#f5f5f5', border: '1px solid #d9d9d9', color: '#595959', fontFamily: 'monospace' }}>
                        Log: {e.logReference}
                      </span>
                    )}
                  </div>
                </td>
                {analysis.hypotheses.map((h: any) => (
                  <td key={`${h.id}-${e.id}`} style={{ padding: 8, borderBottom: '1px solid var(--hef-border)', textAlign: 'center' }}>
                    <select
                      value={getCellScore(h.id, e.id)}
                      onChange={(ev) => handleCellChange(h.id, e.id, ev.target.value)}
                      style={{
                        width: '100%',
                        padding: 8,
                        borderRadius: 4,
                        fontSize: 14,
                        border: '1px solid var(--hef-border)',
                        outline: 'none',
                        background: 'var(--hef-bg-surface)',
                        color: 'var(--hef-text-primary)'
                      }}
                    >
                      {SCORE_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>
                          {opt.value}
                        </option>
                      ))}
                    </select>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Manual Entry Forms */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 32 }}>
        <Card>
          <Title level={4}>Add Hypothesis</Title>
          <Form 
            onFinish={handleAddHypothesis}
            onFinishFailed={(info) => console.error('[ACH] AddHypothesis onFinishFailed:', info)}
            layout="vertical" 
            style={{ marginBottom: 0 }}
          >
            <Form.Item style={{ marginBottom: 8 }}>
              <Input
                value={newHypothesis}
                onChange={(e) => setNewHypothesis(e.target.value)}
                placeholder="Enter new hypothesis..."
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 8 }}>
              <Select
                value={newHypothesisTTP}
                onChange={(value) => setNewHypothesisTTP(value)}
                placeholder="Select MITRE ATT&CK TTP (Optional)"
                showSearch
                allowClear
                optionFilterProp="children"
                filterOption={(input, option) => {
                  const text = ((option?.label ?? option?.children ?? '') as string).toLowerCase();
                  return text.includes(input.toLowerCase());
                }}
                style={{ width: '100%' }}
              >
                {(data?.mitreAttackTechniques || []).map((ttp) => (
                  <Option key={ttp.id} value={ttp.id} label={`${ttp.techniqueId} - ${ttp.name}`}>
                    {ttp.techniqueId} - {ttp.name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" block>Add Hypothesis</Button>
            </Form.Item>
          </Form>
        </Card>

        <Card>
          <Title level={4}>Add Evidence</Title>
          <Form 
            onFinish={handleAddEvidence}
            onFinishFailed={(info) => console.error('[ACH] AddEvidence onFinishFailed:', info)}
            layout="vertical" 
            style={{ marginBottom: 0 }}
          >
            <Form.Item style={{ marginBottom: 8 }}>
              <TextArea
                value={newEvidence}
                onChange={(e) => setNewEvidence(e.target.value)}
                placeholder="Enter evidence..."
                rows={2}
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <Select
                  value={newEvidenceCred}
                  onChange={(value) => setNewEvidenceCred(value)}
                  style={{ flex: 1 }}
                >
                  <Option value="HIGH">High Credibility</Option>
                  <Option value="MEDIUM">Medium Credibility</Option>
                  <Option value="LOW">Low Credibility</Option>
                </Select>
                <Button type="primary" htmlType="submit" style={{ flex: 1 }}>Add Evidence</Button>
              </div>
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <Select
                  value={newEvidenceDS}
                  onChange={(value) => setNewEvidenceDS(value)}
                  placeholder="Link Data Source (Optional)"
                  showSearch
                  optionFilterProp="children"
                  filterOption={(input, option) => {
                    const text = ((option?.label ?? option?.children ?? '') as string).toLowerCase();
                    return text.includes(input.toLowerCase());
                  }}
                  allowClear
                >
                  <Option value="">-- None --</Option>
                  {data?.allDataSources.map((ds) => (
                    <Option key={ds.id} value={ds.id}>{ds.name}</Option>
                  ))}
                </Select>
                <Input
                  value={newEvidenceLog}
                  onChange={(e) => setNewEvidenceLog(e.target.value)}
                  placeholder="Log ID / Query (Optional)"
                />
              </div>
            </Form.Item>
          </Form>
        </Card>
      </div>

      <Modal
        title="Matching Workbenches"
        open={workbenchModal.open}
        onCancel={() => setWorkbenchModal({ open: false, hypothesis: '', items: [] })}
        footer={null}
        width={600}
      >
        <div style={{ marginBottom: 8, color: '#595959' }}>
          Hypothesis: {workbenchModal.hypothesis || 'N/A'}
        </div>
        {!workbenchModal.items.length && (
          <Alert type="info" message="No matching workbenches found" showIcon />
        )}
        {workbenchModal.items.map((w) => (
          <a key={w.id} href={`/playbooks/${w.id}`} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
            <Card size="small" style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600, color: '#1890ff' }}>{w.title}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>{w.mitreTechnique?.techniqueId} {w.mitreTechnique?.name}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>Author: {w.author?.username || 'Unknown'}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>Updated: {w.updatedAt ? new Date(w.updatedAt).toLocaleString() : 'N/A'}</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                  <div style={{
                    padding: '2px 8px',
                    borderRadius: 12,
                    background: '#e6f4ff',
                    color: '#1677ff',
                    fontSize: 12,
                    fontWeight: 600,
                  }}>
                    {w.status}
                  </div>
                </div>
              </div>
            </Card>
          </a>
        ))}
      </Modal>

      <Modal
        title="ACH AI Assistant"
        open={showAiModal}
        onCancel={() => setShowAiModal(false)}
        onOk={handleAiGenerate}
        okText={generating ? 'Generating...' : 'Generate Detection Hypotheses & Evidence'}
        okButtonProps={{ disabled: generating, loading: generating }}
        width={600}
      >
        {myAiSettings && !hasConfiguredAi && (
          <Alert
            message="AI not configured"
            description={<>
              Add an AI provider key and select a model in <Link to="/profile">Profile</Link>.
            </>}
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
          />
        )}
        <Paragraph style={{ marginBottom: 16, color: 'var(--hef-text-muted)' }}>
          Describe the scenario, incident, or observations. The AI will always generate detection engineering-focused hypotheses and evidence items, such as ATT&CK-aligned behaviors, telemetry patterns, data sources, log fields, queries, alerts, and validation artifacts.
        </Paragraph>
        <TextArea
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          rows={8}
          placeholder="e.g., We observed multiple failed login attempts from a known malicious IP followed by a successful login. Generate detection hypotheses and detection evidence using authentication logs, identity telemetry, and alert context..."
        />
      </Modal>

      <Modal
        title="Save as Template"
        open={showSaveTplModal}
        onCancel={() => setShowSaveTplModal(false)}
        onOk={handleSaveAsTemplate}
        confirmLoading={savingTpl}
      >
        <Form layout="vertical">
          <Form.Item label="Template Title" required>
            <Input value={saveTplTitle} onChange={(e) => setSaveTplTitle(e.target.value)} placeholder="e.g., Phishing Investigation Template" />
          </Form.Item>
          <Form.Item label="Description">
            <Input.TextArea value={saveTplDesc} onChange={(e) => setSaveTplDesc(e.target.value)} rows={3} placeholder="Optional description" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Edit Hypothesis"
        open={!!editingHypothesis}
        onCancel={() => setEditingHypothesis(null)}
        onOk={handleUpdateHypothesis}
        okText="Save"
      >
        <Form layout="vertical">
          <Form.Item label="Hypothesis Content" required>
            <TextArea
              value={editingHypothesis?.content || ''}
              onChange={(e) => setEditingHypothesis(editingHypothesis ? { ...editingHypothesis, content: e.target.value } : null)}
              rows={3}
              placeholder="Enter hypothesis content..."
            />
          </Form.Item>
          <Form.Item label="MITRE ATT&CK Technique/Subtechnique">
            <Select
              showSearch
              allowClear
              placeholder="Select technique/subtechnique"
              optionFilterProp="children"
              value={editingHypothesis?.mitreTechniqueId || undefined}
              onChange={(value) => setEditingHypothesis(editingHypothesis ? { ...editingHypothesis, mitreTechniqueId: value || null } : null)}
            >
              {data?.mitreAttackTechniques.map((t) => (
                <Option key={t.id} value={t.id}>
                  {t.techniqueId} — {t.name}
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Edit Evidence"
        open={!!editingEvidence}
        onCancel={() => setEditingEvidence(null)}
        onOk={handleUpdateEvidence}
        okText="Save"
        width={600}
      >
        <Form layout="vertical">
          <Form.Item label="Evidence Content" required>
            <TextArea
              value={editingEvidence?.content || ''}
              onChange={(e) => setEditingEvidence(editingEvidence ? { ...editingEvidence, content: e.target.value } : null)}
              rows={3}
              placeholder="Enter evidence content..."
            />
          </Form.Item>
          <Form.Item label="Credibility">
            <Select
              value={editingEvidence?.credibility || 'MEDIUM'}
              onChange={(value) => setEditingEvidence(editingEvidence ? { ...editingEvidence, credibility: value } : null)}
            >
              <Option value="HIGH">High Credibility</Option>
              <Option value="MEDIUM">Medium Credibility</Option>
              <Option value="LOW">Low Credibility</Option>
            </Select>
          </Form.Item>
          <Form.Item label="Data Source">
            <Select
              value={editingEvidence?.dataSourceId || ''}
              onChange={(value) => setEditingEvidence(editingEvidence ? { ...editingEvidence, dataSourceId: value } : null)}
              placeholder="Link Data Source (Optional)"
              showSearch
              allowClear
            >
              <Option value="">-- None --</Option>
              {data?.allDataSources.map((ds) => (
                <Option key={ds.id} value={ds.id}>{ds.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="Log Reference">
            <Input
              value={editingEvidence?.logReference || ''}
              onChange={(e) => setEditingEvidence(editingEvidence ? { ...editingEvidence, logReference: e.target.value } : null)}
              placeholder="Log reference (Optional)"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="🤔 Devils Advocate Analysis"
        open={!!devilsAdvocateResult}
        onCancel={() => setDevilsAdvocateResult(null)}
        footer={<Button onClick={() => setDevilsAdvocateResult(null)}>Close</Button>}
        width={700}
      >
        {devilsAdvocateResult && (
          <div>
            <Alert
              message={devilsAdvocateResult.msg}
              description={
                <div style={{ marginTop: 12 }}>
                  <strong>Detailed Analysis:</strong>
                  <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6 }}>
                    {devilsAdvocateResult.reasoning}
                  </div>
                </div>
              }
              type={devilsAdvocateResult.msg.includes('No significant') ? 'success' : 'warning'}
              showIcon
            />
          </div>
        )}
      </Modal>
    </div>
  );
};
