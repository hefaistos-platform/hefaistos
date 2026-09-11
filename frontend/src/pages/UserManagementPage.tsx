import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { message } from 'antd';
import { Button } from '../components/ui/Button';
import { PixelIcon } from '../components/ui/PixelIcon';
import { InviteUserModal } from '../components/InviteUserModal';

// Query from Day 184
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

// Mutation from Day 185
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

// --- Org AI Settings ---
const GET_ORG_AI_SETTINGS = gql`
  query GetOrgAISettings {
    orgAiSettings {
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
    }
  }
`;

const UPDATE_ORG_AI_SETTINGS = gql`
  mutation UpdateOrgAISettings($ollamaBaseUrl: String, $ollamaModel: String, $openaiKey: String, $geminiKey: String, $claudeKey: String, $azureOpenaiEndpoint: String, $azureOpenaiKey: String, $azureOpenaiDeployment: String, $orgPreferredModel: String, $ollamaEnabled: Boolean, $openaiEnabled: Boolean, $geminiEnabled: Boolean, $claudeEnabled: Boolean, $azureOpenaiEnabled: Boolean) {
    updateOrgAiSettings(ollamaBaseUrl: $ollamaBaseUrl, ollamaModel: $ollamaModel, openaiKey: $openaiKey, geminiKey: $geminiKey, claudeKey: $claudeKey, azureOpenaiEndpoint: $azureOpenaiEndpoint, azureOpenaiKey: $azureOpenaiKey, azureOpenaiDeployment: $azureOpenaiDeployment, orgPreferredModel: $orgPreferredModel, ollamaEnabled: $ollamaEnabled, openaiEnabled: $openaiEnabled, geminiEnabled: $geminiEnabled, claudeEnabled: $claudeEnabled, azureOpenaiEnabled: $azureOpenaiEnabled) {
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
      }
    }
  }
`;

// --- TypeScript Types ---
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
  } | null;
}

export const UserManagementPage = () => {
  const [activeTab, setActiveTab] = useState<'users' | 'system'>('users');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({ email: '', role: '', bio: '', jobTitle: '', slackHandle: '', organizationId: '' });
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const { data, loading, error, refetch } = useQuery<{ allUsersInOrg: User[] }>(GET_ALL_USERS_QUERY);
  const { data: orgData } = useQuery<{ allOrganizations: { id: string; name: string }[] }>(ALL_ORGANIZATIONS_QUERY, {
    errorPolicy: 'ignore',
  });
  const { data: orgAiData, refetch: refetchOrgAi } = useQuery<OrgAISettingsData>(GET_ORG_AI_SETTINGS, {
    errorPolicy: 'ignore',
  });
  const [orgAiForm, setOrgAiForm] = useState({ ollamaBaseUrl: '', ollamaModel: '', openaiKey: '', geminiKey: '', claudeKey: '', azureOpenaiEndpoint: '', azureOpenaiKey: '', azureOpenaiDeployment: '', orgPreferredModel: '', ollamaEnabled: true, openaiEnabled: true, geminiEnabled: true, claudeEnabled: true, azureOpenaiEnabled: true });
  const [updateOrgAiSettings, { loading: savingOrgAi }] = useMutation(UPDATE_ORG_AI_SETTINGS);

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
    }
  }, [orgAiData?.orgAiSettings]);

  // --- ADD DELETE LOGIC ---
  const [deleteUser, { loading: deleteLoading }] = useMutation(DELETE_USER_MUTATION, {
    // Refetch the list after a user is deleted
    refetchQueries: [{ query: GET_ALL_USERS_QUERY }],
  });
  const [adminUpdateUser, { loading: saving }] = useMutation(ADMIN_UPDATE_USER_MUTATION, {
    refetchQueries: [{ query: GET_ALL_USERS_QUERY }],
    awaitRefetchQueries: true,
  });
  const [adminResetUserPassword, { loading: resettingPassword }] = useMutation(ADMIN_RESET_USER_PASSWORD_MUTATION);

  const handleDelete = async (user: User) => {
    if (user.isStaff) {
      alert("Cannot delete a Staff/Superuser account from this panel.");
      return;
    }
    if (window.confirm(`Are you sure you want to delete the user '${user.username}'?`)) {
      try {
        await deleteUser({ variables: { userId: user.id } });
      } catch (e: any) {
        alert(`Error: ${e.message}`);
      }
    }
  };
  // --- END DELETE LOGIC ---

  const handleResetPassword = async () => {
    if (!resetPasswordUser) return;
    if (!newPassword) {
      message.error('Please enter a new password.');
      return;
    }
    if (newPassword !== confirmPassword) {
      message.error('Passwords do not match.');
      return;
    }
    try {
      await adminResetUserPassword({ variables: { userId: resetPasswordUser.id, newPassword } });
      message.success(`Password reset successfully for ${resetPasswordUser.username}.`);
      setResetPasswordUser(null);
      setNewPassword('');
      setConfirmPassword('');
    } catch (e: any) {
      message.error(e.message || 'Failed to reset password.');
    }
  };

  if (loading) return <p>Loading users...</p>;
  if (error) return <p className="text-hefaistos-accent-red">Error: {error.message}</p>;

  const handleSaveOrgAi = async () => {
    try {
      await updateOrgAiSettings({
        variables: {
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
    } catch (e: any) {
      message.error(e.message || 'Failed to save organization AI settings.');
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-3xl font-bold">Users & System</h2>
        {activeTab === 'users' && (
          <Button variant="primary" onClick={() => setIsModalOpen(true)}>
            <PixelIcon name="add" className="w-5 h-5 mr-2" />
            Invite User
          </Button>
        )}
      </div>

      {/* --- Tabs --- */}
      <div className="flex gap-0 mb-6 border-b-2 border-hefaistos-border">
        <button
          className={`px-6 py-2 text-sm font-semibold border-b-2 -mb-0.5 transition-colors ${
            activeTab === 'users'
              ? 'border-hefaistos-accent text-hefaistos-accent bg-white'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
          onClick={() => setActiveTab('users')}
        >
          Users
        </button>
        <button
          className={`px-6 py-2 text-sm font-semibold border-b-2 -mb-0.5 transition-colors ${
            activeTab === 'system'
              ? 'border-hefaistos-accent text-hefaistos-accent bg-white'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
          onClick={() => setActiveTab('system')}
        >
          System Settings
        </button>
      </div>

      {activeTab === 'users' && (
      <>
      {/* --- Themed Table --- */}
      <div className="bg-white shadow-md rounded-lg overflow-hidden border-2 border-hefaistos-border">
        <table className="w-full text-left border-collapse">
          {/* ... thead ... */}
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
            {data && data.allUsersInOrg.map((user) => (
              <tr key={user.id} className="border-b border-hefaistos-border last:border-b-0 hover:bg-hefaistos-subtle/50">
                <td className="p-4 font-medium">{user.username} {user.isStaff ? '(Staff)' : ''}</td>
                <td className="p-4">{user.email || 'N/A'}</td>
                <td className="p-4">{user.role}</td>
                <td className="p-4">{user.lastLogin ? new Date(user.lastLogin).toLocaleString() : 'Never'}</td>
                <td className="p-4 flex gap-2">
                  <Button 
                    variant="secondary" 
                    onClick={() => {
                      setEditingUser(user);
                      setEditForm({
                        email: user.email || '',
                        role: user.role,
                        bio: (user as any).bio || '',
                        jobTitle: (user as any).jobTitle || '',
                        slackHandle: (user as any).slackHandle || '',
                        organizationId: user.organization?.id || ''
                      });
                    }}
                  >
                    <PixelIcon name="edit" className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="secondary"
                    title="Reset Password"
                    aria-label="Reset Password"
                    onClick={() => {
                      setResetPasswordUser(user);
                      setNewPassword('');
                      setConfirmPassword('');
                    }}
                  >
                    🔑
                  </Button>
                  <Button 
                    variant="danger" 
                    onClick={() => handleDelete(user)} 
                    disabled={deleteLoading || user.isStaff}
                  >
                    <PixelIcon name="delete" className="w-4 h-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* --- ADD THE MODAL --- */}
      <InviteUserModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onUserInvited={() => refetch()} // This tells the page to refetch the user list
      />
      {/* --- END ADD --- */}
      </>
      )}

      {activeTab === 'system' && (
        <div className="space-y-8">
          {/* AI Settings Section */}
          <div className="bg-white rounded-lg shadow-sm border-2 border-hefaistos-border p-6">
            <h3 className="text-xl font-bold mb-1">Organization AI Settings</h3>
            <p className="text-sm text-gray-500 mb-6">
              Configure organization-wide AI models and API keys. Users can opt in to use these instead of their personal API keys.
            </p>

            {/* Ollama Section */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.ollamaEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🦙</span>
                <h4 className="font-semibold text-base">Ollama (Self-Hosted LLM)</h4>
                {orgAiData?.orgAiSettings?.hasOllama && (
                  <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>
                )}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.ollamaEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={orgAiForm.ollamaEnabled}
                    onClick={() => setOrgAiForm(prev => ({ ...prev, ollamaEnabled: !prev.ollamaEnabled }))}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.ollamaEnabled ? 'bg-green-500' : 'bg-gray-300'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.ollamaEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Point to your organization's Ollama instance. All users who opt in will use this model for AI features.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Ollama Base URL</label>
                  <input
                    className="w-full p-2 border rounded text-sm"
                    placeholder="e.g. http://ollama:11434"
                    value={orgAiForm.ollamaBaseUrl}
                    onChange={e => setOrgAiForm({ ...orgAiForm, ollamaBaseUrl: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Model Name</label>
                  <input
                    className="w-full p-2 border rounded text-sm"
                    placeholder="e.g. llama3, mistral, codellama"
                    value={orgAiForm.ollamaModel}
                    onChange={e => setOrgAiForm({ ...orgAiForm, ollamaModel: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* OpenAI Section */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.openaiEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🤖</span>
                <h4 className="font-semibold text-base">OpenAI (ChatGPT)</h4>
                {orgAiData?.orgAiSettings?.hasOpenai && (
                  <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>
                )}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.openaiEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={orgAiForm.openaiEnabled}
                    onClick={() => setOrgAiForm(prev => ({ ...prev, openaiEnabled: !prev.openaiEnabled }))}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.openaiEnabled ? 'bg-green-500' : 'bg-gray-300'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.openaiEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Organization-wide OpenAI API key. Users who opt in will use this key for GPT models.
              </p>
              <div>
                <label className="block text-xs font-semibold mb-1">OpenAI API Key</label>
                <input
                  type="password"
                  className="w-full p-2 border rounded text-sm"
                  placeholder={orgAiData?.orgAiSettings?.hasOpenai ? '•••••••• (set — enter new value to update)' : 'sk-...'}
                  value={orgAiForm.openaiKey}
                  onChange={e => setOrgAiForm({ ...orgAiForm, openaiKey: e.target.value })}
                />
              </div>
            </div>

            {/* Gemini Section */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.geminiEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">✨</span>
                <h4 className="font-semibold text-base">Google Gemini</h4>
                {orgAiData?.orgAiSettings?.hasGemini && (
                  <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>
                )}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.geminiEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={orgAiForm.geminiEnabled}
                    onClick={() => setOrgAiForm(prev => ({ ...prev, geminiEnabled: !prev.geminiEnabled }))}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.geminiEnabled ? 'bg-green-500' : 'bg-gray-300'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.geminiEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Organization-wide Gemini API key. Users who opt in will use this key for Gemini models.
              </p>
              <div>
                <label className="block text-xs font-semibold mb-1">Gemini API Key</label>
                <input
                  type="password"
                  className="w-full p-2 border rounded text-sm"
                  placeholder={orgAiData?.orgAiSettings?.hasGemini ? '•••••••• (set — enter new value to update)' : 'AIza...'}
                  value={orgAiForm.geminiKey}
                  onChange={e => setOrgAiForm({ ...orgAiForm, geminiKey: e.target.value })}
                />
              </div>
            </div>

            {/* Claude Section */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.claudeEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🧠</span>
                <h4 className="font-semibold text-base">Anthropic Claude</h4>
                {orgAiData?.orgAiSettings?.hasClaude && (
                  <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>
                )}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.claudeEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={orgAiForm.claudeEnabled}
                    onClick={() => setOrgAiForm(prev => ({ ...prev, claudeEnabled: !prev.claudeEnabled }))}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.claudeEnabled ? 'bg-green-500' : 'bg-gray-300'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.claudeEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Organization-wide Claude API key. Users who opt in will use this key for Claude models.
              </p>
              <div>
                <label className="block text-xs font-semibold mb-1">Claude API Key</label>
                <input
                  type="password"
                  className="w-full p-2 border rounded text-sm"
                  placeholder={orgAiData?.orgAiSettings?.hasClaude ? '•••••••• (set — enter new value to update)' : 'sk-ant-...'}
                  value={orgAiForm.claudeKey}
                  onChange={e => setOrgAiForm({ ...orgAiForm, claudeKey: e.target.value })}
                />
              </div>
            </div>

            {/* Azure OpenAI Section */}
            <div className={`border rounded-lg p-5 mb-4 ${orgAiForm.azureOpenaiEnabled ? 'border-gray-200' : 'border-gray-200 opacity-60'}`}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">☁️</span>
                <h4 className="font-semibold text-base">Azure OpenAI (Azure Foundry)</h4>
                {orgAiData?.orgAiSettings?.hasAzureOpenai && (
                  <span className="ml-2 px-2 py-0.5 rounded bg-green-100 text-green-800 text-xs font-bold uppercase">Configured</span>
                )}
                <label className="ml-auto flex items-center gap-2 cursor-pointer select-none">
                  <span className="text-xs font-medium text-gray-600">{orgAiForm.azureOpenaiEnabled ? 'Enabled' : 'Disabled'}</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={orgAiForm.azureOpenaiEnabled}
                    onClick={() => setOrgAiForm(prev => ({ ...prev, azureOpenaiEnabled: !prev.azureOpenaiEnabled }))}
                    className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${orgAiForm.azureOpenaiEnabled ? 'bg-green-500' : 'bg-gray-300'}`}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${orgAiForm.azureOpenaiEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                  </button>
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Organization-wide Azure OpenAI endpoint. Users who opt in will use this deployment for GPT-5.x models.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold mb-1">Azure Endpoint URL</label>
                  <input
                    type="text"
                    className="w-full p-2 border rounded text-sm"
                    placeholder="https://YOUR_RESOURCE.openai.azure.com"
                    value={orgAiForm.azureOpenaiEndpoint}
                    onChange={e => setOrgAiForm({ ...orgAiForm, azureOpenaiEndpoint: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">API Key</label>
                  <input
                    type="password"
                    className="w-full p-2 border rounded text-sm"
                    placeholder={orgAiData?.orgAiSettings?.hasAzureOpenai ? '•••••••• (set — enter new value to update)' : 'Your Azure API key'}
                    value={orgAiForm.azureOpenaiKey}
                    onChange={e => setOrgAiForm({ ...orgAiForm, azureOpenaiKey: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Deployment Name</label>
                  <input
                    type="text"
                    className="w-full p-2 border rounded text-sm"
                    placeholder="gpt-5-deployment"
                    value={orgAiForm.azureOpenaiDeployment}
                    onChange={e => setOrgAiForm({ ...orgAiForm, azureOpenaiDeployment: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* Preferred Model */}
            <div className="border border-gray-200 rounded-lg p-5 mb-4">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">⚙️</span>
                <h4 className="font-semibold text-base">Default Model</h4>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Set the default AI model used when users opt in to the organization AI. Leave blank to auto-detect based on configured providers.
              </p>
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
              <Button variant="primary" disabled={savingOrgAi} onClick={handleSaveOrgAi}>
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
      )}

      {editingUser && (
        <div 
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={(e) => {
            // Only close if clicking the backdrop itself, not children
            if (e.target === e.currentTarget) {
              setEditingUser(null);
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-lg w-full max-w-lg p-6 border-2 border-hefaistos-border">
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
                  <select
                    className="w-full p-2 border rounded"
                    value={editForm.organizationId}
                    onChange={e => setEditForm({ ...editForm, organizationId: e.target.value })}
                  >
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
                    const variables: any = {
                      userId: editingUser.id,
                      email: editForm.email || null,
                      role: editForm.role,
                      bio: editForm.bio || null,
                      jobTitle: editForm.jobTitle || null,
                      slackHandle: editForm.slackHandle || null,
                    };
                    
                    // Only include organizationId if it's not empty
                    if (editForm.organizationId) {
                      variables.organizationId = editForm.organizationId;
                    }
                    
                    await adminUpdateUser({ variables });
                    message.success('User updated successfully');
                    setEditingUser(null);
                    setEditForm({ email: '', role: '', bio: '', jobTitle: '', slackHandle: '', organizationId: '' });
                  } catch (e: any) {
                    console.error('Failed to update user:', e);
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

      {/* --- Reset Password Modal --- */}
      {resetPasswordUser && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setResetPasswordUser(null);
            }
          }}
        >
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md p-6 border-2 border-hefaistos-border">
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
                <input
                  type="password"
                  className="w-full p-2 border rounded"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Confirm Password</label>
                <input
                  type="password"
                  className="w-full p-2 border rounded"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <Button variant="secondary" onClick={() => setResetPasswordUser(null)}>Cancel</Button>
              <Button
                variant="primary"
                disabled={resettingPassword}
                onClick={handleResetPassword}
              >
                {resettingPassword ? 'Resetting...' : 'Reset Password'}
              </Button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
