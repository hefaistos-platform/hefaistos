/**
 * GraphQL queries and mutations for OpenTIDE metadata preview and commit.
 *
 * Phase 2 implementation – provides:
 * - `PREVIEW_OPENTIDE_METADATA` query to fetch AI-enriched OpenTIDE metadata (synchronous)
 *
 * Async preview workflow (preferred for AI enrichment):
 * - `START_OPENTIDE_PREVIEW_TASK` mutation creates a preview task and publishes to RabbitMQ
 * - `GET_OPENTIDE_PREVIEW_STATUS` query polls the preview task status every 2 seconds
 */

import { gql } from '@apollo/client';

export const PREVIEW_OPENTIDE_METADATA = gql`
  query PreviewOpentideMetadata(
    $playbookId: UUID!
    $useAiEnrichment: Boolean
    $forceBdrGeneration: Boolean
  ) {
    previewOpentideMetadata(
      playbookId: $playbookId
      useAiEnrichment: $useAiEnrichment
      forceBdrGeneration: $forceBdrGeneration
    ) {
      mdrYaml
      bdrYaml
      domYaml
      fieldMetadata {
        fieldPath
        value
        aiGenerated
        source
        fieldType
      }
      aiClassification
      bdrApplicable
      validationErrors
      totalFields
      aiGeneratedCount
      userProvidedCount
    }
  }
`;

// ---------------------------------------------------------------------------
// Async preview workflow (RabbitMQ-backed)
// ---------------------------------------------------------------------------

export const START_OPENTIDE_PREVIEW_TASK = gql`
  mutation StartOpentidePreviewTask(
    $playbookId: UUID!
    $useAiEnrichment: Boolean
    $forceBdrGeneration: Boolean
  ) {
    startOpentidePreviewTask(
      playbookId: $playbookId
      useAiEnrichment: $useAiEnrichment
      forceBdrGeneration: $forceBdrGeneration
    ) {
      taskId
      success
      message
    }
  }
`;

export const GET_OPENTIDE_PREVIEW_STATUS = gql`
  query GetOpentidePreviewStatus($taskId: UUID!) {
    opentidePreviewStatus(taskId: $taskId) {
      id
      status
      useAiEnrichment
      forceBdrGeneration
      errorMessage
      createdAt
      startedAt
      completedAt
      result {
        mdrYaml
        bdrYaml
        domYaml
        fieldMetadata {
          fieldPath
          value
          aiGenerated
          source
          fieldType
        }
        aiClassification
        bdrApplicable
        validationErrors
        totalFields
        aiGeneratedCount
        userProvidedCount
      }
    }
  }
`;

export const GET_LATEST_OPENTIDE_PREVIEW = gql`
  query GetLatestOpentidePreview($playbookId: UUID!) {
    latestOpentidePreview(playbookId: $playbookId) {
      id
      status
      useAiEnrichment
      forceBdrGeneration
      completedAt
      result {
        mdrYaml
        bdrYaml
        domYaml
        fieldMetadata {
          fieldPath
          value
          aiGenerated
          source
          fieldType
        }
        aiClassification
        bdrApplicable
        validationErrors
        totalFields
        aiGeneratedCount
        userProvidedCount
      }
    }
  }
`;

export const IMPORT_FROM_OPENTIDE = gql`
  mutation ImportFromOpenTide(
    $mdrYaml: String!
    $tvmYaml: String
    $domYaml: String
    $newTitle: String
  ) {
    importFromOpentide(
      mdrYaml: $mdrYaml
      tvmYaml: $tvmYaml
      domYaml: $domYaml
      newTitle: $newTitle
    ) {
      success
      graph {
        id
        title
      }
      message
    }
  }
`;

// ---------------------------------------------------------------------------
// TypeScript interfaces
// ---------------------------------------------------------------------------

export interface FieldOverrideInput {
  fieldPath: string;
  value: string; // JSON-serialised value
}

export type FieldSource = 'ai' | 'user' | 'default';
export type FieldType = 'string' | 'array' | 'object' | 'number' | 'boolean' | 'unknown';

export interface FieldMetadata {
  fieldPath: string;
  value: string; // JSON string
  aiGenerated: boolean;
  source: FieldSource;
  fieldType: FieldType;
}

export interface PreviewOpentideMetadataResult {
  mdrYaml: string | null;       // JSON string representation of the MDR dict
  bdrYaml: string | null;       // null when BDR is not applicable
  domYaml: string | null;       // JSON string representation of the DOM dict
  fieldMetadata: FieldMetadata[];
  aiClassification: string | null; // 'THREAT' | 'BUSINESS' | null
  bdrApplicable: boolean;
  validationErrors: string[];
  totalFields: number;
  aiGeneratedCount: number;
  userProvidedCount: number;
}

// Async preview task (RabbitMQ worker)
export type TaskStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export interface OpentidePreviewTaskResult {
  id: string;
  status: TaskStatus;
  useAiEnrichment: boolean;
  forceBdrGeneration: boolean;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  result: PreviewOpentideMetadataResult | null;
}

export interface StartOpentidePreviewTaskResult {
  taskId: string;
  success: boolean;
  message: string;
}

