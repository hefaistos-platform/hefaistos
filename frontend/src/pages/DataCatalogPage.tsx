import React, { useEffect, useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { useNavigate } from 'react-router-dom';
import { Alert, App, Button, Card, Empty, Input, Pagination, Progress, Select, Space, Tag, Typography } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import { markdownToPlainText } from '../components/MarkdownRenderer';

const GET_DATASOURCES_PAGE_QUERY = gql`
  query GetDataSourcesPage($limit: Int!, $offset: Int!, $query: String, $platform: String) {
    dataSourcesPage(limit: $limit, offset: $offset, query: $query, platform: $platform) {
      items {
        id
        name
        platform
        description
      }
      totalCount
    }
  }
`;

const GET_DATA_SOURCE_PLATFORMS_QUERY = gql`
  query GetDataSourcePlatforms {
    dataSourcePlatforms
  }
`;

const GET_MY_ROLE_QUERY = gql`
  query GetMyRole {
    me {
      id
      role
      username
      email
      avatarUrl
      isSuperuser
      organization {
        id
        name
      }
    }
    myOrganizations {
      id
      name
      isDefault
      isActive
    }
  }
`;

const IMPORT_MITRE_REQUIRED_DATASOURCES_MUTATION = gql`
  mutation ImportMitreRequiredDataSources {
    importMitreRequiredDataSources {
      createdCount
      existingCount
      updatedCount
      totalCandidates
    }
  }
`;

const RUN_MITRE_DEEP_IMPORT_MUTATION = gql`
  mutation RunMitreDeepImport($includeRevoked: Boolean) {
    runMitreDeepImport(includeRevoked: $includeRevoked) {
      job {
        id
        status
        includeRevoked
        progressPercent
        totalAnalytics
        processedAnalytics
        failedAnalytics
        totalRows
        importedRows
        createdCount
        existingCount
        updatedCount
        error
        createdAt
        startedAt
        finishedAt
      }
    }
  }
`;

const MITRE_DEEP_IMPORT_JOB_QUERY = gql`
  query MitreDeepImportJob($id: UUID!) {
    mitreDeepImportJob(id: $id) {
      id
      status
      includeRevoked
      progressPercent
      totalAnalytics
      processedAnalytics
      failedAnalytics
      totalRows
      importedRows
      createdCount
      existingCount
      updatedCount
      error
      createdAt
      startedAt
      finishedAt
    }
  }
`;

const MITRE_DEEP_IMPORT_JOBS_QUERY = gql`
  query MitreDeepImportJobs($limit: Int) {
    mitreDeepImportJobs(limit: $limit) {
      id
      status
      includeRevoked
      progressPercent
      totalAnalytics
      processedAnalytics
      failedAnalytics
      totalRows
      importedRows
      createdCount
      existingCount
      updatedCount
      error
      createdAt
      startedAt
      finishedAt
    }
  }
`;

const DEFAULT_PAGE_SIZE = 60;

interface DataSource {
  id: string;
  name: string;
  platform: string | null;
  description: string | null;
}

interface DataSourcesPageData {
  dataSourcesPage: {
    items: DataSource[];
    totalCount: number;
  };
}

interface DataSourcesPageVars {
  limit: number;
  offset: number;
  query?: string | null;
  platform?: string | null;
}

interface DataSourcePlatformsData {
  dataSourcePlatforms: string[];
}

interface ImportMitreRequiredDataSourcesData {
  importMitreRequiredDataSources: {
    createdCount: number;
    existingCount: number;
    updatedCount: number;
    totalCandidates: number;
  };
}

interface MeData {
  me: {
    id: string;
    role: string;
    username?: string | null;
    email?: string | null;
    avatarUrl?: string | null;
    isSuperuser?: boolean | null;
    organization?: {
      id: string;
      name: string;
    } | null;
  };
  myOrganizations?: Array<{
    id: string;
    name: string;
    isDefault: boolean;
    isActive: boolean;
  }>;
}

interface MitreDeepImportJobRecord {
  id: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED';
  includeRevoked: boolean;
  progressPercent: number;
  totalAnalytics: number;
  processedAnalytics: number;
  failedAnalytics: number;
  totalRows: number;
  importedRows: number;
  createdCount: number;
  existingCount: number;
  updatedCount: number;
  error?: string | null;
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
}

interface RunMitreDeepImportData {
  runMitreDeepImport: {
    job: MitreDeepImportJobRecord;
  };
}

interface MitreDeepImportJobData {
  mitreDeepImportJob: MitreDeepImportJobRecord | null;
}

interface MitreDeepImportJobsData {
  mitreDeepImportJobs: MitreDeepImportJobRecord[];
}

const isTerminalJobStatus = (status?: string | null) => status === 'SUCCESS' || status === 'FAILED';

export const DataCatalogPage = () => {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();

  const [deepJobId, setDeepJobId] = useState<string | null>(null);
  const [lastTerminalJobId, setLastTerminalJobId] = useState<string | null>(null);
  const [enableDeepJobLookup, setEnableDeepJobLookup] = useState<boolean>(false);
  const [isPageVisible, setIsPageVisible] = useState<boolean>(() => {
    if (typeof document === 'undefined') return true;
    return document.visibilityState !== 'hidden';
  });

  const [platformFilter, setPlatformFilter] = useState<string>('ALL');
  const [searchInput, setSearchInput] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchTerm(searchInput.trim());
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  useEffect(() => {
    setCurrentPage(1);
  }, [platformFilter, searchTerm]);

  const baseFilterVars = useMemo(
    () => ({
      query: searchTerm || null,
      platform: platformFilter === 'ALL' ? null : platformFilter,
    }),
    [platformFilter, searchTerm]
  );

  const pageVars: DataSourcesPageVars = useMemo(
    () => ({
      ...baseFilterVars,
      limit: pageSize,
      offset: (currentPage - 1) * pageSize,
    }),
    [baseFilterVars, currentPage, pageSize]
  );

  const {
    data: pageData,
    loading,
    error,
    refetch: refetchPage,
  } = useQuery<DataSourcesPageData, DataSourcesPageVars>(GET_DATASOURCES_PAGE_QUERY, {
    variables: pageVars,
    fetchPolicy: 'cache-first',
    nextFetchPolicy: 'cache-first',
    notifyOnNetworkStatusChange: true,
  });

  const { data: platformsData, refetch: refetchPlatforms } = useQuery<DataSourcePlatformsData>(
    GET_DATA_SOURCE_PLATFORMS_QUERY,
    {
      fetchPolicy: 'cache-first',
      nextFetchPolicy: 'cache-first',
    }
  );

  const { data: meData } = useQuery<MeData>(GET_MY_ROLE_QUERY, {
    fetchPolicy: 'cache-first',
    nextFetchPolicy: 'cache-first',
    returnPartialData: true,
  });

  const [stablePage, setStablePage] = useState<{ items: DataSource[]; totalCount: number }>({
    items: [],
    totalCount: 0,
  });

  useEffect(() => {
    if (pageData?.dataSourcesPage) {
      setStablePage(pageData.dataSourcesPage);
    }
  }, [pageData]);

  const displayedRows = pageData?.dataSourcesPage?.items ?? stablePage.items;
  const displayedTotal = pageData?.dataSourcesPage?.totalCount ?? stablePage.totalCount;
  const initialLoad = loading && displayedRows.length === 0;
  const backgroundLoading = loading && !initialLoad;

  const canRunMitreImports = useMemo(() => {
    const me = meData?.me;
    if (!me) return false;
    return me.role === 'ADMIN' || Boolean(me.isSuperuser);
  }, [meData]);

  useEffect(() => {
    const onVisibilityChange = () => {
      setIsPageVisible(document.visibilityState !== 'hidden');
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (!canRunMitreImports) {
      setEnableDeepJobLookup(false);
      return;
    }

    const timeout = window.setTimeout(() => {
      setEnableDeepJobLookup(true);
    }, 1200);

    return () => window.clearTimeout(timeout);
  }, [canRunMitreImports]);

  const [importMitreRequiredDataSources, { loading: importLoading }] = useMutation<ImportMitreRequiredDataSourcesData>(
    IMPORT_MITRE_REQUIRED_DATASOURCES_MUTATION
  );

  const [runMitreDeepImport, { loading: runDeepImportLoading }] = useMutation<RunMitreDeepImportData>(
    RUN_MITRE_DEEP_IMPORT_MUTATION
  );

  const {
    data: deepJobsData,
    refetch: refetchDeepJobs,
  } = useQuery<MitreDeepImportJobsData>(MITRE_DEEP_IMPORT_JOBS_QUERY, {
    variables: { limit: 1 },
    skip: !canRunMitreImports || !enableDeepJobLookup,
    fetchPolicy: 'cache-first',
    nextFetchPolicy: 'cache-first',
  });

  const {
    data: activeDeepJobData,
    refetch: refetchActiveDeepJob,
  } = useQuery<MitreDeepImportJobData>(MITRE_DEEP_IMPORT_JOB_QUERY, {
    variables: { id: deepJobId },
    skip: !canRunMitreImports || !deepJobId,
    fetchPolicy: 'network-only',
    pollInterval: deepJobId && isPageVisible ? 8000 : 0,
  });

  useEffect(() => {
    if (!canRunMitreImports || deepJobId) return;
    const latestJob = deepJobsData?.mitreDeepImportJobs?.[0];
    if (latestJob && !isTerminalJobStatus(latestJob.status)) {
      setDeepJobId(latestJob.id);
    }
  }, [canRunMitreImports, deepJobId, deepJobsData]);

  useEffect(() => {
    const activeJob = activeDeepJobData?.mitreDeepImportJob;
    if (!activeJob || !isTerminalJobStatus(activeJob.status)) return;
    if (lastTerminalJobId === activeJob.id) return;

    setLastTerminalJobId(activeJob.id);

    if (activeJob.status === 'SUCCESS') {
      message.success(
        `Deep MITRE import complete: ${activeJob.createdCount} new, ${activeJob.existingCount} existing, ${activeJob.updatedCount} updated from ${activeJob.importedRows} scraped rows.`
      );
      setCurrentPage(1);
      void Promise.all([
        refetchPage({ ...baseFilterVars, limit: pageSize, offset: 0 }),
        refetchPlatforms(),
      ]);
    } else {
      message.error(`Deep MITRE import failed.${activeJob.error ? ` ${activeJob.error}` : ''}`);
    }

    setDeepJobId(null);
    refetchDeepJobs();
  }, [
    activeDeepJobData,
    baseFilterVars,
    lastTerminalJobId,
    message,
    pageSize,
    refetchDeepJobs,
    refetchPage,
    refetchPlatforms,
  ]);

  const latestKnownDeepJob = deepJobsData?.mitreDeepImportJobs?.[0] || null;
  const displayedDeepJob = activeDeepJobData?.mitreDeepImportJob || latestKnownDeepJob;
  const deepJobRunning = !!displayedDeepJob && !isTerminalJobStatus(displayedDeepJob.status);

  const allPlatforms = platformsData?.dataSourcePlatforms || [];

  const platformColors = [
    'var(--hef-danger-border)',
    'var(--hef-success-border)',
    'var(--hef-text-link)',
    'var(--hef-warning-border, var(--hef-text-link))',
    'var(--hef-info-border, var(--hef-text-link))',
    'var(--hef-border-strong)',
  ];

  const getPlatformColor = (platform: string | null) => {
    if (!platform) return 'var(--hef-text-muted)';
    const index = allPlatforms.indexOf(platform);
    return platformColors[index % platformColors.length];
  };

  const handleImportMitreSources = () => {
    if (!canRunMitreImports) {
      message.warning('Only ADMIN users can run MITRE imports.');
      return;
    }

    modal.confirm({
      title: 'Import all known MITRE required data sources?',
      content: 'This imports ATT&CK required data-source catalog entries in one pass.',
      okText: 'Import All',
      cancelText: 'Cancel',
      okButtonProps: { loading: importLoading },
      onOk: async () => {
        try {
          const { data: importResult } = await importMitreRequiredDataSources();
          const summary = importResult?.importMitreRequiredDataSources;
          setCurrentPage(1);
          await Promise.all([
            refetchPage({ ...baseFilterVars, limit: pageSize, offset: 0 }),
            refetchPlatforms(),
            refetchDeepJobs(),
          ]);
          if (!summary) {
            message.warning('MITRE import completed, but no summary payload was returned.');
            return;
          }

          message.success(
            `MITRE import complete: ${summary.createdCount} new, ${summary.existingCount} already present, ${summary.updatedCount} enriched (from ${summary.totalCandidates} known sources).`
          );
        } catch (e: any) {
          message.error(`Failed to import MITRE required data sources. ${e?.message || ''}`.trim());
        }
      },
    });
  };

  const handleRunDeepImport = () => {
    if (!canRunMitreImports) {
      message.warning('Only ADMIN users can run MITRE imports.');
      return;
    }

    modal.confirm({
      title: 'Run deep MITRE import across all analytics?',
      content:
        'This background job crawls MITRE analytic pages and imports provider/channel rows into Data Catalog. It may take several minutes.',
      okText: 'Run Deep Import',
      cancelText: 'Cancel',
      okButtonProps: { loading: runDeepImportLoading || deepJobRunning },
      onOk: async () => {
        try {
          const { data: mutationResult } = await runMitreDeepImport({ variables: { includeRevoked: false } });
          const job = mutationResult?.runMitreDeepImport?.job;
          if (!job?.id) {
            message.warning('Deep import started, but no job ID was returned.');
            return;
          }
          setDeepJobId(job.id);
          await refetchActiveDeepJob({ id: job.id });
          await refetchDeepJobs();
          message.info('Deep MITRE import job started. Progress will update automatically.');
        } catch (e: any) {
          message.error(`Failed to start deep MITRE import. ${e?.message || ''}`.trim());
        }
      },
    });
  };

  return (
    <div style={{ padding: '0 24px' }}>
      <div style={{ marginBottom: 24 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <Typography.Title level={3} style={{ margin: 0 }}>Data Source Catalog</Typography.Title>
          <Space>
            {canRunMitreImports ? (
              <>
                <Button onClick={handleImportMitreSources} loading={importLoading} disabled={deepJobRunning}>
                  Import MITRE Required Sources
                </Button>
                <Button onClick={handleRunDeepImport} loading={runDeepImportLoading} disabled={deepJobRunning}>
                  Deep Import (All Analytics)
                </Button>
              </>
            ) : (
              <Typography.Text type="secondary">Import actions are available to ADMIN users only.</Typography.Text>
            )}
            <Button type="primary" onClick={() => navigate('/catalog/new')}>
              <PixelIcon name="add" className="w-5 h-5" />
              <span style={{ marginLeft: 8 }}>New Data Source</span>
            </Button>
          </Space>
        </Space>

        {canRunMitreImports && displayedDeepJob && (
          <Card style={{ marginBottom: 12 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Typography.Text strong>
                  Deep Import Job: <code>{displayedDeepJob.id}</code>
                </Typography.Text>
                <Tag color={displayedDeepJob.status === 'FAILED' ? 'red' : displayedDeepJob.status === 'SUCCESS' ? 'green' : 'blue'}>
                  {displayedDeepJob.status}
                </Tag>
              </Space>

              <Progress
                percent={Math.round(displayedDeepJob.progressPercent || 0)}
                status={displayedDeepJob.status === 'FAILED' ? 'exception' : displayedDeepJob.status === 'SUCCESS' ? 'success' : 'active'}
              />

              <Typography.Text type="secondary">
                Analytics {displayedDeepJob.processedAnalytics}/{displayedDeepJob.totalAnalytics} • Failed analytics {displayedDeepJob.failedAnalytics} • Rows {displayedDeepJob.importedRows}/{displayedDeepJob.totalRows}
              </Typography.Text>
              <Typography.Text type="secondary">
                Catalog results: {displayedDeepJob.createdCount} new, {displayedDeepJob.existingCount} existing, {displayedDeepJob.updatedCount} updated
              </Typography.Text>

              {displayedDeepJob.error && displayedDeepJob.status === 'FAILED' && (
                <Alert type="error" showIcon message={displayedDeepJob.error} />
              )}
            </Space>
          </Card>
        )}

        <Space style={{ marginBottom: 16 }} wrap>
          <Input.Search
            allowClear
            placeholder="Search data sources..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onSearch={(value) => setSearchInput(value)}
            style={{ width: 280 }}
          />
          <Select
            value={platformFilter}
            onChange={setPlatformFilter}
            style={{ minWidth: 220 }}
            options={[{ label: 'All Platforms', value: 'ALL' }, ...allPlatforms.map(p => ({ label: p, value: p }))]}
          />
          <Typography.Text type="secondary">
            Showing {displayedRows.length} of {displayedTotal} data sources
          </Typography.Text>
          {backgroundLoading && (
            <Typography.Text type="secondary">Updating results…</Typography.Text>
          )}
        </Space>
      </div>

      {error && (
        <div style={{ marginBottom: 16 }}>
          <Typography.Text type="danger">Error: {error.message}</Typography.Text>
        </div>
      )}

      {initialLoad ? (
        <Card loading />
      ) : displayedRows.length === 0 ? (
        <Card>
          <Empty
            description={searchTerm || platformFilter !== 'ALL' ? 'No data sources match your filters' : 'No data sources yet'}
          />
        </Card>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
            {displayedRows.map((ds: DataSource) => (
              <Card
                key={ds.id}
                hoverable
                style={{ borderLeft: `5px solid ${getPlatformColor(ds.platform)}` }}
                onClick={() => navigate(`/catalog/${ds.id}`)}
              >
                <div style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 8, marginBottom: 8 }}>
                    <Typography.Title level={4} style={{ margin: 0 }}>
                      {ds.name}
                    </Typography.Title>
                    {ds.platform && (
                      <Tag
                        style={{
                          backgroundColor: getPlatformColor(ds.platform),
                          color: 'var(--hef-text-primary)',
                          border: 'none',
                          fontWeight: 600,
                        }}
                      >
                        {ds.platform}
                      </Tag>
                    )}
                  </div>
                  {ds.description && (
                    <Typography.Text type="secondary" ellipsis={{ tooltip: markdownToPlainText(ds.description) }}>
                      {markdownToPlainText(ds.description)}
                    </Typography.Text>
                  )}
                </div>
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--hef-border)' }}>
                  <Button type="text" size="small" onClick={(e) => { e.stopPropagation(); navigate(`/catalog/${ds.id}`); }}>
                    View Details →
                  </Button>
                </div>
              </Card>
            ))}
          </div>

          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <Pagination
              current={currentPage}
              pageSize={pageSize}
              total={displayedTotal}
              showSizeChanger
              pageSizeOptions={[24, 48, 60, 96]}
              onChange={(page, size) => {
                setCurrentPage(page);
                if (size !== pageSize) {
                  setPageSize(size);
                }
              }}
              showTotal={(total, range) => `${range[0]}-${range[1]} of ${total}`}
            />
          </div>
        </>
      )}
    </div>
  );
};
