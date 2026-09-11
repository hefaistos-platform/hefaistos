import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { message } from 'antd';
import {
  App,
  Card,
  Table,
  Space,
  Button as AntButton,
  Typography,
  Modal,
  Form,
  Input,
  Popconfirm,
  Select,
  Radio,
  Divider,
  Switch,
  Tooltip,
  Tabs,
  Tag,
  Alert,
} from 'antd';
import {
  ClockCircleOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  LockOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { PixelIcon } from '../components/ui/PixelIcon';
import { InviteUserModal } from '../components/InviteUserModal';
import PlatformCredentials from './settings/PlatformCredentials';
import HefPublishTargets from './settings/HefPublishTargets';
import AITasksTab from './settings/AITasks';
import InstanceSharing from './settings/InstanceSharing';
import { getApiBaseUrl } from '../config/env';
import { getStoredAccessToken } from '../utils/authSession';

// ---------------------------------------------------------------------------
// GraphQL – Users & Org AI (from UserManagementPage)
// ---------------------------------------------------------------------------

const GET_ALL_USERS_QUERY = gql`
  query GetAllUsersInOrg {
    allUsersInOrg {
      id
      username
      email
      role
      organization { id name }
      lastLogin
      isStaff
    }
  }
`;

const GET_CONFIG_ACCESS = gql`
  query GetConfigurationAccess {
    me {
      id
      role
      isSuperuser
    }
  }
`;

const DELETE_USER_MUTATION = gql`
  mutation DeleteUser($userId: ID!) {
    deleteUser(userId: $userId) {
      ok
    }
  }
`;

const ADMIN_UPDATE_USER_MUTATION = gql`
  mutation AdminUpdateUser($userId: ID!, $email: String, $role: String, $bio: String, $jobTitle: String, $slackHandle: String, $organizationId: UUID) {
    adminUpdateUser(userId: $userId, email: $email, role: $role, bio: $bio, jobTitle: $jobTitle, slackHandle: $slackHandle, organizationId: $organizationId) {
      id
      username
      email
      role
      bio
      jobTitle
      slackHandle
      organization { id name }
    }
  }
`;

const ADMIN_RESET_USER_PASSWORD_MUTATION = gql`
  mutation AdminResetUserPassword($userId: ID!, $newPassword: String!) {
    adminResetUserPassword(userId: $userId, newPassword: $newPassword) {
      ok
      message
    }
  }
`;

const ALL_ORGANIZATIONS_QUERY = gql`
  query AllOrganizations {
    allOrganizations {
      id
      name
    }
  }
`;

const GET_ORG_AI_SETTINGS = gql`
  query GetOrgAISettings($organizationId: UUID) {
    orgAiSettings(organizationId: $organizationId) {
      id
      ollamaBaseUrl
      ollamaModel
      hasOllama
      hasOpenai
      hasGemini
      hasClaude
      hasAzureOpenai
      hasAnyProvider
      orgPreferredModel
      azureOpenaiEndpoint
      azureOpenaiDeployment
      ollamaEnabled
      openaiEnabled
      geminiEnabled
      claudeEnabled
      azureOpenaiEnabled
      configSource
      sharedProfileId
      sharedProfileName
      sharedProfileLocked
      canEditCustomSettings
    }
  }
`;

const UPDATE_ORG_AI_SETTINGS = gql`
  mutation UpdateOrgAISettings($organizationId: UUID, $ollamaBaseUrl: String, $ollamaModel: String, $openaiKey: String, $geminiKey: String, $claudeKey: String, $azureOpenaiEndpoint: String, $azureOpenaiKey: String, $azureOpenaiDeployment: String, $orgPreferredModel: String, $ollamaEnabled: Boolean, $openaiEnabled: Boolean, $geminiEnabled: Boolean, $claudeEnabled: Boolean, $azureOpenaiEnabled: Boolean) {
    updateOrgAiSettings(organizationId: $organizationId, ollamaBaseUrl: $ollamaBaseUrl, ollamaModel: $ollamaModel, openaiKey: $openaiKey, geminiKey: $geminiKey, claudeKey: $claudeKey, azureOpenaiEndpoint: $azureOpenaiEndpoint, azureOpenaiKey: $azureOpenaiKey, azureOpenaiDeployment: $azureOpenaiDeployment, orgPreferredModel: $orgPreferredModel, ollamaEnabled: $ollamaEnabled, openaiEnabled: $openaiEnabled, geminiEnabled: $geminiEnabled, claudeEnabled: $claudeEnabled, azureOpenaiEnabled: $azureOpenaiEnabled) {
      ok
      settings {
        id
        ollamaBaseUrl
        ollamaModel
        hasOllama
        hasOpenai
        hasGemini
        hasClaude
        hasAzureOpenai
        hasAnyProvider
        orgPreferredModel
        azureOpenaiEndpoint
        azureOpenaiDeployment
        ollamaEnabled
        openaiEnabled
        geminiEnabled
        claudeEnabled
        azureOpenaiEnabled
        configSource
        sharedProfileId
        sharedProfileName
        sharedProfileLocked
        canEditCustomSettings
      }
    }
  }
`;

const GET_SHARED_AI_PROFILES = gql`
  query GetSharedAiProfiles($includeInactive: Boolean) {
    sharedAiProfiles(includeInactive: $includeInactive) {
      id
      name
      hasAnyProvider
      isActive
      updatedAt
    }
  }
`;

const SET_SHARED_AI_PROFILE = gql`
  mutation SetSharedAiProfile(
    $id: UUID
    $name: String
    $ollamaBaseUrl: String
    $ollamaModel: String
    $openaiKey: String
    $geminiKey: String
    $claudeKey: String
    $azureOpenaiEndpoint: String
    $azureOpenaiKey: String
    $azureOpenaiDeployment: String
    $orgPreferredModel: String
    $ollamaEnabled: Boolean
    $openaiEnabled: Boolean
    $geminiEnabled: Boolean
    $claudeEnabled: Boolean
    $azureOpenaiEnabled: Boolean
    $isActive: Boolean
  ) {
    setSharedAiProfile(
      id: $id
      name: $name
      ollamaBaseUrl: $ollamaBaseUrl
      ollamaModel: $ollamaModel
      openaiKey: $openaiKey
      geminiKey: $geminiKey
      claudeKey: $claudeKey
      azureOpenaiEndpoint: $azureOpenaiEndpoint
      azureOpenaiKey: $azureOpenaiKey
      azureOpenaiDeployment: $azureOpenaiDeployment
      orgPreferredModel: $orgPreferredModel
      ollamaEnabled: $ollamaEnabled
      openaiEnabled: $openaiEnabled
      geminiEnabled: $geminiEnabled
      claudeEnabled: $claudeEnabled
      azureOpenaiEnabled: $azureOpenaiEnabled
      isActive: $isActive
    ) {
      ok
      message
      profile {
        id
        name
        hasAnyProvider
        isActive
      }
    }
  }
`;

const ASSIGN_SHARED_AI_PROFILE = gql`
  mutation AssignSharedAiProfile(
    $organizationId: UUID!
    $sharedProfileId: UUID
    $clearAssignment: Boolean
    $sharedProfileLocked: Boolean
  ) {
    assignSharedAiProfile(
      organizationId: $organizationId
      sharedProfileId: $sharedProfileId
      clearAssignment: $clearAssignment
      sharedProfileLocked: $sharedProfileLocked
    ) {
      ok
      message
      settings {
        id
        configSource
        sharedProfileId
        sharedProfileName
        sharedProfileLocked
        canEditCustomSettings
      }
    }
  }
`;

const GET_AUTH_SETTINGS = gql`
  query GetAuthSettings {
    authSettings {
      authMode
      defaultLoginProvider
      enableEntra
      enableOidc
      allowLocalBreakglass
      autoProvisionUsers
      syncClaimsOnLogin
      enforceLocalMfa
      breakglassUsernames
      entraTenantId
      entraClientId
      hasEntraClientSecret
      entraRedirectUri
      entraScopes
      entraEmailClaim
      entraUsernameClaim
      entraRoleClaim
      oidcIssuerUrl
      oidcClientId
      hasOidcClientSecret
      oidcRedirectUri
      oidcScopes
      oidcEmailClaim
      oidcUsernameClaim
      oidcRoleClaim
      oidcVerifySsl
      hasOidcCaCertificate
      roleAdminValues
      roleAnalystValues
      roleReviewerValues
      defaultProvisionedRole
      updatedAt
    }
  }
`;

const UPDATE_AUTH_SETTINGS = gql`
  mutation UpdateAuthSettings(
    $authMode: String
    $defaultLoginProvider: String
    $enableEntra: Boolean
    $enableOidc: Boolean
    $allowLocalBreakglass: Boolean
    $autoProvisionUsers: Boolean
    $syncClaimsOnLogin: Boolean
    $enforceLocalMfa: Boolean
    $breakglassUsernames: String
    $entraTenantId: String
    $entraClientId: String
    $entraClientSecret: String
    $entraRedirectUri: String
    $entraScopes: String
    $entraEmailClaim: String
    $entraUsernameClaim: String
    $entraRoleClaim: String
    $oidcIssuerUrl: String
    $oidcClientId: String
    $oidcClientSecret: String
    $oidcRedirectUri: String
    $oidcScopes: String
    $oidcEmailClaim: String
    $oidcUsernameClaim: String
    $oidcRoleClaim: String
    $oidcVerifySsl: Boolean
    $oidcCaCertificate: String
    $roleAdminValues: String
    $roleAnalystValues: String
    $roleReviewerValues: String
    $defaultProvisionedRole: String
  ) {
    updateAuthSettings(
      authMode: $authMode
      defaultLoginProvider: $defaultLoginProvider
      enableEntra: $enableEntra
      enableOidc: $enableOidc
      allowLocalBreakglass: $allowLocalBreakglass
      autoProvisionUsers: $autoProvisionUsers
      syncClaimsOnLogin: $syncClaimsOnLogin
      enforceLocalMfa: $enforceLocalMfa
      breakglassUsernames: $breakglassUsernames
      entraTenantId: $entraTenantId
      entraClientId: $entraClientId
      entraClientSecret: $entraClientSecret
      entraRedirectUri: $entraRedirectUri
      entraScopes: $entraScopes
      entraEmailClaim: $entraEmailClaim
      entraUsernameClaim: $entraUsernameClaim
      entraRoleClaim: $entraRoleClaim
      oidcIssuerUrl: $oidcIssuerUrl
      oidcClientId: $oidcClientId
      oidcClientSecret: $oidcClientSecret
      oidcRedirectUri: $oidcRedirectUri
      oidcScopes: $oidcScopes
      oidcEmailClaim: $oidcEmailClaim
      oidcUsernameClaim: $oidcUsernameClaim
      oidcRoleClaim: $oidcRoleClaim
      oidcVerifySsl: $oidcVerifySsl
      oidcCaCertificate: $oidcCaCertificate
      roleAdminValues: $roleAdminValues
      roleAnalystValues: $roleAnalystValues
      roleReviewerValues: $roleReviewerValues
      defaultProvisionedRole: $defaultProvisionedRole
    ) {
      ok
      message
      settings {
        authMode
        defaultLoginProvider
        enableEntra
        enableOidc
        allowLocalBreakglass
        autoProvisionUsers
        syncClaimsOnLogin
        enforceLocalMfa
        breakglassUsernames
        entraTenantId
        entraClientId
        hasEntraClientSecret
        entraRedirectUri
        entraScopes
        entraEmailClaim
        entraUsernameClaim
        entraRoleClaim
        oidcIssuerUrl
        oidcClientId
        hasOidcClientSecret
        oidcRedirectUri
        oidcScopes
        oidcEmailClaim
        oidcUsernameClaim
        oidcRoleClaim
        oidcVerifySsl
        hasOidcCaCertificate
        roleAdminValues
        roleAnalystValues
        roleReviewerValues
        defaultProvisionedRole
        updatedAt
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// GraphQL – Rule Repositories & MISP (from RepoListPage)
// ---------------------------------------------------------------------------

const GET_RULE_REPOSITORIES = gql`
  query GetRuleRepositories {
    me { username role }
    allRuleRepositories {
      id name url username verifySsl lastSync ruleCount
      autoPullEnabled autoPullSchedule nextScheduledPull
      ragSyncEnabled ragSyncSchedule ragDatasetPath ragBranch
      ragNextScheduledSync ragLastSynced ragLastSyncStatus ragLastSyncError ragLastSyncedTemplates
      ragFiles {
        id
        sourcePath
        sourceBranch
        language
        ingestionStatus
        templatesCount
        lastSyncedAt
        lastError
        usedInGeneration
        usageCount
        lastUsedAt
      }
    }
  }
`;
const GET_GRAPHS = gql`
  query GetAllPlaybookGraphsForPush {
    allPlaybookGraphs { id title status }
  }
`;
const PULL_RULE_REPOSITORY = gql`
  mutation PullRuleRepository($id: ID!) {
    pullRuleRepository(id: $id) { ok message repository { id lastSync } }
  }
`;
const PUSH_PLAYBOOK_TO_GIT = gql`
  mutation PushPlaybookToGit($graphId: UUID!, $repositoryId: String!, $targetFolder: String) {
    pushPlaybookToGit(graphId: $graphId, repositoryId: $repositoryId, targetFolder: $targetFolder) { ok queuedCount message }
  }
`;
const CREATE_RULE_REPOSITORY = gql`
  mutation CreateRuleRepository(
    $name: String!,
    $url: String!,
    $username: String,
    $token: String,
    $verifySsl: Boolean,
    $ragSyncEnabled: Boolean,
    $ragSyncSchedule: String,
    $ragDatasetPath: String,
    $ragBranch: String
  ) {
    createRuleRepository(
      name: $name,
      url: $url,
      username: $username,
      token: $token,
      verifySsl: $verifySsl,
      ragSyncEnabled: $ragSyncEnabled,
      ragSyncSchedule: $ragSyncSchedule,
      ragDatasetPath: $ragDatasetPath,
      ragBranch: $ragBranch
    ) {
      repository {
        id name url username verifySsl lastSync
        ragSyncEnabled ragSyncSchedule ragDatasetPath ragBranch
        ragNextScheduledSync ragLastSynced ragLastSyncStatus ragLastSyncError ragLastSyncedTemplates
      }
    }
  }
`;
const DELETE_RULE_REPOSITORY = gql`
  mutation DeleteRuleRepository($id: ID!) {
    deleteRuleRepository(id: $id) { ok }
  }
`;
const UPDATE_RULE_REPOSITORY = gql`
  mutation UpdateRuleRepository(
    $id: ID!,
    $url: String,
    $username: String,
    $token: String,
    $name: String,
    $verifySsl: Boolean,
    $autoPullEnabled: Boolean,
    $autoPullSchedule: String,
    $ragSyncEnabled: Boolean,
    $ragSyncSchedule: String,
    $ragDatasetPath: String,
    $ragBranch: String
  ) {
    updateRuleRepository(
      id: $id,
      url: $url,
      username: $username,
      token: $token,
      name: $name,
      verifySsl: $verifySsl,
      autoPullEnabled: $autoPullEnabled,
      autoPullSchedule: $autoPullSchedule,
      ragSyncEnabled: $ragSyncEnabled,
      ragSyncSchedule: $ragSyncSchedule,
      ragDatasetPath: $ragDatasetPath,
      ragBranch: $ragBranch
    ) {
      repository {
        id name url username verifySsl lastSync autoPullEnabled autoPullSchedule nextScheduledPull
        ragSyncEnabled ragSyncSchedule ragDatasetPath ragBranch
        ragNextScheduledSync ragLastSynced ragLastSyncStatus ragLastSyncError ragLastSyncedTemplates
      }
    }
  }
`;

const SYNC_RULE_REPOSITORY_RAG = gql`
  mutation SyncRuleRepositoryRag($id: ID!) {
    syncRuleRepositoryRag(id: $id) {
      ok
      message
      repository {
        id
        ragLastSynced
        ragLastSyncStatus
        ragLastSyncError
        ragLastSyncedTemplates
      }
    }
  }
`;

const GET_MISP_INSTANCES = gql`
  query GetMISPInstances {
    mispInstances {
      id
      name
      url
      verifySsl
      authKeyHint
      autoPullEnabled
      autoPullSchedule
      autoPullTag
      nextAutoPullAt
      createdAt
    }
  }
`;
const CREATE_MISP_INSTANCE = gql`
  mutation CreateMISPInstance(
    $name: String!
    $url: String!
    $authKey: String!
    $verifySsl: Boolean
    $autoPullEnabled: Boolean
    $autoPullSchedule: String
    $autoPullTag: String
  ) {
    createMispInstance(
      name: $name
      url: $url
      authKey: $authKey
      verifySsl: $verifySsl
      autoPullEnabled: $autoPullEnabled
      autoPullSchedule: $autoPullSchedule
      autoPullTag: $autoPullTag
    ) {
      success
      message
      mispInstance { id name url verifySsl authKeyHint autoPullEnabled autoPullSchedule autoPullTag nextAutoPullAt createdAt }
    }
  }
`;
const UPDATE_MISP_INSTANCE = gql`
  mutation UpdateMISPInstance(
    $id: UUID!
    $name: String
    $url: String
    $authKey: String
    $verifySsl: Boolean
    $autoPullEnabled: Boolean
    $autoPullSchedule: String
    $autoPullTag: String
  ) {
    updateMispInstance(
      id: $id
      name: $name
      url: $url
      authKey: $authKey
      verifySsl: $verifySsl
      autoPullEnabled: $autoPullEnabled
      autoPullSchedule: $autoPullSchedule
      autoPullTag: $autoPullTag
    ) {
      success
      message
      mispInstance { id name url verifySsl authKeyHint autoPullEnabled autoPullSchedule autoPullTag nextAutoPullAt createdAt }
    }
  }
`;
const DELETE_MISP_INSTANCE = gql`
  mutation DeleteMISPInstance($id: UUID!) {
    deleteMispInstance(id: $id) {
      success
      message
    }
  }
`;

const GET_SMTP_SETTINGS = gql`
  query GetSmtpSettings($organizationId: UUID) {
    smtpSettings(organizationId: $organizationId) {
      smtpServer
      smtpPort
      encryption
      loginMethod
      smtpUsername
      hasPassword
      fromEmail
      updatedAt
      source
      sharedProfileId
      sharedProfileName
      enforceShared
      customConfigured
      canEditCustom
      organizationId
    }
  }
`;

const UPSERT_SMTP_SETTINGS = gql`
  mutation UpsertSmtpSettings(
    $organizationId: UUID
    $smtpServer: String!
    $smtpPort: Int!
    $encryption: String!
    $loginMethod: String!
    $smtpUsername: String
    $smtpPassword: String
    $fromEmail: String
  ) {
    upsertSmtpSettings(
      organizationId: $organizationId
      smtpServer: $smtpServer
      smtpPort: $smtpPort
      encryption: $encryption
      loginMethod: $loginMethod
      smtpUsername: $smtpUsername
      smtpPassword: $smtpPassword
      fromEmail: $fromEmail
    ) {
      success
      message
      smtpSettings {
        smtpServer
        smtpPort
        encryption
        loginMethod
        smtpUsername
        hasPassword
        fromEmail
        updatedAt
        source
        sharedProfileId
        sharedProfileName
        enforceShared
        customConfigured
        canEditCustom
        organizationId
      }
    }
  }
`;

const GET_SHARED_SMTP_PROFILES = gql`
  query GetSharedSmtpProfiles($includeInactive: Boolean) {
    sharedSmtpProfiles(includeInactive: $includeInactive) {
      id
      name
      smtpServer
      smtpPort
      encryption
      loginMethod
      smtpUsername
      hasPassword
      fromEmail
      isActive
      updatedAt
    }
  }
`;

const SET_SHARED_SMTP_PROFILE = gql`
  mutation SetSharedSmtpProfile(
    $id: UUID
    $name: String
    $smtpServer: String!
    $smtpPort: Int!
    $encryption: String!
    $loginMethod: String!
    $smtpUsername: String
    $smtpPassword: String
    $fromEmail: String
    $isActive: Boolean
  ) {
    setSharedSmtpProfile(
      id: $id
      name: $name
      smtpServer: $smtpServer
      smtpPort: $smtpPort
      encryption: $encryption
      loginMethod: $loginMethod
      smtpUsername: $smtpUsername
      smtpPassword: $smtpPassword
      fromEmail: $fromEmail
      isActive: $isActive
    ) {
      success
      message
      profile {
        id
        name
        smtpServer
        smtpPort
        encryption
        loginMethod
        smtpUsername
        hasPassword
        fromEmail
        isActive
        updatedAt
      }
    }
  }
`;

const SET_ORGANIZATION_SMTP_POLICY = gql`
  mutation SetOrganizationSmtpPolicy(
    $organizationId: UUID!
    $sharedProfileId: UUID
    $enforceShared: Boolean
  ) {
    setOrganizationSmtpPolicy(
      organizationId: $organizationId
      sharedProfileId: $sharedProfileId
      enforceShared: $enforceShared
    ) {
      success
      message
      smtpSettings {
        source
        sharedProfileId
        sharedProfileName
        enforceShared
        canEditCustom
        organizationId
      }
    }
  }
`;

const GET_HEF_PUBLISH_PROFILES = gql`
  query GetOpenTideHefPublishProfilesForDac {
    opentideHefPublishProfiles {
      id
      name
    }
  }
`;

const GET_DAC_DEPLOYMENT_CONFIG = gql`
  query GetDacDeploymentConfig {
    dacDeploymentConfig {
      mode
      targetRepositoryId
      targetBranch
      targetFolder
      targetPlatforms
      publishProfileId
    }
    availableDeploymentPlatforms {
      key
      label
    }
  }
`;

const UPDATE_DAC_DEPLOYMENT_CONFIG = gql`
  mutation UpdateDacDeploymentConfig(
    $mode: String!
    $targetRepositoryId: ID
    $targetBranch: String
    $targetFolder: String
    $targetPlatforms: [String]
    $publishProfileId: UUID
  ) {
    updateDacDeploymentConfig(
      mode: $mode
      targetRepositoryId: $targetRepositoryId
      targetBranch: $targetBranch
      targetFolder: $targetFolder
      targetPlatforms: $targetPlatforms
      publishProfileId: $publishProfileId
    ) {
      success
      message
      config {
        mode
        targetRepositoryId
        targetBranch
        targetFolder
        targetPlatforms
        publishProfileId
      }
    }
  }
`;

const EXPORT_ALL_WORKBENCHES_HEX_V2 = gql`
  mutation ExportAllWorkbenchesHexV2 {
    exportAllWorkbenchesHexV2 {
      success
      fileData
      filename
      contentType
      message
    }
  }
`;

const MISP_INSTANCE_LIMIT = 5;
const RULE_FOLDER_PRESET_OPTIONS = [
  { value: 'rules/kql', label: 'rules/kql (Kusto Query Language)' },
  { value: 'rules/wazuh', label: 'rules/wazuh (Wazuh XML)' },
  { value: 'rules/splunk', label: 'rules/splunk (Splunk SPL)' },
  { value: 'rules/yara', label: 'rules/yara (YARA rules)' },
  { value: 'rules/snort', label: 'rules/snort (Snort/Suricata)' },
  { value: 'rules/other', label: 'rules/other (Other formats)' },
  { value: 'detections', label: 'detections/' },
  { value: '', label: '/ (repository root)' },
];

// ---------------------------------------------------------------------------
// TypeScript types
// ---------------------------------------------------------------------------

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  organization?: { id: string; name: string } | null;
  lastLogin: string | null;
  isStaff: boolean;
}

interface OrgAISettingsData {
  orgAiSettings: {
    id: string;
    ollamaBaseUrl: string;
    ollamaModel: string;
    hasOllama: boolean;
    hasOpenai: boolean;
    hasGemini: boolean;
    hasClaude: boolean;
    hasAzureOpenai: boolean;
    hasAnyProvider: boolean;
    orgPreferredModel: string;
    azureOpenaiEndpoint: string;
    azureOpenaiDeployment: string;
    ollamaEnabled: boolean;
    openaiEnabled: boolean;
    geminiEnabled: boolean;
    claudeEnabled: boolean;
    azureOpenaiEnabled: boolean;
    configSource?: 'CUSTOM' | 'SHARED' | 'SHARED_LOCKED' | string;
    sharedProfileId?: string | null;
    sharedProfileName?: string | null;
    sharedProfileLocked?: boolean;
    canEditCustomSettings?: boolean;
  } | null;
}

interface AuthSettingsShape {
  authMode: string;
  defaultLoginProvider: string;
  enableEntra: boolean;
  enableOidc: boolean;
  allowLocalBreakglass: boolean;
  autoProvisionUsers: boolean;
  syncClaimsOnLogin: boolean;
  enforceLocalMfa: boolean;
  breakglassUsernames: string;
  entraTenantId: string;
  entraClientId: string;
  hasEntraClientSecret: boolean;
  entraRedirectUri: string;
  entraScopes: string;
  entraEmailClaim: string;
  entraUsernameClaim: string;
  entraRoleClaim: string;
  oidcIssuerUrl: string;
  oidcClientId: string;
  hasOidcClientSecret: boolean;
  oidcRedirectUri: string;
  oidcScopes: string;
  oidcEmailClaim: string;
  oidcUsernameClaim: string;
  oidcRoleClaim: string;
  oidcVerifySsl: boolean;
  hasOidcCaCertificate: boolean;
  roleAdminValues: string;
  roleAnalystValues: string;
  roleReviewerValues: string;
  defaultProvisionedRole: string;
  updatedAt?: string | null;
}

interface AuthSettingsData {
  authSettings: AuthSettingsShape | null;
}

interface SharedAiProfile {
  id: string;
  name: string;
  hasAnyProvider: boolean;
  isActive: boolean;
  updatedAt?: string | null;
}

interface MISPInstance {
  id: string;
  name: string;
  url: string;
  verifySsl: boolean;
  authKeyHint: string;
  autoPullEnabled?: boolean;
  autoPullSchedule?: string;
  autoPullTag?: string;
  nextAutoPullAt?: string | null;
  createdAt: string;
}

interface SmtpSettings {
  smtpServer: string;
  smtpPort: number;
  encryption: 'NONE' | 'SSL' | 'STARTTLS';
  loginMethod: 'PLAIN' | 'LOGIN';
  smtpUsername?: string | null;
  hasPassword?: boolean | null;
  fromEmail?: string | null;
  updatedAt?: string | null;
  source?: 'CUSTOM' | 'SHARED' | 'SHARED_LOCKED' | 'LEGACY_GLOBAL' | string;
  sharedProfileId?: string | null;
  sharedProfileName?: string | null;
  enforceShared?: boolean;
  customConfigured?: boolean;
  canEditCustom?: boolean;
  organizationId?: string | null;
}

interface SharedSmtpProfile {
  id: string;
  name: string;
  smtpServer: string;
  smtpPort: number;
  encryption: 'NONE' | 'SSL' | 'STARTTLS';
  loginMethod: 'PLAIN' | 'LOGIN';
  smtpUsername?: string | null;
  hasPassword?: boolean | null;
  fromEmail?: string | null;
  isActive: boolean;
  updatedAt?: string | null;
}

interface Repo {
  id: string;
  name: string;
  url: string | null;
  username: string | null;
  verifySsl?: boolean;
  lastSync: string | null;
  ruleCount?: number;
  autoPullEnabled?: boolean;
  autoPullSchedule?: string;
  nextScheduledPull?: string | null;
  ragSyncEnabled?: boolean;
  ragSyncSchedule?: string;
  ragDatasetPath?: string;
  ragBranch?: string;
  ragNextScheduledSync?: string | null;
  ragLastSynced?: string | null;
  ragLastSyncStatus?: string;
  ragLastSyncError?: string;
  ragLastSyncedTemplates?: number;
  ragFiles?: RepoRAGFileStatus[];
}

interface RepoRAGFileStatus {
  id: string;
  sourcePath: string;
  sourceBranch?: string;
  language?: string;
  ingestionStatus?: string;
  templatesCount?: number;
  lastSyncedAt?: string | null;
  lastError?: string;
  usedInGeneration?: boolean;
  usageCount?: number;
  lastUsedAt?: string | null;
}

interface DacDeploymentConfig {
  mode: 'NONE' | 'GIT_PUSH' | 'GIT_PUSH_AND_DEPLOY' | 'DEPLOY_ONLY';
  targetRepositoryId?: string | null;
  targetBranch?: string | null;
  targetFolder?: string | null;
  targetPlatforms?: string[] | null;
  publishProfileId?: string | null;
}

interface DeploymentPlatformOption {
  key: string;
  label: string;
}

interface ExportAllWorkbenchesHexV2Response {
  exportAllWorkbenchesHexV2?: {
    success: boolean;
    fileData?: string | null;
    filename?: string | null;
    contentType?: string | null;
    message?: string | null;
  } | null;
}

export const REPOSITORIES_TAB_LABEL = 'Repos';

// ---------------------------------------------------------------------------
// MISP tab sub-component
// ---------------------------------------------------------------------------

const MISPTab: React.FC<{ role: string }> = ({ role }) => {
  const { message: msg } = App.useApp();
  const { data, loading, refetch } = useQuery<{ mispInstances: MISPInstance[] }>(GET_MISP_INSTANCES, { fetchPolicy: 'cache-and-network' });
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<MISPInstance | null>(null);
  const [form] = Form.useForm();

  const [createInstance, { loading: creating }] = useMutation(CREATE_MISP_INSTANCE, {
    onCompleted: (res) => {
      if (res.createMispInstance.success) {
        msg.success('MISP instance added');
        refetch();
        setModalVisible(false);
        form.resetFields();
      } else {
        msg.error(res.createMispInstance.message || 'Failed to add MISP instance');
      }
    },
  });
  const [updateInstance, { loading: updating }] = useMutation(UPDATE_MISP_INSTANCE, {
    onCompleted: (res) => {
      if (res.updateMispInstance.success) {
        msg.success('MISP instance updated');
        refetch();
        setModalVisible(false);
        setEditing(null);
        form.resetFields();
      } else {
        msg.error(res.updateMispInstance.message || 'Failed to update MISP instance');
      }
    },
  });
  const [deleteInstance] = useMutation(DELETE_MISP_INSTANCE, {
    onCompleted: (res) => {
      if (res.deleteMispInstance.success) {
        msg.success('MISP instance deleted');
        refetch();
      } else {
        msg.error(res.deleteMispInstance.message || 'Failed to delete MISP instance');
      }
    },
  });

  const canManage = role === 'ADMIN';
  const instances = data?.mispInstances || [];
  const atLimit = instances.length >= MISP_INSTANCE_LIMIT;

  const onAdd = () => { setEditing(null); form.resetFields(); setModalVisible(true); };
  const onEdit = (inst: MISPInstance) => {
    setEditing(inst);
    form.setFieldsValue({
      name: inst.name,
      url: inst.url,
      verifySsl: inst.verifySsl,
      authKey: '',
      autoPullEnabled: inst.autoPullEnabled || false,
      autoPullSchedule: inst.autoPullSchedule || 'DAILY',
      autoPullTag: inst.autoPullTag ?? 'HEFAISTOS',
    });
    setModalVisible(true);
  };
  const onDelete = (id: string) => { deleteInstance({ variables: { id } }); };
  const onModalOk = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        const vars: any = {
          id: editing.id,
          name: values.name,
          url: values.url,
          verifySsl: values.verifySsl,
          autoPullEnabled: values.autoPullEnabled || false,
          autoPullSchedule: values.autoPullSchedule || 'DAILY',
          autoPullTag: values.autoPullTag ?? '',
        };
        if (values.authKey) vars.authKey = values.authKey;
        updateInstance({ variables: vars });
      } else {
        createInstance({
          variables: {
            name: values.name,
            url: values.url,
            authKey: values.authKey,
            verifySsl: values.verifySsl,
            autoPullEnabled: values.autoPullEnabled || false,
            autoPullSchedule: values.autoPullSchedule || 'DAILY',
            autoPullTag: values.autoPullTag ?? 'HEFAISTOS',
          },
        });
      }
    } catch { /* validation failed */ }
  };

  const mispColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'URL', dataIndex: 'url', key: 'url' },
    {
      title: 'Auth Key',
      dataIndex: 'authKeyHint',
      key: 'authKeyHint',
      render: (hint: string) => (
        <Space>
          <LockOutlined />
          <Typography.Text type="secondary">{hint}</Typography.Text>
        </Space>
      ),
    },
    {
      title: 'Verify SSL',
      dataIndex: 'verifySsl',
      key: 'verifySsl',
      render: (v: boolean) => <Tag color={v ? 'green' : 'orange'}>{v ? 'Yes' : 'No'}</Tag>,
    },
    {
      title: 'Auto-Pull', dataIndex: 'autoPullEnabled', key: 'autoPull', render: (_: any, inst: MISPInstance) => (
        inst.autoPullEnabled ? (
          <Tooltip title={`Pulls ${inst.autoPullSchedule?.toLowerCase() || ''}, tag: ${inst.autoPullTag || 'any'}${inst.nextAutoPullAt ? ` — next: ${new Date(inst.nextAutoPullAt).toLocaleString()}` : ''}`}>
            <Space><ClockCircleOutlined style={{ color: '#52c41a' }} /><Typography.Text type="success">On</Typography.Text></Space>
          </Tooltip>
        ) : <Typography.Text type="secondary">Off</Typography.Text>
      )
    },
    ...(canManage ? [{
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: MISPInstance) => (
        <Space>
          <Tooltip title="Edit">
            <AntButton size="small" icon={<EditOutlined />} onClick={() => onEdit(record)} />
          </Tooltip>
          <Popconfirm title="Delete this MISP instance?" onConfirm={() => onDelete(record.id)} okText="Delete" okButtonProps={{ danger: true }}>
            <Tooltip title="Delete">
              <AntButton size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    }] : []),
  ];

  return (
    <Card
      loading={loading}
      extra={
        canManage && (
          <Tooltip title={atLimit ? `Maximum of ${MISP_INSTANCE_LIMIT} instances per organization` : 'Add MISP instance'}>
            <AntButton type="primary" icon={<PlusOutlined />} onClick={onAdd} disabled={atLimit}>
              Add Instance
            </AntButton>
          </Tooltip>
        )
      }
    >
      {!canManage && (
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          Only Admins can manage MISP instances.
        </Typography.Text>
      )}
      {atLimit && (
        <Typography.Text type="warning" style={{ display: 'block', marginBottom: 12 }}>
          Maximum of {MISP_INSTANCE_LIMIT} MISP instances reached.
        </Typography.Text>
      )}
      <Table
        rowKey="id"
        dataSource={instances}
        columns={mispColumns}
        pagination={false}
        locale={{ emptyText: 'No MISP instances configured. Add one to enable per-hunt MISP push.' }}
      />
      <Modal
        title={editing ? 'Edit MISP Instance' : 'Add MISP Instance'}
        open={modalVisible}
        onOk={onModalOk}
        onCancel={() => { setModalVisible(false); setEditing(null); form.resetFields(); }}
        confirmLoading={creating || updating}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ verifySsl: true, autoPullEnabled: false, autoPullSchedule: 'DAILY', autoPullTag: 'HEFAISTOS' }}>
          <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Name is required' }]}>
            <Input placeholder="e.g., Production MISP" />
          </Form.Item>
          <Form.Item name="url" label="URL" rules={[{ required: true, message: 'URL is required' }, { type: 'url', message: 'Enter a valid URL' }]}>
            <Input placeholder="https://misp.example.com" />
          </Form.Item>
          <Form.Item
            name="authKey"
            label="Auth Key"
            rules={editing ? [] : [{ required: true, message: 'Auth key is required' }]}
            extra={editing ? 'Leave blank to keep the existing key.' : undefined}
          >
            <Input.Password placeholder={editing ? '(unchanged)' : 'MISP API auth key'} />
          </Form.Item>
          <Form.Item name="verifySsl" label="Verify SSL" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Divider orientation="left" plain><Space><ClockCircleOutlined />Scheduled Pull</Space></Divider>
          <Form.Item label="Enable Auto-Pull" name="autoPullEnabled" valuePropName="checked" tooltip="When enabled, Waiting Room cases are imported from this MISP instance automatically at the scheduled interval — no manual Import click needed.">
            <Switch />
          </Form.Item>
          <Form.Item label="Pull Schedule" name="autoPullSchedule" tooltip="How often to automatically pull new events from this instance">
            <Select options={[{ value: 'HOURLY', label: 'Hourly' }, { value: 'DAILY', label: 'Daily' }, { value: 'WEEKLY', label: 'Weekly' }]} />
          </Form.Item>
          <Form.Item name="autoPullTag" label="Required tag" tooltip="Only events carrying this tag are auto-imported. Leave blank to import all events on schedule.">
            <Input placeholder="HEFAISTOS" />
          </Form.Item>
          {editing?.nextAutoPullAt && (
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              Next scheduled pull: {new Date(editing.nextAutoPullAt).toLocaleString()}
            </Typography.Text>
          )}
        </Form>
      </Modal>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Repositories tab sub-component
// ---------------------------------------------------------------------------

export const ReposTab: React.FC = () => {
  const { message: msg } = App.useApp();
  const { data, loading, error, refetch, startPolling, stopPolling } = useQuery<{ me?: { username: string; role: string } | null; allRuleRepositories: Repo[] }>(GET_RULE_REPOSITORIES, { fetchPolicy: 'cache-and-network' });
  const { data: graphsData, loading: loadingGraphs } = useQuery<{ allPlaybookGraphs: { id: string; title: string; status?: string }[] }>(GET_GRAPHS, { fetchPolicy: 'cache-first' });
  const [pullRepository, { loading: pulling }] = useMutation<{ pullRuleRepository: { ok: boolean; message?: string; repository: { id: string; lastSync: string | null } } }>(PULL_RULE_REPOSITORY);
  const [syncRepositoryRag] = useMutation<{ syncRuleRepositoryRag: { ok: boolean; message?: string; repository: Repo } }>(SYNC_RULE_REPOSITORY_RAG);
  const [pushPlaybookToGit, { loading: pushing }] = useMutation<{ pushPlaybookToGit: { ok: boolean; queuedCount?: number; message?: string } }>(PUSH_PLAYBOOK_TO_GIT);
  const [createRepository, { loading: creating }] = useMutation(CREATE_RULE_REPOSITORY, {
    onCompleted: () => { msg.success('Repository created'); refetch(); },
    onError: (err) => msg.error(err.message || 'Create failed'),
  });
  const [deleteRepository, { loading: deleting }] = useMutation(DELETE_RULE_REPOSITORY, {
    onCompleted: () => { msg.success('Repository deleted'); refetch(); },
    onError: (err) => msg.error(err.message || 'Delete failed'),
  });
  const [updateRepository, { loading: saving }] = useMutation(UPDATE_RULE_REPOSITORY, {
    onCompleted: () => { msg.success('Repository updated'); refetch(); },
    onError: (err) => msg.error(err.message || 'Update failed'),
  });

  const role = data?.me?.role || 'VIEWER';
  const canAdmin = role === 'ADMIN';

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingRepo, setEditingRepo] = useState<Repo | null>(null);
  const [form] = Form.useForm();
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [pushForm] = Form.useForm();
  const [targetRepoForPush, setTargetRepoForPush] = useState<Repo | null>(null);
  const [folderMode, setFolderMode] = useState<'auto' | 'preset' | 'new'>('auto');
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncingRepoId, setSyncingRepoId] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const pollingTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollingTimeoutRef.current) window.clearTimeout(pollingTimeoutRef.current);
      stopPolling();
    };
  }, [stopPolling]);

  const openCreateModal = () => { setEditingRepo(null); form.resetFields(); setIsModalOpen(true); };
  const openEditModal = (repo: Repo) => {
    setEditingRepo(repo);
    form.setFieldsValue({
      name: repo.name,
      url: repo.url || '',
      username: repo.username || '',
      token: '',
      verifySsl: repo.verifySsl ?? true,
      autoPullEnabled: repo.autoPullEnabled || false,
      autoPullSchedule: repo.autoPullSchedule || 'DISABLED',
      ragSyncEnabled: repo.ragSyncEnabled || false,
      ragSyncSchedule: repo.ragSyncSchedule || 'DISABLED',
      ragDatasetPath: repo.ragDatasetPath || '',
      ragBranch: repo.ragBranch || 'main',
    });
    setIsModalOpen(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      if (editingRepo) {
        await updateRepository({ variables: { id: editingRepo.id, ...values } });
      } else {
        await createRepository({ variables: values });
      }
      setIsModalOpen(false);
      setEditingRepo(null);
      form.resetFields();
      setLastUpdatedAt(new Date());
    } catch { /* validation or mutation error */ }
  };

  const handlePull = async (repoId: string) => {
    const result = await pullRepository({ variables: { id: repoId } });
    const pullResult = result.data?.pullRuleRepository;
    if (!pullResult?.ok) { msg.error(pullResult?.message || 'Failed to queue pull request'); return; }
    msg.success(pullResult.message || 'Pull requested');
    setIsSyncing(true);
    startPolling(3000);
    if (pollingTimeoutRef.current) window.clearTimeout(pollingTimeoutRef.current);
    pollingTimeoutRef.current = window.setTimeout(async () => {
      stopPolling(); setIsSyncing(false); await refetch(); setLastUpdatedAt(new Date());
    }, 15000);
  };

  const handleSyncNow = async (repoId: string) => {
    setSyncingRepoId(repoId);
    try {
      const result = await syncRepositoryRag({ variables: { id: repoId } });
      const syncResult = result.data?.syncRuleRepositoryRag;
      if (!syncResult?.ok) {
        msg.error(syncResult?.message || 'Failed to queue RAG sync');
        return;
      }
      msg.success(syncResult.message || 'RAG sync queued');
      setIsSyncing(true);
      startPolling(3000);
      if (pollingTimeoutRef.current) window.clearTimeout(pollingTimeoutRef.current);
      pollingTimeoutRef.current = window.setTimeout(async () => {
        stopPolling();
        setIsSyncing(false);
        await refetch();
        setLastUpdatedAt(new Date());
      }, 20000);
    } catch (e: any) {
      msg.error(e?.message || 'Failed to queue RAG sync');
    } finally {
      setSyncingRepoId(null);
    }
  };

  const openPushModal = (repo: Repo) => {
    setTargetRepoForPush(repo);
    pushForm.resetFields();
    pushForm.setFieldsValue({ folderMode: 'auto' });
    setFolderMode('auto');
    setIsPushModalOpen(true);
  };

  const handlePush = async () => {
    try {
      const values = await pushForm.validateFields();
      if (!targetRepoForPush) return;
      let targetFolder = values.targetFolder;
      if (values.folderMode === 'new' && values.newFolderName) targetFolder = values.newFolderName.trim();
      const res = await pushPlaybookToGit({ variables: { graphId: values.graphId, repositoryId: targetRepoForPush.id, targetFolder: targetFolder || undefined } });
      const pushResult = res.data?.pushPlaybookToGit;
      if (!pushResult?.ok) { msg.error(pushResult?.message || 'Failed to queue push request'); return; }
      const cnt = pushResult.queuedCount ?? 0;
      if (cnt > 0) { msg.success(`Queued ${cnt} rule${cnt === 1 ? '' : 's'} for push`); } else { msg.info(pushResult.message || 'No rules to push'); }
      setIsPushModalOpen(false);
      setTargetRepoForPush(null);
      if (cnt > 0) {
        setIsSyncing(true); startPolling(3000);
        if (pollingTimeoutRef.current) window.clearTimeout(pollingTimeoutRef.current);
        pollingTimeoutRef.current = window.setTimeout(async () => { stopPolling(); setIsSyncing(false); await refetch(); setLastUpdatedAt(new Date()); }, 15000);
      }
    } catch (e: any) { msg.error(e?.message || 'Push failed'); }
  };

  const updatedHint = useMemo(() => {
    if (isSyncing) return 'Syncing…';
    if (!lastUpdatedAt) return undefined;
    const diff = (Date.now() - lastUpdatedAt.getTime()) / 1000;
    if (diff < 30) return 'Updated just now';
    const minutes = Math.floor(diff / 60);
    if (minutes < 60) return `Updated ${minutes}m ago`;
    return `Updated ${Math.floor(minutes / 60)}h ago`;
  }, [isSyncing, lastUpdatedAt]);

  const ragStatusColor = (status?: string) => {
    const normalized = (status || 'IDLE').toUpperCase();
    if (normalized === 'SUCCESS') return 'green';
    if (normalized === 'PARTIAL') return 'orange';
    if (normalized === 'FAILED') return 'red';
    if (normalized === 'RUNNING') return 'processing';
    if (normalized === 'QUEUED') return 'gold';
    return 'default';
  };

  const columns = [
    { title: 'Name', dataIndex: 'name', key: 'name', width: 160 },
    {
      title: 'Git URL',
      dataIndex: 'url',
      key: 'url',
      width: 300,
      render: (url: string | null) => url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          style={{ display: 'inline-block', maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
          title={url}
        >
          {url}
        </a>
      ) : <Typography.Text type="secondary">N/A</Typography.Text>
    },
    { title: 'Username', dataIndex: 'username', key: 'username', width: 140, render: (u: string | null) => u || <Typography.Text type="secondary">N/A</Typography.Text> },
    { title: 'Last Synced', dataIndex: 'lastSync', key: 'lastSync', width: 180, render: (d: string | null) => d ? new Date(d).toLocaleString() : <Typography.Text type="secondary">Never</Typography.Text> },
    {
      title: 'Auto-Pull', dataIndex: 'autoPullEnabled', key: 'autoPull', width: 120, render: (_: any, repo: Repo) => (
        repo.autoPullEnabled ? (
          <Tooltip title={`Pulls ${repo.autoPullSchedule?.replace('H', ' hours') || ''}`}>
            <Space><ClockCircleOutlined style={{ color: '#52c41a' }} /><Typography.Text type="success">On</Typography.Text></Space>
          </Tooltip>
        ) : <Typography.Text type="secondary">Off</Typography.Text>
      )
    },
    {
      title: 'RAG Dataset',
      key: 'ragDataset',
      width: 240,
      render: (_: any, repo: Repo) => {
        const path = (repo.ragDatasetPath || '').trim();
        const branch = repo.ragBranch || 'main';
        if (!path) return <Typography.Text type="secondary">Not configured</Typography.Text>;
        return (
          <Space direction="vertical" size={0}>
            <Typography.Text code style={{ maxWidth: 220 }} ellipsis={{ tooltip: path }}>{path}</Typography.Text>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>branch: {branch}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: 'RAG Files',
      key: 'ragFiles',
      width: 190,
      render: (_: any, repo: Repo) => {
        const ragFiles = Array.isArray(repo.ragFiles) ? repo.ragFiles : [];
        if (!ragFiles.length) {
          return <Typography.Text type="secondary">No file statuses yet</Typography.Text>;
        }

        const ingestedCount = ragFiles.filter((file) => (file.ingestionStatus || '').toUpperCase() === 'INGESTED').length;
        const usedCount = ragFiles.filter((file) => Boolean(file.usedInGeneration)).length;
        const totalUsageCount = ragFiles.reduce((sum, file) => sum + (file.usageCount || 0), 0);
        const failedCount = Math.max(ragFiles.length - ingestedCount, 0);

        return (
          <Space direction="vertical" size={2}>
            <Space wrap>
              <Tag color={failedCount > 0 ? 'orange' : 'green'}>{ingestedCount}/{ragFiles.length} ingested</Tag>
              <Tag color={usedCount > 0 ? 'blue' : 'default'}>{usedCount} used in AI</Tag>
            </Space>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>usage events: {totalUsageCount}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: 'RAG Sync',
      key: 'ragSync',
      width: 260,
      render: (_: any, repo: Repo) => (
        <Space direction="vertical" size={2}>
          <Space>
            <Tag color={ragStatusColor(repo.ragLastSyncStatus)}>{(repo.ragLastSyncStatus || 'IDLE').toUpperCase()}</Tag>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
              {(repo.ragLastSyncedTemplates || 0)} templates
            </Typography.Text>
          </Space>
          <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
            {repo.ragLastSynced ? `Last: ${new Date(repo.ragLastSynced).toLocaleString()}` : 'Last: Never'}
          </Typography.Text>
          {repo.ragLastSyncError ? (
            <Tooltip title={repo.ragLastSyncError}>
              <Typography.Text type="danger" ellipsis style={{ maxWidth: 260 }}>Error: {repo.ragLastSyncError}</Typography.Text>
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
    { title: 'Rules', dataIndex: 'ruleCount', key: 'ruleCount', width: 90, render: (_: any, repo: Repo) => <>{typeof repo.ruleCount === 'number' ? <Link to={`/rules?repo=${repo.id}`}>{repo.ruleCount}</Link> : 0}</> },
    {
      title: 'Actions', key: 'actions', width: 320,
      render: (_: any, repo: Repo) => (
        <Space wrap>
          <AntButton type="primary" size="small" disabled={!canAdmin} loading={pulling || isSyncing} onClick={() => handlePull(repo.id)}>Pull</AntButton>
          <AntButton
            size="small"
            disabled={!canAdmin}
            loading={syncingRepoId === repo.id || isSyncing}
            onClick={() => handleSyncNow(repo.id)}
          >
            Sync Now
          </AntButton>
          <AntButton size="small" disabled={!canAdmin} loading={pushing || isSyncing} onClick={() => openPushModal(repo)}>Push</AntButton>
          <AntButton size="small" disabled={!canAdmin} loading={saving} onClick={() => openEditModal(repo)}>Edit</AntButton>
          <Popconfirm title="Delete this repository?" okButtonProps={{ danger: true }} okText="Delete" onConfirm={() => deleteRepository({ variables: { id: repo.id } })} disabled={!canAdmin}>
            <AntButton size="small" danger disabled={!canAdmin} loading={deleting}>Delete</AntButton>
          </Popconfirm>
          {!canAdmin && <Typography.Text type="secondary">Admin only</Typography.Text>}
        </Space>
      )
    },
  ];

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          {updatedHint && <Typography.Text type="secondary">{updatedHint}</Typography.Text>}
          <AntButton onClick={() => { refetch(); setLastUpdatedAt(new Date()); }}>Refresh</AntButton>
          {canAdmin && <AntButton type="primary" onClick={openCreateModal}>New Repository</AntButton>}
        </Space>
      </Space>
      {error && <div style={{ marginBottom: 16 }}><Typography.Text type="danger">{error.message}</Typography.Text></div>}
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data?.allRuleRepositories || []}
          columns={columns as any}
          scroll={{ x: 1800 }}
        />
        <Modal
          title={editingRepo ? 'Edit Repository' : 'New Repository'}
          open={isModalOpen}
          onOk={handleModalOk}
          onCancel={() => { setIsModalOpen(false); setEditingRepo(null); }}
          confirmLoading={saving || creating}
          destroyOnClose
        >
          <Form
            layout="vertical"
            form={form}
            preserve={false}
            initialValues={{
              verifySsl: true,
              ragSyncEnabled: false,
              ragSyncSchedule: 'DISABLED',
              ragBranch: 'main',
            }}
          >
            <Form.Item label="Name" name="name" rules={editingRepo ? [] : [{ required: true, message: 'Name is required' }]}>
              <Input placeholder="My Rules Repo" />
            </Form.Item>
            <Form.Item label="Git URL" name="url" rules={editingRepo ? [] : [{ required: true, message: 'Git URL is required' }]}>
              <Input placeholder="https://github.com/org/repo.git" />
            </Form.Item>
            <Form.Item label="Username" name="username">
              <Input placeholder="git username (optional)" />
            </Form.Item>
            <Form.Item label="Token/Password" name="token">
              <Input.Password placeholder="access token (optional)" autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              label="Verify SSL"
              name="verifySsl"
              valuePropName="checked"
              tooltip="Disable only for trusted self-signed certificates."
            >
              <Switch />
            </Form.Item>
            {editingRepo && (
              <>
                <Divider orientation="left" plain><Space><ClockCircleOutlined />Scheduled Pull</Space></Divider>
                <Form.Item label="Enable Auto-Pull" name="autoPullEnabled" valuePropName="checked" tooltip="When enabled, the repository will be automatically pulled at the scheduled interval">
                  <Switch />
                </Form.Item>
                <Form.Item label="Pull Schedule" name="autoPullSchedule" tooltip="How often to automatically pull updates from this repository">
                  <Select options={[{ value: 'DISABLED', label: 'Disabled' }, { value: '24H', label: 'Every 24 hours' }, { value: '48H', label: 'Every 48 hours' }, { value: '72H', label: 'Every 72 hours' }, { value: 'WEEKLY', label: 'Weekly' }]} />
                </Form.Item>
                {editingRepo.nextScheduledPull && (
                  <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                    Next scheduled pull: {new Date(editingRepo.nextScheduledPull).toLocaleString()}
                  </Typography.Text>
                )}
              </>
            )}
            <>
              <Divider orientation="left" plain>RAG Template Sync</Divider>
              <Form.Item
                label="Enable RAG Sync"
                name="ragSyncEnabled"
                valuePropName="checked"
                tooltip="When enabled, JSONL/KQL/EQL/SPL templates can be synced into Qdrant for grounded generation."
              >
                <Switch />
              </Form.Item>
              <Form.Item
                label="RAG Dataset Path / Pattern"
                name="ragDatasetPath"
                tooltip="Repository-relative path or glob pattern (e.g., data-kql/**/*.jsonl, data-eql/**/*.jsonl, data-spl/**/*.jsonl, rules/kql/**/*.kql, rules/eql/**/*.eql, rules/spl/**/*.spl)."
              >
                <Input placeholder="rules/templates/**/*.jsonl" />
              </Form.Item>
              <Form.Item label="RAG Branch" name="ragBranch" tooltip="Branch to clone for template sync.">
                <Input placeholder="main" />
              </Form.Item>
              <Form.Item label="RAG Sync Schedule" name="ragSyncSchedule" tooltip="How often automatic RAG sync should run when enabled.">
                <Select options={[{ value: 'DISABLED', label: 'Disabled' }, { value: '24H', label: 'Every 24 hours' }, { value: '48H', label: 'Every 48 hours' }, { value: '72H', label: 'Every 72 hours' }, { value: 'WEEKLY', label: 'Weekly' }]} />
              </Form.Item>
              {editingRepo?.ragNextScheduledSync && (
                <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                  Next scheduled RAG sync: {new Date(editingRepo.ragNextScheduledSync).toLocaleString()}
                </Typography.Text>
              )}
            </>
          </Form>
        </Modal>
        <Modal
          title={targetRepoForPush ? `Push Workbench to ${targetRepoForPush.name}` : 'Push Workbench'}
          open={isPushModalOpen}
          onOk={handlePush}
          onCancel={() => { setIsPushModalOpen(false); setTargetRepoForPush(null); }}
          confirmLoading={pushing || isSyncing}
          destroyOnClose
          width={520}
        >
          <Form layout="vertical" form={pushForm} preserve={false}>
            <Form.Item label="Workbench" name="graphId" rules={[{ required: true, message: 'Select a workbench to push' }]}>
              <Select
                placeholder={loadingGraphs ? 'Loading workbenches...' : 'Select a workbench'}
                loading={loadingGraphs}
                showSearch
                optionFilterProp="label"
                options={(graphsData?.allPlaybookGraphs || [])
                  .filter(g => ['APPROVED', 'DEPLOYED'].includes((g.status || '').toUpperCase()))
                  .map(g => ({ value: g.id, label: `${g.title}${g.status ? ` (${g.status})` : ''}` }))}
              />
            </Form.Item>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              Only workbenches in status APPROVED or DEPLOYED are eligible for push.
            </Typography.Text>
            <Divider orientation="left" plain>Target Folder</Divider>
            <Form.Item name="folderMode" initialValue="auto">
              <Radio.Group onChange={(e) => setFolderMode(e.target.value)} value={folderMode}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Radio value="auto"><strong>Auto-organize by format</strong><Typography.Text type="secondary" style={{ display: 'block', marginLeft: 24 }}>Rules will be placed in folders based on their format (rules/kql, rules/wazuh, etc.)</Typography.Text></Radio>
                  <Radio value="preset"><strong>Choose existing folder</strong></Radio>
                  <Radio value="new"><strong>Create new folder</strong></Radio>
                </Space>
              </Radio.Group>
            </Form.Item>
            {folderMode === 'preset' && (
              <Form.Item name="targetFolder" label="Select folder" rules={[{ required: folderMode === 'preset', message: 'Select a folder' }]}>
                <Select placeholder="Select target folder" showSearch optionFilterProp="label" options={RULE_FOLDER_PRESET_OPTIONS} />
              </Form.Item>
            )}
            {folderMode === 'new' && (
              <Form.Item name="newFolderName" label="New folder path" rules={[{ required: folderMode === 'new', message: 'Enter a folder path' }]} help="Use forward slashes for nested folders (e.g., detections/windows/process)">
                <Input placeholder="rules/custom" />
              </Form.Item>
            )}
          </Form>
        </Modal>
      </Card>
    </>
  );
};

const SMTPTab: React.FC<{ canManage: boolean; isSuperuser: boolean; organizations: { id: string; name: string }[] }> = ({ canManage, isSuperuser, organizations }) => {
  const { message: msg } = App.useApp();
  const [form] = Form.useForm();
  const [targetOrgId, setTargetOrgId] = useState<string | undefined>(undefined);
  const [sharedProfileName, setSharedProfileName] = useState('');
  const [selectedSharedProfileId, setSelectedSharedProfileId] = useState<string | undefined>(undefined);
  const [enforceShared, setEnforceShared] = useState(false);

  useEffect(() => {
    if (isSuperuser && !targetOrgId && organizations.length > 0) {
      setTargetOrgId(organizations[0].id);
    }
  }, [isSuperuser, organizations, targetOrgId]);

  const orgIdForQuery = isSuperuser ? targetOrgId || null : null;
  const skipForMissingTarget = Boolean(isSuperuser && organizations.length > 0 && !targetOrgId);

  const { data, loading, refetch } = useQuery<{ smtpSettings: SmtpSettings | null }>(GET_SMTP_SETTINGS, {
    variables: { organizationId: orgIdForQuery },
    fetchPolicy: 'cache-and-network',
    errorPolicy: 'all',
    skip: !canManage || skipForMissingTarget,
  });
  const { data: sharedProfilesData, refetch: refetchSharedProfiles } = useQuery<{ sharedSmtpProfiles: SharedSmtpProfile[] }>(
    GET_SHARED_SMTP_PROFILES,
    {
      variables: { includeInactive: false },
      fetchPolicy: 'cache-and-network',
      skip: !isSuperuser,
    },
  );
  const [setOrganizationSmtpPolicy, { loading: savingPolicy }] = useMutation(SET_ORGANIZATION_SMTP_POLICY, {
    onCompleted: (res) => {
      if (res?.setOrganizationSmtpPolicy?.success) {
        msg.success(res.setOrganizationSmtpPolicy.message || 'SMTP policy updated');
        refetch();
      } else {
        msg.error(res?.setOrganizationSmtpPolicy?.message || 'Failed to update SMTP policy');
      }
    },
    onError: (err) => msg.error(err.message || 'Failed to update SMTP policy'),
  });
  const [setSharedSmtpProfile, { loading: savingSharedProfile }] = useMutation(SET_SHARED_SMTP_PROFILE, {
    onCompleted: (res) => {
      if (res?.setSharedSmtpProfile?.success) {
        msg.success(res.setSharedSmtpProfile.message || 'Shared SMTP profile saved');
        setSharedProfileName('');
        refetchSharedProfiles();
      } else {
        msg.error(res?.setSharedSmtpProfile?.message || 'Failed to save shared SMTP profile');
      }
    },
    onError: (err) => msg.error(err.message || 'Failed to save shared SMTP profile'),
  });
  const [upsertSmtpSettings, { loading: saving }] = useMutation(UPSERT_SMTP_SETTINGS, {
    onCompleted: (res) => {
      if (res?.upsertSmtpSettings?.success) {
        msg.success(res.upsertSmtpSettings.message || 'SMTP settings saved');
        refetch();
        form.setFieldsValue({ smtpPassword: '' });
      } else {
        msg.error(res?.upsertSmtpSettings?.message || 'Failed to save SMTP settings');
      }
    },
    onError: (err) => msg.error(err.message || 'Failed to save SMTP settings'),
  });

  const loginMethod = Form.useWatch('loginMethod', form) || 'PLAIN';
  const smtpSettings = data?.smtpSettings;
  const customLocked = Boolean(smtpSettings?.enforceShared) && !isSuperuser;
  const canEditCustom = canManage && !customLocked;

  useEffect(() => {
    if (smtpSettings) {
      form.setFieldsValue({
        smtpServer: smtpSettings.smtpServer || '',
        smtpPort: smtpSettings.smtpPort || 587,
        encryption: smtpSettings.encryption || 'STARTTLS',
        loginMethod: smtpSettings.loginMethod || 'PLAIN',
        smtpUsername: smtpSettings.smtpUsername || '',
        smtpPassword: '',
        fromEmail: smtpSettings.fromEmail || '',
      });
    } else {
      form.setFieldsValue({
        smtpServer: '',
        smtpPort: 587,
        encryption: 'STARTTLS',
        loginMethod: 'PLAIN',
        smtpUsername: '',
        smtpPassword: '',
        fromEmail: '',
      });
    }
  }, [form, smtpSettings]);

  useEffect(() => {
    if (!isSuperuser) {
      return;
    }
    setSelectedSharedProfileId(smtpSettings?.sharedProfileId || undefined);
    setEnforceShared(Boolean(smtpSettings?.enforceShared));
  }, [isSuperuser, smtpSettings?.sharedProfileId, smtpSettings?.enforceShared]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      await upsertSmtpSettings({
        variables: {
          organizationId: isSuperuser ? targetOrgId || null : null,
          smtpServer: values.smtpServer,
          smtpPort: Number(values.smtpPort),
          encryption: values.encryption,
          loginMethod: values.loginMethod,
          smtpUsername: values.loginMethod === 'LOGIN' ? (values.smtpUsername || null) : null,
          smtpPassword: values.loginMethod === 'LOGIN'
            ? ((values.smtpPassword && String(values.smtpPassword).trim()) ? values.smtpPassword : null)
            : null,
          fromEmail: values.fromEmail ? values.fromEmail : null,
        },
      });
    } catch {
      // form validation errors are shown inline
    }
  };

  const handleSaveAsSharedProfile = async () => {
    if (!isSuperuser) return;
    if (!sharedProfileName.trim()) {
      msg.error('Shared profile name is required');
      return;
    }
    try {
      const values = await form.validateFields();
      await setSharedSmtpProfile({
        variables: {
          name: sharedProfileName.trim(),
          smtpServer: values.smtpServer,
          smtpPort: Number(values.smtpPort),
          encryption: values.encryption,
          loginMethod: values.loginMethod,
          smtpUsername: values.loginMethod === 'LOGIN' ? (values.smtpUsername || null) : null,
          smtpPassword: values.loginMethod === 'LOGIN'
            ? ((values.smtpPassword && String(values.smtpPassword).trim()) ? values.smtpPassword : null)
            : null,
          fromEmail: values.fromEmail ? values.fromEmail : null,
          isActive: true,
        },
      });
    } catch {
      // form validation errors are shown inline
    }
  };

  const handleApplyPolicy = async () => {
    if (!isSuperuser || !targetOrgId) return;
    if (!selectedSharedProfileId) {
      msg.error('Select a shared SMTP profile first.');
      return;
    }
    await setOrganizationSmtpPolicy({
      variables: {
        organizationId: targetOrgId,
        sharedProfileId: selectedSharedProfileId,
        enforceShared,
      },
    });
  };

  return (
    <Card loading={loading}>
      {!canManage && (
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          Only Admins can manage SMTP settings.
        </Typography.Text>
      )}
      <Typography.Paragraph type="secondary">
        When SMTP is configured, it overrides Mailgun API for outgoing emails.
      </Typography.Paragraph>
      {isSuperuser && organizations.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Typography.Text strong>Target Organization</Typography.Text>
          <Select
            style={{ width: '100%', marginTop: 8 }}
            value={targetOrgId}
            onChange={setTargetOrgId}
            options={organizations.map((org) => ({ value: org.id, label: org.name }))}
          />
        </div>
      )}
      <Typography.Paragraph type="secondary">
        Current source: <Typography.Text code>{smtpSettings?.source || 'UNSET'}</Typography.Text>
        {smtpSettings?.sharedProfileName ? ` (${smtpSettings.sharedProfileName})` : ''}
      </Typography.Paragraph>
      {customLocked && (
        <Typography.Text type="warning" style={{ display: 'block', marginBottom: 12 }}>
          Shared SMTP is locked by superuser for this organization. Custom override is disabled.
        </Typography.Text>
      )}

      {isSuperuser && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Typography.Title level={5} style={{ marginBottom: 8 }}>Shared SMTP Assignment</Typography.Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Select
              placeholder="Select shared SMTP profile"
              value={selectedSharedProfileId}
              onChange={(value) => setSelectedSharedProfileId(value)}
              options={(sharedProfilesData?.sharedSmtpProfiles || []).map((profile) => ({
                value: profile.id,
                label: profile.name,
              }))}
            />
            <div className="flex items-center gap-2">
              <Switch checked={enforceShared} onChange={setEnforceShared} />
              <Typography.Text>Lock shared SMTP for this organization</Typography.Text>
            </div>
            <AntButton type="default" onClick={handleApplyPolicy} loading={savingPolicy} disabled={!targetOrgId || !selectedSharedProfileId}>
              Apply Shared SMTP Policy
            </AntButton>
          </Space>
        </Card>
      )}

      <Form form={form} layout="vertical" disabled={!canEditCustom}>
        <Form.Item name="smtpServer" label="SMTP server" rules={[{ required: true, message: 'SMTP server is required' }]}>
          <Input placeholder="smtp.example.com" />
        </Form.Item>
        <Form.Item name="smtpPort" label="SMTP port" rules={[{ required: true, message: 'SMTP port is required' }]}>
          <Input type="number" min={1} max={65535} placeholder="587" />
        </Form.Item>
        <Form.Item name="encryption" label="Encryption" rules={[{ required: true, message: 'Select encryption mode' }]}>
          <Select
            options={[
              { value: 'SSL', label: 'SSL' },
              { value: 'STARTTLS', label: 'STARTTLS' },
              { value: 'NONE', label: 'None' },
            ]}
          />
        </Form.Item>
        <Form.Item name="loginMethod" label="Login method" rules={[{ required: true, message: 'Select login method' }]}>
          <Select
            options={[
              { value: 'PLAIN', label: 'PLAIN' },
              { value: 'LOGIN', label: 'LOGIN' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="smtpUsername"
          label="SMTP username"
          rules={loginMethod === 'LOGIN' ? [{ required: true, message: 'SMTP username is required for LOGIN' }] : []}
        >
          <Input placeholder="username or email" />
        </Form.Item>
        <Form.Item
          name="smtpPassword"
          label="SMTP password"
          rules={loginMethod === 'LOGIN' && !smtpSettings?.hasPassword
            ? [{ required: true, message: 'SMTP password is required for LOGIN' }]
            : []}
          extra={smtpSettings?.hasPassword ? 'Leave empty to keep the existing password.' : undefined}
        >
          <Input.Password placeholder={smtpSettings?.hasPassword ? '(unchanged)' : 'SMTP password'} />
        </Form.Item>
        <Form.Item name="fromEmail" label="From (optional)" rules={[{ type: 'email', message: 'Enter a valid email address' }]}>
          <Input placeholder="noreply@example.com" />
        </Form.Item>
        <Form.Item style={{ marginBottom: 0 }}>
          <Space wrap>
            <AntButton type="primary" onClick={handleSave} loading={saving} disabled={!canEditCustom}>
              Save Organization SMTP
            </AntButton>
            {isSuperuser && (
              <>
                <Input
                  placeholder="Shared profile name"
                  value={sharedProfileName}
                  onChange={(e) => setSharedProfileName(e.target.value)}
                  style={{ width: 220 }}
                />
                <AntButton onClick={handleSaveAsSharedProfile} loading={savingSharedProfile}>
                  Save As Shared Profile
                </AntButton>
              </>
            )}
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
};

const DacTab: React.FC<{ repositories: Repo[] }> = ({ repositories }) => {
  const { message: msg } = App.useApp();
  const [form] = Form.useForm();
  const mode = Form.useWatch<'NONE' | 'GIT_PUSH' | 'GIT_PUSH_AND_DEPLOY' | 'DEPLOY_ONLY'>('mode', form) || 'NONE';
  const folderMode = Form.useWatch<'auto' | 'preset' | 'new'>('folderMode', form) || 'auto';
  const showGithubFields = mode === 'GIT_PUSH' || mode === 'GIT_PUSH_AND_DEPLOY';
  const showTargetPlatforms = mode === 'GIT_PUSH_AND_DEPLOY' || mode === 'DEPLOY_ONLY';

  const { data, loading, refetch } = useQuery<{
    dacDeploymentConfig: DacDeploymentConfig | null;
    availableDeploymentPlatforms: DeploymentPlatformOption[];
  }>(GET_DAC_DEPLOYMENT_CONFIG, { fetchPolicy: 'cache-and-network' });

  const { data: profileData } = useQuery<{ opentideHefPublishProfiles: { id: string; name: string }[] }>(
    GET_HEF_PUBLISH_PROFILES,
    { fetchPolicy: 'cache-and-network' },
  );

  const [updateConfig, { loading: saving }] = useMutation(UPDATE_DAC_DEPLOYMENT_CONFIG);
  const [exportAllWorkbenchesHexV2, { loading: exportingArchive }] = useMutation<ExportAllWorkbenchesHexV2Response>(EXPORT_ALL_WORKBENCHES_HEX_V2);

  useEffect(() => {
    const config = data?.dacDeploymentConfig;
    const initialFolder = config?.targetFolder || '';
    let inferredFolderMode: 'auto' | 'preset' | 'new' = 'auto';
    if (initialFolder) {
      inferredFolderMode = RULE_FOLDER_PRESET_OPTIONS.some((option) => option.value === initialFolder)
        ? 'preset'
        : 'new';
    }
    form.setFieldsValue({
      mode: config?.mode || 'NONE',
      targetRepositoryId: config?.targetRepositoryId || undefined,
      targetBranch: config?.targetBranch || 'main',
      targetFolder: inferredFolderMode === 'preset' ? initialFolder : undefined,
      newFolderName: inferredFolderMode === 'new' ? initialFolder : undefined,
      targetPlatforms: config?.targetPlatforms || [],
      publishProfileId: config?.publishProfileId || undefined,
      folderMode: inferredFolderMode,
    });
  }, [data?.dacDeploymentConfig, form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      let targetFolder: string | null = '';
      if (values.folderMode === 'preset') targetFolder = values.targetFolder || '';
      if (values.folderMode === 'new') targetFolder = (values.newFolderName || '').trim();

      const targetPlatforms =
        values.mode === 'GIT_PUSH_AND_DEPLOY' || values.mode === 'DEPLOY_ONLY'
          ? (values.targetPlatforms || []).map((platform: string) => platform.toLowerCase())
          : [];

      const result = await updateConfig({
        variables: {
          mode: values.mode,
          targetRepositoryId:
            values.mode === 'NONE' || values.mode === 'DEPLOY_ONLY' ? null : values.targetRepositoryId || null,
          targetBranch: values.mode === 'NONE' || values.mode === 'DEPLOY_ONLY' ? 'main' : (values.targetBranch || 'main'),
          targetFolder: values.mode === 'NONE' || values.mode === 'DEPLOY_ONLY' ? '' : targetFolder,
          targetPlatforms,
          publishProfileId: values.mode === 'NONE' || values.mode === 'DEPLOY_ONLY' ? null : values.publishProfileId || null,
        },
      });

      const response = result.data?.updateDacDeploymentConfig;
      if (!response?.success) {
        msg.error(response?.message || 'Failed to save DaC deployment configuration');
        return;
      }
      msg.success(response.message || 'DaC deployment configuration saved');
      refetch();
    } catch (err: any) {
      msg.error(err?.message || 'Failed to save DaC deployment configuration');
    }
  };

  const handleDownloadAllWorkbenches = async () => {
    try {
      const result = await exportAllWorkbenchesHexV2();
      const payload = result.data?.exportAllWorkbenchesHexV2;
      if (!payload?.success || !payload.fileData || !payload.filename || !payload.contentType) {
        msg.error(payload?.message || 'Failed to export workbench archive');
        return;
      }

      const binary = atob(payload.fileData);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }

      const blob = new Blob([bytes], { type: payload.contentType });
      const downloadUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = downloadUrl;
      anchor.download = payload.filename;
      anchor.click();
      window.URL.revokeObjectURL(downloadUrl);
      msg.success(payload.message || `Downloaded ${payload.filename}`);
    } catch (err: any) {
      msg.error(err?.message || 'Failed to export workbench archive');
    }
  };

  return (
    <Card loading={loading}>
      <Typography.Title level={4} style={{ marginBottom: 8 }}>Detection-as-Code deployment behavior</Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 20 }}>
        Configure what should happen automatically when a workbench transitions to <Typography.Text code>DEPLOYED</Typography.Text>.
      </Typography.Paragraph>
      <div style={{ marginBottom: 20 }}>
        <AntButton onClick={handleDownloadAllWorkbenches} loading={exportingArchive}>
          Download all Workbench data (HEX v2.0 ZIP)
        </AntButton>
      </div>

      <Form form={form} layout="vertical" initialValues={{ mode: 'NONE', targetBranch: 'main', folderMode: 'auto', targetPlatforms: [] }}>
        <Form.Item name="mode" label="Deployment mode" rules={[{ required: true, message: 'Select a deployment mode' }]}>
          <Radio.Group>
            <Space direction="vertical">
              <Radio value="NONE">A. Do nothing — just change status to DEPLOYED</Radio>
              <Radio value="GIT_PUSH">B. Generate DaC artifacts (rules, OpenTIDE) and push to GitHub</Radio>
              <Radio value="GIT_PUSH_AND_DEPLOY">C. Generate, push to GitHub, and deploy to target systems</Radio>
              <Radio value="DEPLOY_ONLY">D. Just push rule to target platform (no GitHub backup)</Radio>
            </Space>
          </Radio.Group>
        </Form.Item>

        {showGithubFields && (
          <>
            <Form.Item
              name="targetRepositoryId"
              label="Target repository"
              rules={[{ required: true, message: 'Select a target repository' }]}
            >
              <Select
                placeholder="Select repository"
                showSearch
                optionFilterProp="label"
                options={repositories.map((repo) => ({
                  value: repo.id,
                  label: `${repo.name}${repo.url ? ` — ${repo.url}` : ''}`,
                }))}
              />
            </Form.Item>

            <Form.Item
              name="targetBranch"
              label="Branch"
              rules={[{ required: true, message: 'Enter a branch' }]}
            >
              <Input placeholder="main" />
            </Form.Item>

            <Divider orientation="left" plain>Target folder</Divider>
            <Form.Item name="folderMode">
              <Radio.Group>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Radio value="auto"><strong>Auto-organize by format</strong></Radio>
                  <Radio value="preset"><strong>Choose existing folder</strong></Radio>
                  <Radio value="new"><strong>Create new folder</strong></Radio>
                </Space>
              </Radio.Group>
            </Form.Item>
            {folderMode === 'preset' && (
              <Form.Item name="targetFolder" label="Preset folder" rules={[{ required: true, message: 'Select a folder' }]}>
                <Select placeholder="Select target folder" showSearch optionFilterProp="label" options={RULE_FOLDER_PRESET_OPTIONS} />
              </Form.Item>
            )}
            {folderMode === 'new' && (
              <Form.Item name="newFolderName" label="Custom folder path" rules={[{ required: true, message: 'Enter a folder path' }]}>
                <Input placeholder="rules/custom" />
              </Form.Item>
            )}

            <Form.Item name="publishProfileId" label="OpenTIDE publish profile (optional)">
              <Select
                allowClear
                placeholder="Use direct settings (optional profile)"
                options={(profileData?.opentideHefPublishProfiles || []).map((profile) => ({
                  value: profile.id,
                  label: profile.name,
                }))}
              />
            </Form.Item>
          </>
        )}

        {showTargetPlatforms && (
          <Form.Item
            name="targetPlatforms"
            label="Target platforms"
            rules={[{ required: true, message: 'Select at least one platform' }]}
          >
            <Select
              mode="multiple"
              placeholder="Select deployment platforms"
              options={(data?.availableDeploymentPlatforms || []).map((platform) => ({
                value: platform.key,
                label: platform.label,
              }))}
            />
          </Form.Item>
        )}

        <Typography.Paragraph type="secondary">
          Mode A keeps deployment manual. Mode B generates DaC artifacts and pushes them to GitHub. Mode C does Mode B and deploys to the selected platforms. Mode D deploys directly to the selected platforms without any GitHub backup.
        </Typography.Paragraph>

        <Form.Item style={{ marginBottom: 0 }}>
          <AntButton type="primary" onClick={handleSave} loading={saving}>Save</AntButton>
        </Form.Item>
      </Form>
    </Card>
  );
};

type SystemUpdateStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED';

interface SystemUpdateJobState {
  id: string;
  mode: string;
  status: SystemUpdateStatus | string;
  started_at?: string | null;
  ended_at?: string | null;
  failed_step?: string | null;
  error?: string | null;
  summary?: {
    success?: boolean;
    mode?: string;
    failed_step?: string | null;
    started_at?: string | null;
    ended_at?: string | null;
  };
}

interface SystemUpdateCheckState {
  current_version: string;
  build?: {
    commit?: string | null;
    checked_at?: string | null;
  };
  update_capability?: {
    can_update?: boolean;
    reason?: string | null;
  };
  running_job_id?: string | null;
}

const systemUpdateHeaders = () => {
  const token = getStoredAccessToken();
  const bearer = token ? ('B' + 'earer ' + token) : null;
  return {
    'Content-Type': 'application/json',
    ...(bearer ? { Authorization: bearer } : {}),
    ...(bearer ? { 'X-Hefaistos-Authorization': bearer } : {}),
  };
};

export const SystemUpdateTab: React.FC<{ isSuperuser: boolean }> = ({ isSuperuser }) => {
  const [checkData, setCheckData] = useState<SystemUpdateCheckState | null>(null);
  const [activeJob, setActiveJob] = useState<SystemUpdateJobState | null>(null);
  const [logs, setLogs] = useState<Array<{ ts: string; line: string }>>([]);
  const [forceMode, setForceMode] = useState(false);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchCheck = async () => {
    setChecking(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/system/config/update/check`, {
        method: 'GET',
        headers: systemUpdateHeaders(),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || `Check failed (${response.status})`);
      }
      setCheckData(payload);
      if (payload?.running_job_id && !activeJob?.id) {
        setActiveJob({ id: payload.running_job_id, mode: 'default', status: 'RUNNING' });
      }
    } catch (error: any) {
      message.error(error?.message || 'Failed to check update status');
    } finally {
      setChecking(false);
    }
  };

  const fetchJob = async (jobId: string) => {
    const statusResponse = await fetch(`${getApiBaseUrl()}/api/system/config/update/jobs/${jobId}`, {
      method: 'GET',
      headers: systemUpdateHeaders(),
    });
    const statusPayload = await statusResponse.json().catch(() => ({}));
    if (!statusResponse.ok) {
      throw new Error(statusPayload?.detail || `Status failed (${statusResponse.status})`);
    }
    setActiveJob(statusPayload);

    const logsResponse = await fetch(`${getApiBaseUrl()}/api/system/config/update/jobs/${jobId}/logs?start=0&limit=600`, {
      method: 'GET',
      headers: systemUpdateHeaders(),
    });
    const logsPayload = await logsResponse.json().catch(() => ({}));
    if (!logsResponse.ok) {
      throw new Error(logsPayload?.detail || `Logs failed (${logsResponse.status})`);
    }
    setLogs(Array.isArray(logsPayload?.logs) ? logsPayload.logs : []);
  };

  const refreshActiveJob = async () => {
    if (!activeJob?.id) return;
    setRefreshing(true);
    try {
      await fetchJob(activeJob.id);
    } catch (error: any) {
      message.error(error?.message || 'Failed to refresh update job');
    } finally {
      setRefreshing(false);
    }
  };

  const startUpdate = async () => {
    if (!window.confirm(`Start a ${forceMode ? 'force' : 'default'} system-wide update now?`)) {
      return;
    }

    setStarting(true);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/system/config/update/start`, {
        method: 'POST',
        headers: systemUpdateHeaders(),
        body: JSON.stringify({ force: forceMode }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || `Update start failed (${response.status})`);
      }
      const jobId = payload?.job_id as string;
      if (!jobId) throw new Error('Missing job id in response');
      setActiveJob({ id: jobId, mode: payload?.mode || (forceMode ? 'force' : 'default'), status: payload?.status || 'PENDING' });
      await fetchJob(jobId);
      await fetchCheck();
      message.success('System update job started.');
    } catch (error: any) {
      message.error(error?.message || 'Failed to start update');
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    if (!isSuperuser) return;
    void fetchCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperuser]);

  useEffect(() => {
    if (!isSuperuser || !activeJob?.id) return;
    const poll = window.setInterval(() => {
      if (activeJob.status === 'RUNNING' || activeJob.status === 'PENDING') {
        void refreshActiveJob();
      }
    }, 3000);
    return () => window.clearInterval(poll);
  }, [isSuperuser, activeJob?.id, activeJob?.status]);

  if (!isSuperuser) {
    return <Alert type="warning" showIcon message="System update controls are restricted to superuser accounts." />;
  }

  const canUpdate = Boolean(checkData?.update_capability?.can_update);
  const isRunning = activeJob?.status === 'RUNNING' || activeJob?.status === 'PENDING';

  return (
    <Card title="System Update" bordered>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Typography.Text>
          Current Version: <strong>{checkData?.current_version || '—'}</strong>
        </Typography.Text>
        <Typography.Text>
          Build Commit: <strong>{checkData?.build?.commit || '—'}</strong>
        </Typography.Text>
        <Typography.Text>
          Update Capability: <strong>{canUpdate ? 'Ready' : 'Unavailable'}</strong>
          {checkData?.update_capability?.reason ? ` (${checkData.update_capability.reason})` : ''}
        </Typography.Text>

        <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
          <span><strong>Force update (down/up)</strong> — advanced recovery mode with downtime.</span>
          <Switch checked={forceMode} onChange={setForceMode} disabled={isRunning} />
        </label>

        <Space>
          <AntButton onClick={() => void fetchCheck()} loading={checking}>Check updates</AntButton>
          <AntButton type="primary" danger onClick={() => void startUpdate()} disabled={!canUpdate || isRunning} loading={starting}>
            Update now
          </AntButton>
          <AntButton onClick={() => void refreshActiveJob()} disabled={!activeJob?.id} loading={refreshing}>
            Refresh job
          </AntButton>
        </Space>

        {activeJob?.id && (
          <div className="config-theme-panel rounded-lg border-2 border-hefaistos-border p-4">
            <Typography.Paragraph style={{ marginBottom: 8 }}>
              Job: <strong>{activeJob.id}</strong> • Status: <strong>{activeJob.status}</strong> • Mode: <strong>{activeJob.mode}</strong>
            </Typography.Paragraph>
            {activeJob.failed_step && (
              <Typography.Paragraph type="danger" style={{ marginBottom: 8 }}>
                Failed step: {activeJob.failed_step}{activeJob.error ? ` (${activeJob.error})` : ''}
              </Typography.Paragraph>
            )}
            <pre style={{ maxHeight: 280, overflow: 'auto', padding: 12, background: '#0f172a', color: '#e2e8f0', borderRadius: 6, margin: 0 }}>
              {logs.length ? logs.map((entry) => `[${entry.ts}] ${entry.line}`).join('\\n') : 'No logs yet.'}
            </pre>
          </div>
        )}
      </Space>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Main ConfigurationPage
// ---------------------------------------------------------------------------

const VALID_TABS = ['users', 'auth', 'hef', 'rules', 'misp', 'smtp', 'sharing', 'aitasks', 'orgai', 'platforms', 'dac', 'system-update'] as const;
type TabKey = typeof VALID_TABS[number];

export const ConfigurationPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { data: accessData, loading: accessLoading } = useQuery<{
    me?: { id: string; role: string; isSuperuser?: boolean | null } | null
  }>(GET_CONFIG_ACCESS, { fetchPolicy: 'cache-first' });

  const isConfigAdmin = useMemo(() => {
    const role = (accessData?.me?.role || '').toUpperCase();
    return role === 'ADMIN' || role === 'RESOURCE_MANAGER' || role === 'SUPERADMIN' || Boolean(accessData?.me?.isSuperuser);
  }, [accessData?.me?.isSuperuser, accessData?.me?.role]);
  const isCurrentSuperuser = Boolean(accessData?.me?.isSuperuser);

  const isBotAuditorRole = useMemo(() => {
    const role = (accessData?.me?.role || '').toUpperCase();
    return role === 'BOT_AUDITOR_ORG' || role === 'BOT_AUDITOR_GLOBAL';
  }, [accessData?.me?.role]);

  const isConfigAccessAllowed = isConfigAdmin || isBotAuditorRole;

  useEffect(() => {
    if (!accessLoading && !isConfigAccessAllowed) {
      navigate('/', { replace: true });
    }
  }, [accessLoading, isConfigAccessAllowed, navigate]);
  const isAccessPending = accessLoading;
  const isAccessDenied = !accessLoading && !isConfigAccessAllowed;

  const tabFromUrl = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const rawTab = params.get('tab');
    const normalizedTab = rawTab === 'inittide' ? 'hef' : rawTab;
    return normalizedTab && (VALID_TABS as readonly string[]).includes(normalizedTab)
      ? (normalizedTab as TabKey)
      : 'users';
  }, [location.search]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('tab') === 'inittide') {
      params.set('tab', 'hef');
      navigate(`/mgmt/config?${params.toString()}`, { replace: true });
    }
  }, [location.search, navigate]);

  const handleTabChange = (key: string) => {
    navigate(`/mgmt/config?tab=${key}`, { replace: true });
  };

  // --- Users & Org AI state ---
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({ email: '', role: '', bio: '', jobTitle: '', slackHandle: '', organizationId: '' });
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  // Shared AI/SMTP superuser controls were moved to /mgmt/superuser.
  // Keep Configuration focused on organization-level admin settings.
  const isSuperuser = false;
  const [selectedOrgAiOrgId, setSelectedOrgAiOrgId] = useState<string | undefined>(undefined);
  const [sharedAiProfileName, setSharedAiProfileName] = useState('');
  const [selectedSharedAiProfileId, setSelectedSharedAiProfileId] = useState<string | undefined>(undefined);
  const [lockSharedAi, setLockSharedAi] = useState(false);

  const { data: usersData, loading: usersLoading, error: usersError, refetch: refetchUsers } = useQuery<{ allUsersInOrg: User[] }>(GET_ALL_USERS_QUERY, {
    skip: isAccessPending || !isConfigAccessAllowed,
  });
  const { data: orgData } = useQuery<{ allOrganizations: { id: string; name: string }[] }>(ALL_ORGANIZATIONS_QUERY, {
    errorPolicy: 'ignore',
    skip: isAccessPending || !isConfigAccessAllowed,
  });
  useEffect(() => {
    const orgList = orgData?.allOrganizations || [];
    if (isSuperuser && !selectedOrgAiOrgId && orgList.length > 0) {
      setSelectedOrgAiOrgId(orgList[0].id);
    }
  }, [isSuperuser, orgData?.allOrganizations, selectedOrgAiOrgId]);

  const orgAiTargetOrgId = isSuperuser ? selectedOrgAiOrgId || null : null;
  const skipOrgAiForMissingTarget = Boolean(isSuperuser && (orgData?.allOrganizations?.length || 0) > 0 && !selectedOrgAiOrgId);

  const { data: orgAiData, refetch: refetchOrgAi } = useQuery<OrgAISettingsData>(GET_ORG_AI_SETTINGS, {
    variables: { organizationId: orgAiTargetOrgId },
    errorPolicy: 'ignore',
    skip: isAccessPending || !isConfigAccessAllowed || skipOrgAiForMissingTarget,
  });
  const { data: sharedAiData, refetch: refetchSharedAiProfiles } = useQuery<{ sharedAiProfiles: SharedAiProfile[] }>(GET_SHARED_AI_PROFILES, {
    variables: { includeInactive: false },
    errorPolicy: 'ignore',
    skip: !isSuperuser || isAccessPending || !isConfigAccessAllowed,
  });
  const [orgAiForm, setOrgAiForm] = useState({ ollamaBaseUrl: '', ollamaModel: '', openaiKey: '', geminiKey: '', claudeKey: '', azureOpenaiEndpoint: '', azureOpenaiKey: '', azureOpenaiDeployment: '', orgPreferredModel: '', ollamaEnabled: true, openaiEnabled: true, geminiEnabled: true, claudeEnabled: true, azureOpenaiEnabled: true });
  const [authForm, setAuthForm] = useState({
    authMode: 'ENTRA_AND_LOCAL_BREAKGLASS',
    defaultLoginProvider: 'ENTRA',
    enableEntra: false,
    enableOidc: false,
    allowLocalBreakglass: true,
    autoProvisionUsers: true,
    syncClaimsOnLogin: true,
    enforceLocalMfa: true,
    breakglassUsernames: 'admin',
    entraTenantId: '',
    entraClientId: '',
    entraClientSecret: '',
    entraRedirectUri: '',
    entraScopes: 'openid profile email',
    entraEmailClaim: 'preferred_username',
    entraUsernameClaim: 'preferred_username',
    entraRoleClaim: 'roles',
    oidcIssuerUrl: '',
    oidcClientId: '',
    oidcClientSecret: '',
    oidcRedirectUri: '',
    oidcScopes: 'openid profile email',
    oidcEmailClaim: 'email',
    oidcUsernameClaim: 'preferred_username',
    oidcRoleClaim: 'roles',
    oidcVerifySsl: true,
    oidcCaCertificate: '',
    roleAdminValues: 'HEF-Admins,Admin,ADMIN',
    roleAnalystValues: 'HEF-Analysts,Analyst,ANALYST',
    roleReviewerValues: 'HEF-Reviewers,Reviewer,REVIEWER',
    defaultProvisionedRole: 'VIEWER',
  });
  const [oidcCaCertificateTouched, setOidcCaCertificateTouched] = useState(false);
  const [hasSavedOidcCaCertificate, setHasSavedOidcCaCertificate] = useState(false);

  const [deleteUser, { loading: deleteLoading }] = useMutation(DELETE_USER_MUTATION, { refetchQueries: [{ query: GET_ALL_USERS_QUERY }] });
  const [adminUpdateUser, { loading: saving }] = useMutation(ADMIN_UPDATE_USER_MUTATION, { refetchQueries: [{ query: GET_ALL_USERS_QUERY }], awaitRefetchQueries: true });
  const [adminResetUserPassword, { loading: resettingPassword }] = useMutation(ADMIN_RESET_USER_PASSWORD_MUTATION);
  const [updateOrgAiSettings, { loading: savingOrgAi }] = useMutation(UPDATE_ORG_AI_SETTINGS);
  const { data: authSettingsData, refetch: refetchAuthSettings } = useQuery<AuthSettingsData>(GET_AUTH_SETTINGS, {
    skip: isAccessPending || !isConfigAccessAllowed,
    errorPolicy: 'ignore',
    fetchPolicy: 'cache-and-network',
  });
  const [updateAuthSettings, { loading: savingAuthSettings }] = useMutation(UPDATE_AUTH_SETTINGS);
  const [setSharedAiProfile, { loading: savingSharedAiProfile }] = useMutation(SET_SHARED_AI_PROFILE);
  const [assignSharedAiProfile, { loading: assigningSharedAiProfile }] = useMutation(ASSIGN_SHARED_AI_PROFILE);

  useEffect(() => {
    if (orgAiData?.orgAiSettings) {
      setOrgAiForm({
        ollamaBaseUrl: orgAiData.orgAiSettings.ollamaBaseUrl || '',
        ollamaModel: orgAiData.orgAiSettings.ollamaModel || '',
        openaiKey: '',
        geminiKey: '',
        claudeKey: '',
        azureOpenaiEndpoint: orgAiData.orgAiSettings.azureOpenaiEndpoint || '',
        azureOpenaiKey: '',
        azureOpenaiDeployment: orgAiData.orgAiSettings.azureOpenaiDeployment || '',
        orgPreferredModel: orgAiData.orgAiSettings.orgPreferredModel || '',
        ollamaEnabled: orgAiData.orgAiSettings.ollamaEnabled ?? true,
        openaiEnabled: orgAiData.orgAiSettings.openaiEnabled ?? true,
        geminiEnabled: orgAiData.orgAiSettings.geminiEnabled ?? true,
        claudeEnabled: orgAiData.orgAiSettings.claudeEnabled ?? true,
        azureOpenaiEnabled: orgAiData.orgAiSettings.azureOpenaiEnabled ?? true,
      });
      setSelectedSharedAiProfileId(orgAiData.orgAiSettings.sharedProfileId || undefined);
      setLockSharedAi(Boolean(orgAiData.orgAiSettings.sharedProfileLocked));
    }
  }, [orgAiData?.orgAiSettings]);

  useEffect(() => {
    if (!authSettingsData?.authSettings) return;
    const s = authSettingsData.authSettings;
    setAuthForm({
      authMode: s.authMode || 'ENTRA_AND_LOCAL_BREAKGLASS',
      defaultLoginProvider: s.defaultLoginProvider || 'ENTRA',
      enableEntra: !!s.enableEntra,
      enableOidc: !!s.enableOidc,
      allowLocalBreakglass: !!s.allowLocalBreakglass,
      autoProvisionUsers: !!s.autoProvisionUsers,
      syncClaimsOnLogin: !!s.syncClaimsOnLogin,
      enforceLocalMfa: !!s.enforceLocalMfa,
      breakglassUsernames: s.breakglassUsernames || 'admin',
      entraTenantId: s.entraTenantId || '',
      entraClientId: s.entraClientId || '',
      entraClientSecret: '',
      entraRedirectUri: s.entraRedirectUri || '',
      entraScopes: s.entraScopes || 'openid profile email',
      entraEmailClaim: s.entraEmailClaim || 'preferred_username',
      entraUsernameClaim: s.entraUsernameClaim || 'preferred_username',
      entraRoleClaim: s.entraRoleClaim || 'roles',
      oidcIssuerUrl: s.oidcIssuerUrl || '',
      oidcClientId: s.oidcClientId || '',
      oidcClientSecret: '',
      oidcRedirectUri: s.oidcRedirectUri || '',
      oidcScopes: s.oidcScopes || 'openid profile email',
      oidcEmailClaim: s.oidcEmailClaim || 'email',
      oidcUsernameClaim: s.oidcUsernameClaim || 'preferred_username',
      oidcRoleClaim: s.oidcRoleClaim || 'roles',
      oidcVerifySsl: s.oidcVerifySsl ?? true,
      oidcCaCertificate: '',
      roleAdminValues: s.roleAdminValues || '',
      roleAnalystValues: s.roleAnalystValues || '',
      roleReviewerValues: s.roleReviewerValues || '',
      defaultProvisionedRole: s.defaultProvisionedRole || 'VIEWER',
    });
    setOidcCaCertificateTouched(false);
    setHasSavedOidcCaCertificate(Boolean(s.hasOidcCaCertificate));
  }, [authSettingsData?.authSettings]);

  const handleDelete = async (user: User) => {
    if (user.isStaff) { alert("Cannot delete a Staff/Superuser account from this panel."); return; }
    if (window.confirm(`Are you sure you want to delete the user '${user.username}'?`)) {
      try { await deleteUser({ variables: { userId: user.id } }); } catch (e: any) { alert(`Error: ${e.message}`); }
    }
  };

  const handleResetPassword = async () => {
    if (!resetPasswordUser) return;
    if (!newPassword) { message.error('Please enter a new password.'); return; }
    if (newPassword !== confirmPassword) { message.error('Passwords do not match.'); return; }
    try {
      await adminResetUserPassword({ variables: { userId: resetPasswordUser.id, newPassword } });
      message.success(`Password reset successfully for ${resetPasswordUser.username}.`);
      setResetPasswordUser(null); setNewPassword(''); setConfirmPassword('');
    } catch (e: any) { message.error(e.message || 'Failed to reset password.'); }
  };

  const handleSaveOrgAi = async () => {
    try {
      await updateOrgAiSettings({
        variables: {
          organizationId: isSuperuser ? selectedOrgAiOrgId || null : null,
          ollamaBaseUrl: orgAiForm.ollamaBaseUrl || null,
          ollamaModel: orgAiForm.ollamaModel || null,
          openaiKey: orgAiForm.openaiKey || undefined,
          geminiKey: orgAiForm.geminiKey || undefined,
          claudeKey: orgAiForm.claudeKey || undefined,
          azureOpenaiEndpoint: orgAiForm.azureOpenaiEndpoint || null,
          azureOpenaiKey: orgAiForm.azureOpenaiKey || undefined,
          azureOpenaiDeployment: orgAiForm.azureOpenaiDeployment || null,
          orgPreferredModel: orgAiForm.orgPreferredModel || null,
          ollamaEnabled: orgAiForm.ollamaEnabled,
          openaiEnabled: orgAiForm.openaiEnabled,
          geminiEnabled: orgAiForm.geminiEnabled,
          claudeEnabled: orgAiForm.claudeEnabled,
          azureOpenaiEnabled: orgAiForm.azureOpenaiEnabled,
        },
        refetchQueries: ['GetMyAISettings'],
      });
      message.success('Organization AI settings saved.');
      setOrgAiForm(prev => ({ ...prev, openaiKey: '', geminiKey: '', claudeKey: '', azureOpenaiKey: '' }));
      refetchOrgAi();
    } catch (e: any) { message.error(e.message || 'Failed to save organization AI settings.'); }
  };

  const handleSaveSharedAiProfile = async () => {
    if (!isSuperuser) return;
    if (!sharedAiProfileName.trim()) {
      message.error('Shared AI profile name is required.');
      return;
    }
    try {
      const result = await setSharedAiProfile({
        variables: {
          name: sharedAiProfileName.trim(),
          ollamaBaseUrl: orgAiForm.ollamaBaseUrl || null,
          ollamaModel: orgAiForm.ollamaModel || null,
          openaiKey: orgAiForm.openaiKey || undefined,
          geminiKey: orgAiForm.geminiKey || undefined,
          claudeKey: orgAiForm.claudeKey || undefined,
          azureOpenaiEndpoint: orgAiForm.azureOpenaiEndpoint || null,
          azureOpenaiKey: orgAiForm.azureOpenaiKey || undefined,
          azureOpenaiDeployment: orgAiForm.azureOpenaiDeployment || null,
          orgPreferredModel: orgAiForm.orgPreferredModel || null,
          ollamaEnabled: orgAiForm.ollamaEnabled,
          openaiEnabled: orgAiForm.openaiEnabled,
          geminiEnabled: orgAiForm.geminiEnabled,
          claudeEnabled: orgAiForm.claudeEnabled,
          azureOpenaiEnabled: orgAiForm.azureOpenaiEnabled,
          isActive: true,
        },
      });
      if (result.data?.setSharedAiProfile?.ok) {
        message.success(result.data.setSharedAiProfile.message || 'Shared AI profile saved.');
        setSharedAiProfileName('');
        refetchSharedAiProfiles();
      } else {
        message.error(result.data?.setSharedAiProfile?.message || 'Failed to save shared AI profile.');
      }
    } catch (e: any) {
      message.error(e.message || 'Failed to save shared AI profile.');
    }
  };

  const handleAssignSharedAiProfile = async () => {
    if (!isSuperuser || !selectedOrgAiOrgId) return;
    if (!selectedSharedAiProfileId) {
      message.error('Select a shared AI profile first.');
      return;
    }
    try {
      const result = await assignSharedAiProfile({
        variables: {
          organizationId: selectedOrgAiOrgId,
          sharedProfileId: selectedSharedAiProfileId,
          sharedProfileLocked: lockSharedAi,
        },
      });
      if (result.data?.assignSharedAiProfile?.ok) {
        message.success(result.data.assignSharedAiProfile.message || 'Shared AI assignment updated.');
        refetchOrgAi();
      } else {
        message.error(result.data?.assignSharedAiProfile?.message || 'Failed to update shared AI assignment.');
      }
    } catch (e: any) {
      message.error(e.message || 'Failed to update shared AI assignment.');
    }
  };

  const handleSaveAuthSettings = async () => {
    try {
      const variables: Record<string, any> = {
        authMode: authForm.authMode,
        defaultLoginProvider: authForm.defaultLoginProvider,
        enableEntra: authForm.enableEntra,
        enableOidc: authForm.enableOidc,
        allowLocalBreakglass: authForm.allowLocalBreakglass,
        autoProvisionUsers: authForm.autoProvisionUsers,
        syncClaimsOnLogin: authForm.syncClaimsOnLogin,
        enforceLocalMfa: authForm.enforceLocalMfa,
        breakglassUsernames: authForm.breakglassUsernames,
        entraTenantId: authForm.entraTenantId || null,
        entraClientId: authForm.entraClientId || null,
        entraRedirectUri: authForm.entraRedirectUri || null,
        entraScopes: authForm.entraScopes || null,
        entraEmailClaim: authForm.entraEmailClaim || null,
        entraUsernameClaim: authForm.entraUsernameClaim || null,
        entraRoleClaim: authForm.entraRoleClaim || null,
        oidcIssuerUrl: authForm.oidcIssuerUrl || null,
        oidcClientId: authForm.oidcClientId || null,
        oidcRedirectUri: authForm.oidcRedirectUri || null,
        oidcScopes: authForm.oidcScopes || null,
        oidcEmailClaim: authForm.oidcEmailClaim || null,
        oidcUsernameClaim: authForm.oidcUsernameClaim || null,
        oidcRoleClaim: authForm.oidcRoleClaim || null,
        oidcVerifySsl: authForm.oidcVerifySsl,
        roleAdminValues: authForm.roleAdminValues || null,
        roleAnalystValues: authForm.roleAnalystValues || null,
        roleReviewerValues: authForm.roleReviewerValues || null,
        defaultProvisionedRole: authForm.defaultProvisionedRole,
      };
      if (authForm.entraClientSecret.trim()) variables.entraClientSecret = authForm.entraClientSecret.trim();
      if (authForm.oidcClientSecret.trim()) variables.oidcClientSecret = authForm.oidcClientSecret.trim();
      if (oidcCaCertificateTouched) variables.oidcCaCertificate = authForm.oidcCaCertificate.trim();

      const result = await updateAuthSettings({ variables });
      if (result.data?.updateAuthSettings?.ok) {
        message.success(result.data.updateAuthSettings.message || 'Authentication settings saved.');
        setAuthForm((prev) => ({ ...prev, entraClientSecret: '', oidcClientSecret: '', oidcCaCertificate: '' }));
        refetchAuthSettings();
      } else {
        message.error(result.data?.updateAuthSettings?.message || 'Failed to save authentication settings.');
      }
    } catch (e: any) {
      message.error(e.message || 'Failed to save authentication settings.');
    }
  };

  // Determine role for MISP tab (piggyback on repos query result via App.useApp context)
  const { data: repoData } = useQuery<{ me?: { role: string } | null; allRuleRepositories: Repo[] }>(
    GET_RULE_REPOSITORIES,
    { fetchPolicy: 'cache-first', skip: isAccessPending || !isConfigAccessAllowed },
  );
  const repoRole = repoData?.me?.role || 'VIEWER';
  const canAdminConfig = isConfigAdmin;
  const orgAiLocked = Boolean(orgAiData?.orgAiSettings?.sharedProfileLocked) && !isSuperuser;
  const disableOrgAiEditing = !canAdminConfig || orgAiLocked;
  const tabItems = [
    {
      key: 'users',
      label: 'Users',
      children: (
        <div>
          <div className="flex justify-end mb-4">
            {canAdminConfig ? (
              <Button variant="primary" onClick={() => setIsInviteModalOpen(true)}>
                <PixelIcon name="add" className="w-5 h-5 mr-2" />
                Invite User
              </Button>
            ) : (
              <Typography.Text type="secondary">Read-only mode: invite/edit actions are disabled.</Typography.Text>
            )}
          </div>
          {usersLoading && <p>Loading users...</p>}
          {usersError && <p className="text-hefaistos-accent-red">Error: {usersError.message}</p>}
          {!usersLoading && !usersError && (
            <div className="config-theme-panel shadow-md rounded-lg overflow-hidden border-2 border-hefaistos-border">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr>
                    <th className="p-4 text-sm font-semibold uppercase border-b-2 border-hefaistos-border">Username</th>
                    <th className="p-4 text-sm font-semibold uppercase border-b-2 border-hefaistos-border">Email</th>
                    <th className="p-4 text-sm font-semibold uppercase border-b-2 border-hefaistos-border">Role</th>
                    <th className="p-4 text-sm font-semibold uppercase border-b-2 border-hefaistos-border">Last Login</th>
                    <th className="p-4 text-sm font-semibold uppercase border-b-2 border-hefaistos-border">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {usersData?.allUsersInOrg.map((user) => (
                    <tr key={user.id} className="border-b border-hefaistos-border last:border-b-0 hover:bg-hefaistos-subtle/50">
                      <td className="p-4 font-medium">{user.username} {user.isStaff ? '(Staff)' : ''}</td>
                      <td className="p-4">{user.email || 'N/A'}</td>
                      <td className="p-4">{user.role}</td>
                      <td className="p-4">{user.lastLogin ? new Date(user.lastLogin).toLocaleString() : 'Never'}</td>
                      <td className="p-4 flex gap-2">
                        {canAdminConfig ? (
                          <>
                            <Button variant="secondary" onClick={() => {
                              setEditingUser(user);
                              setEditForm({ email: user.email || '', role: user.role, bio: (user as any).bio || '', jobTitle: (user as any).jobTitle || '', slackHandle: (user as any).slackHandle || '', organizationId: user.organization?.id || '' });
                            }}>
                              <PixelIcon name="edit" className="w-4 h-4" />
                            </Button>
                            <Button variant="secondary" title="Reset Password" aria-label="Reset Password" onClick={() => { setResetPasswordUser(user); setNewPassword(''); setConfirmPassword(''); }}>
                              🔑
                            </Button>
                            <Button variant="danger" onClick={() => handleDelete(user)} disabled={deleteLoading || user.isStaff}>
                              <PixelIcon name="delete" className="w-4 h-4" />
                            </Button>
                          </>
                        ) : (
                          <Typography.Text type="secondary">Read-only</Typography.Text>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {canAdminConfig && (
            <InviteUserModal isOpen={isInviteModalOpen} onClose={() => setIsInviteModalOpen(false)} onUserInvited={() => refetchUsers()} />
          )}
        </div>
      ),
    },
    {
      key: 'auth',
      label: 'Authentication',
      children: (
        <div className="configuration-theme space-y-8">
          <div className="config-theme-panel rounded-lg shadow-sm border-2 border-hefaistos-border p-6">
            <h3 className="text-xl font-bold mb-1">Authentication Providers</h3>
            <p className="text-sm text-gray-500 mb-6">
              Configure Entra OIDC and Generic OIDC sign-in. Local username/password can be restricted to break-glass admins.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-xs font-semibold mb-1">Authentication Mode</label>
                <select
                  className="w-full p-2 border rounded text-sm config-auth-native-select"
                  value={authForm.authMode}
                  onChange={(e) => setAuthForm({ ...authForm, authMode: e.target.value })}
                  disabled={!canAdminConfig}
                >
                  <option value="ENTRA_ONLY">ENTRA_ONLY</option>
                  <option value="OIDC_ONLY">OIDC_ONLY</option>
                  <option value="ENTRA_AND_OIDC">ENTRA_AND_OIDC</option>
                  <option value="ENTRA_AND_LOCAL_BREAKGLASS">ENTRA_AND_LOCAL_BREAKGLASS</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Default Login Provider</label>
                <select
                  className="w-full p-2 border rounded text-sm config-auth-native-select"
                  value={authForm.defaultLoginProvider}
                  onChange={(e) => setAuthForm({ ...authForm, defaultLoginProvider: e.target.value })}
                  disabled={!canAdminConfig}
                >
                  <option value="ENTRA">ENTRA</option>
                  <option value="OIDC">OIDC</option>
                  <option value="LOCAL">LOCAL</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                <span>Enable Entra OIDC</span>
                <Switch checked={authForm.enableEntra} onChange={(checked) => setAuthForm({ ...authForm, enableEntra: checked })} disabled={!canAdminConfig} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                <span>Enable Generic OIDC</span>
                <Switch checked={authForm.enableOidc} onChange={(checked) => setAuthForm({ ...authForm, enableOidc: checked })} disabled={!canAdminConfig} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                <span>Allow Local Break-glass Login</span>
                <Switch checked={authForm.allowLocalBreakglass} onChange={(checked) => setAuthForm({ ...authForm, allowLocalBreakglass: checked })} disabled={!canAdminConfig} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                <span>Auto-Provision Users</span>
                <Switch checked={authForm.autoProvisionUsers} onChange={(checked) => setAuthForm({ ...authForm, autoProvisionUsers: checked })} disabled={!canAdminConfig} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                <span>Sync Claims on Login</span>
                <Switch checked={authForm.syncClaimsOnLogin} onChange={(checked) => setAuthForm({ ...authForm, syncClaimsOnLogin: checked })} disabled={!canAdminConfig} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                <span>Enforce MFA for Local Break-glass</span>
                <Switch checked={authForm.enforceLocalMfa} onChange={(checked) => setAuthForm({ ...authForm, enforceLocalMfa: checked })} disabled={!canAdminConfig} />
              </label>
            </div>

            <div className="border border-gray-200 rounded-lg p-4 mb-4">
              <h4 className="font-semibold text-base mb-3">Entra OIDC</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Tenant ID</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraTenantId} onChange={(e) => setAuthForm({ ...authForm, entraTenantId: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Client ID</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraClientId} onChange={(e) => setAuthForm({ ...authForm, entraClientId: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Client Secret</label>
                  <input type="password" className="w-full p-2 border rounded text-sm" placeholder={authSettingsData?.authSettings?.hasEntraClientSecret ? '•••••••• (set — enter new to rotate)' : 'Enter client secret'} value={authForm.entraClientSecret} onChange={(e) => setAuthForm({ ...authForm, entraClientSecret: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Redirect URI</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraRedirectUri} onChange={(e) => setAuthForm({ ...authForm, entraRedirectUri: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Scopes</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraScopes} onChange={(e) => setAuthForm({ ...authForm, entraScopes: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Email Claim</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraEmailClaim} onChange={(e) => setAuthForm({ ...authForm, entraEmailClaim: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Username Claim</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraUsernameClaim} onChange={(e) => setAuthForm({ ...authForm, entraUsernameClaim: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Role Claim</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.entraRoleClaim} onChange={(e) => setAuthForm({ ...authForm, entraRoleClaim: e.target.value })} disabled={!canAdminConfig} />
                </div>
              </div>
            </div>

            <div className="border border-gray-200 rounded-lg p-4 mb-4">
              <h4 className="font-semibold text-base mb-3">Generic OIDC</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Issuer URL</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcIssuerUrl} onChange={(e) => setAuthForm({ ...authForm, oidcIssuerUrl: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Client ID</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcClientId} onChange={(e) => setAuthForm({ ...authForm, oidcClientId: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Client Secret</label>
                  <input type="password" className="w-full p-2 border rounded text-sm" placeholder={authSettingsData?.authSettings?.hasOidcClientSecret ? '•••••••• (set — enter new to rotate)' : 'Enter client secret'} value={authForm.oidcClientSecret} onChange={(e) => setAuthForm({ ...authForm, oidcClientSecret: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Redirect URI</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcRedirectUri} onChange={(e) => setAuthForm({ ...authForm, oidcRedirectUri: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Scopes</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcScopes} onChange={(e) => setAuthForm({ ...authForm, oidcScopes: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Email Claim</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcEmailClaim} onChange={(e) => setAuthForm({ ...authForm, oidcEmailClaim: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Username Claim</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcUsernameClaim} onChange={(e) => setAuthForm({ ...authForm, oidcUsernameClaim: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Role Claim</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.oidcRoleClaim} onChange={(e) => setAuthForm({ ...authForm, oidcRoleClaim: e.target.value })} disabled={!canAdminConfig} />
                </div>
              </div>
              <div className="mt-4 border-t pt-4 space-y-3">
                <label className="flex items-center justify-between gap-3 text-sm border border-gray-200 rounded px-3 py-2">
                  <span>Verify OIDC TLS Certificate</span>
                  <Switch
                    checked={authForm.oidcVerifySsl}
                    onChange={(checked) => {
                      setAuthForm((prev) => ({ ...prev, oidcVerifySsl: checked, oidcCaCertificate: checked ? prev.oidcCaCertificate : '' }));
                      if (!checked) setOidcCaCertificateTouched(true);
                    }}
                    disabled={!canAdminConfig}
                  />
                </label>
                {!authForm.oidcVerifySsl && (
                  <p className="text-xs text-orange-600">
                    TLS verification is disabled. Use only for trusted self-signed OIDC endpoints.
                  </p>
                )}
                {authForm.oidcVerifySsl && (
                  <div>
                    <label className="block text-xs font-semibold mb-1">Internal CA Certificate (PEM)</label>
                    <input
                      type="file"
                      accept=".pem,.crt,.cer,.txt"
                      className="block w-full text-xs mb-2"
                      disabled={!canAdminConfig}
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        const text = await file.text();
                        setAuthForm({ ...authForm, oidcCaCertificate: text });
                        setOidcCaCertificateTouched(true);
                      }}
                    />
                    <textarea
                      className="w-full p-2 border rounded text-sm min-h-[120px]"
                      placeholder="Paste PEM certificate content here (-----BEGIN CERTIFICATE----- ...)."
                      value={authForm.oidcCaCertificate}
                      onChange={(e) => {
                        setAuthForm({ ...authForm, oidcCaCertificate: e.target.value });
                        setOidcCaCertificateTouched(true);
                      }}
                      disabled={!canAdminConfig}
                    />
                    <div className="flex items-center justify-between mt-1">
                      <p className="text-xs text-gray-500">
                        {hasSavedOidcCaCertificate && !oidcCaCertificateTouched ? 'A CA certificate is already configured.' : 'Leave empty to keep current certificate.'}
                      </p>
                      <button
                        type="button"
                        className="text-xs text-red-600 disabled:text-gray-400"
                        disabled={!canAdminConfig}
                        onClick={() => {
                          setAuthForm({ ...authForm, oidcCaCertificate: '' });
                          setOidcCaCertificateTouched(true);
                        }}
                      >
                        Clear certificate
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="border border-gray-200 rounded-lg p-4 mb-4">
              <h4 className="font-semibold text-base mb-3">Role Mapping</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Admin Claim Values (CSV)</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.roleAdminValues} onChange={(e) => setAuthForm({ ...authForm, roleAdminValues: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Analyst Claim Values (CSV)</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.roleAnalystValues} onChange={(e) => setAuthForm({ ...authForm, roleAnalystValues: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Reviewer Claim Values (CSV)</label>
                  <input className="w-full p-2 border rounded text-sm" value={authForm.roleReviewerValues} onChange={(e) => setAuthForm({ ...authForm, roleReviewerValues: e.target.value })} disabled={!canAdminConfig} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Default Provisioned Role</label>
                  <select className="w-full p-2 border rounded text-sm" value={authForm.defaultProvisionedRole} onChange={(e) => setAuthForm({ ...authForm, defaultProvisionedRole: e.target.value })} disabled={!canAdminConfig}>
                    <option value="ADMIN">ADMIN</option>
                    <option value="RESOURCE_MANAGER">RESOURCE_MANAGER</option>
                    <option value="ANALYST">ANALYST</option>
                    <option value="REVIEWER">REVIEWER</option>
                    <option value="VIEWER">VIEWER</option>
                    <option value="ELONE">ELONE</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="border border-gray-200 rounded-lg p-4 mb-6">
              <h4 className="font-semibold text-base mb-3">Local Break-glass</h4>
              <label className="block text-xs font-semibold mb-1">Allowed Usernames (CSV)</label>
              <input className="w-full p-2 border rounded text-sm" value={authForm.breakglassUsernames} onChange={(e) => setAuthForm({ ...authForm, breakglassUsernames: e.target.value })} disabled={!canAdminConfig} />
              <p className="text-xs text-gray-500 mt-1">Only these usernames can use local login when break-glass is enabled.</p>
            </div>

            <div className="flex justify-end">
              <Button variant="primary" disabled={savingAuthSettings || !canAdminConfig} onClick={handleSaveAuthSettings}>
                {savingAuthSettings ? 'Saving...' : 'Save Authentication Settings'}
              </Button>
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'hef',
      label: 'OpenTIDE HEF',
      children: <HefPublishTargets />,
    },
    {
      key: 'rules',
      label: REPOSITORIES_TAB_LABEL,
      children: <App><ReposTab /></App>,
    },
    {
      key: 'misp',
      label: 'MISP',
      children: <App><MISPTab role={canAdminConfig ? 'ADMIN' : repoRole} /></App>,
    },
    {
      key: 'smtp',
      label: 'SMTP',
      children: <App><SMTPTab canManage={canAdminConfig} isSuperuser={false} organizations={orgData?.allOrganizations || []} /></App>,
    },
    {
      key: 'sharing',
      label: 'Instance Sharing',
      children: <App><InstanceSharing /></App>,
    },
    {
      key: 'aitasks',
      label: 'AI Tasks',
      children: <App><AITasksTab canManage={canAdminConfig} /></App>,
    },
    {
      key: 'orgai',
      label: 'Org AI',
      children: (
        <div className={`configuration-theme space-y-8 ${disableOrgAiEditing ? 'pointer-events-none opacity-80' : ''}`}>
          <div className="config-theme-panel rounded-lg shadow-sm border-2 border-hefaistos-border p-6">
            <h3 className="text-xl font-bold mb-1">Organization AI Settings</h3>
            <p className="text-sm text-gray-500 mb-6">
              Configure organization-wide AI models and API keys. Users can opt in to use these instead of their personal API keys.
            </p>
            {isSuperuser && (orgData?.allOrganizations?.length || 0) > 0 && (
              <div className="mb-4">
                <label className="block text-xs font-semibold mb-1">Target Organization</label>
                <Select
                  value={selectedOrgAiOrgId}
                  onChange={setSelectedOrgAiOrgId}
                  options={(orgData?.allOrganizations || []).map((org) => ({ value: org.id, label: org.name }))}
                />
              </div>
            )}
            <p className="text-xs text-gray-500 mb-4">
              Effective source: <span className="font-semibold">{orgAiData?.orgAiSettings?.configSource || 'CUSTOM'}</span>
              {orgAiData?.orgAiSettings?.sharedProfileName ? ` (${orgAiData.orgAiSettings.sharedProfileName})` : ''}
            </p>
            {orgAiLocked && (
              <p className="text-xs text-orange-700 mb-4">
                Shared AI is locked by superuser for this organization. Custom organization AI editing is disabled.
              </p>
            )}
            {isSuperuser && (
              <div className="border border-gray-200 rounded-lg p-5 mb-4">
                <h4 className="font-semibold text-base mb-3">Shared AI Assignment</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold mb-1">Shared AI Profile</label>
                    <Select
                      placeholder="Select shared AI profile"
                      value={selectedSharedAiProfileId}
                      onChange={(value) => setSelectedSharedAiProfileId(value)}
                      options={(sharedAiData?.sharedAiProfiles || []).map((profile) => ({
                        value: profile.id,
                        label: profile.name,
                      }))}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch checked={lockSharedAi} onChange={setLockSharedAi} />
                    <span className="text-xs font-medium text-gray-700">Lock shared AI for organization</span>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <AntButton type="default" onClick={handleAssignSharedAiProfile} loading={assigningSharedAiProfile} disabled={!selectedOrgAiOrgId || !selectedSharedAiProfileId}>
                    Apply Shared AI Assignment
                  </AntButton>
                  <Input
                    style={{ maxWidth: 260 }}
                    placeholder="New shared profile name"
                    value={sharedAiProfileName}
                    onChange={(e) => setSharedAiProfileName(e.target.value)}
                  />
                  <AntButton onClick={handleSaveSharedAiProfile} loading={savingSharedAiProfile}>
                    Save Current Settings As Shared
                  </AntButton>
                </div>
              </div>
            )}

            {/* Ollama */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.ollamaEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🦙</span>
                <h4 className="font-semibold text-base">Ollama (Self-Hosted LLM)</h4>
                {orgAiData?.orgAiSettings?.hasOllama && <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.ollamaEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button type="button" role="switch" aria-checked={orgAiForm.ollamaEnabled} onClick={() => setOrgAiForm(prev => ({ ...prev, ollamaEnabled: !prev.ollamaEnabled }))} className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.ollamaEnabled ? 'bg-green-500' : 'bg-gray-300'}`}>
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.ollamaEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">Point to your organization's Ollama instance. All users who opt in will use this model for AI features.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Ollama Base URL</label>
                  <input className="w-full p-2 border rounded text-sm" placeholder="e.g. http://ollama:11434" value={orgAiForm.ollamaBaseUrl} onChange={e => setOrgAiForm({ ...orgAiForm, ollamaBaseUrl: e.target.value })} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Model Name</label>
                  <input className="w-full p-2 border rounded text-sm" placeholder="e.g. llama3, mistral, codellama" value={orgAiForm.ollamaModel} onChange={e => setOrgAiForm({ ...orgAiForm, ollamaModel: e.target.value })} />
                </div>
              </div>
            </div>

            {/* OpenAI */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.openaiEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🤖</span>
                <h4 className="font-semibold text-base">OpenAI (ChatGPT)</h4>
                {orgAiData?.orgAiSettings?.hasOpenai && <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.openaiEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button type="button" role="switch" aria-checked={orgAiForm.openaiEnabled} onClick={() => setOrgAiForm(prev => ({ ...prev, openaiEnabled: !prev.openaiEnabled }))} className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.openaiEnabled ? 'bg-green-500' : 'bg-gray-300'}`}>
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.openaiEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">Organization-wide OpenAI API key. Users who opt in will use this key for GPT models.</p>
              <div>
                <label className="block text-xs font-semibold mb-1">OpenAI API Key</label>
                <input type="password" className="w-full p-2 border rounded text-sm" placeholder={orgAiData?.orgAiSettings?.hasOpenai ? '•••••••• (set — enter new value to update)' : 'sk-...'} value={orgAiForm.openaiKey} onChange={e => setOrgAiForm({ ...orgAiForm, openaiKey: e.target.value })} />
              </div>
            </div>

            {/* Gemini */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.geminiEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">✨</span>
                <h4 className="font-semibold text-base">Google Gemini</h4>
                {orgAiData?.orgAiSettings?.hasGemini && <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.geminiEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button type="button" role="switch" aria-checked={orgAiForm.geminiEnabled} onClick={() => setOrgAiForm(prev => ({ ...prev, geminiEnabled: !prev.geminiEnabled }))} className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.geminiEnabled ? 'bg-green-500' : 'bg-gray-300'}`}>
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.geminiEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">Organization-wide Gemini API key. Users who opt in will use this key for Gemini models.</p>
              <div>
                <label className="block text-xs font-semibold mb-1">Gemini API Key</label>
                <input type="password" className="w-full p-2 border rounded text-sm" placeholder={orgAiData?.orgAiSettings?.hasGemini ? '•••••••• (set — enter new value to update)' : 'AIza...'} value={orgAiForm.geminiKey} onChange={e => setOrgAiForm({ ...orgAiForm, geminiKey: e.target.value })} />
              </div>
            </div>

            {/* Claude */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.claudeEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🧠</span>
                <h4 className="font-semibold text-base">Anthropic Claude</h4>
                {orgAiData?.orgAiSettings?.hasClaude && <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.claudeEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button type="button" role="switch" aria-checked={orgAiForm.claudeEnabled} onClick={() => setOrgAiForm(prev => ({ ...prev, claudeEnabled: !prev.claudeEnabled }))} className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.claudeEnabled ? 'bg-green-500' : 'bg-gray-300'}`}>
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.claudeEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">Organization-wide Claude API key. Users who opt in will use this key for Claude models.</p>
              <div>
                <label className="block text-xs font-semibold mb-1">Claude API Key</label>
                <input type="password" className="w-full p-2 border rounded text-sm" placeholder={orgAiData?.orgAiSettings?.hasClaude ? '•••••••• (set — enter new value to update)' : 'sk-ant-...'} value={orgAiForm.claudeKey} onChange={e => setOrgAiForm({ ...orgAiForm, claudeKey: e.target.value })} />
              </div>
            </div>

            {/* Azure OpenAI */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.azureOpenaiEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">☁️</span>
                <h4 className="font-semibold text-base">Azure OpenAI (Azure Foundry)</h4>
                {orgAiData?.orgAiSettings?.hasAzureOpenai && <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.azureOpenaiEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button type="button" role="switch" aria-checked={orgAiForm.azureOpenaiEnabled} onClick={() => setOrgAiForm(prev => ({ ...prev, azureOpenaiEnabled: !prev.azureOpenaiEnabled }))} className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.azureOpenaiEnabled ? 'bg-green-500' : 'bg-gray-300'}`}>
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.azureOpenaiEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">Organization-wide Azure OpenAI endpoint. Users who opt in will use this deployment for GPT-5.x models.</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Azure Endpoint URL</label>
                  <input type="text" className="w-full p-2 border rounded text-sm" placeholder="https://YOUR_RESOURCE.openai.azure.com" value={orgAiForm.azureOpenaiEndpoint} onChange={e => setOrgAiForm({ ...orgAiForm, azureOpenaiEndpoint: e.target.value })} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">API Key</label>
                  <input type="password" className="w-full p-2 border rounded text-sm" placeholder={orgAiData?.orgAiSettings?.hasAzureOpenai ? '•••••••• (set — enter new value to update)' : 'Your Azure API key'} value={orgAiForm.azureOpenaiKey} onChange={e => setOrgAiForm({ ...orgAiForm, azureOpenaiKey: e.target.value })} />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Deployment Name</label>
                  <input type="text" className="w-full p-2 border rounded text-sm" placeholder="gpt-5-deployment" value={orgAiForm.azureOpenaiDeployment} onChange={e => setOrgAiForm({ ...orgAiForm, azureOpenaiDeployment: e.target.value })} />
                </div>
              </div>
            </div>

            {/* Preferred Model */}
            <div className="border border-gray-200 rounded-lg p-5 mb-4">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">⚙️</span>
                <h4 className="font-semibold text-base">Default Model</h4>
              </div>
              <p className="text-sm text-gray-500 mb-4">Set the default AI model used when users opt in to the organization AI. Leave blank to auto-detect based on configured providers.</p>
              <div>
                <label className="block text-xs font-semibold mb-1">Preferred Model</label>
                <input
                  type="text"
                  className="w-full p-2 border rounded text-sm"
                  value={orgAiForm.orgPreferredModel}
                  onChange={e => setOrgAiForm({ ...orgAiForm, orgPreferredModel: e.target.value })}
                  placeholder="Auto-detect if blank (e.g. GPT-5.5, GEMINI-3.5-FLASH, CLAUDE-SONNET-4.6, llama3.1)"
                />
                <p className="mt-1 text-xs text-gray-500">Leave blank to auto-detect from enabled providers.</p>
              </div>
            </div>

            <div className="flex justify-end mt-4">
              <Button variant="primary" disabled={savingOrgAi || disableOrgAiEditing} onClick={handleSaveOrgAi}>
                {savingOrgAi ? 'Saving...' : 'Save AI Settings'}
              </Button>
            </div>
            {orgAiData?.orgAiSettings?.hasAnyProvider && (
              <p className="mt-3 text-xs text-green-700">
                ✓ Organization AI is configured. Users can select "Use organization AI" in their profile settings.
              </p>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'platforms',
      label: 'Platform Credentials',
      children: (
        <App>
          <PlatformCredentials />
          <div style={{ maxWidth: 900, margin: '0 auto', padding: '0 0 24px' }}>
          </div>
        </App>
      ),
    },
    ...(canAdminConfig ? [{
      key: 'dac',
      label: (
        <Space size={6}>
          DaC
          <Tooltip title="Detection-as-Code deployment behavior">
            <InfoCircleOutlined />
          </Tooltip>
        </Space>
      ),
      children: <App><DacTab repositories={repoData?.allRuleRepositories || []} /></App>,
    }] : []),
    ...(isCurrentSuperuser ? [{
      key: 'system-update',
      label: 'System Update',
      children: <App><SystemUpdateTab isSuperuser={isCurrentSuperuser} /></App>,
    }] : []),
  ];
  const effectiveTab = tabItems.some((item) => item.key === tabFromUrl) ? tabFromUrl : String(tabItems[0]?.key || 'users');

  if (isAccessPending) return <p>Checking permissions...</p>;
  if (isAccessDenied) return null;

  return (
    <div className="configuration-theme">
      <Tabs
        activeKey={effectiveTab}
        onChange={handleTabChange}
        items={tabItems}
      />

      {/* Edit user modal */}
      {canAdminConfig && editingUser && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={(e) => { if (e.target === e.currentTarget) setEditingUser(null); }}
        >
          <div className="config-theme-panel rounded-lg shadow-lg w-full max-w-lg p-6 border-2 border-hefaistos-border">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold">Edit User: {editingUser.username}</h3>
              <button className="text-gray-500 hover:text-gray-700" onClick={() => setEditingUser(null)}>✕</button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold mb-1">Email</label>
                <input className="w-full p-2 border rounded" value={editForm.email} onChange={e => setEditForm({ ...editForm, email: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Role</label>
                <select className="w-full p-2 border rounded" value={editForm.role} onChange={e => setEditForm({ ...editForm, role: e.target.value })}>
                  <option value="ADMIN">ADMIN</option>
                  <option value="RESOURCE_MANAGER">RESOURCE_MANAGER</option>
                  <option value="ANALYST">ANALYST</option>
                  <option value="REVIEWER">REVIEWER</option>
                  <option value="VIEWER">VIEWER</option>
                  <option value="ELONE">ELONE</option>
                  <option value="BOT_AUDITOR_ORG">BOT_AUDITOR_ORG</option>
                  <option value="BOT_AUDITOR_GLOBAL">BOT_AUDITOR_GLOBAL</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Job Title</label>
                <input className="w-full p-2 border rounded" value={editForm.jobTitle} onChange={e => setEditForm({ ...editForm, jobTitle: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Slack Handle</label>
                <input className="w-full p-2 border rounded" value={editForm.slackHandle} onChange={e => setEditForm({ ...editForm, slackHandle: e.target.value })} />
              </div>
              {orgData?.allOrganizations?.length ? (
                <div>
                  <label className="block text-xs font-semibold mb-1">Organization</label>
                  <select className="w-full p-2 border rounded" value={editForm.organizationId} onChange={e => setEditForm({ ...editForm, organizationId: e.target.value })}>
                    <option value="">Select organization</option>
                    {orgData.allOrganizations.map((org) => (
                      <option key={org.id} value={org.id}>{org.name}</option>
                    ))}
                  </select>
                </div>
              ) : null}
              <div>
                <label className="block text-xs font-semibold mb-1">Bio</label>
                <textarea className="w-full p-2 border rounded h-24" value={editForm.bio} onChange={e => setEditForm({ ...editForm, bio: e.target.value })} />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <Button variant="secondary" onClick={() => setEditingUser(null)}>Cancel</Button>
              <Button
                variant="primary"
                disabled={saving}
                onClick={async () => {
                  try {
                    const variables: any = { userId: editingUser.id, email: editForm.email || null, role: editForm.role, bio: editForm.bio || null, jobTitle: editForm.jobTitle || null, slackHandle: editForm.slackHandle || null };
                    if (editForm.organizationId) variables.organizationId = editForm.organizationId;
                    await adminUpdateUser({ variables });
                    message.success('User updated successfully');
                    setEditingUser(null);
                    setEditForm({ email: '', role: '', bio: '', jobTitle: '', slackHandle: '', organizationId: '' });
                  } catch (e: any) {
                    message.error(e.message || 'Failed to update user');
                  }
                }}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Reset password modal */}
      {canAdminConfig && resetPasswordUser && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={(e) => { if (e.target === e.currentTarget) setResetPasswordUser(null); }}
        >
          <div className="config-theme-panel rounded-lg shadow-lg w-full max-w-md p-6 border-2 border-hefaistos-border">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold">Reset Password: {resetPasswordUser.username}</h3>
              <button className="text-gray-500 hover:text-gray-700" onClick={() => setResetPasswordUser(null)}>✕</button>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Set a new password for <strong>{resetPasswordUser.username}</strong>. The user will be notified by email if email is configured.
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold mb-1">New Password</label>
                <input type="password" className="w-full p-2 border rounded" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Enter new password" />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Confirm Password</label>
                <input type="password" className="w-full p-2 border rounded" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="Confirm new password" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <Button variant="secondary" onClick={() => setResetPasswordUser(null)}>Cancel</Button>
              <Button variant="primary" disabled={resettingPassword} onClick={handleResetPassword}>
                {resettingPassword ? 'Resetting...' : 'Reset Password'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
