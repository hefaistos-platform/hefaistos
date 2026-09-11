import React from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { useNavigate } from 'react-router-dom';
import { RepoForm, RepoFormData } from '../components/RepoForm';

// Shared query (structurally matches RepoListPage) for cache updates
const GET_ALL_REPOS_QUERY = gql`
  query GetAllRuleRepositories {
    allRuleRepositories {
      id
      name
      url
      username
      provider
      apiBaseUrl
      verifySsl
      lastSync
    }
  }
`;

// Mutation from Day 152 (extended with fields for cache append)
const CREATE_REPO_MUTATION = gql`
  mutation CreateRuleRepository($name: String!, $url: String!, $username: String, $token: String, $provider: String, $apiBaseUrl: String, $verifySsl: Boolean) {
    createRuleRepository(name: $name, url: $url, username: $username, token: $token, provider: $provider, apiBaseUrl: $apiBaseUrl, verifySsl: $verifySsl) {
      repository {
        id
        name
        url
        username
        provider
        apiBaseUrl
        verifySsl
        lastSync
      }
    }
  }
`;

// TypeScript types for mutation result & variables
interface CreateRepoVars {
  name: string;
  url: string;
  username?: string; // GraphQL treats undefined as omitted
  token?: string;    // Same for token
  provider?: string;
  apiBaseUrl?: string;
  verifySsl?: boolean;
}

// GraphQL repository node returned from server (distinct from form data)
interface RuleRepositoryNode {
  id: string;
  name: string;
  url: string;
  username: string | null;
  provider?: string | null;
  apiBaseUrl?: string | null;
  verifySsl?: boolean | null;
  lastSync: string | null;
}

interface CreateRepoResponse {
  createRuleRepository: { repository: RuleRepositoryNode };
}

export const CreateRepoPage = () => {
  const navigate = useNavigate();
  const [createRuleRepository, { loading, error }] = useMutation<CreateRepoResponse, CreateRepoVars>(CREATE_REPO_MUTATION);

  const handleSubmit = async (formData: RepoFormData) => {
    try {
      // Map form data (nullable fields) to GraphQL variables (omit when null/empty)
      const variables: CreateRepoVars = {
        name: formData.name,
        url: formData.url,
        ...(formData.username ? { username: formData.username } : {}),
        ...(formData.token ? { token: formData.token } : {}),
        ...(formData.provider ? { provider: formData.provider } : {}),
        ...(formData.apiBaseUrl ? { apiBaseUrl: formData.apiBaseUrl } : {}),
        verifySsl: formData.verifySsl ?? true,
      };
      await createRuleRepository({
        variables,
        update: (cache, { data }) => {
          const newRepo = data?.createRuleRepository?.repository;
          if (!newRepo) return;
          try {
            const existing = cache.readQuery<{ allRuleRepositories: RuleRepositoryNode[] }>({ query: GET_ALL_REPOS_QUERY });
            if (existing) {
              // Avoid duplicate if already present
              if (!existing.allRuleRepositories.find(r => r.id === newRepo.id)) {
                cache.writeQuery<{ allRuleRepositories: RuleRepositoryNode[] }>({
                  query: GET_ALL_REPOS_QUERY,
                  data: { allRuleRepositories: [...existing.allRuleRepositories, newRepo] }
                });
              }
            }
          } catch {
            // If query not in cache yet, no action needed; next mount will fetch
          }
        }
      });
      navigate('/repos');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="max-w-2xl p-6 mx-auto bg-white border-2 border-hefaistos-border rounded-lg shadow-md">
      <h2 className="text-2xl font-bold mb-6 border-b-2 border-hefaistos-border pb-4">
        Add New Repository
      </h2>
      <p className="text-sm text-gray-500 mb-4">
        You can add repositories from GitHub, GitLab, or Gitea.
      </p>
      <RepoForm onSubmit={handleSubmit} loading={loading} error={error} />
    </div>
  );
};
