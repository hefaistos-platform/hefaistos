import React, { useEffect, useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { Card, Form, Input, Button, Typography, Alert, Dropdown, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { SunOutlined, MoonOutlined, MonitorOutlined } from '@ant-design/icons';
import { credentialToJSON, parseAuthenticationOptions } from '../utils/webauthn';

const START_MFA_LOGIN_MUTATION = gql`
  mutation StartMfaLogin($username: String!, $password: String!) {
    startMfaLogin(username: $username, password: $password) {
      token
      mfaRequired
      challengeId
      message
      hasWebauthn
    }
  }
`;

const VERIFY_MFA_LOGIN_MUTATION = gql`
  mutation VerifyMfaLogin($challengeId: String!, $otpCode: String, $backupCode: String) {
    verifyMfaLogin(challengeId: $challengeId, otpCode: $otpCode, backupCode: $backupCode) {
      token
      ok
      message
    }
  }
`;

const START_WEBAUTHN_MFA_AUTH_MUTATION = gql`
  mutation StartWebauthnMfaAuthentication($loginChallengeId: String!) {
    startWebauthnMfaAuthentication(loginChallengeId: $loginChallengeId) {
      optionsJson
      webauthnChallengeId
    }
  }
`;

const VERIFY_WEBAUTHN_MFA_AUTH_MUTATION = gql`
  mutation VerifyWebauthnMfaAuthentication($loginChallengeId: String!, $webauthnChallengeId: String!, $credential: JSONString!) {
    verifyWebauthnMfaAuthentication(
      loginChallengeId: $loginChallengeId,
      webauthnChallengeId: $webauthnChallengeId,
      credential: $credential
    ) {
      ok
      token
    }
  }
`;

const START_PASSWORDLESS_LOGIN_MUTATION = gql`
  mutation StartPasswordlessLogin($username: String!) {
    startPasswordlessLogin(username: $username) {
      webauthnChallengeId
      optionsJson
    }
  }
`;

const VERIFY_PASSWORDLESS_LOGIN_MUTATION = gql`
  mutation VerifyPasswordlessLogin($webauthnChallengeId: String!, $credential: JSONString!) {
    verifyPasswordlessLogin(webauthnChallengeId: $webauthnChallengeId, credential: $credential) {
      ok
      token
    }
  }
`;

const PUBLIC_AUTH_OPTIONS_QUERY = gql`
  query PublicAuthOptions {
    publicAuthOptions {
      authMode
      defaultLoginProvider
      enableEntra
      enableOidc
      showLocalLogin
    }
  }
`;

const START_OIDC_LOGIN_MUTATION = gql`
  mutation StartOidcLogin($provider: String!, $identifier: String) {
    startOidcLogin(provider: $provider, identifier: $identifier) {
      authorizationUrl
      provider
    }
  }
`;

const COMPLETE_OIDC_LOGIN_MUTATION = gql`
  mutation CompleteOidcLogin($code: String!, $state: String!) {
    completeOidcLogin(code: $code, state: $state) {
      ok
      token
      message
      provider
    }
  }
`;

interface StartMfaLoginData {
  startMfaLogin: {
    token: string;
    mfaRequired: boolean;
    challengeId?: string;
    message?: string;
    hasWebauthn: boolean;
  };
}

interface StartMfaLoginVars {
  username: string;
  password: string;
}

interface VerifyMfaLoginData {
  verifyMfaLogin: {
    token: string;
    ok: boolean;
    message?: string;
  };
}

interface VerifyMfaLoginVars {
  challengeId: string;
  otpCode?: string;
  backupCode?: string;
}

interface StartWebAuthnMfaData {
  startWebauthnMfaAuthentication: { optionsJson: string; webauthnChallengeId: string };
}
interface VerifyWebAuthnMfaData {
  verifyWebauthnMfaAuthentication: { ok: boolean; token: string };
}
interface StartPasswordlessData {
  startPasswordlessLogin: { webauthnChallengeId: string; optionsJson: string };
}
interface VerifyPasswordlessData {
  verifyPasswordlessLogin: { ok: boolean; token: string };
}

interface PublicAuthOptionsData {
  publicAuthOptions: {
    authMode: string;
    defaultLoginProvider: string;
    enableEntra: boolean;
    enableOidc: boolean;
    showLocalLogin: boolean;
  };
}

interface StartOidcLoginData {
  startOidcLogin: {
    authorizationUrl: string;
    provider: string;
  };
}

interface CompleteOidcLoginData {
  completeOidcLogin: {
    ok: boolean;
    token?: string | null;
    message?: string | null;
    provider?: string | null;
  };
}

export const LoginPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [challengeId, setChallengeId] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [backupCode, setBackupCode] = useState('');
  const [showBackupCode, setShowBackupCode] = useState(false);
  const [mfaStep, setMfaStep] = useState(false);
  const [hasWebauthn, setHasWebauthn] = useState(false);
  const [oidcError, setOidcError] = useState('');
  const [termsModalOpen, setTermsModalOpen] = useState(false);
  const { login } = useAuth();
  const { mode, setMode, resolvedTheme } = useTheme();
  const { data: publicAuthData } = useQuery<PublicAuthOptionsData>(PUBLIC_AUTH_OPTIONS_QUERY, {
    fetchPolicy: 'cache-and-network',
  });

  const [startMfaLogin, { loading: loginLoading, error: loginError }] = useMutation<StartMfaLoginData, StartMfaLoginVars>(START_MFA_LOGIN_MUTATION);
  const [verifyMfaLogin, { loading: verifyLoading, error: verifyError }] = useMutation<VerifyMfaLoginData, VerifyMfaLoginVars>(VERIFY_MFA_LOGIN_MUTATION);
  const [startWebauthnMfa] = useMutation<StartWebAuthnMfaData>(START_WEBAUTHN_MFA_AUTH_MUTATION);
  const [verifyWebauthnMfa] = useMutation<VerifyWebAuthnMfaData>(VERIFY_WEBAUTHN_MFA_AUTH_MUTATION);
  const [startPasswordless] = useMutation<StartPasswordlessData>(START_PASSWORDLESS_LOGIN_MUTATION);
  const [verifyPasswordless] = useMutation<VerifyPasswordlessData>(VERIFY_PASSWORDLESS_LOGIN_MUTATION);
  const [startOidcLogin, { loading: startingOidc }] = useMutation<StartOidcLoginData>(START_OIDC_LOGIN_MUTATION);
  const [completeOidcLogin, { loading: completingOidc }] = useMutation<CompleteOidcLoginData>(COMPLETE_OIDC_LOGIN_MUTATION);

  const loading = loginLoading || verifyLoading || startingOidc || completingOidc;
  const error = loginError || verifyError;
  const authOptions = publicAuthData?.publicAuthOptions;
  const canUseLocalLogin = authOptions?.showLocalLogin ?? true;
  const canUseEntra = authOptions?.enableEntra ?? true;
  const canUseGenericOidc = authOptions?.enableOidc ?? true;
  const showOidcOptions = (canUseEntra || canUseGenericOidc) && !mfaStep;
  const themeMenuItems: MenuProps['items'] = [
    {
      key: 'light',
      icon: <SunOutlined />,
      label: 'Light',
      onClick: () => setMode('light'),
    },
    {
      key: 'dark',
      icon: <MoonOutlined />,
      label: 'Dark',
      onClick: () => setMode('dark'),
    },
    {
      key: 'system',
      icon: <MonitorOutlined />,
      label: 'System',
      onClick: () => setMode('system'),
    },
  ];
  const activeThemeIcon = mode === 'light' ? <SunOutlined /> : mode === 'dark' ? <MoonOutlined /> : <MonitorOutlined />;
  const activeThemeLabel = mode === 'system' ? `System (${resolvedTheme})` : mode;

  const oidcCallbackPayload = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    return { code, state };
  }, []);

  useEffect(() => {
    const { code, state } = oidcCallbackPayload;
    if (!code || !state) return;
    let canceled = false;

    const run = async () => {
      try {
        const res = await completeOidcLogin({ variables: { code, state } });
        const token = res.data?.completeOidcLogin?.token;
        if (!canceled && token) {
          login(token);
        }
      } catch (e: any) {
        if (!canceled) {
          setOidcError(e?.message || 'OIDC login failed.');
        }
      } finally {
        const cleanUrl = `${window.location.origin}${window.location.pathname}`;
        window.history.replaceState({}, document.title, cleanUrl);
      }
    };

    run();
    return () => {
      canceled = true;
    };
  }, [completeOidcLogin, login, oidcCallbackPayload]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const { data } = await startMfaLogin({
        variables: { username, password },
      });

      const result = data?.startMfaLogin;
      if (!result) return;
      if (result.token) {
        login(result.token);
      } else if (result.mfaRequired && result.challengeId) {
        setChallengeId(result.challengeId);
        setHasWebauthn(!!result.hasWebauthn);
        setMfaStep(true);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Login failed:', e);
    }
  };

  const handleOidcSignIn = async (provider: 'ENTRA' | 'OIDC') => {
    setOidcError('');
    const identifier = username.trim();
    if (!identifier) {
      setOidcError('Enter username or email before OIDC sign-in.');
      return;
    }
    try {
      const res = await startOidcLogin({ variables: { provider, identifier } });
      const url = res.data?.startOidcLogin?.authorizationUrl;
      if (!url) {
        setOidcError('OIDC authorization URL is missing.');
        return;
      }
      window.location.assign(url);
    } catch (e: any) {
      setOidcError(e?.message || 'Failed to start OIDC login.');
    }
  };

  const handleWebAuthnMfa = async () => {
    try {
      const started = await startWebauthnMfa({ variables: { loginChallengeId: challengeId } });
      const optionsJson = started.data?.startWebauthnMfaAuthentication?.optionsJson;
      const webauthnChallengeId = started.data?.startWebauthnMfaAuthentication?.webauthnChallengeId;
      if (!optionsJson || !webauthnChallengeId) return;
      const credential = await navigator.credentials.get({
        publicKey: parseAuthenticationOptions(optionsJson),
      }) as PublicKeyCredential | null;
      if (!credential) return;
      const verified = await verifyWebauthnMfa({
        variables: {
          loginChallengeId: challengeId,
          webauthnChallengeId,
          credential: JSON.stringify(credentialToJSON(credential)),
        },
      });
      const token = verified.data?.verifyWebauthnMfaAuthentication?.token;
      if (token) login(token);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Security key MFA failed:', e);
    }
  };

  const handlePasswordless = async () => {
    try {
      const started = await startPasswordless({ variables: { username } });
      const optionsJson = started.data?.startPasswordlessLogin?.optionsJson;
      const webauthnChallengeId = started.data?.startPasswordlessLogin?.webauthnChallengeId;
      if (!optionsJson || !webauthnChallengeId) return;
      const credential = await navigator.credentials.get({
        publicKey: parseAuthenticationOptions(optionsJson),
      }) as PublicKeyCredential | null;
      if (!credential) return;
      const verified = await verifyPasswordless({
        variables: { webauthnChallengeId, credential: JSON.stringify(credentialToJSON(credential)) },
      });
      const token = verified.data?.verifyPasswordlessLogin?.token;
      if (token) login(token);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Passwordless login failed:', e);
    }
  };

  const handleVerifyMfa = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const { data } = await verifyMfaLogin({
        variables: {
          challengeId,
          otpCode: showBackupCode ? undefined : otpCode,
          backupCode: showBackupCode ? backupCode : undefined,
        },
      });
      if (data?.verifyMfaLogin?.token) {
        login(data.verifyMfaLogin.token);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('MFA verification failed:', e);
    }
  };

  const renderOidcOptions = () => {
    if (!showOidcOptions) return null;

    return (
      <div className="login-alt-options">
        {canUseEntra && (
          <Button
            type="default"
            htmlType="button"
            block
            size="large"
            style={{ fontWeight: 600 }}
            onClick={() => handleOidcSignIn('ENTRA')}
            disabled={loading || !username.trim()}
          >
            ENTRA Login
          </Button>
        )}
        {canUseGenericOidc && (
          <Button
            type="default"
            htmlType="button"
            block
            size="large"
            style={{ fontWeight: 600 }}
            onClick={() => handleOidcSignIn('OIDC')}
            disabled={loading || !username.trim()}
          >
            OIDC Login
          </Button>
        )}
      </div>
    );
  };

  return (
    <div className="auth-shell login-shell">
      <div className="login-layout">
        <section className="login-hero" aria-label="HEFAISTOS introduction">
          <h1 className="login-hero-title">
            <span className="login-hero-brand">HEFAISTOS</span>
            <span className="login-hero-brand-sub">Detection Platform</span>
          </h1>
          <p className="login-hero-subtitle">
            Why settle for generic detection failures when we can engineer our own?
          </p>
        </section>
        <Card className="auth-card login-card" style={{ width: 540 }}>
          <div className="login-theme-toggle">
            <Dropdown menu={{ items: themeMenuItems, selectable: true, selectedKeys: [mode] }} trigger={['click']}>
              <Button icon={activeThemeIcon} size="small">
                Theme: {activeThemeLabel}
              </Button>
            </Dropdown>
          </div>
          <Typography.Title level={2} className="login-card-title">
            Sign In
          </Typography.Title>
          {error && (
            <Alert type="error" showIcon style={{ marginBottom: 16 }} message={error.message} />
          )}
          {oidcError && (
            <Alert type="error" showIcon style={{ marginBottom: 16 }} message={oidcError} />
          )}
          {!mfaStep ? (
            canUseLocalLogin ? (
            <Form layout="vertical" onSubmitCapture={handleSubmit}>
              <Form.Item label="Username" required>
                <Input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  size="large"
                  autoFocus
                  disabled={loading}
                  placeholder="Enter your username"
                />
              </Form.Item>
              <Form.Item label="Password" required>
                <Input.Password
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  size="large"
                  disabled={loading}
                  placeholder="Enter your password"
                />
              </Form.Item>
              <Button
                type="default"
                htmlType="button"
                block
                size="large"
                style={{ marginTop: 8, fontWeight: 600 }}
                onClick={handlePasswordless}
                disabled={loading || !username}
              >
                Use Security Key (Passwordless)
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                block
                size="large"
                loading={loading}
                style={{ marginTop: 8, fontWeight: 600 }}
              >
                {loading ? 'Signing In...' : 'Sign In'}
              </Button>
              {renderOidcOptions()}
              <div className="login-links">
                <Link to="/forgot-password" className="theme-link" style={{ fontSize: 13 }}>
                  Forgot Password
                </Link>
                <span className="theme-link login-link-divider" style={{ fontSize: 13 }}>|</span>
                <Button
                  type="link"
                  htmlType="button"
                  className="login-terms-link theme-link"
                  style={{ fontSize: 13 }}
                  onClick={() => setTermsModalOpen(true)}
                >
                  Terms and Conditions
                </Button>
              </div>
            </Form>
            ) : (
              <>
                <Alert
                  type="info"
                  showIcon
                  message="Local username/password login is disabled. Please use your configured OIDC provider."
                />
                {renderOidcOptions()}
              </>
            )
          ) : (
            <Form layout="vertical" onSubmitCapture={handleVerifyMfa}>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="Second factor required. Enter code from your authenticator app or a backup code."
              />
              {!showBackupCode ? (
                <Form.Item label="Authenticator code" required>
                  <Input
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    size="large"
                    autoFocus
                    disabled={loading}
                    placeholder="6-digit code"
                  />
                </Form.Item>
              ) : (
                <Form.Item label="Backup code" required>
                  <Input
                    value={backupCode}
                    onChange={(e) => setBackupCode(e.target.value)}
                    size="large"
                    autoFocus
                    disabled={loading}
                    placeholder="Enter backup code"
                  />
                </Form.Item>
              )}
              <Button
                type="primary"
                htmlType="submit"
                block
                size="large"
                loading={loading}
                style={{ marginTop: 8, fontWeight: 600 }}
              >
                {loading ? 'Verifying...' : 'Verify and Login'}
              </Button>
              {hasWebauthn && (
                <Button type="default" block size="large" style={{ marginTop: 8 }} onClick={handleWebAuthnMfa}>
                  Use Security Key
                </Button>
              )}
              <div style={{ textAlign: 'center', marginTop: 12 }}>
                <Button type="link" onClick={() => setShowBackupCode(!showBackupCode)}>
                  {showBackupCode ? 'Use authenticator code' : 'Use backup code'}
                </Button>
                <Button
                  type="link"
                  onClick={() => {
                    setMfaStep(false);
                    setChallengeId('');
                    setOtpCode('');
                    setBackupCode('');
                  }}
                >
                  Back
                </Button>
              </div>
            </Form>
          )}
          <Modal
            title="Terms and Conditions"
            open={termsModalOpen}
            centered
            onCancel={() => setTermsModalOpen(false)}
            footer={[
              <Button key="close-terms" type="primary" onClick={() => setTermsModalOpen(false)}>
                Close
              </Button>,
            ]}
          >
            <Typography.Paragraph>
              These terms summarize the AGPL-3.0 license model used by HEFAISTOS and do not replace the full legal
              text in the repository <code>LICENSE</code> file.
            </Typography.Paragraph>
            <Typography.Paragraph>
              The platform is provided "as is", without warranties of any kind. To the maximum extent permitted by
              law, the author and contributors are not liable for damages, losses, or legal consequences resulting from
              use or misuse of the platform.
            </Typography.Paragraph>
            <Typography.Paragraph>
              The responsibility lies with the person using the platform, not with the author of the platform, who is
              th3r3d a.k.a. m3c4n1sm0.
            </Typography.Paragraph>
            <Typography.Paragraph>
              By using this platform, you confirm that you are authorized to do so and that you will follow all
              applicable laws, internal policies, and licensing obligations.
            </Typography.Paragraph>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              Contact (obfuscated): m3c4n1sm0\@xprivacy.cz
            </Typography.Paragraph>
          </Modal>
          <Typography.Paragraph className="auth-footer">
            &copy; 2026 HEFAISTOS by B1gF00t Entertainment
          </Typography.Paragraph>
        </Card>
      </div>
    </div>
  );
};
