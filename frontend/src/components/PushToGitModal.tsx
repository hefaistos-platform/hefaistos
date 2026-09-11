import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Modal } from './ui/Modal';
import { Button } from './ui/Button';
import { Select } from './ui/Select';

// Query from Day 152
const GET_ALL_REPOS_QUERY = gql`
  query GetAllRuleRepositories {
    allRuleRepositories {
      id
      name
      url
    }
  }
`;

// Mutation from Day 169 - updated with targetFolder support
const PUSH_PLAYBOOK_TO_GIT_MUTATION = gql`
  mutation PushPlaybookToGit($graphId: UUID!, $repositoryId: String!, $targetFolder: String) {
    pushPlaybookToGit(graphId: $graphId, repositoryId: $repositoryId, targetFolder: $targetFolder) {
      ok
      queuedCount
    }
  }
`;

// --- TypeScript Types ---
interface Repo { id: string; name: string; url: string; }
interface PushModalProps {
  isOpen: boolean;
  onClose: () => void;
  graphId?: string; // optional for legacy callers; guarded at submit
}
interface GetAllReposData {
  allRuleRepositories: Repo[];
}

type PushResult = { pushPlaybookToGit: { ok: boolean; queuedCount?: number } };
type PushVars = { graphId: string; repositoryId: string; targetFolder?: string };

// Preset folder options
const FOLDER_OPTIONS = [
  { value: '', label: 'Auto (organize by format)' },
  { value: 'rules/kql', label: 'rules/kql (Kusto Query Language)' },
  { value: 'rules/wazuh', label: 'rules/wazuh (Wazuh XML)' },
  { value: 'rules/splunk', label: 'rules/splunk (Splunk SPL)' },
  { value: 'rules/yara', label: 'rules/yara (YARA rules)' },
  { value: 'rules/snort', label: 'rules/snort (Snort/Suricata)' },
  { value: 'rules/other', label: 'rules/other (Other formats)' },
  { value: 'detections', label: 'detections/' },
  { value: 'custom', label: '-- Custom folder --' },
];

export const PushToGitModal: React.FC<PushModalProps> = ({ isOpen, onClose, graphId }) => {
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [targetFolder, setTargetFolder] = useState<string>('');
  const [customFolder, setCustomFolder] = useState<string>('');

  const { data, loading: queryLoading, error: queryError } = useQuery<GetAllReposData>(GET_ALL_REPOS_QUERY);
  const [pushToGit, { loading: pushLoading, error: pushError }] = useMutation<PushResult, PushVars>(PUSH_PLAYBOOK_TO_GIT_MUTATION);

  const handleSubmit = async () => {
    if (!selectedRepoId) {
      alert("Please select a repository.");
      return;
    }

    try {
      if (!graphId) {
        alert('No workbench attached to this playbook. Please create/select a workbench first.');
        return;
      }
      
      // Determine final target folder
      const finalFolder = targetFolder === 'custom' ? customFolder.trim() : (targetFolder || undefined);
      
      console.log("Sending PushPlaybookToGit with variables:", { graphId, repositoryId: selectedRepoId, targetFolder: finalFolder });
      const result = await pushToGit({
        variables: {
          graphId: graphId,
          repositoryId: selectedRepoId,
          targetFolder: finalFolder,
        },
      });
      console.log("Push mutation result:", result);
      const cnt = result.data?.pushPlaybookToGit?.queuedCount;
      alert(typeof cnt === 'number' ? `Queued ${cnt} rule${cnt === 1 ? '' : 's'} for push.` : "Push job started! The connector will process this in the background.");
      onClose(); // Close the modal on success
    } catch (e: any) {
      console.error("Full error object:", e);
      console.error("GraphQL errors:", e.graphQLErrors);
      console.error("Network error:", e.networkError);
      if (e.networkError?.result) {
        console.error("Network error result:", e.networkError.result);
      }
      // Error is already handled by the 'pushError' variable
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Push Playbook to Repository">
      <div>
        <p className="mb-4 text-gray-600">
          Select a repository to push this playbook to. This will trigger a background job.
        </p>
        <div className="mb-4">
          <label className="block mb-1 text-sm font-medium">Repository</label>
          <Select 
            value={selectedRepoId || ''}
            onChange={(e) => setSelectedRepoId(e.target.value || null)}
            disabled={queryLoading}
          >
            <option value="">Select a repository...</option>
            {data?.allRuleRepositories.map((repo: Repo) => (
              <option key={repo.id} value={repo.id}>{repo.name} ({repo.url})</option>
            ))}
          </Select>
        </div>
        
        <div className="mb-4">
          <label className="block mb-1 text-sm font-medium">Target Folder</label>
          <Select 
            value={targetFolder}
            onChange={(e) => setTargetFolder(e.target.value)}
          >
            {FOLDER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-gray-500">
            Auto will organize rules by their format (KQL → rules/kql, etc.)
          </p>
        </div>
        
        {targetFolder === 'custom' && (
          <div className="mb-4">
            <label className="block mb-1 text-sm font-medium">Custom Folder Path</label>
            <input
              type="text"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g., detections/windows/process"
              value={customFolder}
              onChange={(e) => setCustomFolder(e.target.value)}
            />
            <p className="mt-1 text-xs text-gray-500">
              Use forward slashes for nested folders. Folder will be created if it doesn't exist.
            </p>
          </div>
        )}

        {queryError && <p className="mt-2 text-sm text-hefaistos-accent-red">Error loading repositories: {queryError.message}</p>}

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button 
            variant="primary" 
            onClick={handleSubmit} 
            disabled={!selectedRepoId || pushLoading || queryLoading || (targetFolder === 'custom' && !customFolder.trim())}
          >
            {pushLoading ? 'Starting...' : 'Start Push'}
          </Button>
        </div>

        {pushError && <p className="mt-2 text-sm text-hefaistos-accent-red">Error: {pushError.message}</p>}
      </div>
    </Modal>
  );
};

// Export for Sidebar.tsx which needs this query
// Increase limit to load all techniques for autocomplete
export const GET_ALL_ATTACK_QUERY = gql`
  query GetAllAttack {
    allAttackTechniques(limit: 1000) {
      id
      techniqueId
      name
    }
  }
`;
