/**
 * GraphQL queries and mutations for OpenTIDE HEF Publish Profiles.
 *
 * An OpenTIDE HEF Publish Profile (a.k.a. "OpenTIDE HEF Publish Target") is a
 * reusable configuration that pre-fills the Publish dialog on the Workbench
 * Detail page (Export/Import → GitHub tab → "Publish OpenTIDE HEF").  It binds
 * a GitHub :class:`RuleRepository` to a default branch, target folder, and
 * default deployment platforms.  Profiles are managed by organisation admins
 * via the queries/mutations below; they are persisted as
 * ``organizations.OpenTidePublishProfile`` rows in the backend.
 */

import { gql } from '@apollo/client';

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const GET_HEF_PUBLISH_PROFILES = gql`
  query GetOpenTideHefPublishProfilesAdmin {
    opentideHefPublishProfiles {
      id
      name
      repositoryId
      repositoryName
      repositoryUrl
      branch
      targetFolder
      pushPlatformRules
      enabledPlatforms
      useGraphConfiguredPlatforms
      kqlTargetPolicy
      enabled
      createdAt
      updatedAt
    }
  }
`;

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export const SET_HEF_PUBLISH_PROFILE = gql`
  mutation SetOpenTidePublishProfile(
    $id: UUID
    $name: String!
    $repositoryId: ID!
    $branch: String
    $targetFolder: String
    $pushPlatformRules: Boolean
    $enabledPlatforms: [String]
    $useGraphConfiguredPlatforms: Boolean
    $kqlTargetPolicy: String
    $enabled: Boolean
  ) {
    setOpenTidePublishProfile(
      id: $id
      name: $name
      repositoryId: $repositoryId
      branch: $branch
      targetFolder: $targetFolder
      pushPlatformRules: $pushPlatformRules
      enabledPlatforms: $enabledPlatforms
      useGraphConfiguredPlatforms: $useGraphConfiguredPlatforms
      kqlTargetPolicy: $kqlTargetPolicy
      enabled: $enabled
    ) {
      success
      message
      profile {
        id
        name
        repositoryId
        repositoryName
        repositoryUrl
        branch
        targetFolder
        pushPlatformRules
        enabledPlatforms
        useGraphConfiguredPlatforms
        kqlTargetPolicy
        enabled
        createdAt
        updatedAt
      }
    }
  }
`;

export const DELETE_HEF_PUBLISH_PROFILE = gql`
  mutation DeleteOpenTidePublishProfile($id: UUID!) {
    deleteOpenTidePublishProfile(id: $id) {
      success
      message
    }
  }
`;

// ---------------------------------------------------------------------------
// TypeScript interfaces
// ---------------------------------------------------------------------------

export interface HefPublishProfile {
  id: string;
  name: string;
  repositoryId: string;
  repositoryName: string | null;
  repositoryUrl: string | null;
  branch: string;
  targetFolder: string;
  pushPlatformRules: boolean;
  enabledPlatforms: string[];
  useGraphConfiguredPlatforms: boolean;
  kqlTargetPolicy: 'defender' | 'sentinel' | 'both';
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}
