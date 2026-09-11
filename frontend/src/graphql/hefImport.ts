/**
 * GraphQL queries and mutations for the OpenTIDE HEF reverse-import feature.
 *
 * These operations back the "Import Workbench ▾ → From OpenTIDE HEF (GitHub)"
 * flow on the Workbench Hub page.  They allow users to browse HEF bundles
 * stored in a GitHub repository (previously published by the HEF Publish flow)
 * and recreate one or many Workbenches from them — useful for disaster recovery,
 * point-in-time restore, and cross-environment promotion.
 */

import { gql } from '@apollo/client';

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/** List all discoverable OpenTIDE HEF bundles in a GitHub repository. */
export const LIST_HEF_BUNDLES = gql`
  query ListHefBundles(
    $profileId: UUID
    $repoOwner: String
    $repoName: String
    $branch: String
    $commitSha: String
    $targetFolder: String
  ) {
    listHefBundles(
      profileId: $profileId
      repoOwner: $repoOwner
      repoName: $repoName
      branch: $branch
      commitSha: $commitSha
      targetFolder: $targetFolder
    ) {
      path
      mdrTitle
      mdrUuid
      status
      techniques
      lastCommit
      valid
      validationErrors
    }
  }
`;

/** List the current user's recent OpenTIDE HEF import jobs. */
export const GET_MY_OPENTIDE_HEF_IMPORT_JOBS = gql`
  query GetMyOpentideHefImportJobs($limit: Int) {
    myOpentideHefImportJobs(limit: $limit) {
      taskId
      status
      progress
      repoOwner
      repoName
      branch
      targetFolder
      sourceCommitSha
      conflictMode
      importPlatformRules
      dryRun
      results {
        bundlePath
        workbenchId
        status
        errors
      }
      errorMessage
      createdAt
      startedAt
      completedAt
    }
  }
`;

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

/** Enqueue an asynchronous OpenTIDE HEF import job. */
export const QUEUE_OPENTIDE_HEF_IMPORT = gql`
  mutation QueueOpenTideHefImport(
    $profileId: UUID
    $repoOwner: String
    $repoName: String
    $branch: String
    $targetFolder: String
    $commitSha: String
    $selectedBundles: [String!]!
    $conflictMode: String
    $importPlatformRules: Boolean
    $dryRun: Boolean
  ) {
    queueOpentideHefImport(
      profileId: $profileId
      repoOwner: $repoOwner
      repoName: $repoName
      branch: $branch
      targetFolder: $targetFolder
      commitSha: $commitSha
      selectedBundles: $selectedBundles
      conflictMode: $conflictMode
      importPlatformRules: $importPlatformRules
      dryRun: $dryRun
    ) {
      taskId
      status
    }
  }
`;

// ---------------------------------------------------------------------------
// TypeScript interfaces
// ---------------------------------------------------------------------------

export interface HefBundleDescriptor {
  path: string;
  mdrTitle: string;
  mdrUuid: string;
  status: string;
  techniques: string[];
  lastCommit: string;
  valid: boolean;
  validationErrors: string[];
}

export interface HefBundleImportResult {
  bundlePath: string;
  workbenchId: string | null;
  status: string;
  errors: string[];
}

export interface OpentideHefImportJob {
  taskId: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  progress: string;
  repoOwner: string;
  repoName: string;
  branch: string;
  targetFolder: string;
  sourceCommitSha: string;
  conflictMode: string;
  importPlatformRules: boolean;
  dryRun: boolean;
  results: HefBundleImportResult[];
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}
