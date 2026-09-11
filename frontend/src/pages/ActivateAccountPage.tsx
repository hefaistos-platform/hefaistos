import React, { useEffect, useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';

const REDIRECT_DELAY_MS = 4000;

const PREPARE_ACCOUNT_ACTIVATION_MUTATION = gql`
  mutation PrepareAccountActivation($token: String!) {
    prepareAccountActivation(token: $token) {
      username
      email
      role
      requiresMfa
      totpSecret
      otpauthUri
      expiresAt
    }
  }
`;

const COMPLETE_ACCOUNT_ACTIVATION_MUTATION = gql`
  mutation CompleteAccountActivation($token: String!, $newPassword: String!, $otpCode: String) {
    completeAccountActivation(token: $token, newPassword: $newPassword, otpCode: $otpCode) {
      ok
      message
      backupCodes
    }
  }
`;

interface PrepareAccountActivationData {
  prepareAccountActivation: {
    username: string;
    email: string;
    role: string;
    requiresMfa: boolean;
    totpSecret?: string | null;
    otpauthUri?: string | null;
    expiresAt: string;
  };
}

interface PrepareAccountActivationVars {
  token: string;
}

interface CompleteAccountActivationData {
  completeAccountActivation: {
    ok: boolean;
    message: string;
    backupCodes: string[];
  };
}

interface CompleteAccountActivationVars {
  token: string;
  newPassword: string;
  otpCode?: string;
}

export const ActivateAccountPage = () => {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get('token') || '', [searchParams]);
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [validationError, setValidationError] = useState('');
  const [activationContext, setActivationContext] = useState<PrepareAccountActivationData['prepareAccountActivation'] | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [successMessage, setSuccessMessage] = useState('');

  const [prepareAccountActivation, { loading: loadingContext, error: contextError }] = useMutation<
    PrepareAccountActivationData,
    PrepareAccountActivationVars
  >(PREPARE_ACCOUNT_ACTIVATION_MUTATION);

  const [completeAccountActivation, { loading: completing, error: completeError }] = useMutation<
    CompleteAccountActivationData,
    CompleteAccountActivationVars
  >(COMPLETE_ACCOUNT_ACTIVATION_MUTATION);

  useEffect(() => {
    if (!token) return;
    const loadContext = async () => {
      try {
        const { data } = await prepareAccountActivation({ variables: { token } });
        if (data?.prepareAccountActivation) {
          setActivationContext(data.prepareAccountActivation);
        }
      } catch (e) {
        // handled by mutation error state
        console.error('Failed to prepare account activation:', e);
      }
    };
    loadContext();
  }, [token, prepareAccountActivation]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setValidationError('');

    if (!newPassword) {
      setValidationError('Please enter a new password.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setValidationError('Passwords do not match.');
      return;
    }
    if (!token) {
      setValidationError('Missing activation token. Please use your invitation link.');
      return;
    }
    if (activationContext?.requiresMfa && !otpCode.trim()) {
      setValidationError('Authenticator code is required for administrator activation.');
      return;
    }

    try {
      const { data } = await completeAccountActivation({
        variables: {
          token,
          newPassword,
          otpCode: activationContext?.requiresMfa ? otpCode.trim() : undefined,
        },
      });
      if (data?.completeAccountActivation?.ok) {
        setSuccessMessage(data.completeAccountActivation.message || 'Account setup completed successfully.');
        setBackupCodes(data.completeAccountActivation.backupCodes || []);
        setTimeout(() => navigate('/login'), REDIRECT_DELAY_MS);
      }
    } catch (e) {
      console.error('Failed to complete account activation:', e);
    }
  };

  if (!token) {
    return (
      <div className="auth-shell">
        <Card className="auth-card" style={{ width: 460 }}>
          <Alert
            type="error"
            showIcon
            message="Invalid Activation Link"
            description="No activation token found. Ask your administrator to send a new invitation."
          />
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Link to="/login" className="theme-link">
              Back to Login
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="auth-shell">
      <Card className="auth-card" style={{ width: 520 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <span className="logo-title" style={{ display: 'block', fontSize: 32 }}>
            HEFAISTOS
          </span>
        </div>
        <Typography.Paragraph className="auth-subtitle" style={{ marginBottom: 20 }}>
          Complete Account Setup
        </Typography.Paragraph>

        {(contextError || completeError || validationError) && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message={validationError || contextError?.message || completeError?.message}
          />
        )}

        {successMessage ? (
          <div>
            <Alert type="success" showIcon style={{ marginBottom: 16 }} message={successMessage} />
            {backupCodes.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message="Save your backup codes"
                description={
                  <div>
                    <p style={{ marginBottom: 8 }}>These codes are shown once. Store them in a secure location.</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 8 }}>
                      {backupCodes.map((code) => (
                        <code key={code} className="auth-token-box" style={{ padding: '4px 8px' }}>
                          {code}
                        </code>
                      ))}
                    </div>
                  </div>
                }
              />
            )}
            <div style={{ textAlign: 'center' }}>
              <Link to="/login" className="theme-link">
                Go to Login
              </Link>
            </div>
          </div>
        ) : (
          <Form layout="vertical" onSubmitCapture={handleSubmit}>
            {loadingContext ? (
              <Alert type="info" showIcon style={{ marginBottom: 16 }} message="Loading activation details..." />
            ) : (
              activationContext && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message={`Setting up account for ${activationContext.username} (${activationContext.role})`}
                  description={`Activation link expires at ${new Date(activationContext.expiresAt).toLocaleString()}.`}
                />
              )
            )}

            <Form.Item label="New Password" required>
              <Input.Password
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                size="large"
                autoFocus
                disabled={completing || loadingContext}
                placeholder="Enter your new password"
              />
            </Form.Item>
            <Form.Item label="Confirm New Password" required>
              <Input.Password
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                size="large"
                disabled={completing || loadingContext}
                placeholder="Confirm your new password"
              />
            </Form.Item>

            {activationContext?.requiresMfa && (
              <>
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="Administrator MFA enrollment required"
                  description="Scan the secret in your authenticator app and enter the current 6-digit code to complete setup."
                />
                {activationContext.totpSecret && (
                  <div style={{ marginBottom: 12 }}>
                    <Typography.Text strong>Authenticator secret</Typography.Text>
                    <div className="auth-token-box" style={{ marginTop: 4, marginBottom: 8, fontFamily: 'monospace' }}>
                      {activationContext.totpSecret}
                    </div>
                  </div>
                )}
                {activationContext.otpauthUri && (
                  <div style={{ marginBottom: 12 }}>
                    <Typography.Text strong>OTP URI (manual import)</Typography.Text>
                    <div className="auth-token-box" style={{ marginTop: 4, marginBottom: 8, fontFamily: 'monospace', fontSize: 12 }}>
                      {activationContext.otpauthUri}
                    </div>
                  </div>
                )}
                <Form.Item label="Authenticator Code" required>
                  <Input
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    size="large"
                    disabled={completing || loadingContext}
                    placeholder="6-digit code"
                  />
                </Form.Item>
              </>
            )}

            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={completing}
              disabled={loadingContext}
              style={{ marginTop: 8, fontWeight: 600 }}
            >
              {completing ? 'Completing Setup...' : 'Complete Setup'}
            </Button>
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <Link to="/login" className="theme-link">
                Back to Login
              </Link>
            </div>
          </Form>
        )}

        <Typography.Paragraph className="auth-footer">
          © {new Date().getFullYear()} HEFAISTOS Platform
        </Typography.Paragraph>
      </Card>
    </div>
  );
};
