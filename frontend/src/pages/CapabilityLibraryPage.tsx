import React, { useEffect, useMemo, useRef, useState } from 'react';
import { gql } from '@apollo/client';
import { useLazyQuery, useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Card, Descriptions, Drawer, Empty, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useSearchParams } from 'react-router-dom';
import {
  ALL_ATTACK_TECHNIQUES_QUERY,
  AttackTechniqueOption,
  CapabilityAbstractionEntry,
  CapabilityAbstractionFormModal,
  CapabilityAbstractionFormValues,
  CREATE_CAPABILITY_ABSTRACTION_MUTATION,
  getColumnLabel,
  getLayerLabel,
  LAYER_OPTIONS,
  REVIEW_STATUS_OPTIONS,
  UPDATE_CAPABILITY_ABSTRACTION_MUTATION,
} from '../components/playbook/capabilityAbstractionShared';

const { Paragraph, Text, Title } = Typography;

const CAPABILITY_LIBRARY_PAGE_QUERY = gql`
  query CapabilityLibraryPageData {
    capabilityAbstractions(includeBaseline: true) {
      id
      abstractionLayer
      componentArtifact
      adversaryPurpose
      commonEvasions
      expectedObservables
      applicableTelemetry
      detectionValue
      robustnessLevel
      column
      sourceKind
      reviewStatus
      version
      organizationName
      isEditable
      isSharedBaseline
      createdAt
      updatedAt
      technique {
        techniqueId
        name
      }
    }
    allPlaybookGraphs {
      id
      title
      status
      selectedCapabilityAbstractions {
        id
      }
    }
  }
`;

type PlaybookUsage = {
  id: string;
  title: string;
  status: string;
  selectedCapabilityAbstractions?: Array<{ id: string }>;
};

type CapabilityLibraryPageData = {
  capabilityAbstractions: CapabilityAbstractionEntry[];
  allPlaybookGraphs: PlaybookUsage[];
};

type CapabilityLibraryRow = CapabilityAbstractionEntry & {
  usedByCount: number;
  usedByTitles: string[];
};

const SORT_OPTIONS = [
  { value: 'updated_desc', label: 'Updated (Newest first)' },
  { value: 'updated_asc', label: 'Updated (Oldest first)' },
  { value: 'name_asc', label: 'Name (A–Z)' },
  { value: 'name_desc', label: 'Name (Z–A)' },
];

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleString() : 'N/A';
}

function buildTechniqueOptions(
  entries: CapabilityAbstractionEntry[],
  attackTechniques: AttackTechniqueOption[]
): Array<{ value: string; label: string }> {
  const fromEntries = entries
    .filter((entry): entry is CapabilityAbstractionEntry & { technique: { techniqueId: string; name: string } } => Boolean(entry.technique?.techniqueId))
    .map((entry) => ({
      value: entry.technique!.techniqueId,
      label: `${entry.technique!.techniqueId}: ${entry.technique!.name}`,
    }));

  return Array.from(
    new Map(
      [...fromEntries, ...attackTechniques.map((technique) => ({
        value: technique.techniqueId,
        label: `${technique.techniqueId}: ${technique.name}`,
      }))].map((option) => [option.value, option])
    ).values()
  ).sort((a, b) => a.value.localeCompare(b.value));
}

export const CapabilityLibraryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const techniqueSearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [searchText, setSearchText] = useState(searchParams.get('search') || '');
  const [appliedSearch, setAppliedSearch] = useState(searchParams.get('search') || '');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(searchParams.get('status') || undefined);
  const [ownerFilter, setOwnerFilter] = useState<string | undefined>(searchParams.get('owner') || undefined);
  const [layerFilter, setLayerFilter] = useState<string | undefined>(searchParams.get('layer') || undefined);
  const [techniqueFilter, setTechniqueFilter] = useState<string | undefined>(searchParams.get('techniqueId') || undefined);
  const [sortBy, setSortBy] = useState(searchParams.get('sort') || 'updated_desc');
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(searchParams.get('capabilityId'));
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<CapabilityAbstractionEntry | null>(null);

  const { data, loading, error, refetch } = useQuery<CapabilityLibraryPageData>(CAPABILITY_LIBRARY_PAGE_QUERY, {
    fetchPolicy: 'network-only',
    nextFetchPolicy: 'cache-first',
  });
  const [loadAttackTechniques, { data: attackTechniquesData, loading: attackTechniquesLoading, refetch: refetchAttackTechniques }] =
    useLazyQuery<{ allAttackTechniques: AttackTechniqueOption[] }>(ALL_ATTACK_TECHNIQUES_QUERY, { fetchPolicy: 'network-only' });
  const [createCapabilityAbstraction, { loading: creating }] = useMutation(CREATE_CAPABILITY_ABSTRACTION_MUTATION);
  const [updateCapabilityAbstraction, { loading: updating }] = useMutation(UPDATE_CAPABILITY_ABSTRACTION_MUTATION);

  useEffect(() => {
    loadAttackTechniques({ variables: { limit: 50 } });
  }, [loadAttackTechniques]);

  useEffect(() => () => {
    if (techniqueSearchTimeoutRef.current) {
      clearTimeout(techniqueSearchTimeoutRef.current);
    }
  }, []);

  const handleTechniqueSearch = (search: string) => {
    if (techniqueSearchTimeoutRef.current) {
      clearTimeout(techniqueSearchTimeoutRef.current);
    }
    techniqueSearchTimeoutRef.current = setTimeout(() => {
      const variables = { search: search || undefined, limit: 50 };
      if (refetchAttackTechniques) {
        refetchAttackTechniques(variables);
      } else {
        loadAttackTechniques({ variables });
      }
    }, 250);
  };

  const entries = data?.capabilityAbstractions || [];
  const usageByCapabilityId = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const graph of data?.allPlaybookGraphs || []) {
      for (const entry of graph.selectedCapabilityAbstractions || []) {
        const next = map.get(entry.id) || [];
        next.push(graph.title || graph.id);
        map.set(entry.id, next);
      }
    }
    return map;
  }, [data?.allPlaybookGraphs]);

  const techniqueOptions = useMemo(
    () => buildTechniqueOptions(entries, attackTechniquesData?.allAttackTechniques || []),
    [attackTechniquesData?.allAttackTechniques, entries]
  );

  const ownerOptions = useMemo(
    () => Array.from(new Set(entries.map((entry) => entry.organizationName).filter(Boolean) as string[])).sort().map((value) => ({
      value,
      label: value,
    })),
    [entries]
  );

  const rows = useMemo<CapabilityLibraryRow[]>(() => {
    const normalizedSearch = appliedSearch.trim().toLowerCase();
    const result = entries
      .filter((entry) => {
        if (techniqueFilter && entry.technique?.techniqueId !== techniqueFilter) return false;
        if (statusFilter && (entry.reviewStatus || 'DRAFT') !== statusFilter) return false;
        if (ownerFilter && (entry.organizationName || 'Unknown') !== ownerFilter) return false;
        if (layerFilter && entry.abstractionLayer !== layerFilter) return false;
        if (!normalizedSearch) return true;
        const haystack = [
          entry.componentArtifact,
          entry.id,
          entry.reviewStatus,
          entry.organizationName,
          entry.technique?.techniqueId,
          entry.technique?.name,
          entry.adversaryPurpose,
          entry.commonEvasions,
          entry.expectedObservables,
          entry.applicableTelemetry,
          entry.detectionValue,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(normalizedSearch);
      })
      .map((entry) => {
        const usedByTitles = usageByCapabilityId.get(entry.id) || [];
        return {
          ...entry,
          usedByCount: usedByTitles.length,
          usedByTitles,
        };
      });

    switch (sortBy) {
      case 'updated_asc':
        result.sort((a, b) => new Date(a.updatedAt || 0).getTime() - new Date(b.updatedAt || 0).getTime());
        break;
      case 'name_asc':
        result.sort((a, b) => a.componentArtifact.localeCompare(b.componentArtifact));
        break;
      case 'name_desc':
        result.sort((a, b) => b.componentArtifact.localeCompare(a.componentArtifact));
        break;
      case 'updated_desc':
      default:
        result.sort((a, b) => new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime());
        break;
    }

    return result;
  }, [appliedSearch, entries, layerFilter, ownerFilter, sortBy, statusFilter, techniqueFilter, usageByCapabilityId]);

  const selectedEntry = useMemo(
    () => rows.find((entry) => entry.id === selectedEntryId) || entries.find((entry) => entry.id === selectedEntryId) || null,
    [entries, rows, selectedEntryId]
  );

  useEffect(() => {
    if (!selectedEntryId && rows.length > 0 && searchParams.get('capabilityId')) {
      setSelectedEntryId(searchParams.get('capabilityId'));
    }
  }, [rows, searchParams, selectedEntryId]);

  const updateParams = (updates: Record<string, string | undefined | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    });
    setSearchParams(next, { replace: true });
  };

  const openEntry = (entry: CapabilityAbstractionEntry) => {
    setSelectedEntryId(entry.id);
    updateParams({ capabilityId: entry.id });
  };

  const openCreateModal = () => {
    setEditingEntry(null);
    setIsFormOpen(true);
  };

  const openEditModal = (entry: CapabilityAbstractionEntry) => {
    setEditingEntry(entry);
    setIsFormOpen(true);
  };

  const handleSave = async (values: CapabilityAbstractionFormValues) => {
    const { techniqueId, ...restValues } = values;
    let targetId = editingEntry?.id || null;

    if (editingEntry) {
      await updateCapabilityAbstraction({
        variables: {
          capabilityAbstractionId: editingEntry.id,
          ...restValues,
        },
      });
      message.success('Capability abstraction updated.');
    } else {
      if (!techniqueId) {
        return;
      }
      const response = await createCapabilityAbstraction({
        variables: {
          techniqueId,
          ...restValues,
        },
      });
      targetId = response?.data?.createCapabilityAbstraction?.capabilityAbstraction?.id || null;
      if (techniqueId) {
        setTechniqueFilter(techniqueId);
      }
      message.success('Capability abstraction created.');
    }

    await refetch();
    setIsFormOpen(false);
    setEditingEntry(null);
    if (targetId) {
      setSelectedEntryId(targetId);
      updateParams({ capabilityId: targetId, techniqueId: techniqueId || techniqueFilter || undefined });
    }
  };

  const columns: ColumnsType<CapabilityLibraryRow> = useMemo(
    () => [
      {
        title: 'Name',
        dataIndex: 'componentArtifact',
        key: 'componentArtifact',
        render: (_value: string, row: CapabilityLibraryRow) => (
          <Space direction="vertical" size={0}>
            <Typography.Link onClick={() => openEntry(row)}>
              {row.componentArtifact}
            </Typography.Link>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {row.technique?.techniqueId || 'No technique'} · {getLayerLabel(row.abstractionLayer)}
            </Text>
          </Space>
        ),
      },
      {
        title: 'Capability ID',
        dataIndex: 'id',
        key: 'id',
        width: 220,
        render: (value: string) => <Text code>{value}</Text>,
      },
      {
        title: 'State',
        key: 'reviewStatus',
        width: 130,
        render: (_value: unknown, row: CapabilityLibraryRow) => <Tag>{row.reviewStatus || 'DRAFT'}</Tag>,
      },
      {
        title: 'Owner',
        key: 'owner',
        width: 180,
        render: (_value: unknown, row: CapabilityLibraryRow) => row.organizationName || 'Unknown',
      },
      {
        title: 'Used by',
        key: 'usedBy',
        width: 110,
        render: (_value: unknown, row: CapabilityLibraryRow) => row.usedByCount,
      },
      {
        title: 'Last updated',
        dataIndex: 'updatedAt',
        key: 'updatedAt',
        width: 210,
        render: (value?: string) => formatDate(value),
      },
    ],
    []
  );

  return (
    <div style={{ padding: '0 24px' }}>
      <Card
        title={<Title level={3} style={{ margin: 0 }}>Capability Library</Title>}
        extra={
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="Search name, ID, description, observables, telemetry…"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onSearch={(value) => {
                const nextValue = (value || '').trim();
                setAppliedSearch(nextValue);
                updateParams({ search: nextValue || null });
              }}
              style={{ width: 360 }}
            />
            <Button onClick={() => refetch()}>Refresh</Button>
            <Button type="primary" onClick={openCreateModal}>Add Capability Abstraction</Button>
          </Space>
        }
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="Focused workspace for Capability Abstraction items"
            description="This page reuses the existing Capability Abstraction schema and validation while providing a denser library view, lifecycle filters, and best-effort usage visibility."
          />

          <Space wrap size="middle" style={{ width: '100%' }}>
            <Select
              allowClear
              placeholder="Filter by lifecycle state"
              value={statusFilter}
              options={REVIEW_STATUS_OPTIONS}
              style={{ minWidth: 180 }}
              onChange={(value) => {
                setStatusFilter(value);
                updateParams({ status: value || null });
              }}
            />
            <Select
              allowClear
              placeholder="Filter by owner"
              value={ownerFilter}
              options={ownerOptions}
              style={{ minWidth: 220 }}
              onChange={(value) => {
                setOwnerFilter(value);
                updateParams({ owner: value || null });
              }}
            />
            <Select
              allowClear
              placeholder="Filter by technique"
              value={techniqueFilter}
              options={techniqueOptions}
              showSearch
              filterOption={(input, option) => String(option?.label || '').toLowerCase().includes(input.toLowerCase())}
              style={{ minWidth: 240 }}
              onChange={(value) => {
                setTechniqueFilter(value);
                updateParams({ techniqueId: value || null });
              }}
            />
            <Select
              allowClear
              placeholder="Filter by layer"
              value={layerFilter}
              options={LAYER_OPTIONS}
              style={{ minWidth: 180 }}
              onChange={(value) => {
                setLayerFilter(value);
                updateParams({ layer: value || null });
              }}
            />
            <Select
              value={sortBy}
              options={SORT_OPTIONS}
              style={{ minWidth: 220 }}
              onChange={(value) => {
                setSortBy(value);
                updateParams({ sort: value });
              }}
            />
            <Button
              onClick={() => {
                setSearchText('');
                setAppliedSearch('');
                setStatusFilter(undefined);
                setOwnerFilter(undefined);
                setLayerFilter(undefined);
                setTechniqueFilter(undefined);
                setSortBy('updated_desc');
                updateParams({
                  search: null,
                  status: null,
                  owner: null,
                  layer: null,
                  techniqueId: null,
                  sort: 'updated_desc',
                });
              }}
            >
              Clear filters
            </Button>
          </Space>

          {error && (
            <Alert
              type="error"
              showIcon
              message="Failed to load capability abstractions."
              description={error.message}
            />
          )}

          <Table<CapabilityLibraryRow>
            rowKey="id"
            columns={columns}
            dataSource={rows}
            loading={loading}
            size="small"
            pagination={{ pageSize: 20, showSizeChanger: true }}
            locale={{
              emptyText: loading ? 'Loading capability abstractions…' : <Empty description="No capability abstractions match the current filters." />,
            }}
            onRow={(row) => ({
              onClick: () => openEntry(row),
            })}
          />
        </Space>
      </Card>

      <Drawer
        title={selectedEntry?.componentArtifact || 'Capability detail'}
        open={!!selectedEntry}
        onClose={() => {
          setSelectedEntryId(null);
          updateParams({ capabilityId: null });
        }}
        width={720}
        extra={selectedEntry && (
          <Space>
            {selectedEntry.isEditable && (
              <Button type="primary" onClick={() => openEditModal(selectedEntry)}>
                Edit
              </Button>
            )}
          </Space>
        )}
      >
        {selectedEntry ? (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Space wrap>
              <Tag color="geekblue">{getLayerLabel(selectedEntry.abstractionLayer)}</Tag>
              {selectedEntry.column && <Tag color="purple">{getColumnLabel(selectedEntry.column)}</Tag>}
              <Tag>{selectedEntry.reviewStatus || 'DRAFT'}</Tag>
              <Tag>{selectedEntry.organizationName || 'Unknown'}</Tag>
              <Tag>Version {selectedEntry.version || 1}</Tag>
            </Space>

            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Capability ID">
                <Text code>{selectedEntry.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="ATT&CK technique">
                {selectedEntry.technique ? `${selectedEntry.technique.techniqueId}: ${selectedEntry.technique.name}` : 'Not specified'}
              </Descriptions.Item>
              <Descriptions.Item label="Last updated">
                {formatDate(selectedEntry.updatedAt)}
              </Descriptions.Item>
              <Descriptions.Item label="Column">
                {getColumnLabel(selectedEntry.column)}
              </Descriptions.Item>
              <Descriptions.Item label="Adversary purpose">
                {selectedEntry.adversaryPurpose || 'Not specified'}
              </Descriptions.Item>
              <Descriptions.Item label="Expected observables">
                {selectedEntry.expectedObservables || 'Not specified'}
              </Descriptions.Item>
              <Descriptions.Item label="Applicable telemetry">
                {selectedEntry.applicableTelemetry || 'Not specified'}
              </Descriptions.Item>
              <Descriptions.Item label="Detection value">
                {selectedEntry.detectionValue || 'Not specified'}
              </Descriptions.Item>
              <Descriptions.Item label="Common evasions / variations">
                {selectedEntry.commonEvasions || 'Not specified'}
              </Descriptions.Item>
            </Descriptions>

            <Card size="small" title={`Used by (${usageByCapabilityId.get(selectedEntry.id)?.length || 0})`}>
              {(usageByCapabilityId.get(selectedEntry.id) || []).length > 0 ? (
                <Space direction="vertical" size={4}>
                  {(usageByCapabilityId.get(selectedEntry.id) || []).map((title) => (
                    <Text key={title}>{title}</Text>
                  ))}
                </Space>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="No linked Workbench usage is currently visible."
                />
              )}
            </Card>

            {!selectedEntry.isEditable && (
              <Alert
                type="info"
                showIcon
                message="This entry is read-only in your current organization context."
              />
            )}
          </Space>
        ) : (
          <Paragraph type="secondary">Select a capability abstraction to inspect or edit it.</Paragraph>
        )}
      </Drawer>

      <CapabilityAbstractionFormModal
        open={isFormOpen}
        editingEntry={editingEntry}
        defaultTechniqueId={techniqueFilter}
        techniqueOptions={techniqueOptions}
        attackTechniquesLoading={attackTechniquesLoading}
        saving={creating || updating}
        onTechniqueSearch={handleTechniqueSearch}
        onTechniqueFocus={() => loadAttackTechniques({ variables: { limit: 50 } })}
        onCancel={() => {
          setIsFormOpen(false);
          setEditingEntry(null);
        }}
        onSave={handleSave}
      />
    </div>
  );
};

export default CapabilityLibraryPage;
