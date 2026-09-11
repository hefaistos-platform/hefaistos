import React, { useState, useMemo, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation, useLazyQuery } from '@apollo/client/react';
import { DragDropContext, Droppable, Draggable, DropResult } from '@hello-pangea/dnd';
import { usePlaybookMeta } from '../context/PlaybookMetaContext';
import { Card, Tag, Progress, message, Select, Space, Typography, Input, Drawer, Button } from 'antd';
import { ApartmentOutlined, RadarChartOutlined, BranchesOutlined, BookOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';

// Define the GraphQL query to fetch all legacy playbooks
const GET_ALL_PLAYBOOKS_QUERY = gql`
  query GetAllPlaybooks {
    allPlaybooks {
      id
      title
      status
      playbookType
      author {
        username
      }
      tags {
        id
        name
      }
      tasks {
        id
        status
      }
    }
  }
`;

// Define the GraphQL query to fetch all v2 playbook graphs
const GET_ALL_GRAPHS_QUERY = gql`
  query GetAllPlaybookGraphs {
    allPlaybookGraphs {
      id
      title
      status
      pngSnapshotUrl
      author { username }
      tags
    }
  }
`;

// Define the GraphQL query to fetch all ACH analyses
const GET_ALL_ACH_ANALYSES_QUERY = gql`
  query GetAllACHAnalyses {
    achAnalyses {
      id
      title
      status
      owner { username }
      createdAt
      updatedAt
    }
  }
`;

const GET_ALL_ADVOPS_REPORTS_QUERY = gql`
  query GetAllAdvopsReports {
    allAdvopsReports {
      id
      huntId
      hypothesis
      status
      priority
      author { username }
      createdAt
      updatedAt
    }
  }
`;

const GET_ALL_MVE_DRAFTS_QUERY = gql`
  query GetAllMveDraftsForKanban {
    allMveDrafts {
      id
      name
      status
      isAdvopsValidated
      updatedAt
      author {
        username
      }
    }
  }
`;

const ALL_TAGS_QUERY = gql`
  query AllTags { allTags { id name usageCount } }
`;

const GET_ME_QUERY = gql`
  query Me { me { username role } }
`;

interface MeData { me: { username: string; role: string } }

// Dedicated mutation to update a playbook's status
const UPDATE_PLAYBOOK_STATUS_MUTATION = gql`
  mutation UpdatePlaybookStatus($id: UUID!, $status: String!) {
    updatePlaybookStatus(id: $id, status: $status) {
      playbook {
        id
        status
        updatedAt
      }
    }
  }
`;

// Mutation to update a v2 graph's status
const UPDATE_GRAPH_STATUS_MUTATION = gql`
  mutation UpdatePlaybookGraphStatus($id: UUID!, $status: String!) {
    updatePlaybookGraphStatus(id: $id, status: $status) {
      playbookGraph {
        id
        status
        updatedAt
      }
    }
  }
`;

// Mutation to update ACH analysis status
const UPDATE_ACH_STATUS_MUTATION = gql`
  mutation UpdateACHStatus($analysisId: UUID!, $status: String!) {
    updateAchStatus(analysisId: $analysisId, status: $status) {
      analysis {
        id
        status
        updatedAt
      }
    }
  }
`;

// Mutation to update ADVOPS report status
const UPDATE_ADVOPS_STATUS_MUTATION = gql`
  mutation UpdateAdvopsStatus($id: UUID!, $status: String!) {
    updateAdvopsReport(id: $id, input: { status: $status }) {
      report {
        id
        status
        updatedAt
      }
    }
  }
`;

const UPDATE_MVE_DRAFT_STATUS_MUTATION = gql`
  mutation UpdateMveDraftStatusFromKanban($draftId: UUID!, $status: String) {
    updateMveDraft(draftId: $draftId, status: $status) {
      mveDraft {
        id
        status
        updatedAt
      }
    }
  }
`;

// (Removed unused creation mutations to satisfy ESLint)

// --- TypeScript Types ---
type ItemKind = 'legacy' | 'graph' | 'ach' | 'advops' | 'mve';

interface PlaybookCard {
  id: string;
  title: string;
  status: string;
  playbookType: string; // 'DETECTION' | 'HUNT' | 'GRAPH' | 'ACH' | 'ADVOPS' | 'MVE'
  author: { username: string } | null;
  tags: Array<{ id: string; name: string }>;
  tasks: Array<{ id: string; status: string }>;
  kind: ItemKind;
  graphImageUrl?: string | null; // For graph snapshots
  mveEngineStatus?: string;
}

interface AllPlaybooksData {
  allPlaybooks: PlaybookCard[];
}

interface AllGraphsData {
  allPlaybookGraphs: Array<{ 
    id: string; 
    title: string; 
    status: string; 
    pngSnapshotUrl: string | null;
    author: { username: string } | null 
  }>;
}

interface AllACHAnalysesData {
  achAnalyses: Array<{
    id: string;
    title: string;
    status: string;
    owner: { username: string } | null;
    createdAt: string;
    updatedAt: string;
  }>;
}

interface AllAdvopsReportsData {
  allAdvopsReports: Array<{
    id: string;
    huntId: string;
    hypothesis: string;
    status: string;
    priority: string;
    author: { username: string } | null;
    createdAt: string;
    updatedAt: string;
  }>;
}

interface AllMveDraftsData {
  allMveDrafts: Array<{
    id: string;
    name: string;
    status: string;
    isAdvopsValidated: boolean;
    updatedAt: string;
    author: { username: string } | null;
  }>;
}

interface Column {
  id: string;
  title: string;
  playbooks: PlaybookCard[];
}

interface KanbanData {
  columns: Record<string, Column>;
  columnOrder: string[];
}

// Helper to get display config (color, label, icon, URL) for a kanban item
const getItemConfig = (playbook: PlaybookCard) => {
  switch (playbook.kind) {
    case 'mve':
      return {
        color: '#a87900',
        label: 'MVE',
        icon: <ThunderboltOutlined style={{ fontSize: 'inherit' }} />,
        url: `/playbooks?tab=mve`,
      };
    case 'graph':
      return {
        color: '#52c41a',
        label: 'Workbench',
        icon: <ApartmentOutlined style={{ fontSize: 'inherit' }} />,
        url: `/playbooks/${playbook.id}`,
      };
    case 'advops':
      return {
        color: '#f5222d',
        label: 'AdvOps Hunt',
        icon: <RadarChartOutlined style={{ fontSize: 'inherit' }} />,
        url: `/advops/${playbook.id}`,
      };
    case 'ach':
      return {
        color: '#1890ff',
        label: 'ACH Analysis',
        icon: <BranchesOutlined style={{ fontSize: 'inherit' }} />,
        url: `/tools/ach/${playbook.id}`,
      };
    default: // legacy
      return {
        color: '#1677ff',
        label: playbook.playbookType || 'Playbook',
        icon: <BookOutlined style={{ fontSize: 'inherit' }} />,
        url: `/playbooks/detail/${playbook.id}`,
      };
  }
};

const mapMveEngineStatusToLifecycle = (status: string): string => {
  const normalized = (status || '').toUpperCase();
  if (normalized === 'DRAFT' || normalized === 'MODELED' || normalized === 'GENERATION_READY') return 'RESEARCH';
  if (normalized === 'VALIDATED' || normalized === 'EXPORTED') return 'APPROVED';
  return 'RESEARCH';
};

const mapLifecycleToMveEngineStatus = (lifecycleStatus: string, currentEngineStatus?: string): string | null => {
  const normalizedLifecycle = (lifecycleStatus || '').toUpperCase();
  const normalizedEngine = (currentEngineStatus || '').toUpperCase();
  if (normalizedLifecycle === 'RESEARCH') {
    if (normalizedEngine === 'MODELED' || normalizedEngine === 'GENERATION_READY') {
      return normalizedEngine;
    }
    return 'DRAFT';
  }
  if (normalizedLifecycle === 'APPROVED') {
    // Keep EXPORTED when already exported; otherwise APPROVED maps to VALIDATED.
    return normalizedEngine === 'EXPORTED' ? 'EXPORTED' : 'VALIDATED';
  }
  return null;
};

// Helper function to process data for the board
// Optionally restrict to a subset of statuses (for Status filter)
// Accept status value as string | number and normalize to string for column keys
const processPlaybooksForBoard = (
  playbooks: PlaybookCard[],
  statuses: Array<{ value: string | number; label: string }>,
  allowedStatuses?: string[]
): KanbanData => {
  const columns: Record<string, Column> = {};
  const columnOrder: string[] = [];

  // Create a column for each status
  for (const status of statuses) {
    const key = String(status.value);
    if (!allowedStatuses || allowedStatuses.includes(key)) {
      columns[key] = {
        id: key,
        title: status.label,
        playbooks: [],
      };
      columnOrder.push(key);
    }
  }

  // Add each playbook to its correct column
  for (const playbook of playbooks) {
    if (columns[playbook.status]) {
      columns[playbook.status].playbooks.push(playbook);
    }
  }

  return { columns, columnOrder };
};


export const KanbanBoardPage = () => {
    // UI state: collapsed lanes + density
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
      try {
        const raw = localStorage.getItem('kanban-collapsed');
        return raw ? JSON.parse(raw) : {};
      } catch { return {}; }
    });
    const [dense, setDense] = useState<boolean>(() => (localStorage.getItem('kanban-dense') === '1'));
    const [listView, setListView] = useState<boolean>(() => (localStorage.getItem('kanban-listview') === '1'));

    useEffect(() => { localStorage.setItem('kanban-collapsed', JSON.stringify(collapsed)); }, [collapsed]);
    useEffect(() => { localStorage.setItem('kanban-dense', dense ? '1' : '0'); }, [dense]);
    useEffect(() => { localStorage.setItem('kanban-listview', listView ? '1' : '0'); }, [listView]);
    const [selected, setSelected] = useState<PlaybookCard | null>(null);
    const [viewportWidth, setViewportWidth] = useState<number>(typeof window !== 'undefined' ? window.innerWidth : 1024);
    const isMd = viewportWidth >= 768;

    useEffect(() => {
      const onResize = () => setViewportWidth(window.innerWidth);
      window.addEventListener('resize', onResize);
      return () => window.removeEventListener('resize', onResize);
    }, []);

  const meta = usePlaybookMeta();
  const dynamicStatuses = (meta.data?.statuses && meta.data.statuses.length) ? meta.data.statuses : [
    { value: 'IDEA', label: 'Idea/Hypothesis' },
    { value: 'RESEARCH', label: 'In Research' },
    { value: 'DEVELOPMENT', label: 'In Development' },
    { value: 'REVIEW', label: 'Peer Review' },
    { value: 'APPROVED', label: 'Approved' },
    { value: 'TESTING', label: 'Testing/Validation' },
    { value: 'DEPLOYED', label: 'Deployed' },
    { value: 'TUNING', label: 'Tuning/Maintenance' },
  ];
  const dynamicTypes = useMemo(() => {
    const fromMeta = (meta.data?.playbookTypes && meta.data.playbookTypes.length)
      ? meta.data.playbookTypes
      : [{ value: 'HUNT', label: 'Hunt' }, { value: 'DETECTION', label: 'Detection' }];
    const extras = [
      { value: 'GRAPH', label: 'Workbench' },
      { value: 'ACH', label: 'ACH Matrix' },
      { value: 'ADVOPS', label: 'ADVOPS' },
      { value: 'MVE', label: 'MVE' },
    ];
    const byValue: Record<string, { value: string; label: string }> = {};
    [...fromMeta, ...extras].forEach((item: any) => {
      byValue[String(item.value)] = { value: String(item.value), label: String(item.label) };
    });
    return Object.values(byValue);
  }, [meta.data?.playbookTypes]);
  const { data: legacyData, loading: loadingLegacy, error: errorLegacy } = useQuery<AllPlaybooksData>(GET_ALL_PLAYBOOKS_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const { data: graphData, loading: loadingGraphs, error: errorGraphs } = useQuery<AllGraphsData>(GET_ALL_GRAPHS_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const { data: achData, loading: loadingACH, error: errorACH } = useQuery<AllACHAnalysesData>(GET_ALL_ACH_ANALYSES_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const { data: advopsData, loading: loadingADVOPS, error: errorADVOPS } = useQuery<AllAdvopsReportsData>(GET_ALL_ADVOPS_REPORTS_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const { data: mveData, loading: loadingMVE, error: errorMVE } = useQuery<AllMveDraftsData>(GET_ALL_MVE_DRAFTS_QUERY, {
    fetchPolicy: 'cache-first',
  });
  const { data: meData } = useQuery<MeData>(GET_ME_QUERY, { fetchPolicy: 'network-only', nextFetchPolicy: 'cache-first' });
  const [updatePlaybookStatus] = useMutation(UPDATE_PLAYBOOK_STATUS_MUTATION);
  const [updateGraphStatus] = useMutation(UPDATE_GRAPH_STATUS_MUTATION);
  const [updateACHStatus] = useMutation(UPDATE_ACH_STATUS_MUTATION);
  const [updateAdvopsStatus] = useMutation(UPDATE_ADVOPS_STATUS_MUTATION);
  const [updateMveDraftStatus] = useMutation(UPDATE_MVE_DRAFT_STATUS_MUTATION);
  interface AllTagsData { allTags: { id: string; name: string; usageCount?: number }[] }
  const [loadTags, tagsQuery] = useLazyQuery<AllTagsData>(ALL_TAGS_QUERY);
  useEffect(() => { loadTags(); }, [loadTags]);

  // --- NEW FILTER STATE ---
  const [typeFilter, setTypeFilter] = useState<string>(() => localStorage.getItem('kanban-type') || 'ALL');
  const [authorFilter, setAuthorFilter] = useState<string>(() => localStorage.getItem('kanban-author') || 'ALL');
  const [searchQuery, setSearchQuery] = useState<string>(() => localStorage.getItem('kanban-q') || '');
  // Multiple selection; empty means all statuses
  const [statusFilter, setStatusFilter] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem('kanban-statuses');
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  });
  const [tagFilter, setTagFilter] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem('kanban-ptags');
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  });

  // Persist filters to localStorage & URL query params
  useEffect(() => {
    localStorage.setItem('kanban-type', typeFilter);
    localStorage.setItem('kanban-author', authorFilter);
    localStorage.setItem('kanban-q', searchQuery);
  }, [typeFilter, authorFilter, searchQuery]);

  useEffect(() => {
    localStorage.setItem('kanban-statuses', JSON.stringify(statusFilter));
    localStorage.setItem('kanban-ptags', JSON.stringify(tagFilter));
  }, [statusFilter, tagFilter]);

  // Sync URL (shallow) when filters change
  useEffect(() => {
    const params = new URLSearchParams();
    if (typeFilter !== 'ALL') params.set('type', typeFilter);
    if (authorFilter !== 'ALL') params.set('author', authorFilter);
    if (statusFilter.length) params.set('status', statusFilter.join(','));
    if (tagFilter.length) params.set('ptags', tagFilter.join(','));
    if (searchQuery) params.set('q', searchQuery);
    const newRelativePathQuery = window.location.pathname + (params.toString() ? `?${params.toString()}` : '');
    window.history.replaceState(null, '', newRelativePathQuery);
  }, [typeFilter, authorFilter, statusFilter, tagFilter, searchQuery]);

  // On first mount, read URL params (override localStorage if present)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlType = params.get('type');
    const urlAuthor = params.get('author');
    const urlStatuses = params.get('status');
    const urlPTags = params.get('ptags');
    const urlQ = params.get('q');
    if (urlType) setTypeFilter(urlType);
    if (urlAuthor) setAuthorFilter(urlAuthor);
    if (urlStatuses) {
      const parts = urlStatuses.split(',').filter(Boolean);
      setStatusFilter(parts);
    }
    if (urlPTags) {
      const parts = urlPTags.split(',').filter(Boolean);
      setTagFilter(parts);
    }
    if (urlQ) setSearchQuery(urlQ);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onDragEnd = (result: DropResult) => {
    const { destination, source, draggableId } = result;

    // 1. Dropped outside a valid column
    if (!destination) {
      return;
    }

    // 2. Dropped in the same place
    if (
      destination.droppableId === source.droppableId &&
      destination.index === source.index
    ) {
      return;
    }

    // 3. Derive new status from destination column id
    const newStatus = destination.droppableId;
    const [kind, rawId] = draggableId.split(':');

    try {
      if (kind === 'legacy') {
        // Optimistic mutation for legacy playbooks
        updatePlaybookStatus({
          variables: { id: rawId, status: newStatus },
          optimisticResponse: {
            updatePlaybookStatus: {
              __typename: 'UpdatePlaybookStatus',
              playbook: {
                __typename: 'PlaybookType',
                id: rawId,
                status: newStatus,
                updatedAt: new Date().toISOString(),
              },
            },
          },
          update: (cache) => {
            const existing = cache.readQuery<AllPlaybooksData>({ query: GET_ALL_PLAYBOOKS_QUERY });
            if (!existing) return;
            const updated = existing.allPlaybooks.map(pb =>
              pb.id === rawId ? { ...pb, status: newStatus } : pb
            );
            cache.writeQuery<AllPlaybooksData>({
              query: GET_ALL_PLAYBOOKS_QUERY,
              data: { allPlaybooks: updated },
            });
          },
          onError: (err) => {
            // eslint-disable-next-line no-console
            console.error(err);
            message.error('Failed to update status');
          }
        });
      } else if (kind === 'graph') {
        // Optimistic mutation for v2 graphs
        updateGraphStatus({
          variables: { id: rawId, status: newStatus },
          optimisticResponse: {
            updatePlaybookGraphStatus: {
              __typename: 'UpdatePlaybookGraphStatus',
              playbookGraph: {
                __typename: 'PlaybookGraphType',
                id: rawId,
                status: newStatus,
                updatedAt: new Date().toISOString(),
              },
            },
          },
          update: (cache) => {
            const existing = cache.readQuery<AllGraphsData>({ query: GET_ALL_GRAPHS_QUERY });
            if (!existing) return;
            const updated = existing.allPlaybookGraphs.map(g =>
              g.id === rawId ? { ...g, status: newStatus } : g
            );
            cache.writeQuery<AllGraphsData>({
              query: GET_ALL_GRAPHS_QUERY,
              data: { allPlaybookGraphs: updated },
            });
          },
          onError: (err) => {
            // eslint-disable-next-line no-console
            console.error(err);
            message.error('Failed to update graph status');
          }
        });
      } else if (kind === 'ach') {
        // Optimistic mutation for ACH analyses
        updateACHStatus({
          variables: { analysisId: rawId, status: newStatus },
          optimisticResponse: {
            updateAchStatus: {
              __typename: 'UpdateACHStatus',
              analysis: {
                __typename: 'ACHAnalysisType',
                id: rawId,
                status: newStatus,
                updatedAt: new Date().toISOString(),
              },
            },
          },
          update: (cache) => {
            const existing = cache.readQuery<AllACHAnalysesData>({ query: GET_ALL_ACH_ANALYSES_QUERY });
            if (!existing) return;
            const updated = existing.achAnalyses.map(a =>
              a.id === rawId ? { ...a, status: newStatus } : a
            );
            cache.writeQuery<AllACHAnalysesData>({
              query: GET_ALL_ACH_ANALYSES_QUERY,
              data: { achAnalyses: updated },
            });
          },
          onError: (err) => {
            // eslint-disable-next-line no-console
            console.error(err);
            message.error('Failed to update ACH status');
          }
        });
      } else if (kind === 'advops') {
        // Optimistic mutation for ADVOPS reports
        updateAdvopsStatus({
          variables: { id: rawId, status: newStatus },
          optimisticResponse: {
            updateAdvopsReport: {
              __typename: 'UpdateAdvopsReport',
              report: {
                __typename: 'ADVOPSReportType',
                id: rawId,
                status: newStatus,
                updatedAt: new Date().toISOString(),
              },
            },
          },
          update: (cache) => {
            const existing = cache.readQuery<AllAdvopsReportsData>({ query: GET_ALL_ADVOPS_REPORTS_QUERY });
            if (!existing) return;
            const updated = existing.allAdvopsReports.map(r =>
              r.id === rawId ? { ...r, status: newStatus } : r
            );
            cache.writeQuery<AllAdvopsReportsData>({
              query: GET_ALL_ADVOPS_REPORTS_QUERY,
              data: { allAdvopsReports: updated },
            });
          },
          onError: (err) => {
            // eslint-disable-next-line no-console
            console.error(err);
            message.error('Failed to update ADVOPS status');
          }
        });
      } else if (kind === 'mve') {
        if (!['RESEARCH', 'APPROVED'].includes(newStatus)) {
          message.warning('MVE cards can only be moved between In Research and Approved.');
          return;
        }
        const existingDraft = (mveData?.allMveDrafts || []).find((item) => item.id === rawId);
        const mappedStatus = mapLifecycleToMveEngineStatus(newStatus, existingDraft?.status);
        if (!mappedStatus) {
          message.warning('Unsupported MVE lifecycle transition.');
          return;
        }
        updateMveDraftStatus({
          variables: { draftId: rawId, status: mappedStatus },
          optimisticResponse: {
            updateMveDraft: {
              __typename: 'UpdateMveDraft',
              mveDraft: {
                __typename: 'MveDraftType',
                id: rawId,
                status: mappedStatus,
                updatedAt: new Date().toISOString(),
              },
            },
          },
          update: (cache) => {
            const existing = cache.readQuery<AllMveDraftsData>({ query: GET_ALL_MVE_DRAFTS_QUERY });
            if (!existing) return;
            const updated = existing.allMveDrafts.map((d) =>
              d.id === rawId ? { ...d, status: mappedStatus } : d
            );
            cache.writeQuery<AllMveDraftsData>({
              query: GET_ALL_MVE_DRAFTS_QUERY,
              data: { allMveDrafts: updated },
            });
          },
          onError: (err) => {
            // eslint-disable-next-line no-console
            console.error(err);
            message.error('Failed to update MVE status');
          }
        });
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Failed to update status:', e);
      message.error('Status update error');
    }
  };

  // --- NEW DYNAMIC FILTERS ---
  const authors = useMemo(() => {
    const legacyAuthors = (legacyData?.allPlaybooks || []).map(p => p.author?.username).filter(Boolean) as string[];
    const graphAuthors = (graphData?.allPlaybookGraphs || []).map(g => g.author?.username).filter(Boolean) as string[];
    const achAuthors = (achData?.achAnalyses || []).map(a => a.owner?.username).filter(Boolean) as string[];
    const advopsAuthors = (advopsData?.allAdvopsReports || [])
      .filter(r => r && r.author) // Filter out null/undefined records
      .map(r => r.author?.username)
      .filter(Boolean) as string[];
    const mveAuthors = (mveData?.allMveDrafts || []).map(d => d.author?.username).filter(Boolean) as string[];
    const allAuthors = [...legacyAuthors, ...graphAuthors, ...achAuthors, ...advopsAuthors, ...mveAuthors];
    return Array.from(new Set(allAuthors));
  }, [legacyData, graphData, achData, advopsData, mveData]);

  const filteredPlaybooks = useMemo(() => {
    // Helper to trim text to max 8 words
    const trimToWords = (text: string, maxWords: number = 8): string => {
      if (!text) return text;
      const words = text.trim().split(/\s+/);
      if (words.length <= maxWords) return text;
      return words.slice(0, maxWords).join(' ') + '...';
    };
    
    // Exclude HUNT legacy playbooks (abandoned path)
    const legacy: PlaybookCard[] = (legacyData?.allPlaybooks || [])
      .filter(p => (p.playbookType || '').toUpperCase() !== 'HUNT')
      .map(p => ({ ...p, kind: 'legacy' as const }));
    const graphs: PlaybookCard[] = (graphData?.allPlaybookGraphs || []).map(g => ({
      id: g.id,
      title: g.title,
      status: g.status,
      playbookType: 'GRAPH',
      author: g.author,
      tags: ((g as any).tags || []).map((name: string, idx: number) => ({ id: `${g.id}-t-${idx}`, name })),
      tasks: [],
      kind: 'graph' as const,
      graphImageUrl: g.pngSnapshotUrl,
    }));
    const ach: PlaybookCard[] = (achData?.achAnalyses || []).map(a => ({
      id: a.id,
      title: a.title,
      status: (a.status || '').toUpperCase() === 'FINISHED' ? 'APPROVED' : a.status,
      playbookType: 'ACH',
      author: a.owner,
      tags: [],
      tasks: [],
      kind: 'ach' as const,
    }));
    const advops: PlaybookCard[] = (advopsData?.allAdvopsReports || []).map(r => ({
      id: r.id,
      title: trimToWords(r.hypothesis || r.huntId),
      status: r.status,
      playbookType: 'ADVOPS',
      author: r.author,
      tags: [{ id: `${r.id}-priority`, name: `Priority: ${r.priority}` }],
      tasks: [],
      kind: 'advops' as const,
    }));
    const mve: PlaybookCard[] = (mveData?.allMveDrafts || []).map(d => ({
      id: d.id,
      title: d.name,
      status: mapMveEngineStatusToLifecycle(d.status),
      mveEngineStatus: d.status,
      playbookType: 'MVE',
      author: d.author,
      tags: d.isAdvopsValidated ? [{ id: `${d.id}-advops`, name: 'AdvOps Validated' }] : [],
      tasks: [],
      kind: 'mve' as const,
    }));
    const combined = [...legacy, ...graphs, ...ach, ...advops, ...mve];
    const typeAuthorFiltered = combined.filter(playbook => {
      const typeMatch = typeFilter === 'ALL' || playbook.playbookType === typeFilter;
      const authorMatch = authorFilter === 'ALL' || playbook.author?.username === authorFilter;
      return typeMatch && authorMatch;
    });
    const tagFiltered = !tagFilter.length ? typeAuthorFiltered : typeAuthorFiltered.filter(pb => {
      if (!pb.tags || !pb.tags.length) return false;
      const set = new Set(tagFilter.map(t => t.toLowerCase()));
      return pb.tags.some(t => set.has(t.name.toLowerCase()));
    });
    const q = searchQuery.trim().toLowerCase();
    if (!q) return tagFiltered;
    return tagFiltered.filter(p => {
      const inTitle = p.title.toLowerCase().includes(q);
      const inAuthor = (p.author?.username || '').toLowerCase().includes(q);
      const inTags = (p.tags || []).some(t => t.name.toLowerCase().includes(q));
      return inTitle || inAuthor || inTags;
    });
  }, [legacyData, graphData, achData, advopsData, mveData, typeFilter, authorFilter, tagFilter, searchQuery]);

  if (loadingLegacy || loadingGraphs || loadingACH || loadingADVOPS || loadingMVE) return <p>Loading playbook board...</p>;
  if (errorLegacy || errorGraphs || errorACH || errorADVOPS || errorMVE) {
    return <p style={{ color: 'var(--hef-danger-text)' }}>Error loading playbooks.</p>;
  }
  const canDrag = ['ADMIN', 'REVIEWER'].includes(meData?.me?.role || '');
  // Use filtered list instead of all and apply status column visibility
  const allowedStatuses = statusFilter.length ? statusFilter : undefined;
  // Normalize status values to string for processing
  const boardData = processPlaybooksForBoard(filteredPlaybooks, dynamicStatuses, allowedStatuses);
  // Derived state: true only when every column is collapsed
  const allCollapsed = boardData.columnOrder.length > 0 && boardData.columnOrder.every(id => !!collapsed[id]);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>Detection Lifecycle Hub</h2>
      </div>

      {/* --- NEW FILTER BAR --- */}
      <Card size="small" styles={{ body: { padding: 16 } }} style={{ marginBottom: 16 }}>
        <Space size="large" wrap>
          <div style={{ minWidth: 220 }}>
            <Typography.Text strong>Type</Typography.Text>
            <Select
              value={typeFilter}
              onChange={setTypeFilter}
              style={{ width: '100%', marginTop: 8 }}
              options={[{ label: 'All Types', value: 'ALL' }, ...dynamicTypes.map(o => ({ label: o.label, value: o.value }))]}
            />
          </div>
          <div style={{ minWidth: 260 }}>
            <Typography.Text strong>My Tags</Typography.Text>
            <Select
              mode="multiple"
              value={tagFilter}
              onChange={setTagFilter}
              style={{ width: '100%', marginTop: 8 }}
              allowClear
              placeholder="Filter by tags"
              options={[...(tagsQuery.data?.allTags || [])]
                .sort((a: any, b: any) => (b.usageCount || 0) - (a.usageCount || 0))
                .map((t: any) => ({ label: `${t.name} ${t.usageCount ? `(${t.usageCount})` : ''}`.trim(), value: t.name }))}
            />
          </div>
          <div style={{ minWidth: 220 }}>
            <Typography.Text strong>Author</Typography.Text>
            <Select
              value={authorFilter}
              onChange={setAuthorFilter}
              style={{ width: '100%', marginTop: 8 }}
              options={[{ label: 'All Authors', value: 'ALL' }, ...authors.map(a => ({ label: a, value: a }))]}
              showSearch
              optionFilterProp="label"
            />
          </div>
          <div style={{ minWidth: 220 }}>
            <Typography.Text strong>Status</Typography.Text>
            <Select
              mode="multiple"
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: '100%', marginTop: 8 }}
              options={dynamicStatuses.map(o => ({ label: o.label, value: o.value }))}
              placeholder="All Statuses"
              allowClear
            />
          </div>
          <div style={{ minWidth: 280 }}>
            <Typography.Text strong>Search</Typography.Text>
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              allowClear
              placeholder="Search titles, authors, tags"
              style={{ width: '100%', marginTop: 8 }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Typography.Link
              style={{ fontSize: 12 }}
              onClick={() => { setTypeFilter('ALL'); setAuthorFilter('ALL'); setStatusFilter([]); setTagFilter([]); setSearchQuery(''); }}
            >
              Reset Filters
            </Typography.Link>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={dense} onChange={(e) => setDense(e.target.checked)} />
              Dense cards
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={listView} onChange={(e) => setListView(e.target.checked)} />
              List view
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <input
                type="checkbox"
                checked={allCollapsed}
                onChange={(e) => {
                  const val = e.target.checked;
                  // Toggle collapse for all lanes at once
                  const next: Record<string, boolean> = {};
                  boardData.columnOrder.forEach(id => { next[id] = val; });
                  setCollapsed(next);
                }}
              />
              Collapse all
            </label>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Typography.Text type="secondary">
              Showing {filteredPlaybooks.length} of {(legacyData?.allPlaybooks?.length ?? 0) + (graphData?.allPlaybookGraphs?.length ?? 0) + (achData?.achAnalyses?.length ?? 0) + (advopsData?.allAdvopsReports?.length ?? 0) + (mveData?.allMveDrafts?.length ?? 0)} playbooks
            </Typography.Text>
          </div>
        </Space>
      </Card>
      <div>
        <DragDropContext onDragEnd={onDragEnd}>
          {/* Responsive vertical swimlanes with sticky headers */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: (isMd && boardData.columnOrder.length > 6) ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)',
              gap: '1rem',
              padding: '1rem'
            }}
          >
          {boardData.columnOrder.map(columnId => {
            const column = boardData.columns[columnId];
            return (
              <Droppable droppableId={column.id} key={column.id}>
                {(provided) => (
                  <div
                    {...provided.droppableProps}
                    ref={provided.innerRef}
                    style={{
                      background: 'var(--hef-bg-subtle)',
                      padding: '0',
                      borderRadius: '8px',
                      minHeight: '200px',
                      minWidth: 0,
                      border: '1px solid var(--hef-border)'
                    }}
                  >
                    {/* Sticky, collapsible lane header */}
                    <div
                      style={{
                        position: 'sticky',
                        top: 0,
                        zIndex: 1,
                        background: 'var(--hef-bg-accent)',
                        borderBottom: '1px solid var(--hef-border-strong)',
                        padding: '10px 12px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderTopLeftRadius: 8,
                        borderTopRightRadius: 8
                      }}
                    >
                      <div style={{ color: 'var(--hef-text-link)', fontWeight: 700 }}>
                        {column.title} <span style={{ fontWeight: 400 }}>({column.playbooks.length})</span>
                      </div>
                      <button
                        onClick={() => setCollapsed(prev => ({ ...prev, [column.id]: !prev[column.id] }))}
                        style={{
                          fontSize: 12,
                          color: 'var(--hef-text-primary)',
                          background: 'var(--hef-bg-surface)',
                          border: '1px solid var(--hef-border)',
                          borderRadius: 6,
                          padding: '2px 8px',
                        }}
                      >
                        {collapsed[column.id] ? 'Expand' : 'Collapse'}
                      </button>
                    </div>
                    {!collapsed[column.id] && (
                      <div style={{ padding: '12px' }}>
                    {/* Icon card row: first 3 items displayed side-by-side (3 per row) */}
                    {!listView && column.playbooks.slice(0, 3).map((playbook, i) => {
                      const config = getItemConfig(playbook);
                      return (
                        <Draggable
                          key={`${playbook.kind}-${playbook.id}`}
                          draggableId={`${playbook.kind}:${playbook.id}`}
                          index={i}
                          isDragDisabled={!canDrag}
                        >
                          {(provided) => (
                            <div
                              ref={provided.innerRef}
                              {...provided.draggableProps}
                              style={{
                                ...provided.draggableProps.style,
                                display: 'inline-block',
                                width: 'calc(33.33% - 5px)',
                                verticalAlign: 'top',
                                marginRight: i < 2 ? 6 : 0,
                                marginBottom: dense ? 4 : 8,
                              }}
                            >
                              <Card
                                hoverable
                                onClick={() => setSelected(playbook)}
                                style={{
                                  borderBottom: `3px solid ${config.color}`,
                                  textAlign: 'center',
                                  boxShadow: selected?.id === playbook.id && selected?.kind === playbook.kind
                                    ? `0 0 0 2px ${config.color} inset` : undefined,
                                }}
                                styles={{ body: { padding: dense ? '6px 4px' : '10px 6px' } }}
                              >
                                <div style={{ fontSize: dense ? 18 : 24, color: 'var(--hef-text-primary)', lineHeight: 1 }}>
                                  {config.icon}
                                </div>
                                <div style={{ marginTop: dense ? 2 : 6, fontWeight: 600, fontSize: dense ? 11 : 12, lineHeight: 1.3, color: 'var(--hef-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  <Link to={config.url} style={{ color: 'var(--hef-text-primary)', textDecoration: 'none' }} title={playbook.title}>
                                    {playbook.title}
                                  </Link>
                                </div>
                                <div style={{ marginTop: 2, fontSize: 11, color: 'var(--hef-text-secondary)' }}>
                                  {config.label}
                                </div>
                                {playbook.kind === 'legacy' && (() => {
                                  const totalTasks = playbook.tasks.length;
                                  const completedTasks = playbook.tasks.filter((t) => t.status === 'DONE').length;
                                  const percent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
                                  return totalTasks > 0 ? <Progress percent={percent} size="small" style={{ marginTop: 4 }} /> : null;
                                })()}
                                {canDrag && (
                                  <span
                                    {...provided.dragHandleProps}
                                    aria-label="drag handle"
                                    title="Drag"
                                    style={{ cursor: 'grab', userSelect: 'none', fontSize: 12 }}
                                  >
                                    ⠿
                                  </span>
                                )}
                              </Card>
                            </div>
                          )}
                        </Draggable>
                      );
                    })}
                    {/* List items: items 3+ (or all items in list view) */}
                    {column.playbooks.slice(listView ? 0 : 3).map((playbook, i) => {
                      const index = (listView ? 0 : 3) + i;
                      const config = getItemConfig(playbook);
                      return (
                        <Draggable
                          key={`${playbook.kind}-${playbook.id}`}
                          draggableId={`${playbook.kind}:${playbook.id}`}
                          index={index}
                          isDragDisabled={!canDrag}
                        >
                          {(provided) => (
                            // Simple text list item
                            <div
                              ref={provided.innerRef}
                              {...provided.draggableProps}
                              onClick={() => setSelected(playbook)}
                              role="button"
                              tabIndex={0}
                              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSelected(playbook); }}
                              style={{
                                ...provided.draggableProps.style,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: dense ? '2px 6px' : '4px 8px',
                                marginBottom: dense ? 2 : 3,
                                borderBottom: `2px solid ${config.color}`,
                                background: 'transparent',
                                cursor: 'pointer',
                                minWidth: 0,
                              }}
                            >
                              <Link
                                to={config.url}
                                style={{
                                  color: 'var(--hef-text-primary)',
                                  fontWeight: 500,
                                  fontSize: dense ? 12 : 13,
                                  flex: 1,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={playbook.title}
                              >
                                {playbook.title}
                              </Link>
                              <span style={{ fontSize: 10, color: 'var(--hef-text-muted)', marginLeft: 8, whiteSpace: 'nowrap' }}>
                                {config.label}
                              </span>
                              {canDrag && (
                                <span
                                  {...provided.dragHandleProps}
                                  aria-label="drag handle"
                                  style={{ cursor: 'grab', marginLeft: 6, fontSize: 12 }}
                                >
                                  ⠿
                                </span>
                              )}
                            </div>
                          )}
                        </Draggable>
                      );
                    })}
                    {provided.placeholder}
                      </div>
                    )}
                  </div>
                )}
              </Droppable>
            );
          })}
          </div>
        </DragDropContext>
      </div>
      {/* Mobile Drawer for details */}
      {!isMd && (
        <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.title || 'Details'} width={360}>
          {!selected && <Typography.Text type="secondary">Select a card to see details</Typography.Text>}
          {selected && (
            <div>
              <div style={{ marginBottom: 8, fontSize: 13, color: 'var(--hef-text-secondary)' }}>
                {selected.playbookType} | {selected.author?.username || 'N/A'} | Status: {selected.status}
              </div>
              {selected.kind === 'graph' && selected.graphImageUrl && (
                <div style={{ marginBottom: 12 }}>
                  <img
                    src={selected.graphImageUrl}
                    alt="Graph Snapshot"
                    style={{ width: '100%', borderRadius: 4, border: '1px solid var(--hef-border)' }}
                  />
                </div>
              )}
              {selected.tags && selected.tags.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  {selected.tags.map(t => <Tag key={t.id} style={{ marginBottom: 4 }}>{t.name}</Tag>)}
                </div>
              )}
              {selected.kind === 'legacy' && selected.tasks && selected.tasks.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <Typography.Text strong>Tasks</Typography.Text>
                  <div style={{ marginTop: 6 }}>
                    <ul style={{ paddingLeft: 18, margin: 0 }}>
                      {selected.tasks.slice(0, 5).map(t => (
                        <li key={t.id} style={{ fontSize: 12 }}>{t.status}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              <Space>
                {selected.kind === 'legacy' ? (
                  <Link to={`/playbooks/detail/${selected.id}`}>Open Full Page</Link>
                ) : selected.kind === 'advops' ? (
                  <Link to={`/advops/${selected.id}`}>Open Full Page</Link>
                ) : selected.kind === 'mve' ? (
                  <Link to={`/playbooks?tab=mve`}>Open Full Page</Link>
                ) : (
                  <Link to={`/playbooks/${selected.id}`}>Open Full Page</Link>
                )}
                <Button onClick={() => setSelected(null)} size="small">Clear</Button>
              </Space>
            </div>
          )}
        </Drawer>
      )}
    </div>
  );
};
