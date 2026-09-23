import React, { useEffect, useCallback, useState, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { gql } from '@apollo/client';
import { useQuery, useMutation, useLazyQuery } from '@apollo/client/react';
import { 
  useNodesState, 
  useEdgesState,
  Node,
  Edge,
} from '@xyflow/react';
import { message, Tag, Alert } from 'antd';

import { DetectionStrategy } from '../components/playbook/DetectionStrategy';
import { CapabilityAbstractionPanel } from '../components/playbook/CapabilityAbstractionPanel';
import { DeepDive } from '../components/playbook/DeepDive';
import { SoarConfiguration } from '../components/playbook/SoarConfiguration';
import { TestingGuidance } from '../components/playbook/TestingGuidance';
import { ReviewWorkflow } from '../components/playbook/ReviewWorkflow';
import { ActivityOverview } from '../components/playbook/ActivityOverview';
import { PlaybookSidebar } from '../components/playbook/PlaybookSidebar';
import { WorkbenchSectionControls } from '../components/playbook/WorkbenchSectionControls';
import { Button } from '../components/ui/Button';
import { PixelIcon } from '../components/ui/PixelIcon';
import { useRef } from 'react';
import CustomAbstractionNode from '../components/CustomAbstractionNode';
import CapabilityAbstractionMapNode from '../components/CapabilityAbstractionMapNode';
import TechniqueRootNode from '../components/TechniqueRootNode';
import CoverageGapNode from '../components/CoverageGapNode';
import DetectionRuleEditorModal, { DetectionMode } from '../components/DetectionRuleEditorModal';
import DetectionRuleEditor from '../components/DetectionRuleEditor';
import ExportImportModal from '../components/playbook/ExportImportModal';
import { MaieuticEngineModal } from '../components/maieutic/MaieuticEngineModal';
import { ThreatReportPopulateModal } from '../components/playbook/ThreatReportPopulateModal';
import { MaieuticOutput, MaieuticImportSelections } from '../types/maieutic';
import { applyMaieuticToWorkbench } from '../utils/maieuticMapping';
import { OpenTideRule } from '../types/opentide';
import { compileMetadataFromWorkbench, getConfiguredPlatforms } from '../utils/openTideCompiler';
import { isDirty, normalize } from '../utils/ruleDiff';
import OpenTideMetadataPreview from '../components/OpenTideMetadataPreview';
import { OpenTidePreviewModal } from '../components/OpenTidePreviewModal';
import { DETECTION_FORMAT_REGISTRY } from '../components/detectionFormatRegistry';
import { useTheme } from '../context/ThemeContext';
import {
  LAYER_ORDER,
  LAYER_Y,
  computeLayerLayout,
  positionForEntry,
} from '../utils/capabilityAbstractionUtils';
import {
  WORKBENCH_PRESETS,
  WorkbenchSectionKey,
  WorkbenchSectionVisibilityMap,
  normalizeVisibilityLayer,
  resolveWorkbenchSections,
} from '../utils/workbenchVisibility';
import CapabilityAbstractionMapModal from '../components/CapabilityAbstractionMapModal';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { ReferenceContextItem, ReferenceContextPanel } from '../components/playbook/ReferenceContextPanel';
import { getNewWorkbenchDefaultTitle, resolveWorkbenchMapTitle } from '../utils/workbenchNaming';

// Robustness Badge Component
const RobustnessBadge: React.FC<{ level: number }> = ({ level }) => {
  const config: Record<number, { color: string; label: string }> = {
    1: { color: 'bg-red-500', label: 'Ephemeral (Hash/IP)' },
    2: { color: 'bg-orange-500', label: 'Attacker-Controlled' },
    3: { color: 'bg-yellow-500', label: 'System-Constrained' },
    4: { color: 'bg-blue-500', label: 'Low-Variance' },
    5: { color: 'bg-green-500', label: 'Invariant (TTP)' },
  };
  
  const { color, label } = config[level] || config[1];
  
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-white text-sm ${color}`}>
      Level {level}: {label}
    </span>
  );
};

// --- V2 GRAPH QUERY (From Day 180) ---
const GET_PLAYBOOK_GRAPH_QUERY = gql`
  query GetPlaybookGraph($id: UUID!) {
    playbookGraph(id: $id) {
      id
      title
      status
      l1PortalUrl
      tags
      isShared
      allowRemotePull
      notes
      
      # --- Strategy & Context ---
      mitreTechnique { id techniqueId name }
      selectedCapabilityAbstractions {
        id
        abstractionLayer
        componentArtifact
        adversaryPurpose
        commonEvasions
        expectedObservables
        applicableTelemetry
        detectionValue
        robustnessLevel
        column
        sourceKind
        reviewStatus
        version
        organizationName
        isEditable
        isSharedBaseline
        technique {
          techniqueId
          name
        }
      }
      detectionFocusLayer
      selectedStrategy
      detectionRule
      goal
      technicalContext
      blindSpots
      triageGuidance
      falsePositives
      responsePlaybook
      targetFilePath
      testScenario
      testExpectedOutput

      # --- Telemetry Tagging (Milestone 1) ---
      telemetryRequirements
      telemetryRequirementsGeneratedAt
      telemetryTaggingMissingFields

      # --- Metadata & Valuation ---
      customId
      version
      minorVersion
      author { id username }
      robustnessLevel
      dataSourceRobustness
      dataSourceMaturity
      conversationHistory
      createdAt
      updatedAt

      # --- SOAR Configuration ---
      alertTrigger
      defaultSeverity
      enrichmentSteps
      containmentSteps
      notificationSteps
      downstreamCorrelationRequirements

      # --- OpenTide ---
      opentideYaml
      configuredPlatforms

      # --- OpenTide v2.1 ---
      tlpClassification
      publicReferences
      internalReferences
      threatActors
      threatSurface

      activities {
        id
        user { id username }
        action
        details
        timestamp
      }

      activeReview {
        id
        status
        createdAt
        comments {
          id
          text
          createdAt
            user { id username }
        }
      }

      nodes {
        id
        layerName
        positionX
        positionY
        uiMetadata
        color
        mitreAttackMappings { id techniqueId name }
      }
      edges {
        id
        source
        target
      }
    }
    me {
      id
      username
      role
      workbenchVisibilityDefaults
    }
    myOrganization {
      id
      workbenchVisibilityPolicy
    }
    workbenchVisibilitySystemPolicy
  }
`;

// Owner-only: Update Graph Status (restricted transitions enforced server-side)
const UPDATE_OWN_GRAPH_STATUS_MUTATION = gql`
  mutation UpdateOwnGraphStatus($id: UUID!, $status: String!) {
    updateOwnPlaybookGraphStatus(id: $id, status: $status) {
      playbookGraph { id status }
    }
  }
`;

// Owner-only: Update Graph Title (rename)
const UPDATE_GRAPH_TITLE_MUTATION = gql`
  mutation UpdateGraphTitle($id: UUID!, $title: String!) {
    updatePlaybookGraphTitle(id: $id, title: $title) {
      playbookGraph { id title }
    }
  }
`;

const UPDATE_PLAYBOOK_DETAILS_MUTATION = gql`
  mutation UpdatePlaybookDetails(
    $graphId: UUID!, 
    $mitreTechniqueId: String,
    $selectedStrategy: JSONString,
    $detectionRule: String,
    $goal: String,
    $technicalContext: String,
    $blindSpots: String,
    $triageGuidance: String,
    $falsePositives: String,
    $responsePlaybook: String,
    $targetFilePath: String,
    $notes: String,
    $robustnessLevel: Int,
    $dataSourceRobustness: String,
    $dataSourceMaturity: String,
    $conversationHistory: JSONString,
    $selectedCapabilityAbstractionIds: [UUID!],
    $detectionFocusLayer: String,
    $alertTrigger: String,
    $defaultSeverity: String,
    $enrichmentSteps: JSONString,
    $containmentSteps: JSONString,
    $notificationSteps: JSONString
    $downstreamCorrelationRequirements: JSONString
    $testScenario: String
    $testExpectedOutput: String
    $tlpClassification: String
    $publicReferences: JSONString
    $internalReferences: JSONString
    $threatActors: JSONString
    $threatSurface: JSONString
  ) {
    updatePlaybookDetails(
      graphId: $graphId,
      mitreTechniqueId: $mitreTechniqueId,
      selectedStrategy: $selectedStrategy,
      detectionRule: $detectionRule,
      goal: $goal,
      technicalContext: $technicalContext,
      blindSpots: $blindSpots,
      triageGuidance: $triageGuidance,
      falsePositives: $falsePositives,
      responsePlaybook: $responsePlaybook,
      targetFilePath: $targetFilePath,
      notes: $notes,
      robustnessLevel: $robustnessLevel,
      dataSourceRobustness: $dataSourceRobustness,
      dataSourceMaturity: $dataSourceMaturity,
      conversationHistory: $conversationHistory,
      selectedCapabilityAbstractionIds: $selectedCapabilityAbstractionIds,
      detectionFocusLayer: $detectionFocusLayer,
      alertTrigger: $alertTrigger,
      defaultSeverity: $defaultSeverity,
      enrichmentSteps: $enrichmentSteps,
      containmentSteps: $containmentSteps,
      notificationSteps: $notificationSteps,
      downstreamCorrelationRequirements: $downstreamCorrelationRequirements,
      testScenario: $testScenario,
      testExpectedOutput: $testExpectedOutput,
      tlpClassification: $tlpClassification,
      publicReferences: $publicReferences,
      internalReferences: $internalReferences,
      threatActors: $threatActors,
      threatSurface: $threatSurface
    ) {
      graph {
        id
        mitreTechnique { id techniqueId name }
        selectedStrategy
        detectionRule
        goal
        technicalContext
        blindSpots
        triageGuidance
        falsePositives
        responsePlaybook
        targetFilePath
        notes
        customId
        version
        minorVersion
        robustnessLevel
        dataSourceRobustness
        dataSourceMaturity
        conversationHistory
        selectedCapabilityAbstractions {
          id
          abstractionLayer
          componentArtifact
          adversaryPurpose
          commonEvasions
          expectedObservables
          applicableTelemetry
          detectionValue
          robustnessLevel
          column
          sourceKind
          reviewStatus
          version
          organizationName
          isEditable
          isSharedBaseline
          technique {
            techniqueId
            name
          }
        }
        detectionFocusLayer
        alertTrigger
        defaultSeverity
        enrichmentSteps
        containmentSteps
        notificationSteps
        downstreamCorrelationRequirements
        testScenario
        testExpectedOutput
        tlpClassification
        publicReferences
        internalReferences
        threatActors
        threatSurface
      }
    }
  }
`;

const UPDATE_PLAYBOOK_TAGS_MUTATION = gql`
  mutation UpdatePlaybookTags($graphId: UUID!, $tags: [String]!) {
    updatePlaybookDetails(graphId: $graphId, tags: $tags) {
      graph { id tags }
    }
  }
`;

const DERIVE_TELEMETRY_REQUIREMENTS_MUTATION = gql`
  mutation DeriveTelemetryRequirements($id: UUID!) {
    deriveTelemetryRequirements(id: $id) {
      ok
      missingFields
      telemetryRequirements
      playbookGraph {
        id
        telemetryRequirements
        telemetryRequirementsGeneratedAt
        telemetryTaggingMissingFields
      }
    }
  }
`;

const UPDATE_TELEMETRY_REQUIREMENTS_MUTATION = gql`
  mutation UpdateTelemetryRequirements($id: UUID!, $telemetryRequirements: JSONString!) {
    updateTelemetryRequirements(id: $id, telemetryRequirements: $telemetryRequirements) {
      playbookGraph {
        id
        telemetryRequirements
      }
    }
  }
`;

const UPDATE_WORKBENCH_VISIBILITY_DEFAULTS_MUTATION = gql`
  mutation UpdateWorkbenchVisibilityDefaults($workbenchVisibilityDefaults: JSONString, $reset: Boolean) {
    updateWorkbenchVisibilityDefaults(workbenchVisibilityDefaults: $workbenchVisibilityDefaults, reset: $reset) {
      user {
        id
        workbenchVisibilityDefaults
      }
    }
  }
`;

const START_GENERATE_RULE_TASK_MUTATION = gql`
  mutation StartGenerateRuleTask($playbookId: UUID!, $outputFormat: String) {
    startGenerateRuleTask(playbookId: $playbookId, outputFormat: $outputFormat) {
      taskId
      success
      message
    }
  }
`;

const RECOMMEND_REUSABLE_RULE_FROM_RAG_MUTATION = gql`
  mutation RecommendReusableRuleFromRag($playbookId: UUID!, $outputFormat: String) {
    recommendReusableRuleFromRag(playbookId: $playbookId, outputFormat: $outputFormat) {
      success
      message
      providerUsed
      workbenchSummary
      decision
      rationale
      candidateSource
      adaptedRule
      referenceCount
    }
  }
`;

const AI_GENERATION_TASK_STATUS_QUERY = gql`
  query AiGenerationTaskStatus($taskId: UUID!) {
    aiGenerationTaskStatus(taskId: $taskId) {
      id
      taskType
      status
      resultData
      errorMessage
      createdAt
      startedAt
      completedAt
    }
  }
`;

const UPDATE_NODE_MUTATION = gql`
  mutation UpdateNodePos($nodeId: UUID!, $x: Float!, $y: Float!) {
    updatePlaybookNodePosition(nodeId: $nodeId, positionX: $x, positionY: $y) {
      node { id positionX positionY }
    }
  }
`;

const CREATE_NODE_MUTATION = gql`
  mutation CreateNode($graphId: UUID!, $name: String!, $x: Float!, $y: Float!) {
    createPlaybookNode(graphId: $graphId, layerName: $name, positionX: $x, positionY: $y) {
      node { id layerName positionX positionY }
    }
  }
`;

// Share/Unshare Workbench within Entity
const SHARE_PLAYBOOK_GRAPH_MUTATION = gql`
  mutation SharePlaybookGraph($graphId: UUID!, $share: Boolean!) {
    sharePlaybookGraph(graphId: $graphId, share: $share) {
      success
      message
      graph { id isShared }
    }
  }
`;

const SET_PLAYBOOK_GRAPH_REMOTE_PULL_MUTATION = gql`
  mutation SetPlaybookGraphRemotePull($graphId: UUID!, $enabled: Boolean!) {
    setPlaybookGraphRemotePull(graphId: $graphId, enabled: $enabled) {
      success
      message
      graph { id allowRemotePull }
    }
  }
`;

const CLONE_PLAYBOOK_GRAPH_MUTATION = gql`
  mutation ClonePlaybookGraph($graphId: UUID!) {
    clonePlaybookGraph(graphId: $graphId) {
      ok
      playbookGraph { id title }
    }
  }
`;

const CREATE_PLAYBOOK_GRAPH_MUTATION = gql`
  mutation CreatePlaybookGraph($title: String!) {
    createPlaybookGraph(title: $title) {
      graph { id title status updatedAt }
    }
  }
`;

interface SharePlaybookGraphResponse {
  sharePlaybookGraph: {
    success: boolean;
    message: string;
    graph: { id: string; isShared: boolean } | null;
  };
}

interface SetPlaybookGraphRemotePullResponse {
  setPlaybookGraphRemotePull: {
    success: boolean;
    message: string;
    graph: { id: string; allowRemotePull: boolean } | null;
  };
}

// Save Detection Rule to Library
const SAVE_RULE_MUTATION = gql`
  mutation SaveRule($playbookId: UUID!, $rawYaml: String!, $format: String, $autoCommit: Boolean, $commitMessage: String) {
    saveDetectionRule(playbookId: $playbookId, rawYaml: $rawYaml, format: $format, autoCommit: $autoCommit, commitMessage: $commitMessage) {
      success
      message
      commitSha
      errors
    }
  }
`;

const SAVE_ALL_RULES_MUTATION = gql`
  mutation SaveAllRules($playbookId: UUID!, $rules: [SaveRuleInput!]!) {
    saveAllDetectionRules(playbookId: $playbookId, rules: $rules) {
      success
      results {
        format
        status
        filename
        message
      }
    }
  }
`;

interface SaveRuleResponse {
  saveDetectionRule: {
    success: boolean;
    message?: string;
    commitSha?: string;
    errors?: string[];
  };
}

interface SaveRuleVars {
  playbookId: string;
  rawYaml: string;
  format?: string;
  autoCommit?: boolean;
  commitMessage?: string;
}

interface SaveAllRuleResult {
  format: string;
  status: string;
  filename?: string | null;
  message?: string | null;
}

interface SaveAllRulesResponse {
  saveAllDetectionRules: {
    success: boolean;
    results: SaveAllRuleResult[];
  };
}

interface SaveAllRulesVars {
  playbookId: string;
  rules: Array<{
    format: string;
    content: string;
  }>;
}

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



interface CloneGraphResponse {
  clonePlaybookGraph?: {
    ok: boolean;
    playbookGraph?: { id: string } | null;
  } | null;
}

interface CreateGraphResponse {
  createPlaybookGraph: {
    graph: { id: string; title?: string; status?: string; updatedAt?: string };
  };
}

const CREATE_EDGE_MUTATION = gql`
  mutation CreateEdge($graphId: UUID!, $sourceId: UUID!, $targetId: UUID!) {
    createPlaybookEdge(graphId: $graphId, sourceId: $sourceId, targetId: $targetId) {
      edge { id source target }
    }
  }
`;

const DELETE_NODE_MUTATION = gql`
  mutation DeleteNode($nodeId: UUID!) {
    deletePlaybookNode(nodeId: $nodeId) {
      ok
    }
  }
`;

const DELETE_EDGE_MUTATION = gql`
  mutation DeleteEdge($edgeId: UUID!) {
    deletePlaybookEdge(edgeId: $edgeId) {
      ok
    }
  }
`;

const UPDATE_NODE_LAYER_NAME_MUTATION = gql`
  mutation UpdateNodeLayerName($nodeId: UUID!, $layerName: String!) {
    updatePlaybookNodeLayerName(nodeId: $nodeId, layerName: $layerName) {
      node { id layerName }
    }
  }
`;

const UPDATE_NODE_ATTACK_MAPPINGS_MUTATION = gql`
  mutation UpdateNodeAttackMappings($nodeId: UUID!, $mitreAttackIds: [ID]!) {
    updateNodeAttackMappings(nodeId: $nodeId, mitreAttackIds: $mitreAttackIds) {
      node { id }
    }
  }
`;

const UPDATE_PLAYBOOK_NODE_COLOR_MUTATION = gql`
  mutation UpdatePlaybookNodeColor($nodeId: UUID!, $color: String!) {
    updatePlaybookNodeColor(nodeId: $nodeId, color: $color) {
      node {
        id
        color
      }
    }
  }
`;

interface PlaybookGraphData {
  playbookGraph: {
    id: string;
    title: string;
    status: string;
    l1PortalUrl?: string | null;
    tags: string[];
    isShared: boolean;
    allowRemotePull: boolean;
    
    mitreTechnique: { id: string, techniqueId: string, name: string } | null;
    selectedCapabilityAbstractions: Array<{
      id: string;
      abstractionLayer: string;
      componentArtifact: string;
      adversaryPurpose?: string;
      commonEvasions?: string;
      expectedObservables?: string;
      applicableTelemetry?: string;
      detectionValue?: string;
      robustnessLevel?: number;
      sourceKind?: string;
      reviewStatus?: string;
      version?: number;
      organizationName?: string;
      isEditable?: boolean;
      isSharedBaseline?: boolean;
      technique?: {
        techniqueId: string;
        name: string;
      };
    }>;
    detectionFocusLayer: string;
    selectedStrategy: string; // JSON string
    detectionRule: string;
    goal: string;
    technicalContext: string;
    blindSpots: string;
    triageGuidance: string;
    falsePositives: string;
    responsePlaybook: string;
    targetFilePath: string;
    notes: string | null;
    testScenario: string;
    testExpectedOutput: string;

    customId: string;
    version: number;
    minorVersion: number;
    author: { id: string; username: string };
    robustnessLevel: number;
    dataSourceRobustness: string;
    dataSourceMaturity: string;
    conversationHistory: Array<{ role: 'user' | 'ai'; content: string }> | string | null;
    createdAt: string;
    updatedAt: string;

    alertTrigger: string;
    defaultSeverity: string;
    enrichmentSteps: string; // JSON string from backend
    containmentSteps: string; // JSON string from backend
    notificationSteps: string; // JSON string from backend
    downstreamCorrelationRequirements: string | Record<string, unknown> | null;

    opentideYaml: string | null; // JSON string from backend
    configuredPlatforms: string[];

    // OpenTide v2.1 fields
    tlpClassification: string;
    publicReferences: string | null; // JSON string from backend
    internalReferences: string | null; // JSON string from backend
    threatActors: string | null; // JSON string from backend
    threatSurface: string | null; // JSON string from backend

    activities: Array<{
      id: string;
      user: { id: string; username: string } | null;
        action: string;
        details: string;
        timestamp: string;
    }>;

    activeReview: {
      id: string;
      status: string;
      createdAt: string;
      comments: Array<{
        id: string;
        text: string;
        createdAt: string;
        user: { id: string; username: string };
      }>;
    } | null;

    nodes: Array<{
      id: string;
      layerName: string;
      positionX: number;
      positionY: number;
      uiMetadata: string;
      color: string;
      mitreAttackMappings?: Array<{ id: string; techniqueId: string; name: string }>;
    }>;
    edges: Array<{
      id: string;
      source: string;
      target: string;
    }>;
  };
  me?: {
    id: string;
    username: string;
    role: string;
    workbenchVisibilityDefaults?: string | Record<string, unknown> | null;
  } | null;
  myOrganization?: {
    id: string;
    workbenchVisibilityPolicy?: string | Record<string, unknown> | null;
  } | null;
  workbenchVisibilitySystemPolicy?: string | Record<string, unknown> | null;
}

interface CreateNodeData {
  createPlaybookNode: {
    node: {
      id: string;
      layerName: string;
      positionX: number;
      positionY: number;
    };
  };
}

interface CreateEdgeData {
  createPlaybookEdge: {
    edge: {
      id: string;
      source: string;
      target: string;
    };
  };
}

interface RagReuseResult {
  success?: boolean;
  message?: string;
  providerUsed?: string;
  workbenchSummary?: string;
  decision?: string;
  rationale?: string;
  candidateSource?: string;
  adaptedRule?: string;
  referenceCount?: number;
}

type WorkbenchRuleFormat = 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL';
const isWorkbenchRuleFormat = (format: string): format is WorkbenchRuleFormat =>
  format === 'KQL' || format === 'EQL' || format === 'WAZUH' || format === 'SPL' || format === 'AQL';
const RAG_REUSE_SUPPORTED_FORMATS = new Set<WorkbenchRuleFormat>(['KQL', 'EQL', 'SPL']);

export const PlaybookWorkbench = () => {
  const SIDEBAR_DEFAULT_WIDTH = 320;
  const SIDEBAR_COLLAPSED_WIDTH = 40;
  const SIDEBAR_MIN_WIDTH = 280;
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  const { playbookId } = useParams<{ playbookId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isNewPlaybook = playbookId === 'new';

  // React Flow State
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [inlineEditId, setInlineEditId] = useState<string | null>(null);

  const { data, loading, error, refetch } = useQuery<PlaybookGraphData>(GET_PLAYBOOK_GRAPH_QUERY, {
    variables: { id: playbookId },
    skip: isNewPlaybook, // Don't query if it's "new"
    fetchPolicy: 'network-only',
    nextFetchPolicy: 'cache-first',
  });

  const [createGraph] = useMutation<CreateGraphResponse>(CREATE_PLAYBOOK_GRAPH_MUTATION);
  const [updatePlaybookDetails] = useMutation(UPDATE_PLAYBOOK_DETAILS_MUTATION);
  const [updatePlaybookTags] = useMutation(UPDATE_PLAYBOOK_TAGS_MUTATION);
  const [deriveTelemetryRequirements, { loading: derivingTelemetry }] = useMutation(DERIVE_TELEMETRY_REQUIREMENTS_MUTATION);
  const [updateTelemetryRequirements] = useMutation(UPDATE_TELEMETRY_REQUIREMENTS_MUTATION);
  const [updateWorkbenchVisibilityDefaults, { loading: savingWorkbenchDefaults }] = useMutation(
    UPDATE_WORKBENCH_VISIBILITY_DEFAULTS_MUTATION,
  );
  interface StartTaskResult { taskId: string; success: boolean; message: string }
  interface AITaskStatusResult {
    aiGenerationTaskStatus: {
      id: string;
      taskType: string;
      status: string;
      resultData: string | null;
      errorMessage: string | null;
      createdAt: string;
      startedAt: string | null;
      completedAt: string | null;
    };
  }
  const [startGenerateRuleTask, { loading: aiLoading }] = useMutation<
    { startGenerateRuleTask: StartTaskResult },
    { playbookId: string; outputFormat?: string }
  >(START_GENERATE_RULE_TASK_MUTATION);
  const [recommendReusableRuleFromRag, { loading: recommendingReuse }] = useMutation<
    { recommendReusableRuleFromRag: RagReuseResult },
    { playbookId: string; outputFormat?: string }
  >(RECOMMEND_REUSABLE_RULE_FROM_RAG_MUTATION);
  const [fetchAiTaskStatus] = useLazyQuery<AITaskStatusResult>(
    AI_GENERATION_TASK_STATUS_QUERY,
    { fetchPolicy: 'network-only' }
  );
  const [updateNodePos] = useMutation(UPDATE_NODE_MUTATION);
  const [createNode] = useMutation<CreateNodeData>(CREATE_NODE_MUTATION, {
    refetchQueries: [{ query: GET_PLAYBOOK_GRAPH_QUERY, variables: { id: playbookId } }],
  });
  const [saveRule, { loading: saving }] = useMutation<SaveRuleResponse, SaveRuleVars>(SAVE_RULE_MUTATION);
  const [saveAllRules, { loading: savingAll }] = useMutation<SaveAllRulesResponse, SaveAllRulesVars>(SAVE_ALL_RULES_MUTATION);
  const [updateOpenTideYaml] = useMutation(UPDATE_OPENTIDE_YAML_MUTATION);
  const [createEdge] = useMutation<CreateEdgeData>(CREATE_EDGE_MUTATION);
  const [deleteNode] = useMutation(DELETE_NODE_MUTATION);
  const [deleteEdge] = useMutation(DELETE_EDGE_MUTATION);
  const [updateNodeColor] = useMutation(UPDATE_PLAYBOOK_NODE_COLOR_MUTATION);
  const [updateOwnGraphStatus, { loading: updatingStatus }] = useMutation(UPDATE_OWN_GRAPH_STATUS_MUTATION);
  const [updateGraphTitle] = useMutation(UPDATE_GRAPH_TITLE_MUTATION);
  const [updateNodeLayerName] = useMutation(UPDATE_NODE_LAYER_NAME_MUTATION);
  const [updateNodeAttackMappings] = useMutation(UPDATE_NODE_ATTACK_MAPPINGS_MUTATION);
  const [sharePlaybookGraph, { loading: sharingGraph }] = useMutation<SharePlaybookGraphResponse>(SHARE_PLAYBOOK_GRAPH_MUTATION);
  const [setPlaybookGraphRemotePull, { loading: togglingRemotePull }] = useMutation<SetPlaybookGraphRemotePullResponse>(SET_PLAYBOOK_GRAPH_REMOTE_PULL_MUTATION);
  const [clonePlaybookGraph, { loading: cloningGraph }] = useMutation<CloneGraphResponse>(CLONE_PLAYBOOK_GRAPH_MUTATION);

  const [aiTaskId, setAiTaskId] = useState<string | null>(null);
  const aiPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const insightsRef = useRef<HTMLDivElement | null>(null);
  const ragReuseRef = useRef<HTMLDivElement | null>(null);
  const aiBusy = aiLoading || !!aiTaskId;
  const [generationInsights, setGenerationInsights] = useState<{
    quickWinRule?: string;
    robustRule?: string;
    generationSummary?: string;
    correlationIdeas?: string;
    expectedBlindSpots?: string;
    testGuidance?: string;
    referenceContext?: ReferenceContextItem[];
  } | null>(null);
  const [ragReuseResult, setRagReuseResult] = useState<RagReuseResult | null>(null);

  const getReuseDecisionColor = useCallback((decision?: string): 'green' | 'orange' | 'blue' | 'default' => {
    const normalized = String(decision || '').toUpperCase();
    if (normalized === 'REUSE') return 'green';
    if (normalized === 'ADAPT') return 'orange';
    if (normalized === 'CREATE_NEW') return 'blue';
    return 'default';
  }, []);

  const conversationHistory = useMemo(() => {
    const raw = data?.playbookGraph?.conversationHistory;
    if (!raw) return [] as Array<{ role: 'user' | 'ai'; content: string }>;
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
      try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    }
    return [];
  }, [data?.playbookGraph?.conversationHistory]);

  // Navigation hook for redirecting after import

  // --- Local State for Selected Node ---
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  
  // --- Local State for Sidebar Tab ---
  const [sidebarTab, setSidebarTab] = useState<'DETAILS' | 'NOTES'>('DETAILS');
  const [sidebarWidth, setSidebarWidth] = useState<number>(SIDEBAR_DEFAULT_WIDTH);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isSidebarResizing, setIsSidebarResizing] = useState(false);
  const [layoutWidth, setLayoutWidth] = useState(0);
  const workbenchLayoutRef = useRef<HTMLDivElement | null>(null);

  const [isMapModalOpen, setIsMapModalOpen] = useState(false);
  const [isAutoMode, setIsAutoMode] = useState(true);
  const [highlightedEntryId, setHighlightedEntryId] = useState<string | null>(null);
  const [pendingStatus, setPendingStatus] = useState<string>('');

  // Create local state for the rule to ensure instant feedback
  const [localRule, setLocalRule] = useState("");

  // Detection Rule Editor Modal State
  const [editorModalVisible, setEditorModalVisible] = useState(false);
  const [detectionMode, setDetectionMode] = useState<DetectionMode>('logic');

  // OpenTide multi-platform state
  const [openTideRule, setOpenTideRule] = useState<OpenTideRule | undefined>(undefined);

  // Stable playbookData object for DetectionRuleEditorModal – must not be recreated on
  // every render so that the modal's useEffect does not reset editor state while an
  // AI-generation request is in-flight.
  const playbookDataForModal = useMemo(() => {
    if (!data?.playbookGraph) return undefined;
    const g = data.playbookGraph;
    return {
      title: g.title,
      goal: g.goal,
      author: g.author,
      createdAt: g.createdAt,
      updatedAt: g.updatedAt,
      mitreTechnique: g.mitreTechnique,
      technicalContext: g.technicalContext,
      blindSpots: g.blindSpots,
      falsePositives: g.falsePositives,
      detectionFocusLayer: g.detectionFocusLayer,
      selectedCapabilityAbstractions: g.selectedCapabilityAbstractions,
      responsePlaybook: g.responsePlaybook,
      defaultSeverity: g.defaultSeverity,
      alertTrigger: g.alertTrigger,
      robustnessLevel: g.robustnessLevel,
      dataSourceMaturity: g.dataSourceMaturity,
    };
  }, [data?.playbookGraph]);

  // Export/Import Modal State
  const [exportImportModalVisible, setExportImportModalVisible] = useState(false);
  const [exportImportInitialTab, setExportImportInitialTab] = useState<'export' | 'github'>('export');

  // Maieutic Engine Modal State
  const [maieuticModalVisible, setMaieuticModalVisible] = useState(false);
  const [threatReportModalVisible, setThreatReportModalVisible] = useState(false);
  const [pendingMaieuticData, setPendingMaieuticData] = useState<{
    output: MaieuticOutput;
    selections: MaieuticImportSelections;
  } | null>(null);

  const maieuticWorkbenchContext = useMemo(() => {
    const graph = data?.playbookGraph;
    if (!graph) return undefined;
    return {
      techniqueId: graph.mitreTechnique?.techniqueId || '',
      techniqueName: graph.mitreTechnique?.name || '',
      detectionFocusLayer: graph.detectionFocusLayer || '',
      goal: graph.goal || '',
      technicalContext: graph.technicalContext || '',
      selectedCapabilityAbstractions: (graph.selectedCapabilityAbstractions || []).slice(0, 8).map((entry) => ({
        abstractionLayer: entry.abstractionLayer,
        componentArtifact: entry.componentArtifact,
        adversaryPurpose: entry.adversaryPurpose || '',
      })),
    };
  }, [data?.playbookGraph]);

  // OpenTIDE Preview Modal State (Phase 2)
  const [previewModalVisible, setPreviewModalVisible] = useState(false);
  const [localSectionVisibility, setLocalSectionVisibility] = useState<WorkbenchSectionVisibilityMap>({});

  useEffect(() => {
    setLocalSectionVisibility({});
  }, [playbookId]);

  const systemVisibilityLayer = useMemo(
    () => normalizeVisibilityLayer(data?.workbenchVisibilitySystemPolicy),
    [data?.workbenchVisibilitySystemPolicy],
  );
  const organizationVisibilityLayer = useMemo(
    () => normalizeVisibilityLayer(data?.myOrganization?.workbenchVisibilityPolicy),
    [data?.myOrganization?.workbenchVisibilityPolicy],
  );
  const userVisibilityLayer = useMemo(
    () => normalizeVisibilityLayer(data?.me?.workbenchVisibilityDefaults),
    [data?.me?.workbenchVisibilityDefaults],
  );
  const resolvedWorkbenchSections = useMemo(
    () =>
      resolveWorkbenchSections({
        system: systemVisibilityLayer,
        organization: organizationVisibilityLayer,
        userDefaults: userVisibilityLayer,
        localState: localSectionVisibility,
      }),
    [localSectionVisibility, organizationVisibilityLayer, systemVisibilityLayer, userVisibilityLayer],
  );

  const coverageSummary = useMemo(() => {
    const entries = data?.playbookGraph?.selectedCapabilityAbstractions ?? [];
    const layerCount: Record<string, number> = {};
    for (const e of entries) {
      layerCount[e.abstractionLayer] = (layerCount[e.abstractionLayer] ?? 0) + 1;
    }
    const avgRobustness = entries.length
      ? entries.reduce((s, e) => s + (e.robustnessLevel ?? 0), 0) / entries.length
      : 0;
    return { layerCount, avgRobustness, total: entries.length };
  }, [data?.playbookGraph?.selectedCapabilityAbstractions]);

  const layerBands = useMemo(() => {
    const counts: Record<string, number> = {};
    const entries = data?.playbookGraph?.selectedCapabilityAbstractions ?? [];
    for (const entry of entries) {
      counts[entry.abstractionLayer] = (counts[entry.abstractionLayer] ?? 0) + 1;
    }
    return computeLayerLayout(counts);
  }, [data?.playbookGraph?.selectedCapabilityAbstractions]);

  const layerBandMap = useMemo(
    () => Object.fromEntries(layerBands.map((band) => [band.layer, band])),
    [layerBands]
  );

  const derivedNodes = useMemo<Node[]>(() => {
    const selectedAbstractions = data?.playbookGraph?.selectedCapabilityAbstractions ?? [];
    const byLayer: Record<string, typeof selectedAbstractions> = {};
    for (const entry of selectedAbstractions) {
      (byLayer[entry.abstractionLayer] ??= []).push(entry);
    }

    const result: Node[] = [];

    if (selectedAbstractions.length > 0) {
      result.push({
        id: 'technique-root',
        type: 'technique-root',
        position: { x: 400, y: -80 },
        data: {
          label: resolveWorkbenchMapTitle(data?.playbookGraph?.title),
        },
        draggable: false,
      });
    }

    for (const [layer, entries] of Object.entries(byLayer)) {
      entries.forEach((entry, idx) => {
        const band = layerBandMap[layer];
        result.push({
          id: `ca-${entry.id}`,
          type: 'capability-abstraction',
          position: band
            ? positionForEntry(band, idx)
            : { x: 80 + (idx % 4) * 260, y: (LAYER_Y[layer] ?? 300) + Math.floor(idx / 4) * 130 },
          data: {
            entry,
            isFocusLayer: entry.abstractionLayer === data?.playbookGraph?.detectionFocusLayer,
          },
          draggable: false,
        });
      });
    }

    const allLayers = [...LAYER_ORDER];
    const coveredLayers = new Set(selectedAbstractions.map((entry) => entry.abstractionLayer));
    const gapNodes: Node[] = allLayers
      .filter((layer) => !coveredLayers.has(layer))
      .map((layer) => ({
        id: `gap-${layer}`,
        type: 'coverage-gap',
        position: layerBandMap[layer]
          ? positionForEntry(layerBandMap[layer], 0, { xStart: 650 })
          : { x: 650, y: LAYER_Y[layer] ?? 300 },
        data: { layer },
        draggable: false,
        selectable: false,
      }));

    return [...result, ...gapNodes];
  }, [data?.playbookGraph?.selectedCapabilityAbstractions, data?.playbookGraph?.detectionFocusLayer, data?.playbookGraph?.title, layerBandMap]);

  const derivedEdges = useMemo<Edge[]>(() => {
    const selectedAbstractions = data?.playbookGraph?.selectedCapabilityAbstractions ?? [];
    if (selectedAbstractions.length === 0) {
      return [];
    }

    return selectedAbstractions.map((entry) => ({
      id: `edge-root-${entry.id}`,
      source: 'technique-root',
      target: `ca-${entry.id}`,
      animated: entry.abstractionLayer === data?.playbookGraph?.detectionFocusLayer,
      style: {
        stroke: entry.abstractionLayer === data?.playbookGraph?.detectionFocusLayer ? '#2563eb' : '#9ca3af',
      },
    }));
  }, [data?.playbookGraph?.selectedCapabilityAbstractions, data?.playbookGraph?.detectionFocusLayer]);

  const nodeTypes = useMemo(
    () => ({
      'custom-abstraction': CustomAbstractionNode,
      'capability-abstraction': CapabilityAbstractionMapNode,
      'technique-root': TechniqueRootNode,
      'coverage-gap': CoverageGapNode,
    }),
    []
  );

  const getClampedSidebarWidth = useCallback((requestedWidth: number, containerWidth: number) => {
    if (containerWidth <= 0) {
      return requestedWidth;
    }

    const maxWidth = Math.max(Math.floor(containerWidth / 3), SIDEBAR_COLLAPSED_WIDTH);
    const minWidth = Math.min(SIDEBAR_MIN_WIDTH, maxWidth);
    return Math.min(Math.max(requestedWidth, minWidth), maxWidth);
  }, [SIDEBAR_COLLAPSED_WIDTH, SIDEBAR_MIN_WIDTH]);

  const effectiveSidebarWidth = isSidebarCollapsed
    ? SIDEBAR_COLLAPSED_WIDTH
    : getClampedSidebarWidth(sidebarWidth, layoutWidth);

  const handleSidebarResizeStart = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsSidebarResizing(true);
  }, []);

  useEffect(() => {
    const layoutElement = workbenchLayoutRef.current;
    if (!layoutElement) return;

    const updateLayoutWidth = () => {
      setLayoutWidth(layoutElement.getBoundingClientRect().width);
    };

    updateLayoutWidth();

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setLayoutWidth(entry.contentRect.width);
      }
    });

    resizeObserver.observe(layoutElement);
    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    if (layoutWidth <= 0 || isSidebarCollapsed) return;
    setSidebarWidth((previousWidth) => getClampedSidebarWidth(previousWidth, layoutWidth));
  }, [getClampedSidebarWidth, isSidebarCollapsed, layoutWidth]);

  useEffect(() => {
    if (!isSidebarResizing) return;

    const handleMouseMove = (event: MouseEvent) => {
      const layoutElement = workbenchLayoutRef.current;
      if (!layoutElement) return;
      const bounds = layoutElement.getBoundingClientRect();
      const nextWidth = bounds.right - event.clientX;
      setSidebarWidth(getClampedSidebarWidth(nextWidth, bounds.width));
    };

    const handleMouseUp = () => setIsSidebarResizing(false);

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [getClampedSidebarWidth, isSidebarResizing]);

  // Sync local state when data loads from server
  useEffect(() => {
      if (data?.playbookGraph?.detectionRule) {
          const detectedFormat = (data.playbookGraph.tags || [])
            .map((tag: string) => tag.toUpperCase())
            .find((tag: string) => isWorkbenchRuleFormat(tag)) || '';
          setLocalRule(data.playbookGraph.detectionRule);
          if (isWorkbenchRuleFormat(detectedFormat)) {
            setAiFormat(detectedFormat);
          }
      }
      // Always compile fresh metadata from current workbench field values
      if (data?.playbookGraph) {
        try {
          const freshMetadata = compileMetadataFromWorkbench(data.playbookGraph);
          if (data.playbookGraph.opentideYaml) {
            // Merge saved platform queries with recompiled metadata
            const parsed: OpenTideRule = typeof data.playbookGraph.opentideYaml === 'string'
              ? JSON.parse(data.playbookGraph.opentideYaml)
              : data.playbookGraph.opentideYaml as unknown as OpenTideRule;
            setOpenTideRule({ ...parsed, metadata: freshMetadata });
          } else {
            // No saved OpenTide YAML yet – initialise with compiled metadata and empty platforms
            setOpenTideRule({ metadata: freshMetadata, platforms: {} });
          }
        } catch {
          // ignore parse errors
        }
      }
  }, [data]);
  
  const stopAiPolling = useCallback(() => {
    if (aiPollIntervalRef.current) {
      clearInterval(aiPollIntervalRef.current);
      aiPollIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!aiTaskId) {
      stopAiPolling();
      return;
    }

    const poll = async () => {
      try {
        const res = await fetchAiTaskStatus({ variables: { taskId: aiTaskId } });
        const task = res.data?.aiGenerationTaskStatus;
        if (!task) return;
        if (task.status === 'COMPLETED' || task.status === 'FAILED') {
          stopAiPolling();
          setAiTaskId(null);
          message.destroy('workbench-ai-generate');

          if (task.status === 'FAILED') {
            message.error(task.errorMessage || 'AI generation failed. Please try again.');
            return;
          }

          const result = task.resultData ? JSON.parse(task.resultData) : null;
          const rule = result?.rule as string | undefined;
          if (!rule) {
            message.error('AI returned no rule. Please try again.');
            return;
          }

          setGenerationInsights({
            quickWinRule: result.quick_win_rule || '',
            robustRule: result.robust_rule || '',
            generationSummary: result.generation_summary || '',
            correlationIdeas: result.correlation_ideas || '',
            expectedBlindSpots: result.expected_blind_spots || '',
            testGuidance: result.test_guidance || '',
            referenceContext: Array.isArray(result.reference_context) ? result.reference_context : [],
          });
          setLocalRule(rule);
          setDetectionMode('ai');
          if (playbookId) {
            await updatePlaybookDetails({
              variables: {
                graphId: playbookId,
                detectionRule: rule,
              },
            });
          }
          message.success(`AI-generated rule loaded (${result.provider_used || 'AI'})`);
        }
      } catch {
        // keep polling on transient failures
      }
    };

    poll();
    aiPollIntervalRef.current = setInterval(poll, 2000);
    return stopAiPolling;
  }, [aiTaskId, fetchAiTaskStatus, playbookId, stopAiPolling, updatePlaybookDetails]);

  useEffect(() => {
    if (generationInsights && insightsRef.current) {
      insightsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [generationInsights]);

  useEffect(() => {
    if (ragReuseResult && ragReuseRef.current) {
      ragReuseRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [ragReuseResult]);

  // Handle new playbook creation
  useEffect(() => {
    if (isNewPlaybook) {
      const techniqueId = searchParams.get('technique');
      
      const createAndSetup = async () => {
        // Use the standard workbench default title
        const defaultTitle = getNewWorkbenchDefaultTitle();
        
        const title = window.prompt('Name your new workbench', defaultTitle);
        if (!title) {
          navigate(-1);
          return;
        }
        
        try {
          const res = await createGraph({ variables: { title } });
          const newId = res.data?.createPlaybookGraph?.graph?.id;
          
          if (newId) {
            // Apply ATT&CK technique from query params when present
            if (techniqueId) {
              await updatePlaybookDetails({
                variables: {
                  graphId: newId,
                  mitreTechniqueId: techniqueId
                }
              });
            }
            
            navigate(`/playbooks/${newId}`, { replace: true });
          }
        } catch (err: any) {
          console.error('Failed to create workbench', err);
          message.error('Failed to create workbench: ' + err.message);
          navigate(-1);
        }
      };
      
      createAndSetup();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNewPlaybook, navigate, createGraph, updatePlaybookDetails, searchParams]);
  
  const handleTechniqueChange = useCallback(async (technique: any) => {
    if (!playbookId) return;

    await updatePlaybookDetails({
      variables: {
        graphId: playbookId,
        mitreTechniqueId: technique?.techniqueId || "",
      }
    });

    // Auto-tag the workbench with the selected ATT&CK technique ID so it
    // shows up alongside manual tags without the analyst re-typing it.
    // Mirrors the existing "tag by format on rule save" pattern below.
    if (technique?.techniqueId) {
      try {
        const currentTags: string[] = (data?.playbookGraph?.tags || []).slice();
        const hasTag = currentTags.some(t => t.toUpperCase() === technique.techniqueId.toUpperCase());
        if (!hasTag) {
          const updated = [...currentTags, technique.techniqueId];
          await updatePlaybookTags({ variables: { graphId: playbookId, tags: updated } });
        }
      } catch (e) {
        console.error('Failed to auto-tag ATT&CK technique:', e);
      }
    }
  }, [playbookId, updatePlaybookDetails, updatePlaybookTags, data]);

  // Telemetry Tagging (Milestone 1): trigger AI derivation. The five-field
  // gate is enforced server-side in the mutation; this handler just surfaces
  // the result (ok / missingFields / telemetryRequirements) to the caller.
  const handleDeriveTelemetry = useCallback(async () => {
    if (!playbookId) return null;
    const result = await deriveTelemetryRequirements({ variables: { id: playbookId } });
    return result?.data?.deriveTelemetryRequirements ?? null;
  }, [playbookId, deriveTelemetryRequirements]);

  // Persist an analyst-edited/curated telemetry requirement list. Always
  // comes back with status forced to "unverified" server-side regardless of
  // what is sent, since no org-environment verification layer exists yet.
  const handleSaveTelemetryRequirements = useCallback(async (entries: any[]) => {
    if (!playbookId) return;
    await updateTelemetryRequirements({
      variables: {
        id: playbookId,
        telemetryRequirements: JSON.stringify(entries),
      },
    });
  }, [playbookId, updateTelemetryRequirements]);

  const handleCapabilitySelectionChange = useCallback(async (ids: string[], focusLayer: string) => {
    if (!playbookId) return;
    await updatePlaybookDetails({
      variables: {
        graphId: playbookId,
        selectedCapabilityAbstractionIds: ids,
        detectionFocusLayer: focusLayer || '',
      },
    });
  }, [playbookId, updatePlaybookDetails]);

  const handleStrategyChange = useCallback(async (strategyData: any) => {
    if (!playbookId) return;
    
    // 1. Instant UI update
    if (strategyData.detectionRule) {
        setLocalRule(strategyData.detectionRule);
    }

    const variables: any = {
      graphId: playbookId,
      detectionRule: strategyData.detectionRule,
      // We store the strategy metadata (robustness, etc) in selectedStrategy JSON
      selectedStrategy: JSON.stringify({
          robustnessLevel: strategyData.robustnessLevel,
          dataSourceRobustness: strategyData.dataSourceRobustness,
      }),
      technicalContext: strategyData.technicalContext,
      targetFilePath: strategyData.targetFilePath,
      robustnessLevel: strategyData.robustnessLevel
    };

    // Include technique ID if passed to preserve it during strategy selection
    if (strategyData.techniqueId) {
      variables.mitreTechniqueId = strategyData.techniqueId;
    }

    await updatePlaybookDetails({ variables });
  }, [playbookId, updatePlaybookDetails]);

  const handleSidebarUpdate = async (field: string, value: any) => {
      if (field === 'tags') {
        await updatePlaybookTags({
          variables: { graphId: playbookId, tags: value },
        });
        return;
      }
      await updatePlaybookDetails({
        variables: {
          graphId: playbookId,
          [field]: value,
        },
      });
  };

  const handleDeepDiveChange = useCallback(async (field: string, value: string) => {
    if (!playbookId) return;
    
    // Map UI fields to GraphQL arguments
    const variables: any = { graphId: playbookId };
    if (field === 'goal') variables.goal = value;
    if (field === 'technicalContext') variables.technicalContext = value;
    if (field === 'blindSpots') variables.blindSpots = value;
    if (field === 'response') variables.responsePlaybook = value;
    if (field === 'falsePositives') variables.falsePositives = value;

    await updatePlaybookDetails({ variables });
  }, [playbookId, updatePlaybookDetails]);

  const handleSoarSave = useCallback(async (soarData: any) => {
      if (!playbookId) return;
      
      try {
        await updatePlaybookDetails({
            variables: {
                graphId: playbookId,
                alertTrigger: soarData.trigger,
                defaultSeverity: soarData.severity,
                enrichmentSteps: JSON.stringify(soarData.enrichment),
                containmentSteps: JSON.stringify(soarData.containment),
                notificationSteps: JSON.stringify(soarData.notifications),
                downstreamCorrelationRequirements: JSON.stringify(soarData.downstreamCorrelationRequirements ?? {}),
                tlpClassification: soarData.tlpClassification || 'AMBER',
                publicReferences: JSON.stringify(soarData.publicReferences || []),
                internalReferences: JSON.stringify(soarData.internalReferences || []),
                threatActors: JSON.stringify(soarData.threatActors || []),
                threatSurface: JSON.stringify(soarData.threatSurface || []),
            }
        });
        await refetch();
        message.success('SOAR configuration saved');
      } catch (err: any) {
        console.error('Failed to save SOAR config:', err);
        message.error(err?.message || 'Failed to save SOAR configuration');
      }
  }, [playbookId, updatePlaybookDetails, refetch]);

  // Handle edge connections
  const onConnect = useCallback((connection: any) => {
    const newEdge = {
      id: `temp-${Date.now()}`,
      source: connection.source,
      target: connection.target,
      animated: true
    };

    // Optimistic UI update
    setEdges((eds) => [...eds, newEdge]);

    // Save to backend
    createEdge({
      variables: {
        graphId: playbookId,
        sourceId: connection.source,
        targetId: connection.target
      },
      update: (cache, { data }) => {
        if (data?.createPlaybookEdge?.edge) {
          // Replace temp edge with real edge
          setEdges((eds) => eds.map((e) => 
            e.id === newEdge.id 
              ? { ...e, id: data.createPlaybookEdge.edge.id } 
              : e
          ));
        }
      }
    }).catch((err) => {
      console.error('Failed to create edge:', err);
      // Revert optimistic update
      setEdges((eds) => eds.filter((e) => e.id !== newEdge.id));
    });
  }, [playbookId, createEdge, setEdges]);

  // Handle node deletion
  const onNodesDelete = useCallback((nodesToDelete: Node[]) => {
    nodesToDelete.forEach((node) => {
      deleteNode({
        variables: { nodeId: node.id },
        update: () => {
          // Remove node and connected edges
          setNodes((nds) => nds.filter((n) => n.id !== node.id));
          setEdges((eds) => eds.filter((e) => e.source !== node.id && e.target !== node.id));
        }
      }).catch((err) => {
        console.error('Failed to delete node:', err);
        alert('Failed to delete node');
      });
    });
  }, [deleteNode, setNodes, setEdges]);

  // Handle edge deletion
  const onEdgesDelete = useCallback((edgesToDelete: Edge[]) => {
    edgesToDelete.forEach((edge) => {
      deleteEdge({
        variables: { edgeId: edge.id },
        update: () => {
          setEdges((eds) => eds.filter((e) => e.id !== edge.id));
        }
      }).catch((err) => {
        console.error('Failed to delete edge:', err);
        alert('Failed to delete edge');
      });
    });
  }, [deleteEdge, setEdges]);

  // 1. Handle "Add Node"
  const handleAddNode = async () => {
    const label = prompt("Enter Node Name (e.g., 'Tool: Mimikatz'):");
    if (!label) return;

    // Default position: center of the current view or random
    const newNode = {
      graphId: playbookId,
      name: label,
      x: Math.random() * 400,
      y: Math.random() * 200
    };

    try {
      const { data } = await createNode({ variables: newNode });
      if (data) {
        const n = data.createPlaybookNode.node;

        // Optimistically add to React Flow state
        setNodes((nds) => nds.concat({
          id: n.id,
          position: { x: n.positionX, y: n.positionY },
          data: { 
            label: n.layerName,
            uiMetadata: '',
            isEditing: false,
            onRename: (val: string) => commitInlineRename(n.id, val)
          },
          style: {},
          type: 'custom-abstraction'
        }));
      }
    } catch (e: any) {
      alert("Failed to create node: " + e.message);
    }
  };

  // 2. Handle Drag Stop (Save Position)
  const onNodeDragStop = useCallback(async (event: any, node: any) => {
    // Optimistically ensure local state aligns with dragged position
    setNodes((nds) => nds.map((n) => (n.id === node.id ? { ...n, position: { x: node.position.x, y: node.position.y } } : n)));
    try {
      await updateNodePos({
        variables: {
          nodeId: node.id,
          x: node.position.x,
          y: node.position.y
        }
      });
    } catch (e) {
      console.error('Failed to persist node position', e);
    }
  }, [updateNodePos, setNodes]);

  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    console.log('Clicked node:', node);
    setSelectedNodeId(node.id);
  }, []);

  const handleCapabilityMapNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    if (node.id.startsWith('ca-')) {
      const entryId = node.id.replace('ca-', '');
      setHighlightedEntryId(entryId);
      const el = document.getElementById(`ca-entry-${entryId}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => setHighlightedEntryId(null), 2500);
    }
  }, []);

  const onNodeDoubleClick = useCallback((event: React.MouseEvent, node: Node) => {
    setInlineEditId(node.id);
    setSelectedNodeId(node.id);
  }, []);

  const commitInlineRename = useCallback(async (nodeId: string, nextLabel: string) => {
    const label = (nextLabel || '').trim();
    setInlineEditId(null);
    if (!label) return;
    try {
      // Optimistic UI update for snappier feedback
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, label } } : n)));
      await updateNodeLayerName({ variables: { nodeId, layerName: label } });
    } catch (e: any) {
      alert(e?.message || 'Failed to rename node');
    }
  }, [updateNodeLayerName, setNodes]);

  const handleDeleteSelected = useCallback(() => {
    if (!selectedNodeId) return;
    
    if (window.confirm('Are you sure you want to delete this node?')) {
       deleteNode({
          variables: { nodeId: selectedNodeId },
          update: () => {
            setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
            setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
            setSelectedNodeId(null);
          }
       }).catch((err) => {
          console.error('Failed to delete node:', err);
          alert('Failed to delete node');
       });
    }
  }, [selectedNodeId, deleteNode, setNodes, setEdges]);

  const handleUpdateNodeMappings = useCallback(async (techIds: string[]) => {
    if (!selectedNodeId) return;
    try {
      await updateNodeAttackMappings({ variables: { nodeId: selectedNodeId, mitreAttackIds: techIds } });
      await refetch();
      alert('Node ATT&CK mappings updated');
    } catch (e: any) {
      console.error(e);
      alert(e?.message || 'Failed to update node mappings');
    }
  }, [selectedNodeId, updateNodeAttackMappings, refetch]);

  const handleColorChange = useCallback((color: string) => {
    if (!selectedNodeId) return;

    // 1. Optimistic Update
    setNodes((nds) => nds.map((n) => {
      if (n.id === selectedNodeId) {
        let style = {};
        if (color === 'blue') style = { backgroundColor: '#bfdbfe' };
        if (color === 'green') style = { backgroundColor: '#bbf7d0' };
        if (color === 'yellow') style = { backgroundColor: '#fef08a' };
        if (color === 'red') style = { backgroundColor: '#fecaca' };
        if (color === 'default') style = { backgroundColor: '#ffffff' };

        const templateData = { ...(n.data as any)?.templateData, color };
        return { ...n, style: style, data: { ...n.data, templateData } };
      }
      return n;
    }));

    // 2. Persist to Backend
    updateNodeColor({
      variables: {
        nodeId: selectedNodeId,
        color: color
      }
    }).catch((err) => {
      console.error("Failed to update color:", err);
      alert("Failed to update node color");
    });
  }, [selectedNodeId, updateNodeColor, setNodes]);

  // AI Generate handler
  const [aiFormat, setAiFormat] = useState<WorkbenchRuleFormat>('KQL');
  const [savedLibrarySnapshot, setSavedLibrarySnapshot] = useState<{ format: string; content: string }>({
    format: '',
    content: '',
  });
  const [savedPlatformLibrarySnapshots, setSavedPlatformLibrarySnapshots] = useState<Record<string, string>>({});

  const handleAIGenerate = useCallback(async () => {
    if (!playbookId) return;
    try {
      stopAiPolling();
      setAiTaskId(null);
      setGenerationInsights(null);
      const res = await startGenerateRuleTask({ variables: { playbookId, outputFormat: aiFormat } });
      const result = res.data?.startGenerateRuleTask;
      if (result?.success && result.taskId) {
        message.loading({ content: 'Generating rule with AI…', key: 'workbench-ai-generate', duration: 0 });
        setAiTaskId(result.taskId);
      } else {
        message.error(result?.message || 'Failed to start AI generation task.');
      }
    } catch (e: any) {
      console.error('AI generation failed', e);
      message.error(e.message || 'AI generation failed');
    }
  }, [playbookId, aiFormat, startGenerateRuleTask, stopAiPolling]);

  const ragReuseSupported = RAG_REUSE_SUPPORTED_FORMATS.has(aiFormat);

  const handleRecommendReuse = useCallback(async () => {
    if (!playbookId) return;
    if (!ragReuseSupported) {
      message.info('RAG reuse check currently supports KQL, EQL, or SPL.');
      return;
    }

    stopAiPolling();
    setAiTaskId(null);

    try {
      const res = await recommendReusableRuleFromRag({
        variables: { playbookId, outputFormat: aiFormat },
      });
      const payload = res.data?.recommendReusableRuleFromRag;
      if (!payload) {
        message.error('AI returned no reuse recommendation. Please try again.');
        return;
      }

      setRagReuseResult(payload);
      if (!payload.success) {
        message.error(payload.message || 'RAG reuse assessment failed.');
        return;
      }

      const decision = String(payload.decision || 'CREATE_NEW').toUpperCase();
      if (decision === 'CREATE_NEW') {
        message.info(payload.message || 'No close reusable template found; creating a new rule is recommended.');
      } else {
        message.success(`RAG reuse assessment complete (${decision}).`);
      }
    } catch (e: any) {
      console.error('RAG reuse assessment failed', e);
      message.error(e?.message || 'RAG reuse assessment failed.');
    }
  }, [playbookId, aiFormat, ragReuseSupported, recommendReusableRuleFromRag, stopAiPolling]);

  const handleSaveToLibrary = useCallback(async () => {
    if (!playbookId) return;
    const extractedPlatformRules = openTideRule
      ? DETECTION_FORMAT_REGISTRY
        .map((entry) => ({
          format: entry.format,
          content: entry.getContent(openTideRule).trim(),
        }))
        .filter((item) => item.content.length > 0)
      : [];

    if (extractedPlatformRules.length > 0) {
      const changedPlatformRules = extractedPlatformRules.filter((item) => {
        const previous = savedPlatformLibrarySnapshots[item.format] ?? '';
        return previous.length === 0 || isDirty(item.content, previous);
      });

      if (changedPlatformRules.length === 0) {
        message.info('No changes, nothing to save');
        return;
      }

      try {
        const res = await saveAllRules({
          variables: {
            playbookId,
            rules: changedPlatformRules.map((item) => ({
              format: item.format,
              content: item.content,
            })),
          },
        });
        const results = res.data?.saveAllDetectionRules?.results || [];
        const saved = results.filter((r) => (r.status || '').toLowerCase() === 'saved');
        const failed = results.filter((r) => (r.status || '').toLowerCase() !== 'saved');

        if (saved.length > 0) {
          const byFormat = new Map(changedPlatformRules.map((item) => [item.format, item.content]));
          setSavedPlatformLibrarySnapshots((prev) => {
            const next = { ...prev };
            for (const result of saved) {
              const content = byFormat.get(result.format);
              if (content !== undefined) {
                next[result.format] = normalize(content);
              }
            }
            return next;
          });
        }

        if (failed.length === 0) {
          message.success(`Saved to Rule Hub: ${saved.map((r) => r.format).join(', ')}`);
        } else {
          const reasons = failed
            .map((r) => `${r.format}: ${r.message || 'Unknown reason'}`)
            .join(' | ');
          message.error(`Rule Hub save failed for some formats. ${reasons}`);
        }
      } catch (e: any) {
        console.error(e);
        message.error(e?.message || 'Failed to save platform rules to Rule Hub.');
      }
      return;
    }

    if (
      savedLibrarySnapshot.content &&
      savedLibrarySnapshot.format === aiFormat &&
      !isDirty(localRule, savedLibrarySnapshot.content)
    ) {
      message.info('No changes, nothing to save');
      return;
    }
    try {
      const res = await saveRule({ variables: { playbookId, rawYaml: localRule, format: aiFormat } });
      const ok = res.data?.saveDetectionRule?.success;
      const msg = res.data?.saveDetectionRule?.message;
      const commitSha = res.data?.saveDetectionRule?.commitSha;
      const errors = res.data?.saveDetectionRule?.errors;
      if (ok) {
        setSavedLibrarySnapshot({ format: aiFormat, content: normalize(localRule) });
        const successMsg = commitSha
          ? `Saved to Rule Hub. Commit: ${commitSha}`
          : 'Saved to Rule Hub.';
        message.success(successMsg);
      } else {
        const errorDetail = errors && errors.length > 0 ? errors.join('\n') : (msg || 'Unable to save');
        message.error(`Rule Hub save failed: ${errorDetail}`);
      }
    } catch (e: any) {
      console.error(e);
      message.error(e?.message || 'Failed to save.');
    }
  }, [
    playbookId,
    openTideRule,
    savedPlatformLibrarySnapshots,
    saveAllRules,
    savedLibrarySnapshot,
    aiFormat,
    localRule,
    saveRule,
  ]);

  const sanitizeRule = useCallback((raw: string) => {
    // Remove common code fences/backticks and leading/trailing whitespace
    const withoutFences = raw
      .replace(/^```[a-zA-Z]*\n/m, '')
      .replace(/```\s*$/m, '')
      .replace(/^[`\s]+|[`\s]+$/g, '');
    return withoutFences;
  }, []);

  const handleSanitizeRule = useCallback(async () => {
    const cleaned = sanitizeRule(localRule || '');
    setLocalRule(cleaned);
    await handleStrategyChange({ detectionRule: cleaned });
  }, [localRule, sanitizeRule, handleStrategyChange]);

  // Handler for Detection Rule Editor Modal save
  const handleEditorModalSave = useCallback(async (rule: string, format: string, mode: DetectionMode, dataSourceId?: string, newOpenTideRule?: OpenTideRule) => {
    setLocalRule(rule);
    setDetectionMode(mode);
    
    // Update format in state
    if (isWorkbenchRuleFormat(format)) {
      setAiFormat(format);
    }
    
    // Persist detection rule to backend
    await handleStrategyChange({ detectionRule: rule });

    // Save OpenTide rule if provided
    if (newOpenTideRule && playbookId) {
      setOpenTideRule(newOpenTideRule);
      try {
        const configured = getConfiguredPlatforms(newOpenTideRule);
        await updateOpenTideYaml({
          variables: {
            graphId: playbookId,
            opentideYaml: JSON.stringify(newOpenTideRule),
            configuredPlatforms: configured,
          },
        });
      } catch (e) {
        console.error('Failed to save OpenTide YAML:', e);
      }
    }
    
    // Update tags to reflect format
    try {
      const currentTags: string[] = (data?.playbookGraph?.tags || []).slice();
      const hasTag = currentTags.some(t => t.toUpperCase() === format.toUpperCase());
      if (!hasTag) {
        const updated = [...currentTags, format];
        await updatePlaybookTags({ variables: { graphId: playbookId, tags: updated } });
      }
    } catch {}
  }, [handleStrategyChange, data, playbookId, updatePlaybookTags, updateOpenTideYaml]);

  // Handler for Share/Unshare toggle
  const handleToggleShare = useCallback(async () => {
    if (!playbookId || !data?.playbookGraph) return;
    const currentlyShared = data.playbookGraph.isShared;
    const newShareState = !currentlyShared;
    
    try {
      const result = await sharePlaybookGraph({ 
        variables: { graphId: playbookId, share: newShareState }
      });
      
      if (result.data?.sharePlaybookGraph?.success) {
        alert(result.data.sharePlaybookGraph.message);
        refetch(); // Refresh data
      } else {
        alert(result.data?.sharePlaybookGraph?.message || 'Failed to update sharing');
      }
    } catch (e: any) {
      alert(e.message || 'Failed to update sharing');
    }
  }, [playbookId, data, sharePlaybookGraph, refetch]);

  const handleCloneGraph = useCallback(async () => {
    if (!playbookId) return;
    try {
      const res = await clonePlaybookGraph({ variables: { graphId: playbookId } });
      const newId = res.data?.clonePlaybookGraph?.playbookGraph?.id;
      if (newId) {
        alert('Workbench cloned');
        navigate(`/playbooks/${newId}`);
      } else {
        alert('Failed to clone workbench');
      }
    } catch (e: any) {
      alert(e?.message || 'Failed to clone workbench');
    }
  }, [playbookId, clonePlaybookGraph, navigate]);

  const handleToggleRemotePull = useCallback(async () => {
    if (!playbookId || !data?.playbookGraph) return;
    const nextState = !Boolean(data.playbookGraph.allowRemotePull);
    try {
      const result = await setPlaybookGraphRemotePull({
        variables: { graphId: playbookId, enabled: nextState },
      });
      if (result.data?.setPlaybookGraphRemotePull?.success) {
        alert(result.data.setPlaybookGraphRemotePull.message);
        refetch();
      } else {
        alert(result.data?.setPlaybookGraphRemotePull?.message || 'Failed to update remote pull access');
      }
    } catch (e: any) {
      alert(e?.message || 'Failed to update remote pull access');
    }
  }, [playbookId, data, setPlaybookGraphRemotePull, refetch]);

  // Maieutic Engine handlers
  const handleMaieuticSubmit = useCallback((output: MaieuticOutput, selections: MaieuticImportSelections) => {
    // Stage the data in pending state - don't apply yet
    setPendingMaieuticData({ output, selections });
    message.success('Maieutic output staged for review. Use the review panel to apply changes.');
  }, []);

  const handleApplyMaieuticToWorkbench = useCallback(async () => {
    if (!pendingMaieuticData || !playbookId) return;

    const currentFormState = {
      goal: data?.playbookGraph?.goal || '',
      technicalContext: data?.playbookGraph?.technicalContext || '',
      blindSpots: data?.playbookGraph?.blindSpots || '',
      falsePositives: data?.playbookGraph?.falsePositives || '',
      responsePlaybook: data?.playbookGraph?.responsePlaybook || '',
      detectionRule: data?.playbookGraph?.detectionRule || '',
      triageGuidance: data?.playbookGraph?.triageGuidance || '',
      testScenario: data?.playbookGraph?.testScenario || '',
      testExpectedOutput: data?.playbookGraph?.testExpectedOutput || '',
      alertTrigger: data?.playbookGraph?.alertTrigger || '',
      defaultSeverity: data?.playbookGraph?.defaultSeverity || '',
      enrichmentSteps: data?.playbookGraph?.enrichmentSteps
        ? JSON.parse(data.playbookGraph.enrichmentSteps)
        : [],
      containmentSteps: data?.playbookGraph?.containmentSteps
        ? JSON.parse(data.playbookGraph.containmentSteps)
        : [],
      notificationSteps: data?.playbookGraph?.notificationSteps
        ? JSON.parse(data.playbookGraph.notificationSteps)
        : [],
      downstreamCorrelationRequirements: data?.playbookGraph?.downstreamCorrelationRequirements
        ? (typeof data.playbookGraph.downstreamCorrelationRequirements === 'string'
            ? JSON.parse(data.playbookGraph.downstreamCorrelationRequirements)
            : data.playbookGraph.downstreamCorrelationRequirements)
        : {},
    };

    const updatedFormState = applyMaieuticToWorkbench(
      pendingMaieuticData.output,
      pendingMaieuticData.selections,
      currentFormState
    );

    // Apply updates to backend
    try {
      await updatePlaybookDetails({
        variables: {
          graphId: playbookId,
          goal: updatedFormState.goal,
          technicalContext: updatedFormState.technicalContext,
          blindSpots: updatedFormState.blindSpots,
          falsePositives: updatedFormState.falsePositives,
          responsePlaybook: updatedFormState.responsePlaybook,
          detectionRule: updatedFormState.detectionRule,
          triageGuidance: updatedFormState.triageGuidance,
          testScenario: updatedFormState.testScenario,
          testExpectedOutput: updatedFormState.testExpectedOutput,
          alertTrigger: updatedFormState.alertTrigger,
          defaultSeverity: updatedFormState.defaultSeverity,
          enrichmentSteps: updatedFormState.enrichmentSteps
            ? JSON.stringify(updatedFormState.enrichmentSteps)
            : undefined,
          containmentSteps: updatedFormState.containmentSteps
            ? JSON.stringify(updatedFormState.containmentSteps)
            : undefined,
          notificationSteps: updatedFormState.notificationSteps
            ? JSON.stringify(updatedFormState.notificationSteps)
            : undefined,
          downstreamCorrelationRequirements: updatedFormState.downstreamCorrelationRequirements
            ? JSON.stringify(updatedFormState.downstreamCorrelationRequirements)
            : undefined,
          robustnessLevel: updatedFormState.robustnessLevel,
          dataSourceMaturity: updatedFormState.dataSourceMaturity,
          conversationHistory: JSON.stringify(pendingMaieuticData.output.conversationHistory || []),
        },
      });
      
      // Update local rule state for instant feedback
      if (updatedFormState.detectionRule !== undefined) {
        setLocalRule(updatedFormState.detectionRule);
      }

      await refetch();
      setPendingMaieuticData(null); // Clear pending state
      message.success('Maieutic data successfully applied to workbench');
    } catch (e: any) {
      console.error('Failed to apply Maieutic data:', e);
      message.error(e?.message || 'Failed to apply Maieutic data');
    }
  }, [pendingMaieuticData, playbookId, data, updatePlaybookDetails, refetch]);

  const handleDismissMaieuticData = useCallback(() => {
    setPendingMaieuticData(null);
    message.info('Maieutic data dismissed');
  }, []);

  useEffect(() => {
    if (data?.playbookGraph) {
      // Transform Backend Data -> React Flow Format
      const flowNodes: Node[] = data.playbookGraph.nodes.map((n) => {
        let style = {};
        if (n.color === 'blue') style = { backgroundColor: '#bfdbfe' };
        if (n.color === 'green') style = { backgroundColor: '#bbf7d0' };
        if (n.color === 'yellow') style = { backgroundColor: '#fef08a' };
        if (n.color === 'red') style = { backgroundColor: '#fecaca' };

        return {
          id: n.id,
          position: { x: n.positionX, y: n.positionY },
          data: { 
            label: n.layerName,
            uiMetadata: n.uiMetadata,
            templateData: { color: n.color },
            mitreAttackMappings: n.mitreAttackMappings,
            isEditing: inlineEditId === n.id,
            onRename: (val: string) => commitInlineRename(n.id, val)
          },
          style: style,
          type: 'custom-abstraction',
        };
      });

      const flowEdges: Edge[] = data.playbookGraph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        animated: true, // Make them look nice
      }));

      setNodes(flowNodes);
      setEdges(flowEdges);
    }
  }, [data, setNodes, setEdges, inlineEditId, commitInlineRename]);

  // Keep inline editing responsive without waiting for a refetch
  useEffect(() => {
    setNodes((nds) => nds.map((n) => ({
      ...n,
      data: { ...(n.data as any), isEditing: inlineEditId === n.id }
    })));
  }, [inlineEditId, setNodes]);

  // Show loading while creating new playbook
  if (isNewPlaybook) {
    return <div className="workbench-theme p-10">Creating new workbench...</div>;
  }

  if (loading) return <div className="workbench-theme p-10">Loading Workbench...</div>;
  if (error) return <div className="workbench-theme p-10 text-red-500">Error: {error.message}</div>;
  if (!data?.playbookGraph) return <div className="workbench-theme p-10">Graph not found or access denied.</div>;

  const isAuthor = !!(data.playbookGraph.author?.id && data.me?.id && data.playbookGraph.author.id === data.me.id);
  const allowedOwnerStatuses = ['DEVELOPMENT', 'TESTING', 'TUNING'];

  // prompt-based rename handler removed; using inline EditableTitle

  const handleChangeStatus = async (newStatus: string) => {
    if (!newStatus) return;
    try {
      await updateOwnGraphStatus({ variables: { id: playbookId, status: newStatus } });
      setPendingStatus('');
      await refetch();
    } catch (e: any) {
      alert(e?.message || 'Failed to change status');
    }
  };

  const handleToggleSectionVisibility = (section: WorkbenchSectionKey, visible: boolean) => {
    setLocalSectionVisibility((previous) => ({ ...previous, [section]: visible }));
  };

  const handleApplySectionPreset = (preset: keyof typeof WORKBENCH_PRESETS) => {
    setLocalSectionVisibility({ ...WORKBENCH_PRESETS[preset] });
    message.success(preset === 'SIMPLE' ? 'Simple mode deployed successfully' : 'Advanced mode deployed successfully');
  };

  const handleSaveVisibilityDefaults = async () => {
    try {
      await updateWorkbenchVisibilityDefaults({
        variables: {
          workbenchVisibilityDefaults: JSON.stringify({
            sectionVisibility: resolvedWorkbenchSections.visibility,
          }),
          reset: false,
        },
      });
      message.success('Workbench layout defaults saved');
      await refetch();
    } catch (error: any) {
      message.error(error?.message || 'Failed to save workbench layout defaults');
    }
  };

  return (
    <div className="workbench-theme flex flex-col h-screen bg-white">
      {/* --- Header --- */}
      <div className="border-b border-gray-200 p-4 flex justify-between items-center bg-white shadow-sm z-10">
        <div>
          <EditableTitle
            title={data.playbookGraph.title}
            canEdit={isAuthor}
            onSave={async (val) => {
              try {
                await updateGraphTitle({ variables: { id: playbookId, title: val } });
                await refetch();
              } catch (e: any) {
                alert(e?.message || 'Failed to rename');
              }
            }}
          />
          <span className="text-sm text-gray-500 uppercase tracking-wider">
            Capability Abstraction Map
          </span>
          {data.playbookGraph.status === 'DEPLOYED' && data.playbookGraph.l1PortalUrl && (
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span className="px-2 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-700 font-medium">
                L1 URL Ready
              </span>
              <button
                type="button"
                className="px-2 py-1 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(data.playbookGraph.l1PortalUrl || '');
                    message.success('L1 portal URL copied');
                  } catch {
                    message.error('Failed to copy L1 portal URL');
                  }
                }}
              >
                Copy URL
              </button>
              <a
                href={data.playbookGraph.l1PortalUrl}
                target="_blank"
                rel="noreferrer"
                className="px-2 py-1 rounded border border-gray-300 bg-white text-blue-700 hover:bg-blue-50"
              >
                Open
              </a>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Clone Button - Icon only */}
          <Button 
            variant="ghost"
            onClick={handleCloneGraph}
            disabled={cloningGraph}
            className="w-10 h-10 p-2 flex items-center justify-center"
            title="Clone this workbench"
          >
            <PixelIcon name="copy" className="w-5 h-5" />
          </Button>

          {/* Share Toggle Button - Icon only, author only */}
          {isAuthor && (
            <Button 
              variant="ghost"
              onClick={handleToggleShare}
              disabled={sharingGraph}
              className="w-10 h-10 p-2 flex items-center justify-center"
              title={data.playbookGraph.isShared 
                ? "Shared with organization - Click to make private" 
                : "Private - Click to share with organization"
              }
            >
              <PixelIcon name={data.playbookGraph.isShared ? "share" : "lock"} className="w-5 h-5" />
            </Button>
          )}

          {isAuthor && (
            <Button
              variant="ghost"
              onClick={handleToggleRemotePull}
              disabled={togglingRemotePull}
              className="w-10 h-10 p-2 flex items-center justify-center"
              title={data.playbookGraph.allowRemotePull ? 'Remote pull enabled - click to disable' : 'Remote pull disabled - click to enable'}
            >
              <PixelIcon name={data.playbookGraph.allowRemotePull ? 'download' : 'download-off'} className="w-5 h-5" />
            </Button>
          )}
          
          {/* Export/Import Button - Icon only */}
          <Button 
            variant="ghost"
            onClick={() => {
              setExportImportInitialTab('export');
              setExportImportModalVisible(true);
            }}
            className="w-10 h-10 p-2 flex items-center justify-center"
            title="Export or Import workbench"
          >
            <PixelIcon name="download" className="w-5 h-5" />
          </Button>

          {/* Maieutic Engine Button - Icon only */}
          <Button 
            variant="secondary"
            onClick={() => setMaieuticModalVisible(true)}
            className="w-10 h-10 p-2 flex items-center justify-center bg-violet-600 hover:bg-violet-700 border-violet-700 text-white"
            title="Launch hypothesis-driven detection engineering workflow (Maieutic Engine)"
          >
            <PixelIcon name="lightbulb" className="w-5 h-5" />
          </Button>

          {/* Threat Report Populate Button - Icon only */}
          <Button
            variant="secondary"
            onClick={() => setThreatReportModalVisible(true)}
            className="w-10 h-10 p-2 flex items-center justify-center bg-orange-500 hover:bg-orange-600 border-orange-600 text-white"
            title="Populate workbench from Threat Report (PDF)"
          >
            <PixelIcon name="crystal" className="w-5 h-5" />
          </Button>

          {/* OpenTIDE preview / publish shortcuts */}
          <Button
            variant="ghost"
            onClick={() => setPreviewModalVisible(true)}
            className="w-10 h-10 p-2 flex items-center justify-center text-blue-700 hover:bg-blue-50"
            title="Preview OpenTIDE metadata (optional AI enrichment) before HEF publish"
          >
            <PixelIcon name="eye" className="w-5 h-5" />
          </Button>
          
          <span className="px-3 py-1.5 text-xs rounded-full bg-gray-100 text-gray-700 border border-gray-200 font-medium">
            {data.playbookGraph.status}
          </span>
          {isAuthor && (
            <>
              {/* Status changer: only when not in IDEA, limited to DEV/TESTING/TUNING */}
              <select
                className="border border-gray-300 rounded px-3 py-1.5 text-sm font-medium disabled:opacity-50 hover:bg-gray-50 cursor-pointer"
                value={pendingStatus}
                onChange={(e) => {
                  const val = e.target.value;
                  setPendingStatus(val);
                  if (val) handleChangeStatus(val);
                }}
                disabled={data.playbookGraph.status === 'IDEA' || updatingStatus}
              >
                <option value="">Change Status...</option>
                {allowedOwnerStatuses.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </>
          )}
        </div>
      </div>

      {/* Main Content Area (Flex Row) */}
      <div
        ref={workbenchLayoutRef}
        className={`flex flex-1 overflow-hidden ${isSidebarResizing ? 'cursor-col-resize select-none' : ''}`}
      >
        
        {/* CENTER: Graph + Forms */}
        <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-50">
             
             {/* 2. Visual Layer Header */}
             {resolvedWorkbenchSections.sections.capabilityMap.visible && (
             <div className="w-full flex justify-center bg-gray-50 pt-6 px-8 shrink-0">
                 <div className="w-full max-w-7xl border-2 border-hefaistos-border rounded-lg shadow-sm bg-white overflow-hidden flex flex-col">
                     
                     {/* A. The Toggle Header */}
                      <div 
                        className="flex items-center justify-between px-4 py-2 bg-gray-100 border-b border-gray-200 cursor-pointer hover:bg-gray-200 transition-colors select-none"
                        onClick={() => setIsMapModalOpen(true)}
                      >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="flex items-center gap-2 text-xs font-bold text-gray-600 uppercase tracking-wider">
                                <PixelIcon name="share-2" className="w-4 h-4" /> {/* "Network/Graph" icon */}
                                {resolveWorkbenchMapTitle(data?.playbookGraph?.title)}
                            </div>
                            {coverageSummary.total > 0 && (
                              <div className="hidden lg:flex items-center gap-2 text-[10px] text-gray-500 normal-case">
                                <span>{coverageSummary.total} abstraction{coverageSummary.total !== 1 ? 's' : ''}</span>
                                <span>·</span>
                                <span>Avg robustness: {coverageSummary.avgRobustness.toFixed(1)}</span>
                                {Object.entries(coverageSummary.layerCount).map(([layer, count]) => (
                                  <span key={layer} className="px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 uppercase tracking-wide">
                                    {layer.replace(/_/g, ' ')}: {count}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          
                          <div className="flex items-center gap-3">
                              <button
                                type="button"
                                className={`text-[10px] px-2 py-1 rounded border ${
                                  isAutoMode
                                    ? 'bg-blue-50 border-blue-200 text-blue-700'
                                    : 'bg-white border-gray-300 text-gray-600'
                                }`}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setIsAutoMode((value) => !value);
                                  setSelectedNodeId(null);
                                }}
                              >
                                {isAutoMode ? 'Auto (from Library)' : 'Manual'}
                              </button>
                              <span className="text-[10px] text-gray-400 font-normal">
                                  Click to open map
                              </span>
                             <PixelIcon 
                               name={isMapModalOpen ? "chevron-up" : "chevron-down"} 
                               className={`w-4 h-4 text-gray-500 transition-transform duration-300 ${isMapModalOpen ? 'rotate-0' : '-rotate-180'}`} 
                             />
                         </div>
                     </div>
                  </div>
              </div>
             )}

             {/* Maieutic Review Panel - Shows when there's pending data */}
             {pendingMaieuticData && (
               <div className="w-full flex justify-center bg-yellow-50 border-t border-yellow-200 px-8 py-4 shrink-0">
                 <div className="w-full max-w-7xl">
                   <div className="bg-white border-2 border-yellow-300 rounded-lg p-4 shadow-sm">
                     <div className="flex items-start justify-between">
                       <div className="flex-1">
                         <h3 className="text-lg font-bold text-gray-800 mb-2 flex items-center gap-2">
                           <PixelIcon name="alert-circle" className="w-5 h-5 text-yellow-600" />
                           Maieutic Data Ready for Review
                         </h3>
                         <p className="text-sm text-gray-600 mb-3">
                           You have staged Maieutic output. Review the selections and apply to the workbench form below.
                           {' '}
                           <strong>Note:</strong> This will merge data into existing fields but won't auto-save.
                         </p>
                         <div className="flex gap-2">
                           <Button 
                             onClick={handleApplyMaieuticToWorkbench}
                             variant="primary"
                             className="flex items-center gap-1"
                           >
                             <PixelIcon name="check" className="w-4 h-4" />
                             Apply to Workbench
                           </Button>
                           <Button 
                             onClick={handleDismissMaieuticData}
                             variant="secondary"
                             className="flex items-center gap-1"
                           >
                             <PixelIcon name="x" className="w-4 h-4" />
                             Dismiss
                           </Button>
                         </div>
                       </div>
                     </div>
                   </div>
                 </div>
               </div>
             )}

             {/* Forms (Bottom Scrollable) */}
             <div className="flex-1 overflow-y-auto px-8 pb-8 bg-gray-50">
                <div className="max-w-5xl mx-auto mt-6">
                     <div className="animate-fade-in">

                       <div className="flex items-center justify-between mb-6">
                         <h2 className="text-2xl font-bold text-gray-800">
                           Detection Strategy & Context
                         </h2>
                       </div>

                       <WorkbenchSectionControls
                         sections={resolvedWorkbenchSections.sections}
                         onToggleSection={handleToggleSectionVisibility}
                         onApplyPreset={handleApplySectionPreset}
                         onSaveDefaults={handleSaveVisibilityDefaults}
                         savingDefaults={savingWorkbenchDefaults}
                       />

                       {/* Robustness Level Badge */}
                       {data.playbookGraph.robustnessLevel && data.playbookGraph.robustnessLevel > 0 && (
                         <div className="mb-4">
                           <RobustnessBadge level={data.playbookGraph.robustnessLevel} />
                         </div>
                       )}

                       {/* Conversation History Viewer */}
                       {conversationHistory.length > 0 && (
                         <details className="mb-4 border rounded p-3 bg-gray-50">
                           <summary className="cursor-pointer font-semibold text-sm text-gray-700 hover:text-gray-900">
                             📜 View Maieutic Conversation History ({conversationHistory.length} messages)
                           </summary>
                           <div className="mt-2 max-h-64 overflow-y-auto space-y-2">
                             {conversationHistory.map((msg: { role: 'user' | 'ai'; content: string }, idx: number) => (
                               <div 
                                 key={idx} 
                                 className={`p-2 rounded ${msg.role === 'ai' ? 'bg-blue-50 text-blue-800' : 'bg-gray-100 text-gray-800'}`}
                               >
                                 <strong>{msg.role === 'ai' ? '🤖 AI' : '👤 You'}:</strong>
                                 <MarkdownRenderer content={msg.content} variant="small" className="mt-1" skipEmpty={false} />
                               </div>
                             ))}
                           </div>
                         </details>
                       )}

                       {/* Part 1: Detection Strategy */}
                       {resolvedWorkbenchSections.sections.part1.visible && (
                         <>
                           <DetectionStrategy 
                             selectedTechniqueId={data.playbookGraph.mitreTechnique?.techniqueId || null}
                             onTechniqueChange={handleTechniqueChange}
                             onStrategyChange={handleStrategyChange}
                             ruleFormat={aiFormat}
                           />

                           {resolvedWorkbenchSections.sections.capabilityLibrary.visible && (
                             <CapabilityAbstractionPanel
                               techniqueId={data.playbookGraph.mitreTechnique?.techniqueId || null}
                               selectedIds={data.playbookGraph.selectedCapabilityAbstractions?.map((entry) => entry.id) || []}
                               selectedEntryObjects={data.playbookGraph.selectedCapabilityAbstractions || []}
                               detectionFocusLayer={data.playbookGraph.detectionFocusLayer || ''}
                               userRole={data.me?.role || 'VIEWER'}
                               onSelectionChange={handleCapabilitySelectionChange}
                               highlightedEntryId={highlightedEntryId}
                               onEntryHighlight={setHighlightedEntryId}
                             />
                           )}
                         </>
                       )}
                         
                       {/* Part 2: Deep Dive */}
                       {resolvedWorkbenchSections.sections.part2.visible && (
                         <DeepDive 
                           playbookId={playbookId || ''}
                           data={{
                             goal: data.playbookGraph.goal || '',
                             technicalContext: data.playbookGraph.technicalContext || '',
                             blindSpots: data.playbookGraph.blindSpots || '',
                             response: data.playbookGraph.responsePlaybook || '',
                             falsePositives: data.playbookGraph.falsePositives || ''
                           }}
                           onChange={handleDeepDiveChange}
                           onLinkRules={(ruleIds) => {
                             // Persist linked rule IDs inside selectedStrategy JSON
                             const existing = data.playbookGraph.selectedStrategy ? JSON.parse(data.playbookGraph.selectedStrategy) : {};
                             const next = { ...existing, linkedRuleIds: ruleIds };
                             updatePlaybookDetails({ variables: { graphId: playbookId, selectedStrategy: JSON.stringify(next) } });
                           }}
                         />
                       )}

                        {/* Part 3: Detection Rule */}
                        {resolvedWorkbenchSections.sections.part3.visible && (
                         <div className="p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6 space-y-4" id="detection-rule-editor">
                          {/* Header Row */}
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-3 flex-wrap">
                              <h2 className="text-xl font-bold text-hefaistos-primary">Part 3: Detection Rules</h2>
                              {/* Mode Indicator Badge */}
                              <span className={`px-3 py-1 text-xs rounded-full font-medium ${
                                detectionMode === 'logic' ? 'bg-blue-100 text-blue-700 border border-blue-200' :
                               detectionMode === 'ai' ? 'bg-purple-100 text-purple-700 border border-purple-200' :
                               'bg-green-100 text-green-700 border border-green-200'
                             }`}>
                               {detectionMode === 'logic' ? '🔧 Logic Generated' :
                                detectionMode === 'ai' ? '✨ AI Generated' :
                                '✏️ Manual'}
                             </span>
                             {/* Platform Indicators */}
                             {openTideRule && getConfiguredPlatforms(openTideRule).length > 0 && (
                               <div className="flex items-center gap-1 flex-wrap">
                                 {getConfiguredPlatforms(openTideRule).map(p => (
                                   <Tag key={p} color={p === 'kql' ? 'blue' : p === 'spl' ? 'orange' : 'green'} className="text-xs">
                                     {p.toUpperCase()} Configured
                                   </Tag>
                                 ))}
                               </div>
                             )}
                           </div>
                           <Button
                             variant="ghost"
                             className="text-xs px-2 py-1 border border-gray-300"
                             onClick={() => ragReuseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                             disabled={!ragReuseResult}
                           >
                             Jump to RAG Reuse
                           </Button>
                         </div>

                         {/* Toolbar Row */}
                          <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
                           {/* Action Buttons - Equal Width */}
                           <div className="flex items-center gap-2 flex-1">
                             <Button 
                               variant="primary" 
                               className="flex-1 bg-purple-600 hover:bg-purple-700 border-purple-700 text-white justify-center"
                               onClick={handleAIGenerate}
                               disabled={aiBusy}
                             >
                               <span className="flex items-center justify-center">
                                 <PixelIcon name={aiBusy ? "loader" : "zap"} className={`w-4 h-4 mr-2 ${aiBusy ? 'animate-spin' : ''}`} />
                                 {aiBusy ? `Generating ${aiFormat}…` : 'AI Generate'}
                               </span>
                             </Button>
                             <Button
                               variant="secondary"
                               className="flex-1 bg-orange-500 hover:bg-orange-600 border-orange-600 text-white justify-center"
                               onClick={() => setEditorModalVisible(true)}
                             >
                               <span className="flex items-center justify-center">
                                 <PixelIcon name="edit" className="w-4 h-4 mr-2" />
                                 Editor
                               </span>
                             </Button>
                             <Button
                               variant="secondary"
                               className="flex-1 bg-blue-500 hover:bg-blue-600 border-blue-600 text-white justify-center"
                               onClick={handleSanitizeRule}
                             >
                               <span className="flex items-center justify-center">
                                 <PixelIcon name="wand" className="w-4 h-4 mr-2" />
                                 Sanitize
                               </span>
                             </Button>
                             <Button
                               variant="secondary"
                               className="flex-1 bg-emerald-600 hover:bg-emerald-700 border-emerald-700 text-white justify-center"
                               onClick={handleRecommendReuse}
                               disabled={recommendingReuse || !ragReuseSupported}
                             >
                               <span className="flex items-center justify-center">
                                 <PixelIcon name={recommendingReuse ? "loader" : "target"} className={`w-4 h-4 mr-2 ${recommendingReuse ? 'animate-spin' : ''}`} />
                                 {recommendingReuse ? 'Checking Reuse…' : 'RAG Reuse Check'}
                               </span>
                             </Button>
                             <Button
                               variant="primary"
                               className="flex-1 bg-green-600 hover:bg-green-700 border-green-700 text-white justify-center"
                               onClick={handleSaveToLibrary}
                               disabled={saving || savingAll}
                             >
                               <span className="flex items-center justify-center">
                                 <PixelIcon name="save" className="w-4 h-4 mr-2" />
                                 {saving || savingAll ? 'Saving...' : 'Save'}
                               </span>
                             </Button>
                           </div>
                          </div>

                          {!ragReuseSupported && (
                            <p className="text-xs text-gray-500 -mt-2">
                              RAG reuse check currently supports KQL, EQL, or SPL.
                            </p>
                          )}

                          {generationInsights && (
                            <div ref={insightsRef}>
                              <Alert
                                type="info"
                                showIcon
                                closable
                                onClose={() => setGenerationInsights(null)}
                                className="mt-3"
                                message={generationInsights.generationSummary || 'Capability-aware AI generation ready'}
                                description={(
                                  <div className="space-y-3 mt-2">
                                    {generationInsights.correlationIdeas && (
                                      <div>
                                        <strong>Correlation ideas:</strong>
                                        <pre className="whitespace-pre-wrap font-sans text-sm mt-1">{generationInsights.correlationIdeas}</pre>
                                      </div>
                                    )}
                                    {generationInsights.expectedBlindSpots && (
                                      <div>
                                        <strong>Expected blind spots:</strong>
                                        <pre className="whitespace-pre-wrap font-sans text-sm mt-1">{generationInsights.expectedBlindSpots}</pre>
                                      </div>
                                    )}
                                    {generationInsights.testGuidance && (
                                      <div>
                                        <strong>Suggested test guidance:</strong>
                                        <pre className="whitespace-pre-wrap font-sans text-sm mt-1">{generationInsights.testGuidance}</pre>
                                      </div>
                                    )}
                                    <ReferenceContextPanel references={generationInsights.referenceContext || []} />
                                    <div className="flex gap-2 flex-wrap">
                                      {generationInsights.quickWinRule && (
                                        <Button
                                          variant="secondary"
                                          onClick={() => {
                                            setLocalRule(generationInsights.quickWinRule || '');
                                            setDetectionMode('ai');
                                          }}
                                        >
                                          Load quick-win variant
                                        </Button>
                                      )}
                                      {generationInsights.robustRule && (
                                        <Button
                                          variant="secondary"
                                          onClick={() => {
                                            setLocalRule(generationInsights.robustRule || '');
                                            setDetectionMode('ai');
                                          }}
                                        >
                                          Load robust variant
                                        </Button>
                                      )}
                                    </div>
                                  </div>
                                )}
                              />
                            </div>
                          )}

                          {ragReuseResult && (ragReuseResult.decision || ragReuseResult.message || ragReuseResult.rationale || ragReuseResult.workbenchSummary) && (
                            <div ref={ragReuseRef}>
                              <Alert
                                type="success"
                                showIcon
                                closable
                                onClose={() => setRagReuseResult(null)}
                                className="mt-3"
                                message="RAG Template Reuse Assessment"
                                description={(
                                  <div className="space-y-3 mt-2">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <Tag color={getReuseDecisionColor(ragReuseResult.decision)}>
                                        Decision: {String(ragReuseResult.decision || 'CREATE_NEW').replace('_', ' ')}
                                      </Tag>
                                      {typeof ragReuseResult.referenceCount === 'number' && (
                                        <Tag color="default">References: {ragReuseResult.referenceCount}</Tag>
                                      )}
                                      {ragReuseResult.providerUsed && <Tag color="purple">Provider: {ragReuseResult.providerUsed}</Tag>}
                                    </div>

                                    {ragReuseResult.candidateSource && ragReuseResult.candidateSource !== 'NONE' && (
                                      <div>
                                        <strong>Best candidate source:</strong>
                                        <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{ragReuseResult.candidateSource}</pre>
                                      </div>
                                    )}

                                    {ragReuseResult.workbenchSummary && (
                                      <div>
                                        <strong>Workbench summary used for matching:</strong>
                                        <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{ragReuseResult.workbenchSummary}</pre>
                                      </div>
                                    )}

                                    {ragReuseResult.rationale && (
                                      <div>
                                        <strong>Rationale:</strong>
                                        <pre className="whitespace-pre-wrap font-sans text-sm mt-1">{ragReuseResult.rationale}</pre>
                                      </div>
                                    )}

                                    {ragReuseResult.adaptedRule && ragReuseResult.adaptedRule.trim() && (
                                      <div className="space-y-2">
                                        <div className="flex items-center justify-between gap-2 flex-wrap">
                                          <strong>Adapted rule candidate:</strong>
                                          <Button
                                            variant="primary"
                                            className="bg-emerald-600 hover:bg-emerald-700 border-emerald-700 text-white"
                                            onClick={() => {
                                              const adaptedRule = sanitizeRule(ragReuseResult.adaptedRule || '');
                                              if (!adaptedRule) {
                                                message.warning('No adapted rule content to apply.');
                                                return;
                                              }
                                              setLocalRule(adaptedRule);
                                              setDetectionMode('ai');
                                              message.success('Adapted rule loaded into editor.');
                                            }}
                                          >
                                            Use Adapted Rule
                                          </Button>
                                        </div>
                                        <pre className="whitespace-pre-wrap font-mono text-xs bg-[#071108] text-green-100 p-3 rounded border border-green-900/40 max-h-72 overflow-auto">
                                          {sanitizeRule(ragReuseResult.adaptedRule)}
                                        </pre>
                                      </div>
                                    )}
                                  </div>
                                )}
                              />
                            </div>
                          )}

                          {/* Editor */}
                          <div
                            className={`h-[32rem] rounded-lg overflow-hidden shadow-inner ${
                              isDarkTheme ? 'border border-gray-700 bg-[#071108]' : 'border border-gray-300 bg-white'
                            }`}
                          >
                            <DetectionRuleEditor
                              value={localRule}
                              onChange={(value) => {
                                setLocalRule(value);
                                if (detectionMode !== 'manual') setDetectionMode('manual');
                              }}
                              onBlur={() => handleStrategyChange({ detectionRule: localRule })}
                              format={aiFormat}
                              height="100%"
                              enableLSP={false}
                              visualStyle={isDarkTheme ? 'terminal' : 'default'}
                            />
                          </div>
                       </div>
                       )}

                    {/* Part 4: SOAR Configuration */}
                    {resolvedWorkbenchSections.sections.part4.visible && (
                      <SoarConfiguration 
                        data={{
                          trigger: data.playbookGraph.alertTrigger || '',
                          severity: data.playbookGraph.defaultSeverity || 'MEDIUM',
                          enrichment: data.playbookGraph.enrichmentSteps ? JSON.parse(data.playbookGraph.enrichmentSteps) : [],
                          containment: data.playbookGraph.containmentSteps ? JSON.parse(data.playbookGraph.containmentSteps) : [],
                          notifications: data.playbookGraph.notificationSteps ? JSON.parse(data.playbookGraph.notificationSteps) : [],
                          downstreamCorrelationRequirements: data.playbookGraph.downstreamCorrelationRequirements
                            ? (typeof data.playbookGraph.downstreamCorrelationRequirements === 'string'
                                ? JSON.parse(data.playbookGraph.downstreamCorrelationRequirements)
                                : data.playbookGraph.downstreamCorrelationRequirements)
                            : {},
                          tlpClassification: data.playbookGraph.tlpClassification || 'AMBER',
                          publicReferences: data.playbookGraph.publicReferences ? JSON.parse(data.playbookGraph.publicReferences) : [],
                          internalReferences: data.playbookGraph.internalReferences ? JSON.parse(data.playbookGraph.internalReferences) : [],
                          threatActors: data.playbookGraph.threatActors ? JSON.parse(data.playbookGraph.threatActors) : [],
                          threatSurface: data.playbookGraph.threatSurface ? JSON.parse(data.playbookGraph.threatSurface) : [],
                        }}
                        onSave={handleSoarSave}
                      />
                    )}

                    {/* Part 5: Testing & Validation */}
                    {resolvedWorkbenchSections.sections.part5.visible && (
                      <TestingGuidance
                        data={{
                          testScenario: data.playbookGraph.testScenario || '',
                          expectedOutput: data.playbookGraph.testExpectedOutput || '',
                          techniqueId: data.playbookGraph.mitreTechnique?.techniqueId || undefined
                        }}
                        onChange={(field, val) => handleSidebarUpdate(field, val)}
                      />
                    )}

                    {/* Part 6: Review Workflow (label fixed below in component) */}
                    {resolvedWorkbenchSections.sections.part6.visible && (
                      <ReviewWorkflow 
                        playbookId={data.playbookGraph.id}
                        status={data.playbookGraph.status}
                        activeReview={data.playbookGraph.activeReview}
                        userRole={data.me?.role || 'VIEWER'}
                        isAuthor={isAuthor}
                        refetch={refetch}
                      />
                    )}

                    {/* OpenTide YAML Preview */}
                    {openTideRule && (
                      <div className="p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6">
                        <h2 className="text-xl font-bold mb-4 text-hefaistos-primary">OpenTide YAML Preview (MDR)</h2>
                        <details className="border border-hefaistos-border rounded-lg bg-white">
                          <summary className="cursor-pointer px-4 py-3 font-semibold text-sm text-gray-800 hover:text-hefaistos-primary select-none">
                            📋 View YAML Metadata Preview
                            <span className="ml-2 text-xs font-normal text-gray-500">(auto-compiled from workbench fields)</span>
                          </summary>
                          <div className="px-4 pb-4 bg-white rounded-b-lg border-t border-hefaistos-border">
                            <OpenTideMetadataPreview
                              openTideRule={openTideRule}
                              onOpenFullPreview={() => setPreviewModalVisible(true)}
                            />
                          </div>
                        </details>

                     </div>
                    )}

                    {/* Activity Overview */}
                    {resolvedWorkbenchSections.sections.activityOverview.visible && (
                      <ActivityOverview activities={data.playbookGraph.activities || []} />
                    )}
             </div>
        </div>
      </div>
      </div>

        {!isSidebarCollapsed && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize notes panel"
            onMouseDown={handleSidebarResizeStart}
            className={`relative w-2 shrink-0 cursor-col-resize ${
              isSidebarResizing ? 'bg-blue-100' : 'hover:bg-blue-50'
            }`}
          >
            <div
              className={`absolute inset-y-0 left-1/2 w-px -translate-x-1/2 ${
                isSidebarResizing ? 'bg-blue-400' : 'bg-gray-200'
              }`}
            />
          </div>
        )}

        {/* RIGHT: Sidebar (Resizable) */}
        <div className="h-full shrink-0" style={{ width: `${effectiveSidebarWidth}px` }}>
          <PlaybookSidebar 
              playbook={{
                ...data.playbookGraph,
                tags: data.playbookGraph.tags || []
              }}
              onUpdate={handleSidebarUpdate}
              onUpdateNodeMappings={handleUpdateNodeMappings}
              selectedNodeId={selectedNodeId}
              canClearNotes={isAuthor || data.me?.role === 'ADMIN'}
              activeTab={sidebarTab}
              onTabChange={setSidebarTab}
              collapsed={isSidebarCollapsed}
              onCollapsedChange={setIsSidebarCollapsed}
              onDeriveTelemetry={handleDeriveTelemetry}
              derivingTelemetry={derivingTelemetry}
              onSaveTelemetryRequirements={handleSaveTelemetryRequirements}
          />
        </div>

      </div>

      {/* Detection Rule Editor Modal */}
      <CapabilityAbstractionMapModal
        isOpen={isMapModalOpen}
        onClose={() => setIsMapModalOpen(false)}
        workbenchTitle={data.playbookGraph.title}
        derivedNodes={derivedNodes}
        derivedEdges={derivedEdges}
        manualNodes={nodes}
        manualEdges={edges}
        isAutoMode={isAutoMode}
        onToggleAutoMode={() => {
          setIsAutoMode((value) => !value);
          setSelectedNodeId(null);
        }}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        onNodeDragStop={onNodeDragStop}
        onCapabilityMapNodeClick={handleCapabilityMapNodeClick}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        coverageSummary={coverageSummary}
        focusLayer={data.playbookGraph.detectionFocusLayer}
        layerBands={layerBands}
        nodeTypes={nodeTypes}
        onAddNode={handleAddNode}
        onDeleteSelected={handleDeleteSelected}
        hasSelection={!!selectedNodeId}
        onColorChange={handleColorChange}
      />

      {/* Detection Rule Editor Modal */}
      <DetectionRuleEditorModal
        visible={editorModalVisible}
        onClose={() => setEditorModalVisible(false)}
        playbookId={playbookId || ''}
        initialRule={localRule}
        initialFormat={aiFormat}
        initialMode={detectionMode}
        onSave={handleEditorModalSave}
        onSaveToLibrary={async (rule: string, format: string, options?) => {
          const res = await saveRule({ variables: { playbookId: playbookId!, rawYaml: rule, format, autoCommit: options?.autoCommit, commitMessage: options?.commitMessage } });
          return {
            success: res.data?.saveDetectionRule?.success ?? false,
            message: res.data?.saveDetectionRule?.message,
            commitSha: res.data?.saveDetectionRule?.commitSha ?? undefined,
            errors: res.data?.saveDetectionRule?.errors ?? [],
          };
        }}
        initialOpenTideRule={openTideRule}
        playbookData={playbookDataForModal}
      />

      {/* Export/Import Modal */}
      <ExportImportModal
        visible={exportImportModalVisible}
        onClose={() => setExportImportModalVisible(false)}
        playbookId={playbookId || ''}
        playbookTitle={data?.playbookGraph?.title || 'Playbook'}
        configuredPlatforms={data?.playbookGraph?.configuredPlatforms || []}
        initialTab={exportImportInitialTab}
        onImportSuccess={(newGraphId) => {
          // Navigate to the newly imported playbook
          navigate(`/playbooks/${newGraphId}`);
        }}
      />

      {/* Maieutic Engine Modal */}
      <MaieuticEngineModal
        isOpen={maieuticModalVisible}
        onClose={() => setMaieuticModalVisible(false)}
        onSubmit={handleMaieuticSubmit}
        workbenchContext={maieuticWorkbenchContext}
      />

      {/* Threat Report Populate Modal */}
      {playbookId && (
        <ThreatReportPopulateModal
          isOpen={threatReportModalVisible}
          onClose={() => setThreatReportModalVisible(false)}
          playbookId={playbookId}
          onApplied={() => {
            window.location.reload();
          }}
        />
      )}

      {/* OpenTIDE Preview Modal (Phase 2) */}
      {playbookId && (
        <OpenTidePreviewModal
          playbookId={playbookId}
          visible={previewModalVisible}
          onClose={() => setPreviewModalVisible(false)}
          onCommit={(_useAI) => {
            setPreviewModalVisible(false);
            setExportImportInitialTab('github');
            setExportImportModalVisible(true);
          }}
        />
      )}
    </div>
  );
};

export default PlaybookWorkbench;

// Inline editable H1 used above
const EditableTitle: React.FC<{ title: string; canEdit: boolean; onSave: (v: string) => Promise<void> | void }> = ({ title, canEdit, onSave }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setDraft(title);
  }, [title]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const commit = async () => {
    const val = (draft || '').trim();
    setEditing(false);
    if (val && val !== title) {
      await onSave(val);
    }
  };

  const cancel = () => {
    setDraft(title);
    setEditing(false);
  };

  if (!canEdit) {
    return <h1 className="text-2xl font-bold text-gray-800">{title}</h1>;
  }

  return (
    <div className="flex items-center gap-2">
      {editing ? (
        <input
          ref={inputRef}
          className="text-2xl font-bold text-gray-800 border-b border-gray-300 outline-none focus:border-blue-500 bg-transparent"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') cancel();
          }}
        />
      ) : (
        <h1
          className="text-2xl font-bold text-gray-800 hover:bg-yellow-50 rounded px-1 cursor-text"
          onClick={() => setEditing(true)}
          title="Click to edit title"
        >
          {title}
        </h1>
      )}
      {!editing && (
        <button
          type="button"
          className="text-gray-500 hover:text-gray-700"
          onClick={() => setEditing(true)}
          aria-label="Edit title"
          title="Edit title"
        >
          <PixelIcon name="edit-2" className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};
