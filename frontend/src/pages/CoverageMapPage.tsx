import React, { useRef, useMemo, useState, useEffect } from 'react';
import { Button } from 'antd';
import { gql, useQuery } from '@apollo/client';
import { useNavigate, useLocation } from 'react-router-dom';
import { PixelIcon } from '../components/ui/PixelIcon';
import { getApiBaseUrl, getNavigatorBaseUrl } from '../config/env';

const LOADED_ATTACK_VERSIONS_QUERY = gql`
  query CoverageMapLoadedVersions {
    loadedAttackVersions {
      framework
      version
      importedAt
    }
  }
`;

const ME_ROLE_QUERY = gql`
  query CoverageMapMe {
    me {
      id
      role
      isSuperuser
    }
  }
`;

export const CoverageMapPage = () => {
  const [reloadToken, setReloadToken] = useState(0);
  const [coverageAccessToken, setCoverageAccessToken] = useState<string | null>(null);
  const [isCoverageTokenLoading, setIsCoverageTokenLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isNavigatorLoaded, setIsNavigatorLoaded] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const { data: versionsData } = useQuery(LOADED_ATTACK_VERSIONS_QUERY);
  const { data: meData } = useQuery(ME_ROLE_QUERY);

  const userRole = meData?.me?.role;
  const isSuperuser = Boolean(meData?.me?.isSuperuser);
  const enterpriseEntry = (versionsData?.loadedAttackVersions ?? []).find(
    (v: { framework: string; version: string; importedAt: string }) => v.framework === 'enterprise-attack'
  );

  // Reload Navigator when navigating back from the framework-updates page after a successful update
  useEffect(() => {
    if ((location.state as any)?.frameworkUpdated) {
      setReloadToken((t) => t + 1);
      // Clear the state so a second visit doesn't re-trigger
      window.history.replaceState({}, '');
    }
  }, [location.state]);

  // Mint a short-lived token used only for ATT&CK coverage layer fetches.
  useEffect(() => {
    let cancelled = false;

    const fetchCoverageToken = async () => {
      setIsCoverageTokenLoading(true);
      setCoverageAccessToken(null);

      try {
        const apiBase = getApiBaseUrl();
        const tokenUrl = new URL(`${apiBase}/api/coverage/token`);
        const headers: Record<string, string> = {};
        try {
          const accessToken = localStorage.getItem('accessToken');
          if (accessToken) {
            headers.Authorization = `Bearer ${accessToken}`;
          }
        } catch {}

        const response = await fetch(tokenUrl.toString(), {
          method: 'GET',
          headers,
        });

        if (!response.ok) {
          return;
        }

        const payload = await response.json();
        if (!cancelled && payload?.token) {
          setCoverageAccessToken(String(payload.token));
        }
      } catch {
        // Keep fallback behavior (no token) if token minting fails.
      } finally {
        if (!cancelled) {
          setIsCoverageTokenLoading(false);
        }
      }
    };

    fetchCoverageToken();

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // Build absolute URL to the REST layer JSON
  const layerJsonUrl = useMemo(() => {
    const apiBase = getApiBaseUrl();
    const url = new URL(`${apiBase}/api/coverage/layer.json`);
    url.searchParams.set('_', String(reloadToken));

    if (coverageAccessToken) {
      url.searchParams.set('token', coverageAccessToken);
    }

    return url.toString();
  }, [reloadToken, coverageAccessToken]);

  const iframeSrc = useMemo(() => {
    if (isCoverageTokenLoading) {
      return 'about:blank';
    }

    const params = new URLSearchParams();
    params.set('layerURL', layerJsonUrl);
    // Optional UI flags
    params.set('tabs', 'false');
    params.set('selecting_techniques', 'false');

    // Allow overriding Navigator host via env (fallback to locally hosted /navigator).
    const configured = getNavigatorBaseUrl();
    const defaultLocal = `${window.location.origin}/navigator/`;
    const base = (configured && configured.trim().length > 0)
      ? configured
      : defaultLocal;

    // Ensure no duplicate hash
    const hashSep = base.includes('#') ? '' : '#';
    return `${base}${hashSep}${params.toString()}`;
  }, [layerJsonUrl, isCoverageTokenLoading]);

  // Track last time we requested a reload of the layer
  useEffect(() => {
    setLastUpdated(new Date());
    setIsNavigatorLoaded(false);
    setError(null);
    setParseError(null);
    setIsCoverageTokenLoading(true);
  }, [reloadToken]);

  // Validate that the layer JSON is valid before Navigator attempts to load it
  useEffect(() => {
    setParseError(null);

    const validateLayerJson = async () => {
      try {
        // Always fetch from REST URL to ensure Navigator can access it cross-origin
        const response = await fetch(layerJsonUrl);
        if (!response.ok) {
          setError(new Error(`Server returned ${response.status}: ${response.statusText}`));
          return;
        }
        const json = await response.json();
        if (!json.techniques || !Array.isArray(json.techniques)) {
          setParseError("Invalid layer data structure: missing or invalid 'techniques' array.");
          return;
        }
        console.log('Layer JSON validation passed.', json);
      } catch (e) {
        console.error('Failed to parse or validate layer JSON:', e);
        setParseError('Failed to parse layer data. The data may be corrupt.');
      }
    };

    if (!isCoverageTokenLoading && layerJsonUrl) {
      validateLayerJson();
    }

    return () => {
      // Revoke blob URL to prevent memory leaks
      // no blob URL used
    };
  }, [layerJsonUrl, isCoverageTokenLoading]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        gap: '16px',
        margin: '-24px -32px',
        padding: '24px 32px',
        background: 'var(--hef-bg-page)',
      }}
    >
      {/* --- Header --- */}
      <div
        style={{
          flexShrink: 0,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px',
          background: 'var(--hef-bg-surface)',
          border: '1px solid var(--hef-border)',
          borderRadius: '8px',
          boxShadow: 'var(--hef-shadow-card)',
        }}
      >
        <div>
          <h2 style={{ fontSize: '28px', fontWeight: 'bold', margin: 0, marginBottom: '8px' }}>ATT&CK Coverage Map</h2>
          <p style={{ color: 'var(--hef-text-secondary)', margin: 0 }}>
            Live coverage based on deployed detections.
            {enterpriseEntry && (
              <span style={{ marginLeft: 12, color: 'var(--hef-text-muted)', fontSize: 13 }}>
                ATT&amp;CK: v{enterpriseEntry.version}
                {enterpriseEntry.importedAt && (
                  <span> (loaded {new Date(enterpriseEntry.importedAt).toLocaleDateString()})</span>
                )}
              </span>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {/* D3FEND support removed */}
          <span style={{ color: 'var(--hef-text-muted)', fontSize: 12 }}>
            {lastUpdated ? `Last updated: ${lastUpdated.toLocaleTimeString()}` : 'Not updated yet'}
          </span>
          {isSuperuser && (
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => navigate('/mgmt/framework-updates')}
            >
              Update framework
            </Button>
          )}
          <Button
            type="default"
            href={layerJsonUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open raw JSON
          </Button>
          {isSuperuser && (
            <Button
              type="default"
              onClick={() => setReloadToken((t) => t + 1)}
            >
              <PixelIcon name="search" className="w-5 h-5" />
              Refresh
            </Button>
          )}
        </div>
      </div>

      {/* --- UPDATED: Error Handling --- */}
      {error && (
        <div
          style={{
            marginBottom: '16px',
            padding: '16px',
            background: 'var(--hef-danger-bg)',
            border: '1px solid var(--hef-danger-border)',
            color: 'var(--hef-danger-text)',
            borderRadius: '6px',
          }}
        >
          <h3 style={{ fontWeight: 'bold', margin: '0 0 8px 0' }}>Error Loading Coverage Layer</h3>
          <p style={{ margin: 0 }}>{error.message}</p>
        </div>
      )}
      {/* --- END UPDATE --- */}

      {/* --- NEW: Parse Error Display --- */}
      {parseError && (
        <div
          style={{
            marginBottom: '16px',
            padding: '16px',
            background: 'var(--hef-danger-bg)',
            border: '1px solid var(--hef-danger-border)',
            color: 'var(--hef-danger-text)',
            borderRadius: '6px',
          }}
        >
          <h3 style={{ fontWeight: 'bold', margin: '0 0 8px 0' }}>Data Parsing Error</h3>
          <p style={{ margin: 0 }}>{parseError}</p>
        </div>
      )}
      {/* --- END NEW --- */}

      {/* --- iframe Container --- */}
      <div
        style={{
          flex: 1,
          width: '100%',
          background: 'var(--hef-bg-surface)',
          border: '1px solid var(--hef-border)',
          borderRadius: '8px',
          boxShadow: 'var(--hef-shadow-card)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}
      >
        
        {/* --- Loading Skeleton Overlay --- */}
        {!isNavigatorLoaded && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--hef-bg-subtle)', zIndex: 10 }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ color: 'var(--hef-text-muted)', margin: '0 auto', fontSize: '64px' }}>
                <PixelIcon name="folder" className="w-16 h-16" />
              </div>
              <p style={{ fontSize: '18px', fontWeight: '500', color: 'var(--hef-text-secondary)', marginTop: '16px', margin: '16px 0 0 0' }}>Loading ATT&CK Navigator...</p>
            </div>
          </div>
        )}
        {/* --- End Loading Overlay --- */}

        <iframe
          key={iframeSrc}
          ref={iframeRef}
          src={iframeSrc}
          title="ATT&CK Navigator"
          style={{ flex: 1, border: 'none', width: '100%', height: '100%', opacity: isNavigatorLoaded ? 1 : 0, transition: 'opacity 0.3s' }}
          frameBorder={0}
          onLoad={() => {
            console.log("iframe is fully loaded.");
            setIsNavigatorLoaded(true);
            setError(null);
          }}
          onError={() => {
            console.error("iframe failed to load.");
            setError(new Error("Failed to load ATT&CK Navigator. Please check your connection and try again."));
          }}
        />
      </div>
    </div>
  );
};
