import React, { useState, useEffect } from 'react';
import { Button } from './ui/Button';
import { Input } from './ui/Input';

export interface RepoFormData {
  name: string;
  url: string;
  username?: string | null;
  token?: string | null;
  provider?: string | null;
  apiBaseUrl?: string | null;
  verifySsl?: boolean | null;
}

interface RepoFormProps {
  initialData?: RepoFormData;
  onSubmit: (formData: RepoFormData) => Promise<void> | void;
  loading: boolean;
  error: any;
}

export const RepoForm: React.FC<RepoFormProps> = ({ initialData, onSubmit, loading, error }) => {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [provider, setProvider] = useState('AUTO');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [verifySsl, setVerifySsl] = useState(true);

  useEffect(() => {
    if (initialData) {
      setName(initialData.name);
      setUrl(initialData.url);
      setUsername(initialData.username || '');
      setProvider(initialData.provider || 'AUTO');
      setApiBaseUrl(initialData.apiBaseUrl || '');
      setVerifySsl(initialData.verifySsl ?? true);
      // NOTE: We do NOT load the token. Token field is "write-only" for security.
    }
  }, [initialData]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const formData: RepoFormData = {
      name,
      url,
      username: username || null,
      provider: provider || 'AUTO',
      apiBaseUrl: apiBaseUrl || null,
      verifySsl,
    };
    // Only include the token if the user actually typed one in
    if (token) {
      formData.token = token;
    }
    onSubmit(formData);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block mb-1 text-sm font-medium">Repository Name</label>
        <Input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div>
        <label className="block mb-1 text-sm font-medium">Git Clone URL</label>
        <Input type="text" value={url} onChange={(e) => setUrl(e.target.value)} required placeholder="https://github.com/SigmaHQ/sigma.git" />
        <p className="text-xs text-gray-500 mt-1">
          Supported services: GitHub, GitLab, and Gitea (including self-hosted instances).
        </p>
      </div>

      <div className="p-4 border-2 border-hefaistos-border rounded-lg">
        <h3 className="font-bold">Private Repository (Optional)</h3>
        <p className="text-sm text-gray-500 mb-2">
          For private repos, provide a username and a Personal Access Token (PAT).
        </p>
        <div>
          <label className="block mb-1 text-sm font-medium">Username</label>
          <Input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g., git-user" />
        </div>
        <div className="mt-2">
          <label className="block mb-1 text-sm font-medium">Provider</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2"
          >
            <option value="AUTO">Auto-detect from URL</option>
            <option value="GITHUB">GitHub</option>
            <option value="GITLAB">GitLab</option>
            <option value="GITEA">Gitea</option>
          </select>
        </div>
        <div className="mt-2">
          <label className="block mb-1 text-sm font-medium">API Base URL (optional)</label>
          <Input
            type="text"
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="https://gitlab.example.com/api/v4"
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <input
            id="verify-ssl"
            type="checkbox"
            checked={verifySsl}
            onChange={(e) => setVerifySsl(e.target.checked)}
          />
          <label htmlFor="verify-ssl" className="text-sm font-medium">
            Verify SSL certificate
          </label>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          Disable only for trusted self-signed certificates.
        </p>
        <div className="mt-2">
          <label className="block mb-1 text-sm font-medium">Token (Personal Access Token)</label>
          <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={initialData ? "Leave blank to keep existing token" : "Enter new token"} />
        </div>
      </div>

      <div className="pt-4">
        <Button type="submit" variant="primary" disabled={loading}>
          {loading ? 'Saving...' : 'Save Repository'}
        </Button>
      </div>

      {error && <p className="text-sm text-hefaistos-accent-red">Error: {error.message}</p>}
    </form>
  );
};
