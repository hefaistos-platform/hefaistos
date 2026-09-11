import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Modal, Tabs, Button, Input, Upload, message, Typography, Alert, Collapse, Select } from 'antd';
import { UploadOutlined, GithubOutlined, CloudDownloadOutlined, ApiOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;
const { Panel } = Collapse;

// GraphQL Mutations
const IMPORT_PLAYBOOK_MUTATION = gql`
  mutation ImportPlaybookGraph($importData: JSONString!, $newTitle: String) {
    importPlaybookGraph(importData: $importData, newTitle: $newTitle) {
      success
      graph { id title }
      message
    }
  }
`;

const GET_RULE_REPOSITORIES = gql`
  query GetRuleRepositoriesForImportModal {
    allRuleRepositories {
      id
      name
      url
      provider
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
  ) {
    pullPlaybookFromGithub(
      repositoryId: $repositoryId
      githubToken: $githubToken
      repoOwner: $repoOwner
      repoName: $repoName
      filePath: $filePath
      branch: $branch
      newTitle: $newTitle
    ) {
      success
      graph { id title }
      message
    }
  }
`;

const IMPORT_FROM_OPENTIDE_MUTATION = gql`
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
      graph { id title }
      message
    }
  }
`;

// TypeScript interfaces for mutation responses
interface ImportPlaybookResponse {
  importPlaybookGraph: {
    success: boolean;
    graph: { id: string; title: string } | null;
    message: string;
  };
}

interface PullFromGitHubResponse {
  pullPlaybookFromGithub: {
    success: boolean;
    graph: { id: string; title: string } | null;
    message: string;
  };
}

interface ImportFromOpenTideResponse {
  importFromOpentide: {
    success: boolean;
    graph: { id: string; title: string } | null;
    message: string;
  };
}

interface ImportWorkbenchModalProps {
  visible: boolean;
  onClose: () => void;
  onImportSuccess?: (graphId?: string) => void;
}

interface RepoOption {
  id: string;
  name: string;
  url?: string | null;
  provider?: string | null;
}

export const ImportWorkbenchModal: React.FC<ImportWorkbenchModalProps> = ({
  visible,
  onClose,
  onImportSuccess
}) => {
  const [activeTab, setActiveTab] = useState<string>('file');
  const [importData, setImportData] = useState<string>('');
  const [newTitle, setNewTitle] = useState<string>('');
  
  // Repository state
  const [selectedRepoId, setSelectedRepoId] = useState<string>('');
  const [githubToken, setGithubToken] = useState<string>('');
  const [repoOwner, setRepoOwner] = useState<string>('');
  const [repoName, setRepoName] = useState<string>('');
  const [filePath, setFilePath] = useState<string>('');
  const [branch, setBranch] = useState<string>('main');

  // OpenTide state
  const [mdrYaml, setMdrYaml] = useState<string>('');
  const [tvmYaml, setTvmYaml] = useState<string>('');
  const [domYaml, setDomYaml] = useState<string>('');
  const [openTideTitle, setOpenTideTitle] = useState<string>('');

  const { data: reposData, loading: reposLoading } = useQuery<{ allRuleRepositories: RepoOption[] }>(
    GET_RULE_REPOSITORIES,
    { fetchPolicy: 'cache-and-network' }
  );
  const repositoryOptions = reposData?.allRuleRepositories ?? [];

  // Mutations
  const [importPlaybook, { loading: importing }] = useMutation<ImportPlaybookResponse>(IMPORT_PLAYBOOK_MUTATION);
  const [pullFromGitHub, { loading: pulling }] = useMutation<PullFromGitHubResponse>(PULL_FROM_GITHUB_MUTATION);
  const [importFromOpenTide, { loading: importingOpenTide }] = useMutation<ImportFromOpenTideResponse>(IMPORT_FROM_OPENTIDE_MUTATION);

  // Reset state on close
  const handleClose = () => {
    setImportData('');
    setNewTitle('');
    setSelectedRepoId('');
    setGithubToken('');
    setRepoOwner('');
    setRepoName('');
    setFilePath('');
    setBranch('main');
    setMdrYaml('');
    setTvmYaml('');
    setDomYaml('');
    setOpenTideTitle('');
    setActiveTab('file');
    onClose();
  };

  // Import from file/JSON handler
  const handleImport = async () => {
    if (!importData.trim()) {
      message.error('Please paste or upload import data');
      return;
    }
    try {
      const result = await importPlaybook({ 
        variables: { 
          importData: importData,
          newTitle: newTitle || undefined
        } 
      });
      
      // Check for successful import
      const importResult = result.data?.importPlaybookGraph;
      if (importResult?.success) {
        message.success(importResult.message || 'Workbench imported successfully!');
        // Close modal first, then call success callback
        handleClose();
        if (onImportSuccess) {
          // Small delay to ensure modal closes smoothly before refreshing the list.
          // graphId may be undefined if the server response omits graph; the callback
          // only needs it to trigger a list refresh, so this is acceptable.
          setTimeout(() => {
            onImportSuccess(importResult.graph?.id);
          }, 100);
        }
      } else if (importResult) {
        message.error(importResult.message || 'Import failed');
      } else {
        message.error('Import failed: No response from server');
      }
    } catch (e: any) {
      console.error('Import error:', e);
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

  // Repository Pull handler
  const handlePullFromGitHub = async () => {
    const manualMode = !selectedRepoId;
    if (!filePath) {
      message.error('Please provide a file path');
      return;
    }
    if (manualMode && (!githubToken || !repoOwner || !repoName)) {
      message.error('Please select a repository or fill in all manual repository fields');
      return;
    }
    try {
      const result = await pullFromGitHub({
        variables: {
          repositoryId: selectedRepoId || undefined,
          githubToken: manualMode ? githubToken : undefined,
          repoOwner: manualMode ? repoOwner : undefined,
          repoName: manualMode ? repoName : undefined,
          filePath,
          branch: branch || 'main',
          newTitle: newTitle || undefined
        }
      });
      
      // Check for successful pull
      const pullResult = result.data?.pullPlaybookFromGithub;
      if (pullResult?.success) {
        message.success(pullResult.message || 'Workbench imported from repository successfully!');
        // Close modal first, then call success callback
        handleClose();
        if (onImportSuccess) {
          // Small delay to ensure modal closes smoothly before refreshing the list.
          // graphId may be undefined if the server response omits graph; the callback
          // only needs it to trigger a list refresh, so this is acceptable.
          setTimeout(() => {
            onImportSuccess(pullResult.graph?.id);
          }, 100);
        }
      } else if (pullResult) {
        message.error(pullResult.message || 'Pull failed');
      } else {
        message.error('Pull failed: No response from server');
      }
    } catch (e: any) {
      console.error('Repository pull error:', e);
      message.error(e.message || 'Pull failed');
    }
  };

  // OpenTide import handler
  const handleImportFromOpenTide = async () => {
    if (!mdrYaml.trim()) {
      message.error('MDR (Detection Rule) YAML is required');
      return;
    }
    try {
      const result = await importFromOpenTide({
        variables: {
          mdrYaml: mdrYaml.trim(),
          tvmYaml: tvmYaml.trim() || undefined,
          domYaml: domYaml.trim() || undefined,
          newTitle: openTideTitle.trim() || undefined,
        },
      });

      const importResult = result.data?.importFromOpentide;
      if (importResult?.success) {
        message.success(importResult.message || 'Workbench imported from OpenTide successfully!');
        handleClose();
        if (onImportSuccess) {
          setTimeout(() => {
            onImportSuccess(importResult.graph?.id);
          }, 100);
        }
      } else if (importResult) {
        message.error(importResult.message || 'OpenTide import failed');
      } else {
        message.error('OpenTide import failed: No response from server');
      }
    } catch (e: any) {
      console.error('OpenTide import error:', e);
      message.error(e.message || 'OpenTide import failed');
    }
  };

  const tabItems = [
    {
      key: 'file',
      label: (
        <span>
          <UploadOutlined /> From File
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="Import Workbench"
            description="Import a workbench from a previously exported JSON file. A new workbench will be created in your organization."
            type="info"
            showIcon
          />

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
            placeholder='{"hefaistos_version": "1.0", "export_type": "playbook_graph", ...}'
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
            disabled={!importData.trim() || importing}
            block
          >
            {importing ? 'Importing...' : 'Import Workbench'}
          </Button>
        </div>
      )
    },
    {
      key: 'repository',
      label: (
        <span>
          <GithubOutlined /> From Repository
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="Import from Repository"
            description="Import a workbench from a JSON file stored in a configured repository (GitHub, GitLab, or Gitea)."
            type="info"
            showIcon
          />
          
          <div className="border rounded-lg p-4 space-y-3">
            <Text strong>Repository Settings</Text>
            <Select
              placeholder="Select configured repository (recommended)"
              value={selectedRepoId || undefined}
              onChange={(value) => setSelectedRepoId(value || '')}
              loading={reposLoading}
              allowClear
              options={repositoryOptions.map((repo) => ({
                value: repo.id,
                label: `${repo.name}${repo.url ? ` (${repo.url})` : ''}${repo.provider ? ` [${repo.provider}]` : ''}`,
              }))}
            />
            <Text type="secondary">
              Supported services: GitHub, GitLab, and Gitea.
            </Text>

            {!selectedRepoId && (
              <>
                <Alert
                  type="warning"
                  showIcon
                  message="Manual mode"
                  description="Manual owner/repo entry is best for GitHub. For GitLab/Gitea (especially self-hosted), use a configured repository."
                />
                <Input.Password
                  placeholder="Repository Personal Access Token"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  prefix={<GithubOutlined />}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Repository Owner/Namespace"
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
              placeholder="File Path (e.g., playbooks/my-detection.json)"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
            />
            <Input
              placeholder="Branch (default: main)"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
          </div>

          <Input
            placeholder="New title (optional - override imported title)"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />

          <Button 
            type="primary" 
            icon={<CloudDownloadOutlined />}
            onClick={handlePullFromGitHub}
            loading={pulling}
            disabled={(!selectedRepoId && (!githubToken || !repoOwner || !repoName)) || !filePath || pulling}
            block
          >
            {pulling ? 'Importing...' : 'Import from Repository'}
          </Button>

          <Alert
            message="Security Note"
            description="Tokens entered in manual mode are only used for this request and are not stored. Configured repository tokens are stored encrypted in repository settings."
            type="warning"
            showIcon
          />
        </div>
      )
    },
    {
      key: 'opentide',
      label: (
        <span>
          <ApiOutlined /> From OpenTide
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Alert
            message="Import from OpenTide / ShareTide"
            description="Import a workbench from OpenTide YAML files published in a ShareTide repository. Paste the MDR (Detection Rule) YAML below. Optionally include the TVM and DOM YAML files to enrich additional workbench fields. Detection rules for each configured platform (KQL, SPL, WAZUH) will be imported automatically."
            type="info"
            showIcon
          />

          <div className="space-y-2">
            <Text strong>
              MDR YAML <Text type="danger">*</Text>
            </Text>
            <Text type="secondary" className="block text-xs">
              Managed Detection Rule — contains detection queries and response metadata.
              File located at <code>Objects/Detection Rules/&lt;name&gt;.yaml</code> in the ShareTide repository.
            </Text>
            <TextArea
              value={mdrYaml}
              onChange={(e) => setMdrYaml(e.target.value)}
              rows={8}
              placeholder={`name: mdr_de_t1070_001\nmetadata:\n  schema: mdr::2.1\ndescription: "Detect suspicious activity"\nresponse:\n  alert_severity: HIGH\nconfigurations:\n  defender_for_endpoint:\n    query: |\n      DeviceProcessEvents | ...`}
              className="font-mono text-xs"
            />
          </div>

          <Collapse ghost>
            <Panel
              header={<Text type="secondary">TVM YAML (optional) — Threat Vector Model</Text>}
              key="tvm"
            >
              <div className="space-y-2">
                <Text type="secondary" className="block text-xs">
                  Provides MITRE technique, technical context, and blind spots.
                  File located at <code>Objects/Threat Vectors/&lt;name&gt;.yaml</code>.
                </Text>
                <TextArea
                  value={tvmYaml}
                  onChange={(e) => setTvmYaml(e.target.value)}
                  rows={6}
                  placeholder={`name: tvm_t1070\nmetadata:\n  schema: tvm::2.1\ndescription: "Indicator Removal"\nmitre:\n  technique_id: T1070\n  technique_name: Indicator Removal\ntechnical_context: "..."\nblind_spots: "..."`}
                  className="font-mono text-xs"
                />
              </div>
            </Panel>
            <Panel
              header={<Text type="secondary">DOM YAML (optional) — Detection Objective Model</Text>}
              key="dom"
            >
              <div className="space-y-2">
                <Text type="secondary" className="block text-xs">
                  Provides detection goal, false positives, triage guidance, and priority.
                  File located at <code>Objects/Detection Objectives/&lt;name&gt;.yaml</code>.
                </Text>
                <TextArea
                  value={domYaml}
                  onChange={(e) => setDomYaml(e.target.value)}
                  rows={6}
                  placeholder={`name: dom_de_t1070_001\nmetadata:\n  schema: dom::2.1\ndescription: "Detect indicator removal"\npriority: High\nfalse_positives: "Legitimate cleanup scripts"\ntriage_guidance: "Review process tree"\nresponse:\n  alert_trigger: "..."`}
                  className="font-mono text-xs"
                />
              </div>
            </Panel>
          </Collapse>

          <Input
            placeholder="New title (optional — override title derived from YAML)"
            value={openTideTitle}
            onChange={(e) => setOpenTideTitle(e.target.value)}
          />

          <Button
            type="primary"
            icon={<ApiOutlined />}
            onClick={handleImportFromOpenTide}
            loading={importingOpenTide}
            disabled={!mdrYaml.trim() || importingOpenTide}
            block
          >
            {importingOpenTide ? 'Importing...' : 'Import from OpenTide'}
          </Button>
        </div>
      )
    }
  ];

  // Prevent closing modal during import
  const isProcessing = importing || pulling || importingOpenTide;

  return (
    <Modal
      title="Import Workbench"
      open={visible}
      onCancel={isProcessing ? undefined : handleClose}
      footer={null}
      width={600}
      destroyOnClose
      maskClosable={!isProcessing}
      closable={!isProcessing}
    >
      <Tabs 
        activeKey={activeTab} 
        onChange={setActiveTab}
        items={tabItems}
      />
    </Modal>
  );
};

export default ImportWorkbenchModal;
