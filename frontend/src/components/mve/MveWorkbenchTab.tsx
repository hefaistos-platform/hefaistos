import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { gql } from '@apollo/client';
import apolloClient from '../../apollo-client';
import { useMutation, useQuery } from '@apollo/client/react';
import {
  Background,
  Connection,
  Controls,
  Edge,
  Node,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import { DeleteOutlined, ExportOutlined, PlusOutlined, QuestionCircleOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Checkbox, Col, Collapse, Form, Input, InputNumber, Modal, Popconfirm, Radio, Row, Select, Space, Spin, Switch, Tag, Tooltip, Typography, message } from 'antd';
import DetectionRuleEditorModal, { DetectionMode } from '../DetectionRuleEditorModal';
import { ReviewWorkflow } from '../playbook/ReviewWorkflow';

const GET_MVE_DRAFTS_QUERY = gql`
  query GetMveDrafts {
    allMveDrafts {
      id
      name
      status
      anchorEntity
      maxTotalSpanMs
      analyticFamily
      primaryMethodology
      isAdvopsValidated
      updatedAt
    }
  }
`;

const GET_MVE_DRAFT_QUERY = gql`
  query GetMveDraft($id: UUID!) {
    mveDraft(id: $id) {
      id
      name
      status
      anchorEntity
      maxTotalSpanMs
      analyticFamily
      primaryMethodology
      behaviorObject
      dimensions
      measurementModel
      timeWindowLogic
      baselineStrategy
      contextRisk
      generationProfile
      downstreamHandoff
      isAdvopsValidated
      validationSummary
      lastValidatedAt
      updatedAt
      nodes {
        id
        stepOrder
        nodeType
        label
        tacticRef
        techniqueRef
        criteria
        nodeConfig
        positionX
        positionY
        dataSource {
          id
          name
        }
        detectionRule {
          id
          title
          format
        }
        capabilityAbstraction {
          id
          abstractionLayer
          componentArtifact
          technique {
            techniqueId
            name
          }
        }
      }
      edges {
        id
        source
        target
      }
      latestValidation {
        id
        status
        createdAt
        completedAt
        errorMessage
        resultData
      }
      validationErrors
    }
  }
`;

const GET_MVE_OPTIONS_QUERY = gql`
  query GetMveOptions {
    capabilityAbstractions(includeBaseline: true) {
      id
      abstractionLayer
      componentArtifact
      technique {
        techniqueId
        name
      }
    }
    allDataSources {
      id
      name
    }
    searchAllRules(query: "", limit: 200) {
      id
      title
      format
    }
    allRuleRepositories {
      id
      name
      provider
      url
    }
    mveAppendTargets {
      id
      title
      status
      updatedAt
      author {
        id
        username
      }
    }
    me {
      id
      role
    }
  }
`;

const GET_MVE_VALIDATION_QUERY = gql`
  query GetMveValidationRun($id: UUID!) {
    mveValidationRun(id: $id) {
      id
      status
      errorMessage
      resultData
      createdAt
      completedAt
    }
  }
`;

const CREATE_MVE_DRAFT_MUTATION = gql`
  mutation CreateMveDraft(
    $name: String!
    $anchorEntity: String!
    $maxTotalSpanMs: Int!
    $analyticFamily: String
    $primaryMethodology: String
    $behaviorObject: GenericScalar
    $dimensions: GenericScalar
    $measurementModel: GenericScalar
    $timeWindowLogic: GenericScalar
    $baselineStrategy: GenericScalar
    $contextRisk: GenericScalar
    $generationProfile: GenericScalar
    $downstreamHandoff: GenericScalar
  ) {
    createMveDraft(
      name: $name
      anchorEntity: $anchorEntity
      maxTotalSpanMs: $maxTotalSpanMs
      analyticFamily: $analyticFamily
      primaryMethodology: $primaryMethodology
      behaviorObject: $behaviorObject
      dimensions: $dimensions
      measurementModel: $measurementModel
      timeWindowLogic: $timeWindowLogic
      baselineStrategy: $baselineStrategy
      contextRisk: $contextRisk
      generationProfile: $generationProfile
      downstreamHandoff: $downstreamHandoff
    ) {
      mveDraft {
        id
      }
    }
  }
`;

const UPDATE_MVE_DRAFT_MUTATION = gql`
  mutation UpdateMveDraft(
    $draftId: UUID!
    $name: String
    $anchorEntity: String
    $maxTotalSpanMs: Int
    $status: String
    $analyticFamily: String
    $primaryMethodology: String
    $behaviorObject: GenericScalar
    $dimensions: GenericScalar
    $measurementModel: GenericScalar
    $timeWindowLogic: GenericScalar
    $baselineStrategy: GenericScalar
    $contextRisk: GenericScalar
    $generationProfile: GenericScalar
    $downstreamHandoff: GenericScalar
  ) {
    updateMveDraft(
      draftId: $draftId
      name: $name
      anchorEntity: $anchorEntity
      maxTotalSpanMs: $maxTotalSpanMs
      status: $status
      analyticFamily: $analyticFamily
      primaryMethodology: $primaryMethodology
      behaviorObject: $behaviorObject
      dimensions: $dimensions
      measurementModel: $measurementModel
      timeWindowLogic: $timeWindowLogic
      baselineStrategy: $baselineStrategy
      contextRisk: $contextRisk
      generationProfile: $generationProfile
      downstreamHandoff: $downstreamHandoff
    ) {
      mveDraft {
        id
        name
        status
        anchorEntity
        maxTotalSpanMs
        analyticFamily
        primaryMethodology
      }
    }
  }
`;

const DELETE_MVE_DRAFT_MUTATION = gql`
  mutation DeleteMveDraft($draftId: UUID!) {
    deleteMveDraft(draftId: $draftId) {
      ok
    }
  }
`;

const ADD_MVE_NODE_MUTATION = gql`
  mutation AddMveNode(
    $draftId: UUID!
    $nodeType: String!
    $stepOrder: Int
    $label: String
    $dataSourceId: ID
    $detectionRuleId: ID
    $capabilityAbstractionId: UUID
    $tacticRef: String
    $techniqueRef: String
    $criteria: GenericScalar
    $nodeConfig: GenericScalar
    $positionX: Float
    $positionY: Float
  ) {
    addMveNode(
      draftId: $draftId
      nodeType: $nodeType
      stepOrder: $stepOrder
      label: $label
      dataSourceId: $dataSourceId
      detectionRuleId: $detectionRuleId
      capabilityAbstractionId: $capabilityAbstractionId
      tacticRef: $tacticRef
      techniqueRef: $techniqueRef
      criteria: $criteria
      nodeConfig: $nodeConfig
      positionX: $positionX
      positionY: $positionY
    ) {
      node {
        id
      }
    }
  }
`;

const UPDATE_MVE_NODE_MUTATION = gql`
  mutation UpdateMveNode(
    $nodeId: UUID!
    $stepOrder: Int
    $label: String
    $dataSourceId: ID
    $detectionRuleId: ID
    $capabilityAbstractionId: UUID
    $tacticRef: String
    $techniqueRef: String
    $criteria: GenericScalar
    $nodeConfig: GenericScalar
    $positionX: Float
    $positionY: Float
  ) {
    updateMveNode(
      nodeId: $nodeId
      stepOrder: $stepOrder
      label: $label
      dataSourceId: $dataSourceId
      detectionRuleId: $detectionRuleId
      capabilityAbstractionId: $capabilityAbstractionId
      tacticRef: $tacticRef
      techniqueRef: $techniqueRef
      criteria: $criteria
      nodeConfig: $nodeConfig
      positionX: $positionX
      positionY: $positionY
    ) {
      node {
        id
      }
    }
  }
`;

const DELETE_MVE_NODE_MUTATION = gql`
  mutation DeleteMveNode($nodeId: UUID!) {
    deleteMveNode(nodeId: $nodeId) {
      ok
    }
  }
`;

const ADD_MVE_EDGE_MUTATION = gql`
  mutation AddMveEdge($draftId: UUID!, $sourceNodeId: UUID!, $targetNodeId: UUID!) {
    addMveEdge(draftId: $draftId, sourceNodeId: $sourceNodeId, targetNodeId: $targetNodeId) {
      edge {
        id
      }
    }
  }
`;

const DELETE_MVE_EDGE_MUTATION = gql`
  mutation DeleteMveEdge($edgeId: UUID!) {
    deleteMveEdge(edgeId: $edgeId) {
      ok
    }
  }
`;

const START_MVE_VALIDATION_MUTATION = gql`
  mutation StartMveValidation($draftId: UUID!) {
    startMveValidation(draftId: $draftId) {
      success
      message
      validationErrors
      validationRun {
        id
        status
      }
    }
  }
`;

const GENERATE_MVE_DETECTION_RULE_MUTATION = gql`
  mutation GenerateMveDetectionRule($draftId: UUID!, $outputFormat: String) {
    generateMveDetectionRule(draftId: $draftId, outputFormat: $outputFormat) {
      success
      message
      providerUsed
      generatedRule
      outputFormat
      validationErrors
      warnings
      generationContext
    }
  }
`;

const EXPORT_MVE_YAML_MUTATION = gql`
  mutation ExportMveOpenTideYaml(
    $draftId: UUID!
    $mode: String
    $repositoryId: ID
    $branch: String
    $filePath: String
    $commitMessage: String
    $targetGraphId: UUID
  ) {
    exportMveOpenTideYaml(
      draftId: $draftId
      mode: $mode
      repositoryId: $repositoryId
      branch: $branch
      filePath: $filePath
      commitMessage: $commitMessage
      targetGraphId: $targetGraphId
    ) {
      success
      message
      validationErrors
      yamlText
      url
      generatedFileName
      mveDraft {
        id
        status
      }
    }
  }
`;

const CREATE_WORKBENCH_FROM_MVE_MUTATION = gql`
  mutation CreateWorkbenchFromMve($draftId: UUID!, $enrichWithAi: Boolean) {
    createWorkbenchFromMve(draftId: $draftId, enrichWithAi: $enrichWithAi) {
      success
      message
      aiProviderUsed
      warnings
      validationErrors
      mveDraft {
        id
        status
      }
      playbookGraph {
        id
        title
        status
      }
    }
  }
`;

const SAVE_RULE_MUTATION = gql`
  mutation SaveRule($playbookId: UUID!, $rawYaml: String!, $format: String, $autoCommit: Boolean, $commitMessage: String) {
    saveDetectionRule(playbookId: $playbookId, rawYaml: $rawYaml, format: $format, autoCommit: $autoCommit, commitMessage: $commitMessage) {
      success
      message
      commitSha
      errors
      filename
    }
  }
`;

const UPDATE_OPENTIDE_YAML_MUTATION = gql`
  mutation UpdatePlaybookOpentideYaml($graphId: UUID!, $opentideYaml: JSONString!, $configuredPlatforms: [String]) {
    updatePlaybookOpentideYaml(graphId: $graphId, opentideYaml: $opentideYaml, configuredPlatforms: $configuredPlatforms) {
      success
      playbookGraph {
        id
        opentideYaml
        configuredPlatforms
      }
    }
  }
`;

const GET_TARGET_WORKBENCH_REVIEW_QUERY = gql`
  query GetTargetWorkbenchReview($id: UUID!) {
    playbookGraph(id: $id) {
      id
      status
      activeReview {
        id
        status
        createdAt
        comments {
          id
          text
          createdAt
          user { username }
        }
      }
      author { id username role }
      opentideYaml
      configuredPlatforms
    }
    me {
      id
      role
    }
  }
`;

type DraftRow = {
  id: string;
  name: string;
  status: string;
  anchorEntity: string;
  maxTotalSpanMs: number;
  analyticFamily?: string | null;
  primaryMethodology?: string;
  behaviorObject?: Record<string, unknown>;
  dimensions?: Record<string, unknown>;
  measurementModel?: Record<string, unknown>;
  timeWindowLogic?: Record<string, unknown>;
  baselineStrategy?: Record<string, unknown>;
  contextRisk?: Record<string, unknown>;
  generationProfile?: Record<string, unknown>;
  downstreamHandoff?: Record<string, unknown>;
  isAdvopsValidated: boolean;
  updatedAt: string;
};

type DraftNode = {
  id: string;
  stepOrder: number;
  nodeType: 'EVENT' | 'RULE' | 'FEATURE' | 'BASELINE' | 'CONTEXT' | 'DECEPTION' | 'DECISION';
  label: string;
  tacticRef?: string;
  techniqueRef?: string;
  criteria?: Record<string, unknown>;
  nodeConfig?: Record<string, unknown>;
  positionX: number;
  positionY: number;
  dataSource?: { id: string; name: string } | null;
  detectionRule?: { id: string; title: string; format?: string } | null;
  capabilityAbstraction?: {
    id: string;
    abstractionLayer: string;
    componentArtifact: string;
    technique?: { techniqueId: string; name: string } | null;
  } | null;
};

type AddNodeFormValues = {
  nodeType: 'EVENT' | 'RULE' | 'FEATURE' | 'BASELINE' | 'CONTEXT' | 'DECEPTION' | 'DECISION';
  label?: string;
  dataSourceId?: string;
  detectionRuleId?: string;
  capabilityAbstractionId?: string;
  tacticRef?: string;
  techniqueRef?: string;
  criteriaText?: string;
  nodeConfigText?: string;
  featureType?: string;
  featureOutputField?: string;
  featureFormula?: string;
  baselineType?: string;
  baselineHistoryWindow?: string;
  contextCondition?: string;
  contextEffect?: string;
  deceptionType?: string;
  deceptionConfidenceEffect?: string;
  decisionRecommendation?: string;
  decisionThresholdLogic?: string;
};

type MveConstraintFormValues = {
  name: string;
  anchorEntity: string;
  maxTotalSpanMs: number;
  analyticFamily?: string;
  primaryMethodology?: string;
  behaviorActorEntityType?: string;
  behaviorActionFamily?: string;
  behaviorTargetEntityType?: string;
  behaviorChannel?: string;
  behaviorDetectionObjective?: string;
  behaviorCanonicalSentence?: string;
  dimensionsPrimary?: string[];
  dimensionsSecondary?: string[];
  dimensionsRationale?: string;
  measurementCountedAction?: string;
  measurementAggregationKeysText?: string;
  measurementGroupingKeysText?: string;
  measurementFeatureSet?: string[];
  timeLookbackWindow?: string;
  timeDetectionWindow?: string;
  timeWindowType?: string;
  timeEventField?: string;
  timeOrderingConfidence?: string;
  baselineRequired?: boolean;
  baselineTypes?: string[];
  baselineHistoricalPeriod?: string;
  contextExpectedAutomation?: string;
  contextBenignOverlapsText?: string;
  generationOutputFormat?: string;
  generationMode?: string;
  hardeningIncludeBenignOverlapHandling?: boolean;
  hardeningIncludeBaselineComparison?: boolean;
  hardeningIncludeTriageEvidenceFields?: boolean;
  hardeningIncludeDeceptionConfidenceLogic?: boolean;
  hardeningIncludeThresholdRationaleComments?: boolean;
  groundingUseBehaviorObject?: boolean;
  groundingUseDimensions?: boolean;
  groundingUseMeasurementModel?: boolean;
  groundingUseTimeWindowLogic?: boolean;
  groundingUseBaselineStrategy?: boolean;
  groundingUseContextRisk?: boolean;
  groundingUseNodeGraph?: boolean;
  handoffOpenInMonacoEditor?: boolean;
  handoffSaveToRuleHub?: boolean;
  handoffGenerateOpentideYaml?: boolean;
  handoffAppendToWorkbench?: boolean;
  handoffAutoOpenTargetWorkbench?: boolean;
  handoffTargetWorkbenchId?: string;
};

type ExportMode = 'SAVE' | 'PUSH_GIT' | 'APPEND_WORKBENCH';

type AbstractionOption = {
  value: string;
  label: string;
  techniqueId: string;
};

type ExportFormValues = {
  repositoryId?: string;
  branch?: string;
  filePath?: string;
  commitMessage?: string;
  targetGraphId?: string;
};

type SaveRuleResponse = {
  saveDetectionRule?: {
    success?: boolean;
    message?: string;
    commitSha?: string;
    errors?: string[];
    filename?: string;
  };
};

type TargetWorkbenchReviewData = {
  playbookGraph?: {
    id: string;
    status: string;
    activeReview?: {
      id: string;
      status: string;
      createdAt: string;
      comments: Array<{ id: string; text: string; createdAt: string; user?: { username?: string } }>;
    } | null;
    author?: { id: string; username: string; role?: string } | null;
    opentideYaml?: string | null;
    configuredPlatforms?: string[];
  } | null;
  me?: { id: string; role?: string } | null;
};

const CARD_HEIGHT = 620;
const SECTION_ROW_GUTTER: [number, number] = [16, 16];
const ACTION_ICON_BUTTON_STYLE: React.CSSProperties = {
  width: 36,
  height: 36,
  borderRadius: 10,
  boxShadow: 'var(--hef-shadow-card)',
};
const ACTION_TEXT_BUTTON_STYLE: React.CSSProperties = {
  borderRadius: 10,
};
const PANEL_SECTION_TITLE_STYLE: React.CSSProperties = {
  display: 'block',
  marginBottom: 8,
  fontWeight: 600,
};
const MVE_STATUS_TAG_COLOR: Record<'DRAFT' | 'MODELED' | 'GENERATION_READY' | 'VALIDATED' | 'EXPORTED', string> = {
  DRAFT: 'default',
  MODELED: 'processing',
  GENERATION_READY: 'purple',
  VALIDATED: 'success',
  EXPORTED: 'cyan',
};
const COMPACT_SUBTITLE_STYLE: React.CSSProperties = {
  display: 'block',
  fontSize: 12,
  marginBottom: 8,
};
const TOOLTIP_STYLE: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  borderRadius: 8,
  padding: '6px 10px',
};

const MveWorkbenchTab: React.FC = () => {
  const navigate = useNavigate();
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [yamlPreview, setYamlPreview] = useState<string>('');
  const [yamlOpen, setYamlOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportMode, setExportMode] = useState<ExportMode>('SAVE');
  const [addNodeOpen, setAddNodeOpen] = useState(false);
  const [constraintsForm] = Form.useForm<MveConstraintFormValues>();
  const [addNodeForm] = Form.useForm<AddNodeFormValues>();
  const [exportForm] = Form.useForm<ExportFormValues>();
  const targetWorkbenchId = Form.useWatch('handoffTargetWorkbenchId', constraintsForm);
  const autoOpenTargetWorkbench = Form.useWatch('handoffAutoOpenTargetWorkbench', constraintsForm);

  const { data: draftsData, loading: draftsLoading, refetch: refetchDrafts } = useQuery<{ allMveDrafts: DraftRow[] }>(
    GET_MVE_DRAFTS_QUERY,
    { fetchPolicy: 'network-only' }
  );
  const { data: optionsData, loading: optionsLoading } = useQuery(GET_MVE_OPTIONS_QUERY, { fetchPolicy: 'cache-and-network' });
  const {
    data: selectedDraftData,
    loading: selectedDraftLoading,
    refetch: refetchSelectedDraft,
  } = useQuery(
    GET_MVE_DRAFT_QUERY,
    {
      variables: { id: selectedDraftId },
      skip: !selectedDraftId,
      fetchPolicy: 'network-only',
    }
  );
  const {
    data: validationData,
    stopPolling,
  } = useQuery(
    GET_MVE_VALIDATION_QUERY,
    {
      variables: { id: activeRunId },
      skip: !activeRunId,
      pollInterval: activeRunId ? 2000 : 0,
      fetchPolicy: 'network-only',
    }
  );
  const {
    data: targetWorkbenchReviewData,
    refetch: refetchTargetWorkbenchReview,
  } = useQuery<TargetWorkbenchReviewData>(GET_TARGET_WORKBENCH_REVIEW_QUERY, {
    variables: { id: targetWorkbenchId },
    skip: !targetWorkbenchId,
    fetchPolicy: 'network-only',
  });

  const [createDraft, { loading: creatingDraft }] = useMutation(CREATE_MVE_DRAFT_MUTATION);
  const [updateDraft, { loading: savingConstraints }] = useMutation(UPDATE_MVE_DRAFT_MUTATION);
  const [deleteDraft, { loading: deletingDraft }] = useMutation(DELETE_MVE_DRAFT_MUTATION);
  const [addNode, { loading: addingNode }] = useMutation(ADD_MVE_NODE_MUTATION);
  const [updateNode] = useMutation(UPDATE_MVE_NODE_MUTATION);
  const [deleteNode, { loading: deletingNode }] = useMutation(DELETE_MVE_NODE_MUTATION);
  const [addEdgeMutation] = useMutation(ADD_MVE_EDGE_MUTATION);
  const [deleteEdgeMutation] = useMutation(DELETE_MVE_EDGE_MUTATION);
  const [startValidation, { loading: startingValidation }] = useMutation(START_MVE_VALIDATION_MUTATION);
  const [exportYaml, { loading: exportingYaml }] = useMutation(EXPORT_MVE_YAML_MUTATION);
  const [updateOpenTideYaml] = useMutation(UPDATE_OPENTIDE_YAML_MUTATION);
  const [saveRuleToHub, { loading: savingGeneratedRule }] = useMutation<SaveRuleResponse>(SAVE_RULE_MUTATION);
  const [generateMveRule, { loading: generatingRule }] = useMutation(GENERATE_MVE_DETECTION_RULE_MUTATION);
  const [createWorkbenchFromMve, { loading: creatingWorkbenchFromMve }] = useMutation(CREATE_WORKBENCH_FROM_MVE_MUTATION);
  const [generatedRule, setGeneratedRule] = useState<string>('');
  const [generatedFormat, setGeneratedFormat] = useState<string>('KQL');
  const [generationWarnings, setGenerationWarnings] = useState<string[]>([]);
  const [editorModalVisible, setEditorModalVisible] = useState(false);
  const [enrichMveImportWithAiByDefault, setEnrichMveImportWithAiByDefault] = useState(true);

  const selectedDraft = selectedDraftData?.mveDraft ?? null;
  const dataSources = optionsData?.allDataSources ?? [];
  const rules = optionsData?.searchAllRules ?? [];
  const abstractions = optionsData?.capabilityAbstractions ?? [];
  const repositories = optionsData?.allRuleRepositories ?? [];
  const appendTargets = optionsData?.mveAppendTargets ?? [];
  const preferredHandoffTargetId = appendTargets[0]?.id || '';
  const currentUserRole = ((optionsData as any)?.me?.role || '').toUpperCase();
  const canReviewProtectedMveStatus = currentUserRole === 'ADMIN' || currentUserRole === 'REVIEWER';
  const selectedDraftStatus = (selectedDraft?.status || '').toUpperCase();
  const isExportedMveDraft = selectedDraftStatus === 'EXPORTED';
  const isProtectedMveStatus = selectedDraftStatus === 'VALIDATED' || selectedDraftStatus === 'EXPORTED';
  const canQuickChangeMveStatus = Boolean(selectedDraftId) && (!isProtectedMveStatus || canReviewProtectedMveStatus);
  const statusOptions: Array<{ value: 'DRAFT' | 'MODELED' | 'GENERATION_READY' | 'VALIDATED' | 'EXPORTED'; label: string; disabled?: boolean }> = [
    { value: 'DRAFT', label: 'DRAFT', disabled: isProtectedMveStatus && !canReviewProtectedMveStatus },
    { value: 'MODELED', label: 'MODELED', disabled: isProtectedMveStatus && !canReviewProtectedMveStatus },
    { value: 'GENERATION_READY', label: 'GENERATION_READY', disabled: isProtectedMveStatus && !canReviewProtectedMveStatus },
    { value: 'VALIDATED', label: 'VALIDATED' },
    { value: 'EXPORTED', label: 'EXPORTED' },
  ];

  useEffect(() => {
    const available = draftsData?.allMveDrafts ?? [];
    if (!available.length) {
      setSelectedDraftId(null);
      return;
    }
    if (!selectedDraftId || !available.some((item) => item.id === selectedDraftId)) {
      setSelectedDraftId(available[0].id);
    }
  }, [draftsData?.allMveDrafts, selectedDraftId]);

  useEffect(() => {
    if (!selectedDraft) return;
    const behavior = selectedDraft.behaviorObject || {};
    const dims = selectedDraft.dimensions || {};
    const measurement = selectedDraft.measurementModel || {};
    const timeLogic = selectedDraft.timeWindowLogic || {};
    const baseline = selectedDraft.baselineStrategy || {};
    const contextRisk = selectedDraft.contextRisk || {};
    const generation = selectedDraft.generationProfile || {};
    const hardening = (generation as any).hardening_options || {};
    const grounding = (generation as any).grounding_inputs || {};
    const handoff = selectedDraft.downstreamHandoff || {};

    constraintsForm.setFieldsValue({
      name: selectedDraft.name,
      anchorEntity: selectedDraft.anchorEntity,
      maxTotalSpanMs: selectedDraft.maxTotalSpanMs,
      analyticFamily: selectedDraft.analyticFamily || '',
      primaryMethodology: selectedDraft.primaryMethodology || 'volumetric_de',
      behaviorActorEntityType: (behavior as any).actor_entity_type || '',
      behaviorActionFamily: (behavior as any).action_family || '',
      behaviorTargetEntityType: (behavior as any).target_entity_type || '',
      behaviorChannel: (behavior as any).channel || '',
      behaviorDetectionObjective: (behavior as any).detection_objective || '',
      behaviorCanonicalSentence: (behavior as any).canonical_sentence || '',
      dimensionsPrimary: Array.isArray((dims as any).primary) ? (dims as any).primary : [],
      dimensionsSecondary: Array.isArray((dims as any).secondary) ? (dims as any).secondary : [],
      dimensionsRationale: (dims as any).rationale || '',
      measurementCountedAction: (measurement as any).counted_action || '',
      measurementAggregationKeysText: Array.isArray((measurement as any).aggregation_keys) ? (measurement as any).aggregation_keys.join(', ') : '',
      measurementGroupingKeysText: Array.isArray((measurement as any).grouping_keys) ? (measurement as any).grouping_keys.join(', ') : '',
      measurementFeatureSet: Array.isArray((measurement as any).feature_set) ? (measurement as any).feature_set : [],
      timeLookbackWindow: (timeLogic as any).lookback_window || '',
      timeDetectionWindow: (timeLogic as any).detection_window || '',
      timeWindowType: (timeLogic as any).window_type || '',
      timeEventField: (timeLogic as any).event_time_field || '',
      timeOrderingConfidence: (timeLogic as any).ordering_confidence || '',
      baselineRequired: Boolean((baseline as any).baseline_required),
      baselineTypes: Array.isArray((baseline as any).baseline_types) ? (baseline as any).baseline_types : [],
      baselineHistoricalPeriod: (baseline as any).historical_period || '',
      contextExpectedAutomation: (contextRisk as any).expected_automation || '',
      contextBenignOverlapsText: Array.isArray((contextRisk as any).benign_overlaps) ? (contextRisk as any).benign_overlaps.join('\n') : '',
      generationOutputFormat: (generation as any).selected_output_format || 'KQL',
      generationMode: (generation as any).generation_mode || 'single_hardened_rule',
      hardeningIncludeBenignOverlapHandling: Boolean((hardening as any).include_benign_overlap_handling),
      hardeningIncludeBaselineComparison: Boolean((hardening as any).include_baseline_comparison),
      hardeningIncludeTriageEvidenceFields: Boolean((hardening as any).include_triage_evidence_fields),
      hardeningIncludeDeceptionConfidenceLogic: Boolean((hardening as any).include_deception_confidence_logic),
      hardeningIncludeThresholdRationaleComments: Boolean((hardening as any).include_threshold_rationale_comments),
      groundingUseBehaviorObject: (grounding as any).use_behavior_object ?? true,
      groundingUseDimensions: (grounding as any).use_dimensions ?? true,
      groundingUseMeasurementModel: (grounding as any).use_measurement_model ?? true,
      groundingUseTimeWindowLogic: (grounding as any).use_time_window_logic ?? true,
      groundingUseBaselineStrategy: (grounding as any).use_baseline_strategy ?? true,
      groundingUseContextRisk: (grounding as any).use_context_risk ?? true,
      groundingUseNodeGraph: (grounding as any).use_node_graph ?? true,
      handoffOpenInMonacoEditor: (handoff as any).open_in_monaco_editor ?? true,
      handoffSaveToRuleHub: (handoff as any).save_to_rule_hub ?? true,
      handoffGenerateOpentideYaml: (handoff as any).generate_opentide_yaml ?? true,
      handoffAppendToWorkbench: Boolean((handoff as any).append_to_workbench),
      handoffAutoOpenTargetWorkbench: Boolean((handoff as any).auto_open_target_workbench),
      handoffTargetWorkbenchId: (handoff as any).target_workbench_id || '',
    });
    const sortedNodes: DraftNode[] = [...(selectedDraft.nodes || [])].sort(
      (a, b) => (a.stepOrder || 0) - (b.stepOrder || 0)
    );
    const nodeBorderByType: Record<DraftNode['nodeType'], string> = {
      EVENT: '2px solid var(--hef-text-link)',
      RULE: '2px solid var(--hef-info-border, var(--hef-text-link))',
      FEATURE: '2px solid var(--hef-success-text)',
      CONTEXT: '2px solid color-mix(in srgb, var(--hef-success-text) 70%, var(--hef-success-border))',
      DECISION: '2px solid var(--hef-success-border)',
      BASELINE: '2px solid #ffffff',
      DECEPTION: '2px solid var(--hef-danger-border)',
    };
    const mappedNodes: Node[] = sortedNodes.map((node: DraftNode, index: number) => {
      const sourceLabel = node.nodeType === 'EVENT'
        ? node.dataSource?.name || 'Data source'
        : node.nodeType === 'RULE'
          ? node.detectionRule?.title || 'Rule'
          : node.nodeConfig?.type?.toString() || node.nodeType;
      const capLabel = node.capabilityAbstraction?.componentArtifact || 'Unbound abstraction';
      const label = `${index + 1}. ${node.label || sourceLabel}`;
      return {
        id: node.id,
        position: { x: node.positionX || 120, y: node.positionY || 120 },
        data: {
          label: (
            <div>
              <div style={{ fontWeight: 600, color: 'var(--hef-text-primary)' }}>{label}</div>
              <div style={{ fontSize: 11, color: 'var(--hef-text-secondary)' }}>{capLabel}</div>
            </div>
          ),
          nodeType: node.nodeType,
        },
        style: {
          width: 230,
          borderRadius: 8,
          border: nodeBorderByType[node.nodeType] || '2px solid var(--hef-border)',
          background: 'var(--hef-bg-surface)',
          color: 'var(--hef-text-primary)',
        },
      };
    });
    const mappedEdges: Edge[] = (selectedDraft.edges || []).map((edge: any) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      markerEnd: { type: 'arrowclosed' as any },
    }));
    setNodes(mappedNodes);
    setEdges(mappedEdges);
  }, [selectedDraft, constraintsForm, setNodes, setEdges]);

  useEffect(() => {
    if (!activeRunId || !validationData?.mveValidationRun) return;
    const run = validationData.mveValidationRun;
    if (run.status === 'COMPLETED' || run.status === 'FAILED') {
      stopPolling();
      setActiveRunId(null);
      refetchSelectedDraft();
      message.info(run.status === 'COMPLETED' ? 'MVE validation finished.' : 'MVE validation failed.');
    }
  }, [activeRunId, validationData, stopPolling, refetchSelectedDraft]);

  useEffect(() => {
    if (!exportOpen || !selectedDraft) return;
    exportForm.setFieldsValue({
      branch: exportForm.getFieldValue('branch') || 'main',
      commitMessage: exportForm.getFieldValue('commitMessage') || `Publish MVE VelocityDetection: ${selectedDraft.name}`,
      filePath: exportForm.getFieldValue('filePath') || '',
    });
  }, [exportOpen, selectedDraft, exportForm]);

  useEffect(() => {
    if (targetWorkbenchId || !preferredHandoffTargetId) return;
    constraintsForm.setFieldValue('handoffTargetWorkbenchId', preferredHandoffTargetId);
  }, [targetWorkbenchId, preferredHandoffTargetId, constraintsForm]);

  const abstractionOptions = useMemo<AbstractionOption[]>(
    () =>
      abstractions.map((item: any) => ({
        value: item.id,
        label: `${item.abstractionLayer} :: ${item.componentArtifact} (${item.technique?.techniqueId || 'N/A'})`,
        techniqueId: item.technique?.techniqueId || '',
      })),
    [abstractions]
  );

  const handleCreateDraft = async () => {
    const name = window.prompt('Name this Velocity chain', 'New Velocity Chain');
    if (!name) return;
    try {
      const result = await createDraft({
        variables: {
          name,
          anchorEntity: 'host.hostname',
          maxTotalSpanMs: 800,
          analyticFamily: 'identity_fan_out',
          primaryMethodology: 'volumetric_de',
          behaviorObject: {},
          dimensions: {},
          measurementModel: {},
          timeWindowLogic: {},
          baselineStrategy: {},
          contextRisk: {},
          generationProfile: {},
          downstreamHandoff: {},
        },
      });
      const newId = result.data?.createMveDraft?.mveDraft?.id as string | undefined;
      await refetchDrafts();
      if (newId) {
        setSelectedDraftId(newId);
      }
      message.success('MVE draft created.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to create MVE draft.');
    }
  };

  const handleDeleteDraft = async () => {
    if (!selectedDraftId) return;
    try {
      await deleteDraft({ variables: { draftId: selectedDraftId } });
      setSelectedDraftId(null);
      await refetchDrafts();
      message.success('MVE draft deleted.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to delete draft.');
    }
  };

  const handleQuickStatusChange = async (nextStatus: 'DRAFT' | 'MODELED' | 'GENERATION_READY' | 'VALIDATED' | 'EXPORTED') => {
    if (!selectedDraftId) return;
    if (!canQuickChangeMveStatus) {
      message.error('Protected MVE statuses require Reviewer/Admin to change.');
      return;
    }
    if ((selectedDraft?.status || '').toUpperCase() === nextStatus) return;
    try {
      await updateDraft({
        variables: {
          draftId: selectedDraftId,
          status: nextStatus,
        },
      });
      await Promise.all([refetchSelectedDraft(), refetchDrafts()]);
      message.success(`MVE status updated to ${nextStatus}.`);
    } catch (error: any) {
      message.error(error?.message || 'Failed to update MVE status.');
    }
  };

  const handleCreateWorkbenchFromMve = async () => {
    if (!selectedDraftId) return;
    if (isExportedMveDraft) {
      message.info('This MVE draft is already EXPORTED. Continue from Workbench.');
      return;
    }
    let enrichWithAi = enrichMveImportWithAiByDefault;
    Modal.confirm({
      title: 'Create Workbench from this MVE?',
      content: (
        <Space direction="vertical" size={4}>
          <Typography.Text>
            This will import Global Constraints / vNext Modeling into Workbench Technical Context.
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Preconditions: all GENERATION_READY-required fields must be valid.
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Side effect: MVE status will be set to EXPORTED and locked in MVE lane.
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            AI enrichment will run if configured; otherwise source context is imported as-is.
          </Typography.Text>
          <Checkbox
            checked={enrichMveImportWithAiByDefault}
            onChange={(event: any) => {
              enrichWithAi = event.target.checked;
              setEnrichMveImportWithAiByDefault(event.target.checked);
            }}
          >
            Enrich imported Technical Context with AI (if configured)
          </Checkbox>
        </Space>
      ),
      okText: 'Create & Export',
      cancelText: 'Cancel',
      okButtonProps: { loading: creatingWorkbenchFromMve },
      onOk: async () => {
        try {
          const result = await createWorkbenchFromMve({
            variables: {
              draftId: selectedDraftId,
              enrichWithAi,
            },
          });
          const payload = (result.data as any)?.createWorkbenchFromMve;
          if (!payload?.success) {
            if (payload?.validationErrors?.length) {
              message.error(`Import blocked: ${payload.validationErrors[0]?.message || 'fill required fields first'}`);
            } else {
              message.error(payload?.message || 'Failed to create Workbench from MVE.');
            }
            return;
          }
          await Promise.all([refetchSelectedDraft(), refetchDrafts()]);
          if (payload?.warnings?.length) {
            message.warning(payload.warnings[0]);
          }
          const graphId = payload?.playbookGraph?.id;
          if (graphId) {
            message.success('Workbench created from MVE. Opening it now.');
            navigateToTargetWorkbenchIfNeeded(graphId);
          } else {
            message.success(payload?.message || 'Workbench created from MVE.');
          }
        } catch (error: any) {
          message.error(error?.message || 'Failed to create Workbench from MVE.');
        }
      },
    });
  };

  const handleSaveConstraints = async () => {
    if (!selectedDraftId) return;
    if (isExportedMveDraft) {
      message.info('EXPORTED MVE draft is immutable. Continue editing in Workbench.');
      return;
    }
    try {
      const values = await constraintsForm.validateFields();
      const resolvedTargetWorkbenchId = values.handoffTargetWorkbenchId || preferredHandoffTargetId || '';
      const splitCsv = (value?: string) => (value || '').split(',').map((item) => item.trim()).filter(Boolean);
      const splitLines = (value?: string) => (value || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
      await updateDraft({
        variables: {
          draftId: selectedDraftId,
          name: values.name,
          anchorEntity: values.anchorEntity,
          maxTotalSpanMs: Number(values.maxTotalSpanMs),
          analyticFamily: values.analyticFamily || null,
          primaryMethodology: values.primaryMethodology || 'volumetric_de',
          behaviorObject: {
            actor_entity_type: values.behaviorActorEntityType || '',
            action_family: values.behaviorActionFamily || '',
            target_entity_type: values.behaviorTargetEntityType || '',
            channel: values.behaviorChannel || '',
            detection_objective: values.behaviorDetectionObjective || '',
            canonical_sentence: values.behaviorCanonicalSentence || '',
          },
          dimensions: {
            primary: values.dimensionsPrimary || [],
            secondary: values.dimensionsSecondary || [],
            rationale: values.dimensionsRationale || '',
          },
          measurementModel: {
            counted_action: values.measurementCountedAction || '',
            aggregation_keys: splitCsv(values.measurementAggregationKeysText),
            grouping_keys: splitCsv(values.measurementGroupingKeysText),
            feature_set: values.measurementFeatureSet || [],
          },
          timeWindowLogic: {
            lookback_window: values.timeLookbackWindow || '',
            detection_window: values.timeDetectionWindow || '',
            window_type: values.timeWindowType || '',
            event_time_field: values.timeEventField || '',
            ordering_confidence: values.timeOrderingConfidence || '',
          },
          baselineStrategy: {
            baseline_required: Boolean(values.baselineRequired),
            baseline_types: values.baselineTypes || [],
            historical_period: values.baselineHistoricalPeriod || '',
          },
          contextRisk: {
            expected_automation: values.contextExpectedAutomation || '',
            benign_overlaps: splitLines(values.contextBenignOverlapsText),
          },
          generationProfile: {
            selected_output_format: values.generationOutputFormat || 'KQL',
            generation_mode: values.generationMode || 'single_hardened_rule',
            hardening_options: {
              include_benign_overlap_handling: Boolean(values.hardeningIncludeBenignOverlapHandling),
              include_baseline_comparison: Boolean(values.hardeningIncludeBaselineComparison),
              include_triage_evidence_fields: Boolean(values.hardeningIncludeTriageEvidenceFields),
              include_deception_confidence_logic: Boolean(values.hardeningIncludeDeceptionConfidenceLogic),
              include_threshold_rationale_comments: Boolean(values.hardeningIncludeThresholdRationaleComments),
            },
            grounding_inputs: {
              use_behavior_object: Boolean(values.groundingUseBehaviorObject),
              use_dimensions: Boolean(values.groundingUseDimensions),
              use_measurement_model: Boolean(values.groundingUseMeasurementModel),
              use_time_window_logic: Boolean(values.groundingUseTimeWindowLogic),
              use_baseline_strategy: Boolean(values.groundingUseBaselineStrategy),
              use_context_risk: Boolean(values.groundingUseContextRisk),
              use_node_graph: Boolean(values.groundingUseNodeGraph),
            },
          },
          downstreamHandoff: {
            open_in_monaco_editor: Boolean(values.handoffOpenInMonacoEditor),
            save_to_rule_hub: Boolean(values.handoffSaveToRuleHub),
            generate_opentide_yaml: Boolean(values.handoffGenerateOpentideYaml),
            append_to_workbench: Boolean(values.handoffAppendToWorkbench),
            auto_open_target_workbench: Boolean(values.handoffAutoOpenTargetWorkbench),
            target_workbench_id: resolvedTargetWorkbenchId || null,
          },
        },
      });
      if (!values.handoffTargetWorkbenchId && resolvedTargetWorkbenchId) {
        constraintsForm.setFieldValue('handoffTargetWorkbenchId', resolvedTargetWorkbenchId);
      }
      await Promise.all([refetchSelectedDraft(), refetchDrafts()]);
      message.success('MVE constraints saved.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to save constraints.');
    }
  };

  const handleAddNode = async () => {
    if (!selectedDraftId) return;
    if (isExportedMveDraft) {
      message.info('EXPORTED MVE draft is immutable. Continue editing in Workbench.');
      return;
    }
    try {
      const values = await addNodeForm.validateFields();
      let parsedCriteria: Record<string, unknown> = {};
      let parsedNodeConfig: Record<string, unknown> = {};
      if (values.criteriaText && values.criteriaText.trim()) {
        parsedCriteria = JSON.parse(values.criteriaText);
      }
      if (values.nodeConfigText && values.nodeConfigText.trim()) {
        parsedNodeConfig = JSON.parse(values.nodeConfigText);
      }
      if (values.nodeType === 'FEATURE') {
        parsedNodeConfig = {
          ...parsedNodeConfig,
          type: 'FEATURE',
          feature_type: values.featureType || '',
          output_field: values.featureOutputField || '',
          formula: values.featureFormula || '',
        };
      }
      if (values.nodeType === 'BASELINE') {
        parsedNodeConfig = {
          ...parsedNodeConfig,
          type: 'BASELINE',
          baseline_type: values.baselineType || '',
          history_window: values.baselineHistoryWindow || '',
        };
      }
      if (values.nodeType === 'CONTEXT') {
        parsedNodeConfig = {
          ...parsedNodeConfig,
          type: 'CONTEXT',
          condition: values.contextCondition || '',
          effect: values.contextEffect || '',
        };
      }
      if (values.nodeType === 'DECEPTION') {
        parsedNodeConfig = {
          ...parsedNodeConfig,
          type: 'DECEPTION',
          deception_type: values.deceptionType || '',
          confidence_effect: values.deceptionConfidenceEffect || '',
        };
      }
      if (values.nodeType === 'DECISION') {
        parsedNodeConfig = {
          ...parsedNodeConfig,
          type: 'DECISION',
          downstream_recommendation: values.decisionRecommendation || '',
          threshold_logic: values.decisionThresholdLogic || '',
        };
      }
      await addNode({
        variables: {
          draftId: selectedDraftId,
          nodeType: values.nodeType,
          stepOrder: null,
          label: values.label || '',
          dataSourceId: values.nodeType === 'EVENT' ? values.dataSourceId : null,
          detectionRuleId: values.nodeType === 'RULE' ? values.detectionRuleId : null,
          capabilityAbstractionId: values.capabilityAbstractionId || null,
          tacticRef: values.tacticRef || null,
          techniqueRef: values.techniqueRef || null,
          criteria: parsedCriteria,
          nodeConfig: parsedNodeConfig,
          positionX: 120 + Math.random() * 240,
          positionY: 120 + Math.random() * 240,
        },
      });
      setAddNodeOpen(false);
      addNodeForm.resetFields();
      await refetchSelectedDraft();
      message.success('Node added.');
    } catch (error: any) {
      if (error?.message?.includes('JSON')) {
        message.error('Criteria must be valid JSON.');
      } else if (error?.errorFields) {
        return;
      } else {
        message.error(error?.message || 'Failed to add node.');
      }
    }
  };

  const handleDeleteSelectedNode = async () => {
    if (!selectedNodeId) return;
    if (isExportedMveDraft) {
      message.info('EXPORTED MVE draft is immutable. Continue editing in Workbench.');
      return;
    }
    try {
      await deleteNode({ variables: { nodeId: selectedNodeId } });
      setSelectedNodeId(null);
      await refetchSelectedDraft();
      message.success('Node deleted.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to delete node.');
    }
  };

  const handleValidation = async () => {
    if (!selectedDraftId) return;
    if (isExportedMveDraft) {
      message.info('This MVE draft is already EXPORTED. Continue validation/review in Workbench.');
      return;
    }
    try {
      const result = await startValidation({ variables: { draftId: selectedDraftId } });
      const payload = result.data?.startMveValidation;
      if (!payload?.success) {
        if (payload?.validationErrors?.length) {
          message.error(`Validation blocked: ${payload.validationErrors[0]?.message || 'draft is incomplete'}`);
        } else {
          message.error(payload?.message || 'Failed to queue validation.');
        }
        return;
      }
      const runId = payload.validationRun?.id as string | undefined;
      if (runId) {
        setActiveRunId(runId);
      }
      message.success(payload.message || 'Validation queued.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to start validation.');
    }
  };

  const handleGenerateRule = async () => {
    if (!selectedDraftId) return;
    if (isExportedMveDraft) {
      message.info('This MVE draft is already EXPORTED. Continue generation/editing in Workbench.');
      return;
    }
    try {
      const outputFormat = constraintsForm.getFieldValue('generationOutputFormat') || 'KQL';
      const result = await generateMveRule({ variables: { draftId: selectedDraftId, outputFormat } });
      const payload = result.data?.generateMveDetectionRule;
      if (!payload?.success) {
        if (payload?.validationErrors?.length) {
          message.error(`Generation blocked: ${payload.validationErrors[0]?.message || 'draft is incomplete'}`);
        } else {
          message.error(payload?.message || 'MVE rule generation failed.');
        }
        setGenerationWarnings(payload?.warnings || []);
        return;
      }
      setGeneratedRule(payload.generatedRule || '');
      setGeneratedFormat(payload.outputFormat || outputFormat);
      setGenerationWarnings(payload.warnings || []);
      setEditorModalVisible(true);
      message.success(payload.message || 'MVE rule generated.');
      await refetchSelectedDraft();
      await refetchDrafts();
    } catch (error: any) {
      message.error(error?.message || 'Failed to generate MVE rule.');
    }
  };

  const persistMveHandoffToTargetWorkbench = async (
    targetGraphId: string,
    ruleText: string,
    ruleFormat: string
  ) => {
    try {
      const reviewResult = await apolloClient.query<TargetWorkbenchReviewData>({
        query: GET_TARGET_WORKBENCH_REVIEW_QUERY,
        variables: { id: targetGraphId },
        fetchPolicy: 'network-only',
      });
      const targetGraph = reviewResult.data?.playbookGraph;
      if (!targetGraph) return;

      let parsedOpenTide: any = {};
      if (targetGraph.opentideYaml) {
        try {
          parsedOpenTide =
            typeof targetGraph.opentideYaml === 'string'
              ? JSON.parse(targetGraph.opentideYaml)
              : targetGraph.opentideYaml;
        } catch {
          parsedOpenTide = {};
        }
      }
      parsedOpenTide = parsedOpenTide && typeof parsedOpenTide === 'object' ? parsedOpenTide : {};
      parsedOpenTide.mve_handoff = {
        linked_mve_draft_id: selectedDraftId,
        generated_rule_format: ruleFormat,
        generated_rule: ruleText,
        validation_summary: selectedDraft?.validationSummary || {},
        behavior_object_summary: selectedDraft?.behaviorObject || {},
        dimension_summary: selectedDraft?.dimensions || {},
        measurement_summary: selectedDraft?.measurementModel || {},
        baseline_summary: selectedDraft?.baselineStrategy || {},
      };
      await updateOpenTideYaml({
        variables: {
          graphId: targetGraphId,
          opentideYaml: JSON.stringify(parsedOpenTide),
          configuredPlatforms: targetGraph.configuredPlatforms || [],
        },
      });
      await refetchTargetWorkbenchReview();
    } catch (handoffError) {
      console.warn('Failed to update target workbench OpenTIDE handoff payload', handoffError);
    }
  };

  const navigateToTargetWorkbenchIfNeeded = (targetGraphId: string) => {
    const targetPath = `/playbooks/${targetGraphId}`;
    if (window.location.pathname !== targetPath) {
      navigate(targetPath);
    }
  };

  const saveRuleAndHandoff = async (
    targetGraphId: string,
    rule: string,
    format: string,
    options?: { autoCommit?: boolean; commitMessage?: string }
  ) => {
    const res = await saveRuleToHub({
      variables: {
        playbookId: targetGraphId,
        rawYaml: rule,
        format,
        autoCommit: options?.autoCommit,
        commitMessage: options?.commitMessage,
      },
    });
    const payload = res.data?.saveDetectionRule;
    if (payload?.success) {
      setGeneratedRule(rule);
      setGeneratedFormat(format);
      await persistMveHandoffToTargetWorkbench(targetGraphId, rule, format);
      if (autoOpenTargetWorkbench) {
        navigateToTargetWorkbenchIfNeeded(targetGraphId);
      }
    }
    return payload;
  };

  const handleSaveGeneratedRule = async () => {
    if (!generatedRule.trim()) return;
    const targetGraphId = targetWorkbenchId;
    if (!targetGraphId) {
      message.error('Target Workbench ID is required before saving generated rule to Rule Hub.');
      return;
    }
    try {
      const payload = await saveRuleAndHandoff(targetGraphId, generatedRule, generatedFormat);
      if (!payload?.success) {
        message.error(payload?.message || payload?.errors?.[0] || 'Failed to save generated rule.');
        return;
      }
      message.success(payload.message || 'Generated rule saved to Rule Hub.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to save generated rule.');
    }
  };

  const openExportModal = () => {
    if (!selectedDraftId) return;
    if (isExportedMveDraft) {
      message.info('This MVE draft is already EXPORTED. Continue export/deploy from Workbench.');
      return;
    }
    setExportMode('SAVE');
    exportForm.setFieldsValue({
      repositoryId: undefined,
      branch: 'main',
      filePath: '',
      commitMessage: selectedDraft ? `Publish MVE VelocityDetection: ${selectedDraft.name}` : '',
      targetGraphId: undefined,
    });
    setExportOpen(true);
  };

  const downloadYamlToPc = (yamlText: string, fileName: string) => {
    const blob = new Blob([yamlText], { type: 'text/yaml;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(href);
  };

  const handleExportAction = async () => {
    if (!selectedDraftId) return;
    try {
      const values = await exportForm.validateFields();
      const variables: Record<string, unknown> = {
        draftId: selectedDraftId,
        mode: exportMode,
      };
      if (exportMode === 'PUSH_GIT') {
        variables.repositoryId = values.repositoryId;
        variables.branch = values.branch || 'main';
        variables.filePath = values.filePath || null;
        variables.commitMessage = values.commitMessage || null;
      }
      if (exportMode === 'APPEND_WORKBENCH') {
        variables.targetGraphId = values.targetGraphId;
      }

      const result = await exportYaml({ variables });
      const payload = result.data?.exportMveOpenTideYaml;
      if (!payload?.success) {
        if (payload?.validationErrors?.length) {
          message.error(`Export blocked: ${payload.validationErrors[0]?.message || 'draft is incomplete'}`);
        } else {
          message.error(payload?.message || 'Export failed.');
        }
        return;
      }

      const yamlText = payload.yamlText || '';
      const generatedName = payload.generatedFileName || `mve-${selectedDraftId}.yaml`;
      if (exportMode === 'SAVE') {
        downloadYamlToPc(yamlText, generatedName);
      }
      if (exportMode === 'PUSH_GIT' && payload.url) {
        window.open(payload.url, '_blank', 'noopener,noreferrer');
      }

      setYamlPreview(yamlText);
      setYamlOpen(true);
      setExportOpen(false);
      await Promise.all([refetchSelectedDraft(), refetchDrafts()]);
      message.success(payload.message || 'Export completed.');
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message || 'Export failed.');
    }
  };

  const handleConnect = async (connection: Connection) => {
    if (!selectedDraftId || !connection.source || !connection.target) return;
    setEdges((existing) => addEdge(connection, existing));
    try {
      await addEdgeMutation({
        variables: {
          draftId: selectedDraftId,
          sourceNodeId: connection.source,
          targetNodeId: connection.target,
        },
      });
      await refetchSelectedDraft();
    } catch (error: any) {
      message.error(error?.message || 'Failed to create edge.');
      await refetchSelectedDraft();
    }
  };

  const handleNodeDragStop = async (_event: React.MouseEvent, node: Node) => {
    try {
      await updateNode({
        variables: {
          nodeId: node.id,
          positionX: node.position.x,
          positionY: node.position.y,
        },
      });
    } catch (error: any) {
      message.warning(error?.message || 'Could not persist node position.');
    }
  };

  const handleEdgeDoubleClick = async (_event: React.MouseEvent, edge: Edge) => {
    try {
      await deleteEdgeMutation({ variables: { edgeId: edge.id } });
      setEdges((existing) => existing.filter((item) => item.id !== edge.id));
    } catch (error: any) {
      message.error(error?.message || 'Failed to delete edge.');
    }
  };

  const draftOptions = (draftsData?.allMveDrafts || []).map((item) => ({
    value: item.id,
    label: `${item.name} (${item.status})`,
  }));

  const nodeType = Form.useWatch('nodeType', addNodeForm);

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Alert
        type="info"
        showIcon
        message="Machina Velocity Engine (MVE)"
        description="Build chain-sequence detections with capability abstractions, global velocity constraints, and asynchronous AdvOps/ACH validation."
      />

      <Card title="Kinetic Chain Canvas" style={{ minHeight: CARD_HEIGHT }}>
        <Row gutter={12}>
          <Col xs={24} lg={6}>
            <Card size="small" title="Drafts">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button onClick={handleCreateDraft} loading={creatingDraft} type="primary" block>
                  + New MVE Draft
                </Button>
                <Popconfirm
                  title="Delete whole MVE draft?"
                  description="This deletes the full MVE chain (nodes and edges)."
                  okText="Delete MVE"
                  cancelText="Cancel"
                  okButtonProps={{ danger: true, loading: deletingDraft }}
                  onConfirm={handleDeleteDraft}
                  disabled={!selectedDraftId}
                >
                  <Button
                    danger
                    icon={<DeleteOutlined />}
                    disabled={!selectedDraftId}
                    loading={deletingDraft}
                    aria-label="Delete selected MVE draft"
                    block
                  >
                    Delete MVE
                  </Button>
                </Popconfirm>
                <Select
                  style={{ width: '100%' }}
                  placeholder="Select draft"
                  value={selectedDraftId || undefined}
                  options={draftOptions}
                  onChange={(value: string) => setSelectedDraftId(value)}
                  loading={draftsLoading}
                />
                {selectedDraft && (
                  <Card size="small">
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Typography.Text strong>{selectedDraft.name}</Typography.Text>
                      <Space size={4}>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                          Lifecycle
                        </Typography.Text>
                        <Tooltip title="Quick status update. If status is VALIDATED/EXPORTED, only Reviewer/Admin can change it.">
                          <QuestionCircleOutlined style={{ fontSize: 12, color: 'var(--hef-text-muted)' }} />
                        </Tooltip>
                      </Space>
                      <Space>
                        <Tag color={selectedDraft.isAdvopsValidated ? 'green' : 'gold'}>
                          {selectedDraft.isAdvopsValidated ? 'AdvOps Validated' : 'Pending Validation'}
                        </Tag>
                        <Tag color={MVE_STATUS_TAG_COLOR[selectedDraft.status as keyof typeof MVE_STATUS_TAG_COLOR] || 'default'}>
                          {selectedDraft.status}
                        </Tag>
                      </Space>
                      <Select
                        size="small"
                        style={{ width: '100%' }}
                        placeholder="Change lifecycle status"
                        aria-label="Change MVE lifecycle status"
                        value={selectedDraft.status}
                        disabled={!canQuickChangeMveStatus}
                        options={statusOptions}
                        onChange={(value: 'DRAFT' | 'MODELED' | 'GENERATION_READY' | 'VALIDATED' | 'EXPORTED') => handleQuickStatusChange(value)}
                      />
                      {!canQuickChangeMveStatus ? (
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                          Status in {selectedDraft.status} can be changed only by Reviewer/Admin.
                        </Typography.Text>
                      ) : null}
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        Updated: {new Date(selectedDraft.updatedAt).toLocaleString()}
                      </Typography.Text>
                    </Space>
                  </Card>
                )}
                <Space
                  wrap
                  size={[8, 8]}
                  style={{ width: '100%', marginTop: 8, paddingTop: 10, borderTop: '1px solid var(--hef-border)' }}
                >
                  <Tooltip title="Add node" styles={{ body: TOOLTIP_STYLE }}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => setAddNodeOpen(true)}
                      disabled={!selectedDraftId}
                      style={ACTION_ICON_BUTTON_STYLE}
                    />
                  </Tooltip>
                  <Tooltip title="Delete selected node" styles={{ body: TOOLTIP_STYLE }}>
                    <Button
                      danger
                      icon={<DeleteOutlined />}
                      onClick={handleDeleteSelectedNode}
                      disabled={!selectedNodeId}
                      loading={deletingNode}
                      style={ACTION_ICON_BUTTON_STYLE}
                    />
                  </Tooltip>
                  <Button
                    type="primary"
                    icon={<SearchOutlined />}
                    onClick={handleValidation}
                    disabled={!selectedDraftId}
                    loading={startingValidation}
                    style={ACTION_TEXT_BUTTON_STYLE}
                  >
                    AdvOps
                  </Button>
                  <Button
                    type="dashed"
                    icon={<ExportOutlined />}
                    onClick={openExportModal}
                    disabled={!selectedDraftId}
                    loading={exportingYaml}
                    style={ACTION_TEXT_BUTTON_STYLE}
                  >
                    OpenTide
                  </Button>
                </Space>
                {isExportedMveDraft ? (
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    This MVE is EXPORTED and locked. Continue lifecycle changes in Workbench.
                  </Typography.Text>
                ) : null}
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={18}>
            {selectedDraftLoading || optionsLoading ? (
              <Spin />
            ) : !selectedDraft ? (
              <Typography.Text type="secondary">Create or select an MVE draft to start.</Typography.Text>
            ) : (
              <>
                <div className="mve-kinetic-flow" style={{ height: 520, border: '1px solid var(--hef-border)', borderRadius: 8 }}>
                  <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={handleConnect}
                    onNodeDragStop={handleNodeDragStop}
                    onNodeClick={(_evt, node) => setSelectedNodeId(node.id)}
                    onPaneClick={() => setSelectedNodeId(null)}
                    onEdgeDoubleClick={handleEdgeDoubleClick}
                    fitView
                  >
                    <Background color="var(--hef-border)" />
                    <Controls />
                  </ReactFlow>
                </div>
                <Space style={{ marginTop: 8 }}>
                  <Typography.Text type="secondary">
                    Double-click an edge to delete it. Drag nodes to persist placement.
                  </Typography.Text>
                  {selectedNodeId ? <Tag color="blue">Selected node: {selectedNodeId.slice(0, 8)}</Tag> : null}
                </Space>
              </>
            )}
          </Col>
        </Row>
      </Card>

      <Card title="Global Constraints / vNext Modeling">
        <Form layout="vertical" form={constraintsForm}>
          <Row gutter={12}>
            <Col xs={24} md={8}>
              <Form.Item label="Name" name="name" rules={[{ required: true, message: 'Required' }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item label="Anchor Entity" name="anchorEntity" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="host.hostname" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item label="Max Total Span (ms)" name="maxTotalSpanMs" rules={[{ required: true, message: 'Required' }]}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={SECTION_ROW_GUTTER}>
            <Col xs={24} xl={12}>
              <Form.Item label="Analytic Family" name="analyticFamily" rules={[{ required: true, message: 'Required' }]}>
                <Select
                  allowClear
                  options={[
                    { value: 'identity_fan_out', label: 'identity_fan_out' },
                    { value: 'fan_in', label: 'fan_in' },
                    { value: 'burstiness', label: 'burstiness' },
                    { value: 'rate_anomaly', label: 'rate_anomaly' },
                    { value: 'acceleration', label: 'acceleration' },
                    { value: 'sequence_compression', label: 'sequence_compression' },
                    { value: 'periodicity_rhythm', label: 'periodicity_rhythm' },
                    { value: 'baseline_deviation', label: 'baseline_deviation' },
                    { value: 'rare_event_amplification', label: 'rare_event_amplification' },
                    { value: 'hybrid_behavior_shape', label: 'hybrid_behavior_shape' },
                  ]}
                />
              </Form.Item>
              <Form.Item label="Primary Methodology" name="primaryMethodology" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="volumetric_de" />
              </Form.Item>

              <Typography.Text style={PANEL_SECTION_TITLE_STYLE}>Modeling Core</Typography.Text>
              <Collapse
                items={[
              {
                key: 'behavior',
                label: 'Behavior Object',
                children: (
                  <>
                    <Form.Item label="Actor Entity Type" name="behaviorActorEntityType" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Action Family" name="behaviorActionFamily" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Target Entity Type" name="behaviorTargetEntityType" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Channel" name="behaviorChannel" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Detection Objective" name="behaviorDetectionObjective" rules={[{ required: true, message: 'Required' }]}><Input.TextArea rows={3} /></Form.Item>
                    <Form.Item label="Canonical Sentence" name="behaviorCanonicalSentence" rules={[{ required: true, message: 'Required' }]}><Input.TextArea rows={3} /></Form.Item>
                  </>
                )
              },
              {
                key: 'dimensions',
                label: 'Dimensions',
                children: (
                  <>
                    <Form.Item label="Primary Dimensions" name="dimensionsPrimary" rules={[{ required: true, message: 'Required' }]}>
                      <Select mode="multiple" options={[
                        'volume','cardinality','rate','acceleration','inter_arrival_timing','duration','burstiness','fan_out','fan_in','sequence_compression','periodicity','rhythm','novelty','baseline_deviation','context_aware_deviation'
                      ].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Form.Item label="Secondary Dimensions" name="dimensionsSecondary">
                      <Select mode="multiple" options={[
                        'volume','cardinality','rate','acceleration','inter_arrival_timing','duration','burstiness','fan_out','fan_in','sequence_compression','periodicity','rhythm','novelty','baseline_deviation','context_aware_deviation'
                      ].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Form.Item label="Rationale" name="dimensionsRationale" rules={[{ required: true, message: 'Required' }]}><Input.TextArea rows={3} /></Form.Item>
                  </>
                )
              },
              {
                key: 'measurement',
                label: 'Measurement Model',
                children: (
                  <>
                    <Form.Item label="Counted Action" name="measurementCountedAction" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Aggregation Keys (comma-separated)" name="measurementAggregationKeysText" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Grouping Keys (comma-separated)" name="measurementGroupingKeysText" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Feature Set" name="measurementFeatureSet" rules={[{ required: true, message: 'Required' }]}>
                      <Select mode="multiple" options={[
                        'event_count','distinct_targets','distinct_target_families','actions_per_minute','acceleration_between_windows','median_inter_arrival','min_inter_arrival','p10_inter_arrival','p90_inter_arrival','session_duration','chain_duration_seconds','active_window_count','first_seen_target_ratio','sensitive_target_ratio','retry_ratio','success_failure_ratio','distinct_tools','distinct_step_types','source_rarity','self_baseline_deviation','peer_baseline_deviation','sequence_compression_score'
                      ].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                  </>
                )
              },
              {
                key: 'time',
                label: 'Time / Window Logic',
                children: (
                  <>
                    <Form.Item label="Lookback Window" name="timeLookbackWindow" rules={[{ required: true, message: 'Required' }]}><Input placeholder="14d" /></Form.Item>
                    <Form.Item label="Detection Window" name="timeDetectionWindow" rules={[{ required: true, message: 'Required' }]}><Input placeholder="5m" /></Form.Item>
                    <Form.Item label="Window Type" name="timeWindowType" rules={[{ required: true, message: 'Required' }]}>
                      <Select options={['fixed_bin','rolling_window','sessionized_window','sequence_window'].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Form.Item label="Event Time Field" name="timeEventField" rules={[{ required: true, message: 'Required' }]}><Input /></Form.Item>
                    <Form.Item label="Ordering Confidence" name="timeOrderingConfidence" rules={[{ required: true, message: 'Required' }]}>
                      <Select options={['high','medium','low','unknown'].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                  </>
                )
              }
            ]}
          />
        </Col>
        <Col xs={24} xl={12}>
          <Typography.Text style={PANEL_SECTION_TITLE_STYLE}>Execution & Handoff</Typography.Text>
          <Collapse
            items={[
              {
                key: 'baseline',
                label: 'Baseline Strategy',
                children: (
                  <>
                    <Form.Item label="Baseline Required" name="baselineRequired" valuePropName="checked"><Switch /></Form.Item>
                    <Form.Item label="Baseline Types" name="baselineTypes">
                      <Select mode="multiple" options={['static_threshold','self_baseline','peer_baseline','percentile_baseline','robust_deviation','seasonality_aware','novelty_baseline','rare_event_amplification'].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Form.Item label="Historical Period" name="baselineHistoricalPeriod"><Input placeholder="30d" /></Form.Item>
                  </>
                )
              },
              {
                key: 'context',
                label: 'Context / Risk',
                children: (
                  <>
                    <Form.Item label="Expected Automation" name="contextExpectedAutomation" rules={[{ required: true, message: 'Required' }]}>
                      <Select options={['none_expected','low_expected','moderate_expected','high_expected','unknown'].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Form.Item label="Benign Overlaps (one per line)" name="contextBenignOverlapsText" rules={[{ required: true, message: 'Required' }]}><Input.TextArea rows={4} /></Form.Item>
                  </>
                )
              },
              {
                key: 'generation',
                label: 'Rule Generation',
                children: (
                  <>
                    <Form.Item label="Selected Output Format" name="generationOutputFormat" rules={[{ required: true, message: 'Required' }]}>
                      <Select options={['KQL','EQL','SPL','WAZUH'].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Form.Item label="Generation Mode" name="generationMode" rules={[{ required: true, message: 'Required' }]}>
                      <Select options={['single_hardened_rule','multiple_variants','quick_win_plus_robust','chain_centric'].map((value) => ({ value, label: value }))} />
                    </Form.Item>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Form.Item label="Include Benign Overlap Handling" name="hardeningIncludeBenignOverlapHandling" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Include Baseline Comparison" name="hardeningIncludeBaselineComparison" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Include Triage Evidence Fields" name="hardeningIncludeTriageEvidenceFields" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Include Deception Confidence Logic" name="hardeningIncludeDeceptionConfidenceLogic" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Include Threshold Rationale Comments" name="hardeningIncludeThresholdRationaleComments" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Behavior Object" name="groundingUseBehaviorObject" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Dimensions" name="groundingUseDimensions" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Measurement Model" name="groundingUseMeasurementModel" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Time / Window Logic" name="groundingUseTimeWindowLogic" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Baseline Strategy" name="groundingUseBaselineStrategy" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Context / Risk" name="groundingUseContextRisk" valuePropName="checked"><Switch /></Form.Item>
                      <Form.Item label="Use Node Graph" name="groundingUseNodeGraph" valuePropName="checked"><Switch /></Form.Item>
                    </Space>
                  </>
                )
              },
              {
                key: 'handoff',
                label: 'Downstream Handoff',
                children: (
                  <>
                    <Form.Item label="Open in Monaco Editor" name="handoffOpenInMonacoEditor" valuePropName="checked"><Switch /></Form.Item>
                    <Form.Item label="Save to Rule Hub" name="handoffSaveToRuleHub" valuePropName="checked"><Switch /></Form.Item>
                    <Form.Item label="Generate OpenTIDE YAML" name="handoffGenerateOpentideYaml" valuePropName="checked"><Switch /></Form.Item>
                    <Form.Item label="Append to Workbench" name="handoffAppendToWorkbench" valuePropName="checked"><Switch /></Form.Item>
                    <Form.Item label="Auto-open Target Workbench after Save" name="handoffAutoOpenTargetWorkbench" valuePropName="checked"><Switch /></Form.Item>
                    <Form.Item label="Target Workbench" name="handoffTargetWorkbenchId">
                      <Select
                        showSearch
                        optionFilterProp="label"
                        allowClear
                        options={appendTargets.map((target: any) => ({
                          value: target.id,
                          label: `${target.title} (${target.status})`,
                        }))}
                        placeholder={preferredHandoffTargetId ? 'Auto-selected from available Workbench targets' : 'No eligible Workbench target available'}
                      />
                    </Form.Item>
                  </>
                )
              }
            ]}
          />
            </Col>
          </Row>
        </Form>
        <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
          <Row gutter={SECTION_ROW_GUTTER}>
            <Col xs={24} md={12}>
              <Button block onClick={handleSaveConstraints} loading={savingConstraints} disabled={!selectedDraftId}>
                Save Constraints
              </Button>
            </Col>
            <Col xs={24} md={12}>
              <Button block type="primary" onClick={handleGenerateRule} loading={generatingRule} disabled={!selectedDraftId}>
                Generate Rule
              </Button>
            </Col>
            <Col xs={24}>
              <Button
                block
                type="dashed"
                onClick={handleCreateWorkbenchFromMve}
                loading={creatingWorkbenchFromMve}
                disabled={!selectedDraftId || isExportedMveDraft}
              >
                Create Workbench from MVE
              </Button>
            </Col>
          </Row>
        </Space>
      </Card>

      {validationData?.mveValidationRun && (
        <Alert
          type={validationData.mveValidationRun.status === 'FAILED' ? 'error' : 'info'}
          showIcon
          message={`Validation status: ${validationData.mveValidationRun.status}`}
          description={
            validationData.mveValidationRun.errorMessage
              ? validationData.mveValidationRun.errorMessage
              : `Run ID ${validationData.mveValidationRun.id}`
          }
        />
      )}

      {selectedDraft?.validationErrors?.length ? (
        <Alert
          type="warning"
          showIcon
          message="MVE draft has unresolved validation errors"
          description={selectedDraft.validationErrors.map((item: any) => item.message).join(' | ')}
        />
      ) : null}

      {(generatedRule || generationWarnings.length > 0) && (
        <Card title={`Generated Rule${generatedFormat ? ` (${generatedFormat})` : ''}`}>
          <Row gutter={SECTION_ROW_GUTTER}>
            <Col xs={24} xl={14}>
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                {generationWarnings.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    message="Generation warnings"
                    description={generationWarnings.join(' | ')}
                  />
                )}
                <Typography.Text type="secondary" style={COMPACT_SUBTITLE_STYLE}>
                  {generatedFormat
                    ? `Generated in ${generatedFormat}. Save it, then hand off to target Workbench review.`
                    : 'Generated output is ready. Save and hand off to target Workbench review.'}
                </Typography.Text>
                <Space wrap size={[8, 8]}>
                  <Button type="primary" onClick={handleSaveGeneratedRule} loading={savingGeneratedRule}>
                    Save Generated Rule to Rule Hub
                  </Button>
                  <Button onClick={() => setEditorModalVisible(true)}>
                    Open Rule Workflow
                  </Button>
                  {targetWorkbenchId ? (
                    <Button type="dashed" onClick={() => navigateToTargetWorkbenchIfNeeded(targetWorkbenchId)}>
                      Open Target Workbench
                    </Button>
                  ) : null}
                </Space>
              </Space>
            </Col>
            <Col xs={24} xl={10}>
              <Card
                size="small"
                title="Downstream Review"
              >
                <Typography.Text type="secondary" style={COMPACT_SUBTITLE_STYLE}>
                  Review and approval status for the selected target Workbench.
                </Typography.Text>
                {targetWorkbenchId ? (
                  <ReviewWorkflow
                    playbookId={targetWorkbenchId}
                    status={(targetWorkbenchReviewData?.playbookGraph?.status || 'RESEARCH') as any}
                    activeReview={targetWorkbenchReviewData?.playbookGraph?.activeReview || null}
                    userRole={targetWorkbenchReviewData?.me?.role}
                    isAuthor={targetWorkbenchReviewData?.playbookGraph?.author?.id === targetWorkbenchReviewData?.me?.id}
                    refetch={async () => {
                      await refetchTargetWorkbenchReview();
                    }}
                  />
                ) : (
                  <Alert
                    type="info"
                    showIcon
                    message="No target Workbench selected"
                    description="Pick a target in Downstream Handoff to enable review actions."
                  />
                )}
              </Card>
            </Col>
          </Row>
        </Card>
      )}

      <Modal
        title="Add MVE Node"
        open={addNodeOpen}
        onCancel={() => setAddNodeOpen(false)}
        onOk={handleAddNode}
        okButtonProps={{ loading: addingNode }}
        width={760}
      >
        <Form form={addNodeForm} layout="vertical" initialValues={{ nodeType: 'EVENT', criteriaText: '{}', nodeConfigText: '{}' }}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="nodeType" label="Type" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'EVENT', label: 'Event (Data Catalog)' },
                    { value: 'RULE', label: 'Rule (Rule Hub)' },
                    { value: 'FEATURE', label: 'Feature (Derived Measurement)' },
                    { value: 'BASELINE', label: 'Baseline (Comparison Logic)' },
                    { value: 'CONTEXT', label: 'Context (Risk/Suppression)' },
                    { value: 'DECEPTION', label: 'Deception (Decoy Signal)' },
                    { value: 'DECISION', label: 'Decision (Classification/Output)' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="label" label="Label">
                <Input placeholder="Optional custom label" />
              </Form.Item>
            </Col>
          </Row>

          {nodeType === 'EVENT' && (
            <Form.Item name="dataSourceId" label="Data Source" rules={[{ required: true, message: 'Required for EVENT node' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={dataSources.map((item: any) => ({ value: item.id, label: item.name }))}
              />
            </Form.Item>
          )}

          {nodeType === 'RULE' && (
            <Form.Item name="detectionRuleId" label="Detection Rule" rules={[{ required: true, message: 'Required for RULE node' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={rules.map((item: any) => ({ value: item.id, label: `[${item.format}] ${item.title}` }))}
              />
            </Form.Item>
          )}

          {nodeType === 'FEATURE' && (
            <>
              <Form.Item name="featureType" label="Feature Type" rules={[{ required: true, message: 'Required for FEATURE node' }]}>
                <Select options={['event_count','distinct_targets','actions_per_minute','chain_duration_seconds','median_inter_arrival','source_rarity','self_baseline_deviation','peer_baseline_deviation','sequence_compression_score'].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="featureOutputField" label="Output Field" rules={[{ required: true, message: 'Required for FEATURE node' }]}>
                <Input placeholder="feature_output" />
              </Form.Item>
              <Form.Item name="featureFormula" label="Formula">
                <Input.TextArea rows={3} />
              </Form.Item>
            </>
          )}

          {nodeType === 'BASELINE' && (
            <>
              <Form.Item name="baselineType" label="Baseline Type" rules={[{ required: true, message: 'Required for BASELINE node' }]}>
                <Select options={['static_threshold','self_baseline','peer_baseline','percentile_baseline','robust_deviation','seasonality_aware','novelty_baseline','rare_event_amplification'].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="baselineHistoryWindow" label="History Window">
                <Input placeholder="30d" />
              </Form.Item>
            </>
          )}

          {nodeType === 'CONTEXT' && (
            <>
              <Form.Item name="contextCondition" label="Condition" rules={[{ required: true, message: 'Required for CONTEXT node' }]}>
                <Input.TextArea rows={3} />
              </Form.Item>
              <Form.Item name="contextEffect" label="Effect" rules={[{ required: true, message: 'Required for CONTEXT node' }]}>
                <Select options={['suppress','lower_confidence','raise_confidence','raise_severity','annotate'].map((value) => ({ value, label: value }))} />
              </Form.Item>
            </>
          )}

          {nodeType === 'DECEPTION' && (
            <>
              <Form.Item name="deceptionType" label="Deception Type" rules={[{ required: true, message: 'Required for DECEPTION node' }]}>
                <Select options={['honey_spn','fake_credential','canary_url','decoy_config','decoy_account','decoy_path','other'].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="deceptionConfidenceEffect" label="Confidence Effect" rules={[{ required: true, message: 'Required for DECEPTION node' }]}>
                <Select options={['medium','high','critical'].map((value) => ({ value, label: value }))} />
              </Form.Item>
            </>
          )}

          {nodeType === 'DECISION' && (
            <>
              <Form.Item name="decisionRecommendation" label="Downstream Recommendation" rules={[{ required: true, message: 'Required for DECISION node' }]}>
                <Select options={['save_rule','export_yaml','append_workbench','review_only'].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="decisionThresholdLogic" label="Threshold Logic">
                <Input.TextArea rows={3} />
              </Form.Item>
            </>
          )}

          <Form.Item name="capabilityAbstractionId" label="Capability Abstraction Binding">
            <Select
              showSearch
              optionFilterProp="label"
              options={abstractionOptions}
              onChange={(value: string) => {
                const selected = abstractionOptions.find((item: AbstractionOption) => item.value === value);
                if (selected?.techniqueId) {
                  addNodeForm.setFieldValue('techniqueRef', selected.techniqueId);
                }
              }}
            />
          </Form.Item>

          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="tacticRef" label="Tactic Ref">
                <Input placeholder="TA0001" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="techniqueRef" label="Technique Ref">
                <Input placeholder="T1190" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="criteriaText" label="Criteria (JSON)">
            <Input.TextArea rows={6} />
          </Form.Item>

          <Form.Item name="nodeConfigText" label="Node Config (JSON)">
            <Input.TextArea rows={6} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Export MVE VelocityDetection"
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        onOk={handleExportAction}
        okText={exportMode === 'SAVE' ? 'Download' : exportMode === 'PUSH_GIT' ? 'Push' : 'Append'}
        okButtonProps={{ loading: exportingYaml }}
        width={760}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Radio.Group
            value={exportMode}
            onChange={(event) => setExportMode(event.target.value as ExportMode)}
            options={[
              { label: 'Save to PC', value: 'SAVE' },
              { label: 'Push to Git', value: 'PUSH_GIT' },
              { label: 'Append to Workbench', value: 'APPEND_WORKBENCH' },
            ]}
            optionType="button"
            buttonStyle="solid"
          />

          <Form layout="vertical" form={exportForm}>
            {exportMode === 'PUSH_GIT' && (
              <>
                <Form.Item
                  name="repositoryId"
                  label="Configured Repository"
                  rules={[{ required: true, message: 'Select a repository' }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={repositories.map((repo: any) => ({
                      value: repo.id,
                      label: `${repo.name} (${repo.provider || 'N/A'})`,
                    }))}
                    placeholder="Select configured Git repository"
                  />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={8}>
                    <Form.Item
                      name="branch"
                      label="Branch"
                      rules={[{ required: true, message: 'Branch required' }]}
                      initialValue="main"
                    >
                      <Input placeholder="main" />
                    </Form.Item>
                  </Col>
                  <Col span={16}>
                    <Form.Item name="filePath" label="File Path (optional)">
                      <Input placeholder="Objects/Velocity Detections/MVE-CHAIN-0001.yaml" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="commitMessage" label="Commit Message (optional)">
                  <Input placeholder="Publish MVE VelocityDetection" />
                </Form.Item>
              </>
            )}

            {exportMode === 'APPEND_WORKBENCH' && (
              <Form.Item
                name="targetGraphId"
                label="Target Workbench (DEPLOYED + authored by you)"
                rules={[{ required: true, message: 'Select target workbench' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={appendTargets.map((target: any) => ({
                    value: target.id,
                    label: `${target.title} (${target.status})`,
                  }))}
                  placeholder="Select Workbench"
                />
              </Form.Item>
            )}
          </Form>

          {exportMode === 'SAVE' && (
            <Alert
              type="info"
              showIcon
              message="Save to PC"
              description="Generates OpenTide YAML and downloads it directly to your machine."
            />
          )}
          {exportMode === 'PUSH_GIT' && (
            <Alert
              type="info"
              showIcon
              message="Push to Git"
              description="Pushes generated YAML to the selected configured repository."
            />
          )}
          {exportMode === 'APPEND_WORKBENCH' && (
            <Alert
              type="info"
              showIcon
              message="Append to Workbench"
              description="Appends this velocity chain to the target Workbench OpenTide YAML under mve_velocity_detections."
            />
          )}
        </Space>
      </Modal>

      <Modal
        title="OpenTide VelocityDetection YAML"
        open={yamlOpen}
        onCancel={() => setYamlOpen(false)}
        width={900}
        footer={[
          <Button key="copy" onClick={() => navigator.clipboard.writeText(yamlPreview || '')}>
            Copy YAML
          </Button>,
          <Button key="close" type="primary" onClick={() => setYamlOpen(false)}>
            Close
          </Button>,
        ]}
      >
        <Input.TextArea value={yamlPreview} rows={24} readOnly style={{ fontFamily: 'monospace' }} />
      </Modal>

      <DetectionRuleEditorModal
        visible={editorModalVisible}
        onClose={() => setEditorModalVisible(false)}
        playbookId={targetWorkbenchId || ''}
        initialRule={generatedRule}
        initialFormat={(generatedFormat as any) || 'KQL'}
        initialMode={'ai' as DetectionMode}
        onSave={async (rule: string, format: string) => {
          setGeneratedRule(rule);
          setGeneratedFormat(format);
        }}
        onSaveToLibrary={async (rule: string, format: string, options?: any) => {
          const targetGraphId = targetWorkbenchId;
          if (!targetGraphId) {
            return { success: false, message: 'Target Workbench ID is required.', errors: ['Missing target workbench id'] };
          }
          const payload = await saveRuleAndHandoff(targetGraphId, rule, format, {
            autoCommit: options?.autoCommit,
            commitMessage: options?.commitMessage,
          });
          return {
            success: payload?.success ?? false,
            message: payload?.message,
            commitSha: payload?.commitSha,
            errors: payload?.errors ?? [],
          };
        }}
      />
    </Space>
  );
};

export default MveWorkbenchTab;
