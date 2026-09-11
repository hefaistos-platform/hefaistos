import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Modal } from './ui/Modal';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Select } from './ui/Select';

const INVITE_USER_MUTATION = gql`
  mutation InviteUser($username: String!, $email: String!, $role: String!) {
    inviteUser(username: $username, email: $email, role: $role) {
      user {
        id
        username
        role
      }
      message
      setupLink
    }
  }
`;

interface InviteUserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUserInvited: () => void; // Function to refetch the user list
}

export const InviteUserModal: React.FC<InviteUserModalProps> = ({ isOpen, onClose, onUserInvited }) => {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('ANALYST'); // Default to Analyst
  const [setupLink, setSetupLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [inviteUser, { loading, error }] = useMutation(INVITE_USER_MUTATION);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const { data } = await inviteUser({ variables: { username, email, role } });
      const returnedLink = data?.inviteUser?.setupLink || null;
      setSetupLink(returnedLink);
      onUserInvited(); // Refetch the list on the parent page
      if (!returnedLink) {
        onClose(); // Close the modal if email delivery is expected
        setUsername('');
        setEmail('');
        setRole('ANALYST');
      }
    } catch (e) {
      console.error("Failed to invite user:", e);
    }
  };

  const handleCopyLink = async () => {
    if (!setupLink) return;
    try {
      await navigator.clipboard.writeText(setupLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy setup link:', err);
    }
  };

  const handleClose = () => {
    setSetupLink(null);
    setCopied(false);
    setUsername('');
    setEmail('');
    setRole('ANALYST');
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Invite New User">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block mb-1 text-sm font-medium">Username</label>
          <Input type="text" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div>
          <label className="block mb-1 text-sm font-medium">Email</label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="block mb-1 text-sm font-medium">Role</label>
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="ANALYST">Analyst</option>
            <option value="RESOURCE_MANAGER">Resource Manager</option>
            <option value="REVIEWER">Reviewer</option>
            <option value="VIEWER">Viewer</option>
            <option value="ELONE">ElOne</option>
            <option value="BOT_AUDITOR_ORG">Bot Auditor (Org)</option>
            <option value="BOT_AUDITOR_GLOBAL">Bot Auditor (Global)</option>
            <option value="ADMIN">Admin</option>
          </Select>
        </div>

        <div className="flex justify-end gap-2 pt-4">
          <Button type="button" variant="secondary" onClick={handleClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? 'Inviting...' : 'Send Invite'}
          </Button>
        </div>

        {error && <p className="mt-2 text-sm text-hefaistos-accent-red">Error: {error.message}</p>}
        {setupLink && (
          <div className="mt-2 rounded border border-yellow-300 bg-yellow-50 p-3 text-sm">
            <p className="mb-2 font-medium">Email service is unavailable. Share this activation link manually:</p>
            <div className="mb-2 break-all rounded bg-white p-2 font-mono text-xs">{setupLink}</div>
            <Button type="button" variant="secondary" onClick={handleCopyLink}>
              {copied ? 'Copied' : 'Copy Link'}
            </Button>
          </div>
        )}
      </form>
    </Modal>
  );
};
