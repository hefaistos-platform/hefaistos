import React, { useEffect, useMemo, useRef, useState } from 'react';
import { gql } from '@apollo/client';
import { useLazyQuery, useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Card, Checkbox, Collapse, Empty, Form, Input, Modal, Popconfirm, Select, Space, Tag, Tooltip, Typography, message } from 'antd';
import { CloseOutlined, InfoCircleOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const CAPABILITY_ABSTRACTIONS_QUERY = gql`
  query CapabilityAbstractions($techniqueId: String, $includeBaseline: Boolean) {
    capabilityAbstractions(techniqueId: $techniqueId, includeBaseline: $includeBaseline) {
      id
      abstractionLayer
      componentArtifact
      adversaryPurpose
      commonEvasions
      expectedObservables
      applicableTelemetry
      detectionValue
      robustnessLevel
      sourceKind
      reviewStatus
      version
      organizationName
      isEditable
      isSharedBaseline
      technique {
        techniqueId
        name
      }
    }
  }
`;

const ALL_ATTACK_TECHNIQUES_QUERY = gql`
  query AllAttackTechniquesForCAL($search: String, $limit: Int) {
    allAttackTechniques(search: $search, limit: $limit) {
      id
      techniqueId
      name
    }
  }
`;

const CREATE_CAPABILITY_ABSTRACTION_MUTATION = gql`
  mutation CreateCapabilityAbstraction(
    $techniqueId: String!
    $abstractionLayer: String!
    $componentArtifact: String!
    $adversaryPurpose: String
    $commonEvasions: String
    $expectedObservables: String
    $applicableTelemetry: String
    $detectionValue: String
    $robustnessLevel: Int
    $reviewStatus: String
  ) {
    createCapabilityAbstraction(
      techniqueId: $techniqueId
      abstractionLayer: $abstractionLayer
      componentArtifact: $componentArtifact
      adversaryPurpose: $adversaryPurpose
      commonEvasions: $commonEvasions
      expectedObservables: $expectedObservables
      applicableTelemetry: $applicableTelemetry
      detectionValue: $detectionValue
      robustnessLevel: $robustnessLevel
      reviewStatus: $reviewStatus
    ) {
      capabilityAbstraction {
        id
        abstractionLayer
      }
    }
  }
`;

const UPDATE_CAPABILITY_ABSTRACTION_MUTATION = gql`
  mutation UpdateCapabilityAbstraction(
    $capabilityAbstractionId: UUID!
    $abstractionLayer: String
    $componentArtifact: String
    $adversaryPurpose: String
    $commonEvasions: String
    $expectedObservables: String
    $applicableTelemetry: String
    $detectionValue: String
    $robustnessLevel: Int
    $reviewStatus: String
  ) {
    updateCapabilityAbstraction(
      capabilityAbstractionId: $capabilityAbstractionId
      abstractionLayer: $abstractionLayer
      componentArtifact: $componentArtifact
      adversaryPurpose: $adversaryPurpose
      commonEvasions: $commonEvasions
      expectedObservables: $expectedObservables
      applicableTelemetry: $applicableTelemetry
      detectionValue: $detectionValue
      robustnessLevel: $robustnessLevel
      reviewStatus: $reviewStatus
    ) {
      capabilityAbstraction {
        id
      }
    }
  }
`;

const DELETE_CAPABILITY_ABSTRACTION_MUTATION = gql`
  mutation DeleteCapabilityAbstraction($capabilityAbstractionId: UUID!) {
    deleteCapabilityAbstraction(capabilityAbstractionId: $capabilityAbstractionId) {
      ok
    }
  }
`;

const LAYER_OPTIONS = [
  { value: 'TOOL', label: 'Tool / Binary' },
  { value: 'API_EXPORT', label: 'API / Export' },
  { value: 'COM_IPC', label: 'COM / IPC' },
  { value: 'REGISTRY_OBJECT', label: 'Registry Object' },
  { value: 'PROTOCOL', label: 'Protocol' },
  { value: 'PROCESS_BEHAVIOR', label: 'Process Behavior' },
  { value: 'NETWORK_BEHAVIOR', label: 'Network Behavior' },
];

type CapabilityAbstractionEntry = {
  id: string;
  abstractionLayer: string;
  componentArtifact: string;
  adversaryPurpose?: string;
  commonEvasions?: string;
  expectedObservables?: string;
  applicableTelemetry?: string;
  detectionValue?: string;
  robustnessLevel?: number;
  sourceKind?: string;
  reviewStatus?: string;
  version?: number;
  organizationName?: string;
  isEditable?: boolean;
  isSharedBaseline?: boolean;
  technique?: {
    techniqueId: string;
    name: string;
  };
};

type AttackTechniqueOption = {
  id: string;
  techniqueId: string;
  name: string;
};

type FormValues = {
  techniqueId?: string;
  abstractionLayer: string;
  componentArtifact: string;
  adversaryPurpose?: string;
  commonEvasions?: string;
  expectedObservables?: string;
  applicableTelemetry?: string;
  detectionValue?: string;
  robustnessLevel?: number;
  reviewStatus?: string;
};

interface CapabilityAbstractionPanelProps {
  techniqueId?: string | null;
  selectedIds: string[];
  selectedEntryObjects?: CapabilityAbstractionEntry[];
  detectionFocusLayer?: string;
  userRole: string;
  onSelectionChange: (ids: string[], focusLayer: string) => void | Promise<void>;
  highlightedEntryId?: string | null;
  onEntryHighlight?: (entryId: string | null) => void;
}

function getLayerLabel(layer: string): string {
  return LAYER_OPTIONS.find((option) => option.value === layer)?.label || layer;
}

function getRobustnessColor(level?: number): string {
  if ((level || 0) >= 5) return 'green';
  if ((level || 0) >= 4) return 'blue';
  if ((level || 0) >= 3) return 'gold';
  if ((level || 0) >= 2) return 'orange';
  return 'red';
}

export const CapabilityAbstractionPanel: React.FC<CapabilityAbstractionPanelProps> = ({
  techniqueId,
  selectedIds,
  selectedEntryObjects = [],
  detectionFocusLayer = '',
  userRole,
  onSelectionChange,
  highlightedEntryId = null,
  onEntryHighlight,
}) => {
  const [form] = Form.useForm<FormValues>();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<CapabilityAbstractionEntry | null>(null);
  const [filterTechniqueId, setFilterTechniqueId] = useState<string | undefined>(techniqueId || undefined);
  const [layerFilters, setLayerFilters] = useState<string[]>([]);
  const [reviewStatusFilters, setReviewStatusFilters] = useState<string[]>([]);
  const [nameFilter, setNameFilter] = useState('');
  const [quickSelectValue, setQuickSelectValue] = useState<string | null>(null);
  const techniqueSearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Persistent map of selected entry objects — survives filter/technique changes.
  // Seeded from selectedEntryObjects (parent query data) and augmented when the
  // user picks additional entries from the library query results.
  const [selectedEntriesMap, setSelectedEntriesMap] = useState<Map<string, CapabilityAbstractionEntry>>(
    () => new Map(selectedEntryObjects.map((e) => [e.id, e]))
  );

  const { data, refetch } = useQuery<{ capabilityAbstractions: CapabilityAbstractionEntry[] }>(
    CAPABILITY_ABSTRACTIONS_QUERY,
    {
      variables: { techniqueId: filterTechniqueId || undefined, includeBaseline: true },
      fetchPolicy: 'network-only',
    }
  );

  const [loadAttackTechniques, { data: attackTechniquesData, loading: attackTechniquesLoading, refetch: refetchAttackTechniques }] =
    useLazyQuery<{ allAttackTechniques: AttackTechniqueOption[] }>(ALL_ATTACK_TECHNIQUES_QUERY, { fetchPolicy: 'network-only' });
  const [createCapabilityAbstraction, { loading: creating }] = useMutation(CREATE_CAPABILITY_ABSTRACTION_MUTATION);
  const [updateCapabilityAbstraction, { loading: updating }] = useMutation(UPDATE_CAPABILITY_ABSTRACTION_MUTATION);
  const [deleteCapabilityAbstraction, { loading: deleting }] = useMutation(DELETE_CAPABILITY_ABSTRACTION_MUTATION);

  useEffect(() => {
    setFilterTechniqueId(techniqueId || undefined);
  }, [techniqueId]);

  useEffect(() => {
    loadAttackTechniques({ variables: { limit: 50 } });
  }, [loadAttackTechniques]);

  useEffect(() => () => {
    if (techniqueSearchTimeoutRef.current) {
      clearTimeout(techniqueSearchTimeoutRef.current);
    }
  }, []);

  const entries = useMemo(
    () => data?.capabilityAbstractions || [],
    [data?.capabilityAbstractions]
  );

  // Sync selectedEntriesMap when the parent provides updated entry objects (e.g. after
  // backend refetch) or when selectedIds changes (e.g. external deselection).
  useEffect(() => {
    setSelectedEntriesMap((prev) => {
      const next = new Map(prev);
      // Add or refresh entries provided by the parent query.
      for (const entry of selectedEntryObjects) {
        next.set(entry.id, entry);
      }
      // Remove any entry that is no longer in the canonical selectedIds list.
      for (const [id] of Array.from(next)) {
        if (!selectedIds.includes(id)) {
          next.delete(id);
        }
      }
      return next;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEntryObjects, selectedIds]);

  // When the library query returns new results, enrich selectedEntriesMap with full
  // objects for entries that are selected but were not yet in the map.
  useEffect(() => {
    setSelectedEntriesMap((prev) => {
      const next = new Map(prev);
      let changed = false;
      for (const entry of entries) {
        if (selectedIds.includes(entry.id)) {
          next.set(entry.id, entry);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries, selectedIds]);

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

  const techniqueOptions = useMemo(
    () => (attackTechniquesData?.allAttackTechniques || []).map((technique) => ({
      value: technique.techniqueId,
      label: `${technique.techniqueId}: ${technique.name}`,
    })),
    [attackTechniquesData?.allAttackTechniques]
  );

  const hasActiveFilters =
    (filterTechniqueId !== undefined && filterTechniqueId !== (techniqueId || undefined)) ||
    layerFilters.length > 0 ||
    reviewStatusFilters.length > 0 ||
    nameFilter.trim().length > 0;

  const filteredEntries = useMemo(() => {
    const alwaysVisible = new Set(selectedIds);

    if (!hasActiveFilters) {
      return entries.filter(
        (entry) =>
          alwaysVisible.has(entry.id) ||
          (techniqueId && entry.technique?.techniqueId === techniqueId)
      );
    }

    return entries.filter((entry) => {
      if (alwaysVisible.has(entry.id)) return true;
      const matchesLayer = layerFilters.length === 0 || layerFilters.includes(entry.abstractionLayer);
      const entryReviewStatus = entry.reviewStatus || 'DRAFT';
      const matchesReviewStatus =
        reviewStatusFilters.length === 0 || reviewStatusFilters.includes(entryReviewStatus);
      const matchesName =
        !nameFilter.trim() ||
        entry.componentArtifact.toLowerCase().includes(nameFilter.trim().toLowerCase());
      return matchesLayer && matchesReviewStatus && matchesName;
    });
  }, [entries, hasActiveFilters, layerFilters, reviewStatusFilters, nameFilter, techniqueId, selectedIds]);
  const selectedEntries = useMemo(
    () => selectedIds
      .map((id) => selectedEntriesMap.get(id))
      .filter((entry): entry is CapabilityAbstractionEntry => Boolean(entry)),
    [selectedEntriesMap, selectedIds]
  );
  const availableFocusLayers = useMemo(
    () => Array.from(new Set(selectedEntries.map((entry) => entry.abstractionLayer))),
    [selectedEntries]
  );

  const openCreateModal = () => {
    setEditingEntry(null);
    form.resetFields();
    form.setFieldsValue({ reviewStatus: 'DRAFT', techniqueId: techniqueId || filterTechniqueId });
    setIsModalOpen(true);
  };

  const openEditModal = (entry: CapabilityAbstractionEntry) => {
    setEditingEntry(entry);
    form.setFieldsValue({
      abstractionLayer: entry.abstractionLayer,
      componentArtifact: entry.componentArtifact,
      adversaryPurpose: entry.adversaryPurpose,
      commonEvasions: entry.commonEvasions,
      expectedObservables: entry.expectedObservables,
      applicableTelemetry: entry.applicableTelemetry,
      detectionValue: entry.detectionValue,
      robustnessLevel: entry.robustnessLevel,
      reviewStatus: entry.reviewStatus,
    });
    setIsModalOpen(true);
  };

  const handleSelection = async (ids: string[]) => {
    // Rebuild the map: keep existing known entries that are still selected, add newly
    // selected entries that can be found in the current query results.
    const nextMap = new Map(selectedEntriesMap);
    for (const entry of entries) {
      if (ids.includes(entry.id)) {
        nextMap.set(entry.id, entry);
      }
    }
    for (const [id] of Array.from(nextMap)) {
      if (!ids.includes(id)) {
        nextMap.delete(id);
      }
    }
    setSelectedEntriesMap(nextMap);

    const allSelected = Array.from(nextMap.values());
    const nextFocusLayer =
      ids.length === 0
        ? ''
        : allSelected.some((entry) => entry.abstractionLayer === detectionFocusLayer)
          ? detectionFocusLayer
          : allSelected[0]?.abstractionLayer || '';
    await onSelectionChange(ids, nextFocusLayer);
  };

  const handleLibrarySelection = async (visibleIds: string[]) => {
    const visibleEntryIds = new Set(filteredEntries.map((entry) => entry.id));
    const hiddenSelectedIds = selectedIds.filter((id) => !visibleEntryIds.has(id));
    const nextIds = Array.from(new Set([...hiddenSelectedIds, ...visibleIds]));
    await handleSelection(nextIds);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const { techniqueId: formTechniqueId, ...restValues } = values;

    if (editingEntry) {
      await updateCapabilityAbstraction({
        variables: {
          capabilityAbstractionId: editingEntry.id,
          ...restValues,
        },
      });
    } else {
      if (!formTechniqueId) {
        return;
      }
      const res = await createCapabilityAbstraction({
        variables: {
          techniqueId: formTechniqueId,
          ...restValues,
        },
      });
      const createdId = res.data?.createCapabilityAbstraction?.capabilityAbstraction?.id as string | undefined;
      const createdLayer = res.data?.createCapabilityAbstraction?.capabilityAbstraction?.abstractionLayer as string | undefined;
      if (createdId) {
        // Optimistically add the new entry to the selected entries map so it
        // appears in the selected section immediately (full data arrives after refetch).
        const optimisticEntry: CapabilityAbstractionEntry = {
          id: createdId,
          abstractionLayer: createdLayer || restValues.abstractionLayer,
          componentArtifact: restValues.componentArtifact,
          adversaryPurpose: restValues.adversaryPurpose,
          commonEvasions: restValues.commonEvasions,
          expectedObservables: restValues.expectedObservables,
          applicableTelemetry: restValues.applicableTelemetry,
          detectionValue: restValues.detectionValue,
          robustnessLevel: restValues.robustnessLevel,
          reviewStatus: restValues.reviewStatus,
          sourceKind: 'CUSTOM',
        };
        const nextMap = new Map(selectedEntriesMap);
        nextMap.set(createdId, optimisticEntry);
        setSelectedEntriesMap(nextMap);
        const nextSelected = Array.from(new Set([...selectedIds, createdId]));
        await onSelectionChange(nextSelected, detectionFocusLayer || createdLayer || restValues.abstractionLayer);
      }
    }
    await refetch();
    setIsModalOpen(false);
  };

  const handleDelete = async (entry: CapabilityAbstractionEntry) => {
    try {
      await deleteCapabilityAbstraction({
        variables: {
          capabilityAbstractionId: entry.id,
        },
      });
      // Remove the deleted entry from the persistent map and from the selection.
      const nextMap = new Map(selectedEntriesMap);
      nextMap.delete(entry.id);
      setSelectedEntriesMap(nextMap);
      const nextSelectedIds = selectedIds.filter((id) => id !== entry.id);
      const nextSelectedEntries = Array.from(nextMap.values());
      const nextFocusLayer =
        nextSelectedIds.length === 0
          ? ''
          : nextSelectedEntries.some((item) => item.abstractionLayer === detectionFocusLayer)
            ? detectionFocusLayer
            : nextSelectedEntries[0]?.abstractionLayer || '';
      await onSelectionChange(nextSelectedIds, nextFocusLayer);
      await refetch();
      message.success('Capability abstraction deleted.');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to delete capability abstraction. Please try again.');
    }
  };

  return (
    <Card className="capability-library-card" title="Capability Abstraction Library" style={{ marginTop: 16 }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="Use structured capability abstractions as grounding data for AI generation."
          description="Browse and manage capability abstractions across techniques, then choose which selected layer AI should prioritize when generating detections."
        />

        {hasActiveFilters ? (
          <Alert
            type="warning"
            showIcon
            message="Browsing the full library with active filters. Clear filters to return to workbench scope."
          />
        ) : techniqueId ? (
          <Alert
            type="info"
            showIcon
            message="Showing entries for this workbench's technique and your selected entries. Use 'Filter entries' to browse the full library."
          />
        ) : (
          <Alert
            type="info"
            showIcon
            message="No technique is set on this workbench. Showing only your selected entries. Use 'Filter entries' to browse the full library."
          />
        )}

        {/* ── Selected abstractions section ── */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Text strong>📌 Selected abstractions ({selectedIds.length})</Text>
            <Tooltip title="Selected items are saved automatically. Entries remain in the platform library even after this workbench is deleted.">
              <InfoCircleOutlined
                style={{ color: 'var(--hef-text-muted)', fontSize: 13, cursor: 'help' }}
              />
            </Tooltip>
          </div>
          {selectedIds.length === 0 ? (
            <Text type="secondary" italic>
              No items selected. Use 'Filter entries' or the selector below to add items.
            </Text>
          ) : (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {selectedEntries.map((entry) => (
                  <div
                    key={entry.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      flexWrap: 'wrap',
                      padding: '5px 10px',
                      background: 'var(--hef-bg-subtle)',
                      borderRadius: 6,
                      border: '1px solid var(--hef-border)',
                    }}
                  >
                    <Tag color="geekblue" style={{ margin: 0 }}>{getLayerLabel(entry.abstractionLayer)}</Tag>
                    <Text strong style={{ fontSize: 13 }}>{entry.componentArtifact}</Text>
                    <Tag color="blue" style={{ margin: 0 }}>{entry.technique?.techniqueId || 'Unknown'}</Tag>
                    <Tag color={getRobustnessColor(entry.robustnessLevel)} style={{ margin: 0 }}>
                      R{entry.robustnessLevel || 0}
                    </Tag>
                    <Button
                      type="text"
                      size="small"
                      icon={<CloseOutlined />}
                      style={{ marginLeft: 'auto', color: 'var(--hef-text-muted)' }}
                      title="Remove from selection"
                      onClick={() => handleSelection(selectedIds.filter((id) => id !== entry.id))}
                    />
                  </div>
                ))}
            </Space>
          )}
        </div>

        {/* ── Quick-select dropdown ── */}
        <Select
          showSearch
          allowClear
          style={{ width: '100%' }}
          placeholder="+ Add from library"
          value={quickSelectValue}
          filterOption={(input, option) =>
            (option?.label as string || '').toLowerCase().includes(input.toLowerCase())
          }
          options={entries
            .filter((e) => !selectedIds.includes(e.id))
            .map((e) => ({
              value: e.id,
              label: `${e.technique?.techniqueId || 'Unknown'} · ${e.componentArtifact} (${getLayerLabel(e.abstractionLayer)})`,
            }))}
          onChange={(value: string | null) => {
            if (value) {
              handleSelection([...selectedIds, value]);
              setQuickSelectValue(null);
            }
          }}
        />

        <Collapse
          defaultActiveKey={!techniqueId ? ['cal-entry-filters'] : []}
          items={[
            {
              key: 'cal-entry-filters',
              label: '🔍 Filter entries',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Text strong>Technique</Text>
                    <Select
                      showSearch
                      allowClear
                      filterOption={false}
                      style={{ width: '100%', marginTop: 8 }}
                      placeholder="Filter by ATT&CK technique"
                      value={filterTechniqueId}
                      options={techniqueOptions}
                      loading={attackTechniquesLoading}
                      onSearch={handleTechniqueSearch}
                      onFocus={() => loadAttackTechniques({ variables: { limit: 50 } })}
                      onChange={(value) => setFilterTechniqueId(value !== undefined ? value : (techniqueId || undefined))}
                    />
                  </div>
                  <div>
                    <Text strong>Layer</Text>
                    <Select
                      mode="multiple"
                      allowClear
                      style={{ width: '100%', marginTop: 8 }}
                      placeholder="Filter by abstraction layer"
                      value={layerFilters}
                      options={LAYER_OPTIONS}
                      onChange={setLayerFilters}
                    />
                  </div>
                  <div>
                    <Text strong>Review status</Text>
                    <Select
                      mode="multiple"
                      allowClear
                      style={{ width: '100%', marginTop: 8 }}
                      placeholder="Filter by review status"
                      value={reviewStatusFilters}
                      options={[
                        { value: 'DRAFT', label: 'Draft' },
                        { value: 'REVIEWED', label: 'Reviewed' },
                        { value: 'APPROVED', label: 'Approved' },
                      ]}
                      onChange={setReviewStatusFilters}
                    />
                  </div>
                  <div>
                    <Text strong>Name</Text>
                    <Input
                      allowClear
                      style={{ marginTop: 8 }}
                      placeholder="Search by component / artifact name"
                      value={nameFilter}
                      onChange={(e) => setNameFilter(e.target.value)}
                    />
                  </div>
                </Space>
              ),
            },
          ]}
        />

        <>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <Text type="secondary">
              Baseline entries are shared and read-only. Custom entries are organization-scoped and versioned.
            </Text>
            <button
              type="button"
              onClick={openCreateModal}
              className="px-3 py-1.5 rounded bg-purple-600 text-white text-sm hover:bg-purple-700"
            >
              Add Custom Entry
            </button>
          </div>

          <div>
            <Text strong>Detection focus layer</Text>
            <Select
              allowClear
              style={{ width: '100%', marginTop: 8 }}
              placeholder="Select the abstraction layer AI should prioritize"
              value={detectionFocusLayer || undefined}
              disabled={selectedIds.length === 0}
              options={availableFocusLayers.map((layer) => ({ value: layer, label: getLayerLabel(layer) }))}
              onChange={(value) => onSelectionChange(selectedIds, value || '')}
            />
          </div>

          {filteredEntries.length === 0 ? (
            <Empty description="No capability abstraction entries match the current filters." />
          ) : (
            <Checkbox.Group style={{ width: '100%' }} value={selectedIds} onChange={(values) => handleLibrarySelection(values as string[])}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {filteredEntries.map((entry) => (
                  <div
                    key={entry.id}
                    id={`ca-entry-${entry.id}`}
                    className={highlightedEntryId === entry.id ? 'ring-2 ring-blue-500 rounded' : ''}
                    onMouseEnter={() => onEntryHighlight?.(entry.id)}
                    onMouseLeave={() => onEntryHighlight?.(null)}
                  >
                    <Card
                      size="small"
                      styles={{ body: { padding: 16 } }}
                      extra={entry.isEditable ? (
                        <Space size="middle">
                          <button type="button" className="text-blue-600 text-sm" onClick={() => openEditModal(entry)}>
                            Edit
                          </button>
                          {userRole === 'ADMIN' && (
                            <Popconfirm
                              title="Delete capability abstraction entry?"
                              description="This action cannot be undone."
                              okText="Delete"
                              okButtonProps={{ danger: true, loading: deleting }}
                              onConfirm={() => handleDelete(entry)}
                            >
                              <button
                                type="button"
                                className="text-red-600 text-sm"
                                disabled={deleting}
                              >
                                Delete
                              </button>
                            </Popconfirm>
                          )}
                        </Space>
                      ) : undefined}
                    >
                      <div className="flex items-start gap-3">
                        <Checkbox value={entry.id} />
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <Tag color="blue">
                              {entry.technique?.techniqueId || 'Unknown'}
                              {entry.technique?.name ? ` · ${entry.technique.name.slice(0, 30)}${entry.technique.name.length > 30 ? '…' : ''}` : ''}
                            </Tag>
                            <Tag color="geekblue">{getLayerLabel(entry.abstractionLayer)}</Tag>
                            <Tag color={getRobustnessColor(entry.robustnessLevel)}>
                              Robustness {entry.robustnessLevel || 0}
                            </Tag>
                            <Tag>{entry.sourceKind === 'SEEDED' ? 'Seeded' : 'Custom'}</Tag>
                            <Tag>{entry.reviewStatus || 'DRAFT'}</Tag>
                            {entry.isSharedBaseline && <Tag color="purple">Shared baseline</Tag>}
                          </div>
                           <Paragraph strong style={{ fontSize: 16, marginBottom: 8, marginTop: 8 }}>
                            {entry.componentArtifact}
                          </Paragraph>
                          <Paragraph style={{ marginBottom: 8 }}>
                            <strong>Purpose:</strong> {entry.adversaryPurpose || 'Not specified'}
                          </Paragraph>
                          <Paragraph style={{ marginBottom: 8 }}>
                            <strong>Expected observables:</strong> {entry.expectedObservables || 'Not specified'}
                          </Paragraph>
                          <Paragraph style={{ marginBottom: 8 }}>
                            <strong>Telemetry:</strong> {entry.applicableTelemetry || 'Not specified'}
                          </Paragraph>
                          <Paragraph style={{ marginBottom: 8 }}>
                            <strong>Detection value:</strong> {entry.detectionValue || 'Not specified'}
                          </Paragraph>
                          <Paragraph style={{ marginBottom: 0 }}>
                            <strong>Evasions / variants:</strong> {entry.commonEvasions || 'Not specified'}
                          </Paragraph>
                          <Text type="secondary">Scope: {entry.organizationName} · Version {entry.version || 1}</Text>
                        </div>
                      </div>
                    </Card>
                  </div>
                ))}
              </Space>
            </Checkbox.Group>
          )}
        </>
      </Space>

      <Modal
        title={editingEntry ? 'Edit Capability Abstraction' : 'Add Capability Abstraction'}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={handleSave}
        okButtonProps={{ loading: creating || updating }}
        destroyOnClose
        className="capability-library-modal"
      >
        <Form<FormValues> form={form} layout="vertical">
          {!editingEntry && (
            <Form.Item
              name="techniqueId"
              label="ATT&CK technique"
              rules={[{ required: true, message: 'Please select an ATT&CK technique.' }]}
            >
              <Select
                showSearch
                allowClear
                filterOption={false}
                placeholder="Select ATT&CK technique"
                options={techniqueOptions}
                loading={attackTechniquesLoading}
                onSearch={handleTechniqueSearch}
                onFocus={() => loadAttackTechniques({ variables: { limit: 50 } })}
              />
            </Form.Item>
          )}
          <Form.Item name="abstractionLayer" label="Abstraction layer" rules={[{ required: true }]}>
            <Select options={LAYER_OPTIONS} />
          </Form.Item>
          <Form.Item name="componentArtifact" label="Component / artifact" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="adversaryPurpose" label="Adversary purpose">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="commonEvasions" label="Common evasions / variations">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="expectedObservables" label="Expected observables">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="applicableTelemetry" label="Applicable telemetry">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="detectionValue" label="Detection value">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="robustnessLevel" label="Robustness level">
            <Select
              options={[
                { value: 1, label: '1 - Ephemeral' },
                { value: 2, label: '2 - Tool / artifact' },
                { value: 3, label: '3 - Moderate' },
                { value: 4, label: '4 - Strong behavior' },
                { value: 5, label: '5 - Invariant / technique' },
              ]}
            />
          </Form.Item>
          <Form.Item name="reviewStatus" label="Review status">
            <Select
              options={[
                { value: 'DRAFT', label: 'Draft' },
                { value: 'REVIEWED', label: 'Reviewed' },
                { value: 'APPROVED', label: 'Approved' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};
