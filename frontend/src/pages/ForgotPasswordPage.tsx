import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Link } from 'react-router-dom';
import { Card, Form, Input, Button, Typography, Alert } from 'antd';

const COPY_FEEDBACK_DURATION_MS = 2000;

const REQUEST_PASSWORD_RESET_MUTATION = gql`
  mutation RequestPasswordReset($usernameOrEmail: String!) {
    requestPasswordReset(usernameOrEmail: $usernameOrEmail) {
      ok
      resetToken
      message
    }
  }
`;

interface RequestPasswordResetData {
  requestPasswordReset: {
    ok: boolean;
    resetToken: string | null;
    message: string;
  };
}

interface RequestPasswordResetVars {
  usernameOrEmail: string;
}

export const ForgotPasswordPage = () => {
  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [requestPasswordReset, { loading, error }] = useMutation<
    RequestPasswordResetData,
    RequestPasswordResetVars
  >(REQUEST_PASSWORD_RESET_MUTATION);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!usernameOrEmail.trim()) return;
    try {
      const { data } = await requestPasswordReset({
        variables: { usernameOrEmail: usernameOrEmail.trim() },
      });
      if (data?.requestPasswordReset?.ok) {
        setResetToken(data.requestPasswordReset.resetToken || null);
        setSubmitted(true);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Request password reset failed:', e);
    }
  };

  const handleCopy = () => {
    if (resetToken) {
      navigator.clipboard.writeText(`${window.location.origin}/reset-password?token=${resetToken}`);
      setCopied(true);
      setTimeout(() => setCopied(false), COPY_FEEDBACK_DURATION_MS);
    }
  };

  return (
    <div className="auth-shell">
      <Card className="auth-card" style={{ width: 420 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <span className="logo-title" style={{ display: 'block', fontSize: 32 }}>
            HEFAISTOS
          </span>
        </div>
        <Typography.Paragraph className="auth-subtitle">
          Password Reset
        </Typography.Paragraph>

        {submitted ? (
          <div>
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
              message="Reset request submitted"
              description="If an account with that username/email exists, a reset link has been generated."
            />
            {resetToken && (
              <div style={{ marginBottom: 16 }}>
                <Typography.Paragraph style={{ fontSize: 13, marginBottom: 8 }}>
                  Email is not configured. Share the link below with the user:
                </Typography.Paragraph>
                <div className="auth-token-box" style={{ marginBottom: 8 }}>
                  {`${window.location.origin}/reset-password?token=${resetToken}`}
                </div>
                <Button size="small" onClick={handleCopy} style={{ marginBottom: 8 }}>
                  {copied ? '✓ Copied!' : 'Copy Link'}
                </Button>
              </div>
            )}
            <div style={{ textAlign: 'center' }}>
              <Link to="/login" className="theme-link">
                ← Back to Login
              </Link>
            </div>
          </div>
        ) : (
          <>
            {error && (
              <Alert type="error" showIcon style={{ marginBottom: 16 }} message={error.message} />
            )}
            <Form layout="vertical" onSubmitCapture={handleSubmit}>
              <Form.Item label="Username or Email" required>
                <Input
                  value={usernameOrEmail}
                  onChange={(e) => setUsernameOrEmail(e.target.value)}
                  size="large"
                  autoFocus
                  disabled={loading}
                  placeholder="Enter your username or email"
                />
              </Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                block
                size="large"
                loading={loading}
                style={{ marginTop: 8, fontWeight: 600 }}
              >
                {loading ? 'Sending...' : 'Request Password Reset'}
              </Button>
            </Form>
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <Link to="/login" className="theme-link">
                ← Back to Login
              </Link>
            </div>
          </>
        )}

        <Typography.Paragraph className="auth-footer">
          © {new Date().getFullYear()} HEFAISTOS Platform
        </Typography.Paragraph>
      </Card>
    </div>
  );
};
