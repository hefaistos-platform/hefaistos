import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Modal, Tabs, Button, Input, Upload, message, Typography, Alert, Select, Divider, Checkbox } from 'antd';
import { DownloadOutlined, UploadOutlined, GithubOutlined, CloudDownloadOutlined, CloudUploadOutlined, FileTextOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const VALID_DEPLOYMENT_PLATFORMS = ['defender', 'sentinel', 'splunk', 'qradar', 'wazuh'] as const;
const DEPLOYMENT_PLATFORM_SET = new Set<string>(VALID_DEPLOYMENT_PLATFORMS);
type KqlTargetPolicy = 'defender' | 'sentinel' | 'both';

const PLATFORM_VALUE_MAP: Record<string, string | null> = {
  // OpenTIDE detection format keys -> deployment target keys
  kql: 'defender',
  spl: 'splunk',
  wazuh: 'wazuh',
  qradar: 'qradar',
  eql: null,
  elastic: null,
  opensearch: null,
};

function normalizeDeploymentPlatforms(
  rawPlatforms: string[],
  kqlTargetPolicy: KqlTargetPolicy = 'defender',
): { mapped: string[]; dropped: string[] } {
  const mapped: string[] = [];
  const dropped: string[] = [];

  rawPlatforms.forEach((raw) => {
    if (!raw) {
      return;
    }
    const normalized = String(raw).trim().toLowerCase();
    if (!normalized) {
      return;
    }

    if (DEPLOYMENT_PLATFORM_SET.has(normalized)) {
      mapped.push(normalized);
      return;
    }

    if (normalized === 'kql') {
      if (kqlTargetPolicy === 'both') {
        mapped.push('defender', 'sentinel');
      } else if (kqlTargetPolicy === 'sentinel') {
        mapped.push('sentinel');
      } else {
        mapped.push('defender');
      }
      return;
    }

    const mappedPlatform = Object.prototype.hasOwnProperty.call(PLATFORM_VALUE_MAP, normalized)
      ? PLATFORM_VALUE_MAP[normalized]
      : null;
    if (mappedPlatform && DEPLOYMENT_PLATFORM_SET.has(mappedPlatform)) {
      mapped.push(mappedPlatform);
    } else {
      dropped.push(normalized);
    }
  });

  return {
    mapped: Array.from(new Set(mapped)),
    dropped: Array.from(new Set(dropped)),
  };
}

// GraphQL Queries
const GET_RULE_REPOSITORIES = gql`
  query GetRuleRepositories {
    allRuleRepositories {
      id
      name
      url
      username
    }
  }
`;

const GET_HEF_PUBLISH_PROFILES = gql`
  query GetOpenTideHefPublishProfiles {
    opentideHefPublishProfiles(enabled: true) {
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
    }
  }
`;

const GET_PLATFORM_CREDENTIALS = gql`
  query GetPlatformCredentialsForHefPublish {
    platformCredentials {
      id
      platform
      platformDisplay
      enabled
      hasCredentials
    }
  }
`;

const GET_HEF_PUBLISH_JOB_STATUS = gql`
  query GetOpenTideHefPublishJobStatus($taskId: UUID!) {
    opentideHefPublishJobStatus(taskId: $taskId) {
      taskId
      status
      progress
      commitSha
      githubUrl
      filePaths
      requestedPlatforms
      deployedPlatforms
      deploymentResults
      failureSummary
      errorMessage
      createdAt
      startedAt
      completedAt
    }
  }
`;

// GraphQL Mutations
const EXPORT_PLAYBOOK_MUTATION = gql`
  mutation ExportPlaybookGraph($graphId: UUID!) {
    exportPlaybookGraph(graphId: $graphId) {
      success
      exportData
      message
    }
  }
`;

const IMPORT_PLAYBOOK_MUTATION = gql`
  mutation ImportPlaybookGraph($importData: JSONString!, $newTitle: String, $graphId: UUID) {
    importPlaybookGraph(importData: $importData, newTitle: $newTitle, graphId: $graphId) {
      success
      graph { id title }
      message
    }
  }
`;

const PULL_FROM_GITHUB_MUTATION = gql`
  mutation PullPlaybookFromGitHub(
    $repositoryId: String
    $githubToken: String
    $repoOwner: String
    $repoName: String
    $filePath: String!
    $branch: String
    $newTitle: String
    $graphId: UUID
  ) {
    pullPlaybookFromGithub(
      repositoryId: $repositoryId
      githubToken: $githubToken
      repoOwner: $repoOwner
      repoName: $repoName
      filePath: $filePath
      branch: $branch
      newTitle: $newTitle
      graphId: $graphId
    ) {
      success
      graph { id title }
      message
    }
  }
`;

const PUBLISH_WORKBENCH_OPENTIDE_MUTATION = gql`
  mutation PublishWorkbenchOpenTide(
    $graphId: UUID!
    $profileId: UUID
    $repositoryId: ID
    $branch: String
    $targetFolder: String
    $platforms: [String]
    $kqlTargetPolicy: String
    $commitMessage: String
    $pushOpentideBundle: Boolean
    $pushPlatformRules: Boolean
  ) {
    publishWorkbenchOpenTide(
      graphId: $graphId
      profileId: $profileId
      repositoryId: $repositoryId
      branch: $branch
      targetFolder: $targetFolder
      platforms: $platforms
      kqlTargetPolicy: $kqlTargetPolicy
      commitMessage: $commitMessage
      pushOpentideBundle: $pushOpentideBundle
      pushPlatformRules: $pushPlatformRules
    ) {
      success
      message
      taskId
    }
  }
`;

const EXPORT_WORKBENCH_DOCUMENT_MUTATION = gql`
  mutation ExportWorkbenchDocument($graphId: UUID!, $format: String!) {
    exportWorkbenchDocument(graphId: $graphId, format: $format) {
      success
      fileData
      filename
      contentType
      message
    }
  }
`;

// TypeScript interfaces for mutation responses
interface ExportPlaybookResponse {
  exportPlaybookGraph: {
    success: boolean;
    exportData: string;
    message: string;
  };
}

interface ImportPlaybookResponse {
  importPlaybookGraph: {
    success: boolean;
    graph: { id: string; title: string } | null;
    message: string;
  };
}

interface PublishWorkbenchOpenTideResponse {
  publishWorkbenchOpenTide: {
    success: boolean;
    message: string;
    taskId: string | null;
  };
}

interface PullFromGitHubResponse {
  pullPlaybookFromGithub: {
    success: boolean;
    graph: { id: string; title: string } | null;
    message: string;
  };
}

interface ExportWorkbenchDocumentResponse {
  exportWorkbenchDocument: {
    success: boolean;
    fileData: string | null;
    filename: string | null;
    contentType: string | null;
    message: string;
  };
}

interface ExportImportModalProps {
  visible: boolean;
  onClose: () => void;
  playbookId: string;
  playbookTitle: string;
  onImportSuccess?: (graphId: string) => void;
  configuredPlatforms?: string[];
  initialTab?: string;
}

export const ExportImportModal: React.FC<ExportImportModalProps> = ({
  visible,
  onClose,
  playbookId,
  playbookTitle,
  onImportSuccess,
  configuredPlatforms = [],
  initialTab = 'export',
}) => {
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  const [exportData, setExportData] = useState<string>('');
  const [importData, setImportData] = useState<string>('');
  const [newTitle, setNewTitle] = useState<string>('');
  
  // Document export state
  const [docFormat, setDocFormat] = useState<string>('docx');

  // Repository state
  const [githubToken, setGithubToken] = useState<string>('');
  const [repoOwner, setRepoOwner] = useState<string>('');
  const [repoName, setRepoName] = useState<string>('');
  const [filePath, setFilePath] = useState<string>('');
  const [branch, setBranch] = useState<string>('main');
  const [commitMessage, setCommitMessage] = useState<string>('');
  const [selectedRepoId, setSelectedRepoId] = useState<string>('');
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [publishTaskId, setPublishTaskId] = useState<string | null>(null);
  const [publishNoticeShownForTask, setPublishNoticeShownForTask] = useState<string | null>(null);
  const [publishDebugError, setPublishDebugError] = useState<string>('');
  const [publishDebugWarning, setPublishDebugWarning] = useState<string>('');
  const [pushOpentideBundle, setPushOpentideBundle] = useState<boolean>(true);
  const [pushPlatformRules, setPushPlatformRules] = useState<boolean>(false);
  const [kqlTargetPolicy, setKqlTargetPolicy] = useState<KqlTargetPolicy>('defender');

  // Query configured repositories
  const { data: reposData, loading: reposLoading, error: reposError } = useQuery(GET_RULE_REPOSITORIES);
  const { data: profilesData, loading: profilesLoading, error: profilesError } = useQuery(GET_HEF_PUBLISH_PROFILES, {
    skip: !visible,
  });
  const { data: platformData, error: platformError } = useQuery(GET_PLATFORM_CREDENTIALS, {
    skip: !visible,
  });
  const { data: publishStatusData, error: publishStatusError } = useQuery(GET_HEF_PUBLISH_JOB_STATUS, {
    variables: { taskId: publishTaskId },
    skip: !publishTaskId,
    pollInterval: publishTaskId ? 2000 : 0,
    fetchPolicy: 'network-only',
  });

  useEffect(() => {
    if (!visible) {
      return;
    }
    if (reposError) {
      console.error('[HEF-PUBLISH][repositories-query-error]', {
        playbookId,
        error: reposError.message,
      });
    }
    if (profilesError) {
      console.error('[HEF-PUBLISH][profiles-query-error]', {
        playbookId,
        error: profilesError.message,
      });
    }
    if (platformError) {
      console.error('[HEF-PUBLISH][platform-credentials-query-error]', {
        playbookId,
        error: platformError.message,
      });
    }
  }, [visible, playbookId, reposError, profilesError, platformError]);

  // Auto-fill owner/repo when a configured repository is selected
  useEffect(() => {
    if (selectedRepoId && reposData?.allRuleRepositories) {
      const selectedRepo = reposData.allRuleRepositories.find((r: any) => r.id === selectedRepoId);
      if (selectedRepo) {
        const urlMatch = (selectedRepo.url || '').match(/(?:github\.com|gitlab\.com|bitbucket\.org)[:/]([^/]+)\/([^/.]+)/);
        if (urlMatch) {
          setRepoOwner(urlMatch[1]);
          setRepoName(urlMatch[2]);
        }
      }
    } else if (!selectedRepoId) {
      setRepoOwner('');
      setRepoName('');
    }
  }, [selectedRepoId, reposData]);

  useEffect(() => {
    if (visible) {
      setActiveTab(initialTab);
    }
  }, [initialTab, visible]);

  useEffect(() => {
    if (!visible) {
      setSelectedProfileId('');
      setSelectedRepoId('');
      setSelectedPlatforms([]);
      setPublishTaskId(null);
      setPublishNoticeShownForTask(null);
      setPublishDebugError('');
      setPublishDebugWarning('');
      setPushOpentideBundle(true);
      setPushPlatformRules(false);
      setKqlTargetPolicy('defender');
      return;
    }
    setSelectedPlatforms([]);
  }, [visible]);

  useEffect(() => {
    if (!selectedProfileId || !profilesData?.opentideHefPublishProfiles) {
      return;
    }

    const profile = profilesData.opentideHefPublishProfiles.find((item: any) => item.id === selectedProfileId);
    if (!profile) {
      return;
    }

    setSelectedRepoId(profile.repositoryId || '');
    setBranch(profile.branch || 'main');
    setFilePath(profile.targetFolder || '');
    setSelectedPlatforms(
      profile.enabledPlatforms?.length
        ? profile.enabledPlatforms
        : []
    );
    setKqlTargetPolicy(
      (profile.kqlTargetPolicy === 'sentinel' || profile.kqlTargetPolicy === 'both')
        ? profile.kqlTargetPolicy
        : 'defender'
    );
    setPushPlatformRules(Boolean(profile.pushPlatformRules));
  }, [selectedProfileId, profilesData]);

  useEffect(() => {
    const job = publishStatusData?.opentideHefPublishJobStatus;
    if (!job || !publishTaskId || publishNoticeShownForTask === publishTaskId) {
      return;
    }

    console.info('[HEF-PUBLISH][job-status]', {
      playbookId,
      taskId: publishTaskId,
      status: job.status,
      progress: job.progress,
      errorMessage: job.errorMessage,
    });

    if (job.status === 'COMPLETED') {
      message.success(job.progress || 'OpenTIDE HEF publish completed successfully');
      if (job.githubUrl) {
        window.open(job.githubUrl, '_blank');
      }
      setPublishNoticeShownForTask(publishTaskId);
    } else if (job.status === 'FAILED') {
      message.error(job.errorMessage || job.progress || 'OpenTIDE HEF publish failed');
      setPublishNoticeShownForTask(publishTaskId);
    }
  }, [publishStatusData, publishTaskId, publishNoticeShownForTask, playbookId]);

  useEffect(() => {
    if (!publishStatusError || !publishTaskId) {
      return;
    }

    const statusErrorMessage = publishStatusError.message || 'Unknown polling error';
    console.error('[HEF-PUBLISH][status-polling-error]', {
      playbookId,
      taskId: publishTaskId,
      error: statusErrorMessage,
    });

    setPublishDebugError(`HEF status polling failed for task ${publishTaskId}: ${statusErrorMessage}`);
    if (statusErrorMessage.toLowerCase().includes('authentication required')) {
      message.error('HEF status polling failed: authentication required. Please sign in again.');
      // Stop infinite polling when user session is invalid.
      setPublishTaskId(null);
    }
  }, [publishStatusError, publishTaskId, playbookId]);

  // Mutations with proper types
  const [exportPlaybook, { loading: exporting }] = useMutation<ExportPlaybookResponse>(EXPORT_PLAYBOOK_MUTATION);
  const [importPlaybook, { loading: importing }] = useMutation<ImportPlaybookResponse>(IMPORT_PLAYBOOK_MUTATION);
  const [pullFromGitHub, { loading: pulling }] = useMutation<PullFromGitHubResponse>(PULL_FROM_GITHUB_MUTATION);
  const [exportDocument, { loading: exportingDoc }] = useMutation<ExportWorkbenchDocumentResponse>(EXPORT_WORKBENCH_DOCUMENT_MUTATION);
  const [publishWorkbenchOpenTide, { loading: pushing }] = useMutation<PublishWorkbenchOpenTideResponse>(PUBLISH_WORKBENCH_OPENTIDE_MUTATION);
  const repositoryOptions = reposData?.allRuleRepositories ?? [];
  const publishProfiles = profilesData?.opentideHefPublishProfiles ?? [];
  const platformOptions = (platformData?.platformCredentials ?? [])
    .filter((credential: any) => credential.enabled && credential.hasCredentials)
    .map((credential: any) => ({
      label: credential.platformDisplay,
      value: credential.platform,
    }));

  // Export handler
  const handleExport = async () => {
    try {
      const result = await exportPlaybook({ variables: { graphId: playbookId } });
      if (result.data?.exportPlaybookGraph?.success) {
        setExportData(result.data.exportPlaybookGraph.exportData);
        message.success('Playbook exported successfully!');
      } else {
        message.error(result.data?.exportPlaybookGraph?.message || 'Export failed');
      }
    } catch (e: any) {
      message.error(e.message || 'Export failed');
    }
  };

  // Download as file
  const handleDownload = () => {
    if (!exportData) return;
    const blob = new Blob([exportData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${playbookTitle.replace(/[^a-zA-Z0-9]/g, '_')}_export.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success('File downloaded!');
  };

  // Import handler
  const handleImport = async () => {
    if (!importData.trim()) {
      message.error('Please paste or upload import data');
      return;
    }
    try {
      const result = await importPlaybook({ 
        variables: { 
          importData: importData,
          newTitle: newTitle || undefined,
          graphId: playbookId
        } 
      });
      if (result.data?.importPlaybookGraph?.success) {
        message.success(result.data.importPlaybookGraph.message);
        if (onImportSuccess && result.data.importPlaybookGraph.graph?.id) {
          onImportSuccess(result.data.importPlaybookGraph.graph.id);
        }
        onClose();
      } else {
        message.error(result.data?.importPlaybookGraph?.message || 'Import failed');
      }
    } catch (e: any) {
      message.error(e.message || 'Import failed');
    }
  };

  // File upload handler
  const handleFileUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setImportData(content);
      message.success('File loaded!');
    };
    reader.readAsText(file);
    return false; // Prevent auto upload
  };

  // Repository Push handler
  const handlePublishOpenTide = async () => {
    const publishAttemptId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setPublishDebugError('');
    setPublishDebugWarning('');

    const { mapped: normalizedPlatforms, dropped: droppedPlatforms } = normalizeDeploymentPlatforms(
      selectedPlatforms,
      kqlTargetPolicy,
    );

    if (droppedPlatforms.length > 0) {
      const droppedMsg = `Ignoring unsupported platform values: ${droppedPlatforms.join(', ')}`;
      setPublishDebugWarning(droppedMsg);
      message.warning(droppedMsg);
    }

    console.info('[HEF-PUBLISH][attempt-start]', {
      attemptId: publishAttemptId,
      playbookId,
      selectedProfileId,
      selectedRepoId,
      branch,
      targetFolder: filePath,
      selectedPlatforms,
      normalizedPlatforms,
      droppedPlatforms,
      kqlTargetPolicy,
      hasCommitMessage: Boolean(commitMessage),
    });

    if (!selectedProfileId && !selectedRepoId) {
      message.error('Please select a HEF publish profile or a configured repository');
      console.warn('[HEF-PUBLISH][attempt-blocked]', {
        attemptId: publishAttemptId,
        reason: 'No profile/repository selected',
      });
      return;
    }

    try {
      const result = await publishWorkbenchOpenTide({
        variables: {
          graphId: playbookId,
          profileId: selectedProfileId || undefined,
          repositoryId: selectedProfileId ? undefined : (selectedRepoId || undefined),
          targetFolder: filePath || undefined,
          branch: branch || 'main',
          platforms: normalizedPlatforms,
          kqlTargetPolicy,
          commitMessage: commitMessage || undefined,
          pushOpentideBundle,
          pushPlatformRules,
        }
      });

      console.info('[HEF-PUBLISH][attempt-response]', {
        attemptId: publishAttemptId,
        response: result.data?.publishWorkbenchOpenTide,
      });

      if (result.data?.publishWorkbenchOpenTide?.success) {
        message.success(result.data.publishWorkbenchOpenTide.message || 'OpenTIDE HEF publish queued successfully');
        setPublishTaskId(result.data.publishWorkbenchOpenTide.taskId || null);
        setPublishNoticeShownForTask(null);
      } else {
        const backendMsg = result.data?.publishWorkbenchOpenTide?.message || 'OpenTIDE HEF publish failed';
        message.error(backendMsg);
        setPublishDebugError(`Publish attempt ${publishAttemptId} failed: ${backendMsg}`);
      }
    } catch (e: any) {
      const errMsg = e?.message || 'OpenTIDE HEF publish failed';
      const gqlErrors = e?.graphQLErrors?.map((err: any) => err?.message).filter(Boolean) || [];
      const networkError = e?.networkError?.message || null;

      console.error('[HEF-PUBLISH][attempt-error]', {
        attemptId: publishAttemptId,
        playbookId,
        error: errMsg,
        graphQLErrors: gqlErrors,
        networkError,
      });

      const details = [errMsg, ...gqlErrors, networkError].filter(Boolean).join(' | ');
      message.error(details || 'OpenTIDE HEF publish failed');
      setPublishDebugError(`Publish attempt ${publishAttemptId} exception: ${details || 'Unknown error'}`);
    }
  };

  const currentPublishJob = publishStatusData?.opentideHefPublishJobStatus;

  const handlePullFromGitHub = async () => {
    if (!selectedRepoId && (!githubToken || !repoOwner || !repoName)) {
      message.error('Please select a repository or fill in all required repository fields');
      return;
    }
    if (!filePath) {
      message.error('Please specify the file path in the repository');
      return;
    }
    try {
      const result = await pullFromGitHub({
        variables: {
          repositoryId: selectedRepoId || undefined,
          githubToken: selectedRepoId ? undefined : githubToken,
          repoOwner: selectedRepoId ? undefined : repoOwner,
          repoName: selectedRepoId ? undefined : repoName,
          filePath,
          branch: branch || 'main',
          newTitle: newTitle || undefined,
          graphId: playbookId
        }
      });
      if (result.data?.pullPlaybookFromGithub?.success) {
        message.success(result.data.pullPlaybookFromGithub.message);
        if (onImportSuccess && result.data.pullPlaybookFromGithub.graph?.id) {
          onImportSuccess(result.data.pullPlaybookFromGithub.graph.id);
        }
        onClose();
      } else {
        message.error(result.data?.pullPlaybookFromGithub?.message || 'Pull failed');
      }
    } catch (e: any) {
      message.error(e.message || 'Pull failed');
    }
  };

  // Export document handler
  const handleExportDocument = async () => {
    try {
      const result = await exportDocument({ variables: { graphId: playbookId, format: docFormat } });
      const payload = result.data?.exportWorkbenchDocument;
      if (payload?.success && payload.fileData && payload.filename && payload.contentType) {
        const binary = atob(payload.fileData);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: payload.contentType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = payload.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        message.success(`Document exported as ${payload.filename}`);
      } else {
        message.error(payload?.message || 'Export failed');
      }
    } catch (e: any) {
      message.error(e.message || 'Export failed');
    }
  };

  const tabItems = [
    {
      key: 'export',
      label: (
        <span>
          <DownloadOutlined /> Export (HEX v2.0)
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="Export Playbook as HEX v2.0"
            description="Export this playbook in the HEFAISTOS standardized format (HEX v2.0) - a human-readable, developer-friendly JSON format that includes capability abstraction layers. Perfect for sharing, version control, and community contribution."
            type="info"
            showIcon
          />
          
          <div className="bg-blue-50 p-3 rounded border border-blue-200">
            <Typography.Text strong>📋 HEX v2.0 Format Features:</Typography.Text>
            <ul className="mt-2 space-y-1 text-sm">
              <li>✅ Clear section organization (metadata, strategy, detection, SOAR config, etc.)</li>
              <li>✅ Explicit capability abstraction layer mapping</li>
              <li>✅ Human-readable and easy to manually edit</li>
              <li>✅ Developer-friendly for creating playbooks outside HEFAISTOS</li>
              <li>✅ Includes all graph nodes, edges, and configurations</li>
            </ul>
          </div>
          
          <Button 
            type="primary" 
            icon={<DownloadOutlined />} 
            onClick={handleExport}
            loading={exporting}
            block
          >
            Generate Export
          </Button>

          {exportData && (
            <>
              <TextArea 
                value={exportData} 
                rows={10} 
                readOnly 
                className="font-mono text-xs"
              />
              <Button 
                type="primary" 
                icon={<DownloadOutlined />} 
                onClick={handleDownload}
                block
              >
                Download as File
              </Button>
            </>
          )}
        </div>
      )
    },
    {
      key: 'import',
      label: (
        <span>
          <UploadOutlined /> Import (HEX v2.0)
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="Import Playbook from HEX v2.0"
            description="Import a playbook from a HEX v2.0 JSON file. This will overwrite the current workbench with the imported data."
            type="info"
            showIcon
          />

          <div className="bg-green-50 p-3 rounded border border-green-200">
            <Typography.Text strong>✨ Import Options:</Typography.Text>
            <ul className="mt-2 space-y-1 text-sm">
              <li>📄 Paste JSON directly into the text area below</li>
              <li>📁 Drag & drop a .json file</li>
              <li>📋 Upload a file from your computer</li>
              <li>🔗 Create playbooks manually using HEX v2.0 schema</li>
            </ul>
          </div>

          <Upload.Dragger
            accept=".json"
            beforeUpload={handleFileUpload}
            showUploadList={false}
          >
            <p className="ant-upload-drag-icon">
              <UploadOutlined />
            </p>
            <p className="ant-upload-text">Click or drag JSON file to upload</p>
          </Upload.Dragger>

          <Text type="secondary">Or paste JSON directly:</Text>
          <TextArea
            value={importData}
            onChange={(e) => setImportData(e.target.value)}
            rows={8}
            placeholder='{"hefaistos_version": "1.0", ...}'
            className="font-mono text-xs"
          />

          <Input
            placeholder="New title (optional - override imported title)"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />

          <Button 
            type="primary" 
            icon={<UploadOutlined />} 
            onClick={handleImport}
            loading={importing}
            disabled={!importData.trim()}
            block
          >
            Import Playbook
          </Button>
        </div>
      )
    },
    {
      key: 'github',
      label: (
        <span>
          <GithubOutlined /> Repository
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="OpenTIDE Publishing"
            description="OpenTIDE HEF validates the workbench, pushes YAML to the selected repository, and can deploy to selected platforms in the background. Supported Git services: GitHub, GitLab, and Gitea."
            type="info"
            showIcon
          />

          <div className="border rounded-lg p-4 space-y-3">
            <Text strong>OpenTIDE HEF Publish Target</Text>
            <Select
              placeholder="Select a HEF publish profile (optional)"
              value={selectedProfileId || undefined}
              onChange={(value) => setSelectedProfileId(value || '')}
              loading={profilesLoading}
              allowClear
              style={{ width: '100%' }}
            >
              {publishProfiles.map((profile: any) => (
                <Select.Option key={profile.id} value={profile.id}>
                  {profile.name} ({profile.repositoryName || profile.repositoryUrl})
                </Select.Option>
              ))}
            </Select>

            {publishProfiles.length === 0 && (
              <Alert
                type="warning"
                showIcon
                message="No OpenTIDE HEF publish profiles configured"
                description={
                  <span>
                    Create one in <a href="/mgmt/config?tab=hef">Configuration → OpenTIDE HEF</a>.
                  </span>
                }
              />
            )}

            <Text strong>Select Repository</Text>
            <Select
              placeholder="Select a configured repository"
              value={selectedRepoId || undefined}
              onChange={(value) => setSelectedRepoId(value || '')}
              loading={reposLoading}
              allowClear
              style={{ width: '100%' }}
            >
              {repositoryOptions.map((repo: any) => (
                <Select.Option key={repo.id} value={repo.id}>
                  {repo.name} ({repo.url}){repo.provider ? ` [${repo.provider}]` : ''}
                </Select.Option>
              ))}
            </Select>
            <Text type="secondary" className="text-xs">
              Supported services: GitHub, GitLab, and Gitea.
            </Text>

            {!reposLoading && repositoryOptions.length === 0 && (
              <Text type="secondary" className="text-xs">
                No repositories are configured in Configuration → Rules yet.
              </Text>
            )}

            {selectedRepoId && repoOwner && (
              <Text type="secondary" className="text-xs">
                Using: {repoOwner}/{repoName}
              </Text>
            )}

            {!selectedRepoId && !selectedProfileId && (
              <>
                <Divider plain style={{ margin: '8px 0' }}>
                  <Text type="secondary" className="text-xs">Or enter repository details manually</Text>
                </Divider>
                <Input.Password
                  placeholder="Repository Personal Access Token"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  prefix={<GithubOutlined />}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Repository Owner"
                    value={repoOwner}
                    onChange={(e) => setRepoOwner(e.target.value)}
                  />
                  <Input
                    placeholder="Repository Name"
                    value={repoName}
                    onChange={(e) => setRepoName(e.target.value)}
                  />
                </div>
              </>
            )}

            <Input
              placeholder="Target Folder (optional, e.g., content/hefaistos)"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
            />
            <Input
              placeholder="Branch (default: main)"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
            <Select
              mode="multiple"
              placeholder="Deployment platforms (optional)"
              value={selectedPlatforms}
              onChange={setSelectedPlatforms}
              options={platformOptions}
              style={{ width: '100%' }}
            />
            <Select
              value={kqlTargetPolicy}
              onChange={(value) => setKqlTargetPolicy(value as KqlTargetPolicy)}
              style={{ width: '100%' }}
              options={[
                { value: 'defender', label: 'KQL deploy target: Defender' },
                { value: 'sentinel', label: 'KQL deploy target: Sentinel' },
                { value: 'both', label: 'KQL deploy target: Defender + Sentinel' },
              ]}
            />
            <Text type="secondary" className="text-xs">
              Applies when selected or inherited platforms contain KQL.
            </Text>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Push Section */}
            <div className="border rounded-lg p-4 space-y-3">
              <Text strong><CloudUploadOutlined /> Publish OpenTIDE HEF</Text>
              <Paragraph type="secondary" className="text-xs">
                Queue a background job that compiles TVM, DOM, and MDR YAML, validates the bundle, commits it to the selected repository, and deploys the resulting OpenTIDE rule to the selected platforms.
              </Paragraph>
              <Input
                placeholder="Commit message (optional)"
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
              />
              <Checkbox
                checked={pushOpentideBundle}
                onChange={(e) => setPushOpentideBundle(e.target.checked)}
              >
                Push OpenTide bundle
              </Checkbox>
              <Checkbox
                checked={pushPlatformRules}
                onChange={(e) => setPushPlatformRules(e.target.checked)}
              >
                Also save individual rules by format
              </Checkbox>
              <Text type="secondary" className="text-xs">
                Saves each platform rule as a standalone file in kql/, splunk/, wazuh/, qradar/ directories
              </Text>
              <Button 
                type="primary" 
                icon={<CloudUploadOutlined />}
                onClick={handlePublishOpenTide}
                loading={pushing}
                disabled={!selectedProfileId && !selectedRepoId}
                block
              >
                Publish
              </Button>
              {currentPublishJob && publishTaskId && (
                <Alert
                  type={currentPublishJob.status === 'FAILED' ? 'error' : currentPublishJob.status === 'COMPLETED' ? 'success' : 'info'}
                  showIcon
                  message={`Job ${currentPublishJob.status}`}
                  description={
                    <div>
                      <div>{currentPublishJob.progress || 'Queued for processing'}</div>
                      {currentPublishJob.commitSha && <div>Commit: {currentPublishJob.commitSha}</div>}
                      {currentPublishJob.deployedPlatforms?.length > 0 && (
                        <div>Deployed: {currentPublishJob.deployedPlatforms.join(', ')}</div>
                      )}
                      {(() => {
                        let summary: { failure_type_counts?: Record<string, number> } | null = null;
                        try {
                          summary = currentPublishJob.failureSummary
                            ? JSON.parse(currentPublishJob.failureSummary)
                            : null;
                        } catch {
                          summary = null;
                        }
                        const counts = summary?.failure_type_counts || {};
                        const labels = Object.entries(counts).map(([k, v]) => `${k}=${v}`);
                        if (!labels.length) return null;
                        return <div>Failure types: {labels.join(', ')}</div>;
                      })()}
                      {(() => {
                        let results: Array<{
                          platform: string;
                          success: boolean;
                          message?: string;
                          errors?: string[];
                          failure_type?: string;
                          probable_cause?: string;
                          operator_hint?: string;
                        }> = [];
                        try {
                          results = currentPublishJob.deploymentResults
                            ? JSON.parse(currentPublishJob.deploymentResults)
                            : [];
                        } catch {
                          results = [];
                        }
                        const failed = results.filter((r) => !r.success);
                        if (failed.length === 0) return null;
                        return (
                          <div style={{ marginTop: 6 }}>
                            <Text strong>Platform deployment errors:</Text>
                            {failed.map((r, i) => (
                              <div key={i} style={{ marginTop: 4, paddingLeft: 8, borderLeft: '3px solid var(--ant-color-error, #ff4d4f)' }}>
                                <Text strong>{r.platform}: </Text>
                                <Text>{r.message || 'Unknown error'}</Text>
                                {r.failure_type && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      Type: {r.failure_type}
                                    </Text>
                                  </div>
                                )}
                                {r.probable_cause && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      Cause: {r.probable_cause}
                                    </Text>
                                  </div>
                                )}
                                {r.operator_hint && (
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      Hint: {r.operator_hint}
                                    </Text>
                                  </div>
                                )}
                                {r.errors && r.errors.length > 0 && (
                                  <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                                    {r.errors.map((e, j) => (
                                      <li key={j}><Text type="secondary" style={{ fontSize: 12 }}>{e}</Text></li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            ))}
                          </div>
                        );
                      })()}
                    </div>
                  }
                />
              )}
              {publishDebugError && (
                <Alert
                  type="error"
                  showIcon
                  message="HEF Publish Debug"
                  description={publishDebugError}
                />
              )}
              {publishDebugWarning && (
                <Alert
                  type="warning"
                  showIcon
                  message="HEF Publish Warning"
                  description={publishDebugWarning}
                />
              )}
            </div>

            {/* Pull Section */}
            <div className="border rounded-lg p-4 space-y-3">
              <Text strong><CloudDownloadOutlined /> Pull from Repository</Text>
              <Paragraph type="secondary" className="text-xs">
                Import a playbook from a JSON file in your repository.
              </Paragraph>
              <Input
                placeholder="New title (optional)"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
              <Button 
                type="primary" 
                icon={<CloudDownloadOutlined />}
                onClick={handlePullFromGitHub}
                loading={pulling}
                disabled={(!selectedRepoId && (!githubToken || !repoOwner || !repoName)) || !filePath}
                block
              >
                Pull
              </Button>
            </div>
          </div>

          <Alert
            message="Tip"
            description="The HEF publish action now runs asynchronously. If you pick a publish profile, its repository, folder, branch, and platform defaults are used unless you override them here."
            type="info"
            showIcon
          />
        </div>
      )
    },
    {
      key: 'document',
      label: (
        <span>
          <FileTextOutlined /> Export Document
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="Export Workbench as Document"
            description="Export this workbench as a formatted document containing: Title, ID, Technical Context, Response Playbook, and Tags."
            type="info"
            showIcon
          />

          <div className="border rounded-lg p-4 space-y-3">
            <Typography.Text strong>Select Format</Typography.Text>
            <Select
              value={docFormat}
              onChange={setDocFormat}
              style={{ width: '100%' }}
              options={[
                { label: 'Word Document (.docx)', value: 'docx' },
                { label: 'PDF Document (.pdf)', value: 'pdf' },
                { label: 'CSV Spreadsheet (.csv)', value: 'csv' },
              ]}
            />
          </div>

          <div className="bg-blue-50 p-3 rounded border border-blue-200">
            <Typography.Text strong>📄 Document Contents:</Typography.Text>
            <ul className="mt-2 space-y-1 text-sm">
              <li>✅ Title — name of the detection workbench</li>
              <li>✅ ID — unique workbench identifier</li>
              <li>✅ Technical Context</li>
              <li>✅ Response Playbook</li>
              <li>✅ Tags</li>
            </ul>
          </div>

          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleExportDocument}
            loading={exportingDoc}
            block
          >
            Download {docFormat.toUpperCase()}
          </Button>
        </div>
      )
    }
  ];

  return (
    <Modal
      title="Export / Import Playbook"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={700}
      destroyOnClose
      className="export-import-modal"
    >
      <Tabs 
        activeKey={activeTab} 
        onChange={setActiveTab}
        items={tabItems}
      />
    </Modal>
  );
};

export default ExportImportModal;
