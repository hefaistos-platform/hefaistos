import React from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { useNavigate, useParams } from 'react-router-dom';
import { RepoForm } from '../components/RepoForm';
import { Button } from '../components/ui/Button';
import { message, Skeleton } from 'antd';

// Queries/Mutations from Day 152
// Use new single-repo query
interface RuleRepositoryNode {
  id: string;
  name: string;
  url: string;
  username: string | null;
  provider?: string | null;
  apiBaseUrl?: string | null;
  verifySsl?: boolean | null;
  lastSync?: string | null;
}

const GET_REPO_QUERY = gql`
  query GetRuleRepository($id: ID!) {
    ruleRepository(id: $id) { id name url username provider apiBaseUrl verifySsl lastSync }
  }
`;

const UPDATE_REPO_MUTATION = gql`
  mutation UpdateRuleRepository($id: ID!, $name: String, $url: String, $username: String, $token: String, $provider: String, $apiBaseUrl: String, $verifySsl: Boolean) {
    updateRuleRepository(id: $id, name: $name, url: $url, username: $username, token: $token, provider: $provider, apiBaseUrl: $apiBaseUrl, verifySsl: $verifySsl) {
      repository { id }
    }
  }
`;

const DELETE_REPO_MUTATION = gql`
  mutation DeleteRuleRepository($id: ID!) {
    deleteRuleRepository(id: $id) { ok }
  }
`;

export const EditRepoPage = () => {
  const { repoId } = useParams<{ repoId: string }>();
  const navigate = useNavigate();

  // This is a workaround. Ideally, we'd have a `repository(id: $id)` query.
  const { data, loading: queryLoading } = useQuery<{ ruleRepository: RuleRepositoryNode | null }>(GET_REPO_QUERY, { variables: { id: repoId } });

  const [updateRepo, { loading: updateLoading, error: updateError }] = useMutation(UPDATE_REPO_MUTATION);
  const [deleteRepo, { loading: deleteLoading, error: deleteError }] = useMutation(DELETE_REPO_MUTATION);

  const handleSubmit = async (formData: any) => {
    try {
      await updateRepo({ variables: { id: repoId, ...formData } });
      message.success('Repository updated');
      navigate('/repos');
    } catch (e) { console.error(e); }
  };

  const handleDelete = async () => {
    if (window.confirm("Are you sure you want to delete this repository? This will not delete the rules.")) {
      try {
        await deleteRepo({
          variables: { id: repoId },
          optimisticResponse: {
            deleteRuleRepository: { __typename: 'DeleteRuleRepository', ok: true }
          },
          update: (cache) => {
            try {
              const existing = cache.readQuery<{ allRuleRepositories: any[] }>({
                query: gql`query GetAllRuleRepositories { allRuleRepositories { id name url username provider apiBaseUrl verifySsl lastSync } }`
              });
              if (existing) {
                cache.writeQuery({
                  query: gql`query GetAllRuleRepositories { allRuleRepositories { id name url username provider apiBaseUrl verifySsl lastSync } }`,
                  data: { allRuleRepositories: existing.allRuleRepositories.filter(r => r.id !== repoId) }
                });
              }
            } catch { /* cache may not have list yet */ }
          }
        });
        message.success('Repository deleted');
        navigate('/repos');
      } catch (e) { console.error(e); }
    }
  };

  if (queryLoading) {
    return (
      <div className="max-w-2xl p-6 mx-auto bg-white border-2 border-hefaistos-border rounded-lg shadow-md">
        <Skeleton active paragraph={{ rows: 1 }} title />
        <Skeleton active paragraph={{ rows: 4 }} />
      </div>
    );
  }

  const initialData = data?.ruleRepository || undefined;

  return (
    <div className="max-w-2xl p-6 mx-auto bg-white border-2 border-hefaistos-border rounded-lg shadow-md">
      <div className="flex justify-between items-center mb-6 border-b-2 border-hefaistos-border pb-4">
        <h2 className="text-2xl font-bold">Edit Repository</h2>
        <Button variant="danger" onClick={handleDelete} disabled={deleteLoading}>
          {deleteLoading ? 'Deleting...' : 'Delete'}
        </Button>
      </div>
      <p className="text-sm text-gray-500 mb-3">
        Supported services: GitHub, GitLab, and Gitea.
      </p>
      {initialData && initialData.lastSync && (
        <p className="text-xs text-gray-500 mb-2">Last synced: {new Date(initialData.lastSync).toLocaleString()}</p>
      )}
      <RepoForm 
        initialData={initialData}
        onSubmit={handleSubmit} 
        loading={updateLoading} 
        error={updateError || deleteError}
      />
    </div>
  );
};
