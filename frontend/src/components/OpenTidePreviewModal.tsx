/**
 * OpenTidePreviewModal
 *
 * Full Phase 2 implementation.
 *
 * Displays AI-enriched OpenTIDE metadata before continuing to the OpenTIDE HEF publish flow.
 *
 * IMPORTANT: Detection rules (KQL, SPL, Sigma, WAZUH queries) are NEVER
 * AI-generated. Only metadata fields (response procedures, platforms, targets)
 * may be AI-enriched. The configurations block in MDR always comes
 * exclusively from the user's saved Detection Library entries.
 *
 * Async workflows:
 * Preview: startOpentidePreviewTask mutation → poll opentidePreviewStatus every 2 s
 *
 * Persistence: on open the modal auto-loads the latest completed preview for the
 * playbook so users do not need to regenerate every time.
 *
 * Editability: each YAML tab has an Edit toggle that converts the read-only
 * syntax-highlighted view into a plain textarea so users can inspect and adjust the generated bundle before publishing.
 */

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Modal,
  Tabs,
  Switch,
  Input,
  Button,
  Alert,
  Spin,
  Tag,
  Space,
  Statistic,
  Row,
  Col,
  Tooltip,
  message as antMessage,
  Typography,
} from 'antd';
import {
  RobotOutlined,
  CopyOutlined,
  ReloadOutlined,
  EditOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery } from '@apollo/client/react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import yaml from 'js-yaml';
import { useTheme } from '../context/ThemeContext';

import {
  START_OPENTIDE_PREVIEW_TASK,
  GET_OPENTIDE_PREVIEW_STATUS,
  GET_LATEST_OPENTIDE_PREVIEW,
  PreviewOpentideMetadataResult,
  OpentidePreviewTaskResult,
} from '../graphql/opentide';
import OpenTideFieldList from './OpenTideFieldList';

const { Text } = Typography;

const POLL_INTERVAL_MS = 2000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a JSON-string dict returned by the API to a YAML string. */
function jsonStringToYaml(jsonStr: string | null | undefined): string {
  if (!jsonStr) return '';
  try {
    const obj = JSON.parse(jsonStr);
    return yaml.dump(obj, { lineWidth: 120, noRefs: true });
  } catch {
    return String(jsonStr);
  }
}

// ---------------------------------------------------------------------------
// Subcomponent: YAML tab content (read-only view + optional inline editor)
// ---------------------------------------------------------------------------

interface YamlTabProps {
  yamlText: string;
  label: string;
  /** Current user-edited override value (undefined = not edited) */
  editedValue?: string;
  /** Called when the user saves an edit; undefined = editing not supported */
  onEdit?: (newYaml: string) => void;
}

const YamlTab: React.FC<YamlTabProps> = ({ yamlText, label, editedValue, onEdit }) => {
  const { resolvedTheme } = useTheme();
  const syntaxTheme = resolvedTheme === 'dark' ? vscDarkPlus : oneLight;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);

  const displayText = editedValue !== undefined ? editedValue : yamlText;

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(displayText);
      antMessage.success(`${label} YAML copied to clipboard`);
    } catch {
      antMessage.error('Failed to copy to clipboard');
    }
  }, [displayText, label]);

  const startEdit = useCallback(() => {
    setDraft(displayText);
    setParseError(null);
    setEditing(true);
  }, [displayText]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setParseError(null);
  }, []);

  const saveEdit = useCallback(() => {
    // Validate YAML syntax before saving
    try {
      const parsed = yaml.load(draft);
      if (typeof parsed !== 'object' || parsed === null) {
        setParseError('YAML must be a mapping (key: value) document.');
        return;
      }
    } catch (e: unknown) {
      setParseError(`YAML syntax error: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    onEdit?.(draft);
    setEditing(false);
    setParseError(null);
  }, [draft, onEdit]);

  const isEdited = editedValue !== undefined;

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 4, alignItems: 'center' }}>
        {isEdited && !editing && (
          <Tag color="orange" style={{ margin: 0 }}>✏️ Edited</Tag>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {onEdit && !editing && (
            <Tooltip title={isEdited ? 'Edit your changes' : 'Edit this YAML'}>
              <Button size="small" icon={<EditOutlined />} onClick={startEdit}>
                {isEdited ? 'Re-edit' : 'Edit'}
              </Button>
            </Tooltip>
          )}
          {onEdit && isEdited && !editing && (
            <Tooltip title="Discard edits and restore compiled YAML">
              {/* Empty string signals "discard" to the parent via onEdit */}
              <Button size="small" onClick={() => onEdit?.('')} danger>
                Discard Edits
              </Button>
            </Tooltip>
          )}
          {editing && (
            <>
              <Button size="small" type="primary" onClick={saveEdit}>Save</Button>
              <Button size="small" onClick={cancelEdit}>Cancel</Button>
            </>
          )}
          {!editing && (
            <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>
              Copy YAML
            </Button>
          )}
        </div>
      </div>
      {editing ? (
        <div>
          <Input.TextArea
            autoFocus
            rows={18}
            value={draft}
            onChange={(e) => { setDraft(e.target.value); setParseError(null); }}
            style={{
              fontFamily: 'monospace',
              fontSize: 11,
              background: 'var(--hef-bg-subtle)',
              color: 'var(--hef-text-primary)',
              borderColor: 'var(--hef-border)',
            }}
          />
          {parseError && (
            <Text type="danger" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
              {parseError}
            </Text>
          )}
        </div>
      ) : (
        <SyntaxHighlighter
          language="yaml"
          style={syntaxTheme}
          showLineNumbers
          wrapLines
          customStyle={{
            fontSize: 11,
            maxHeight: 400,
            overflowY: 'auto',
            borderRadius: 4,
            background: 'var(--hef-bg-subtle)',
          }}
        >
          {displayText || '# (empty)'}
        </SyntaxHighlighter>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface OpenTidePreviewModalProps {
  playbookId: string;
  visible: boolean;
  onClose: () => void;
  /**
   * Called when the user confirms commit.
   * @param useAI - Whether to apply AI metadata enrichment
   */
  onCommit: (useAI: boolean) => void;
}

export const OpenTidePreviewModal: React.FC<OpenTidePreviewModalProps> = ({
  playbookId,
  visible,
  onClose,
  onCommit,
}) => {
  // Controls
  const [useAiEnrichment, setUseAiEnrichment] = useState(false);
  const [activeTab, setActiveTab] = useState('mdr');

  // Field overrides: Map<fieldPath, JSON string value>
  const [overrides, setOverrides] = useState<Map<string, string>>(new Map());

  // Raw YAML edits: keys are 'mdr' | 'dom' | 'bdr', value is the edited YAML string.
  // Empty string means "discard edits" (reset to compiled).
  const [rawYamlEdits, setRawYamlEdits] = useState<Record<string, string>>({});


  // ---------------------------------------------------------------------------
  // Load latest persisted preview on open
  // ---------------------------------------------------------------------------
  const [hasStarted, setHasStarted] = useState(false);

  // Fetch the latest completed preview task for this playbook (runs once on open)
  const { data: latestPreviewData, loading: loadingLatest } = useQuery<{
    latestOpentidePreview: OpentidePreviewTaskResult | null;
  }>(GET_LATEST_OPENTIDE_PREVIEW, {
    variables: { playbookId },
    skip: !visible || !playbookId,
    fetchPolicy: 'network-only',
  });

  // When we get a latest preview back, pre-populate the state so users see it
  // immediately without having to click "Generate Preview".
  useEffect(() => {
    if (
      latestPreviewData?.latestOpentidePreview?.result &&
      latestPreviewData.latestOpentidePreview.status === 'COMPLETED' &&
      !hasStarted
    ) {
      setHasStarted(true);
    }
  }, [latestPreviewData, hasStarted]);

  // ---------------------------------------------------------------------------
  // Async preview state (RabbitMQ worker)
  // ---------------------------------------------------------------------------
  const [previewTaskId, setPreviewTaskId] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  // GraphQL – start preview task mutation
  const [startTask, { loading: starting }] = useMutation<{
    startOpentidePreviewTask: { taskId: string; success: boolean; message: string };
  }>(START_OPENTIDE_PREVIEW_TASK);

  // GraphQL – poll preview task status (skip until we have a previewTaskId)
  const { data: pollData, startPolling, stopPolling } = useQuery<{
    opentidePreviewStatus: OpentidePreviewTaskResult;
  }>(GET_OPENTIDE_PREVIEW_STATUS, {
    variables: { taskId: previewTaskId ?? '' },
    skip: !previewTaskId,
    fetchPolicy: 'network-only',
  });

  const taskStatus = pollData?.opentidePreviewStatus?.status;
  // Use polling result if available, otherwise fall back to the persisted latest preview
  const preview: PreviewOpentideMetadataResult | null =
    pollData?.opentidePreviewStatus?.result ??
    latestPreviewData?.latestOpentidePreview?.result ??
    null;

  // Start polling when we get a previewTaskId; stop on terminal state
  useEffect(() => {
    if (!previewTaskId) return;
    startPolling(POLL_INTERVAL_MS);
    return () => stopPolling();
  }, [previewTaskId, startPolling, stopPolling]);

  useEffect(() => {
    if (taskStatus === 'COMPLETED' || taskStatus === 'FAILED') {
      stopPolling();
      if (taskStatus === 'FAILED') {
        setTaskError(pollData?.opentidePreviewStatus?.errorMessage ?? 'Preview generation failed');
      }
    }
  }, [taskStatus, stopPolling, pollData]);

  // ---------------------------------------------------------------------------
  // Preview trigger helpers
  // ---------------------------------------------------------------------------

  // Fire a new async preview task
  const triggerTask = useCallback(
    async (aiEnrichment: boolean) => {
      setPreviewTaskId(null);
      setTaskError(null);
      // Clear raw YAML edits when regenerating so we don't keep stale edits
      setRawYamlEdits({});
      try {
        const res = await startTask({
          variables: { playbookId, useAiEnrichment: aiEnrichment, forceBdrGeneration: false },
        });
        const result = res.data?.startOpentidePreviewTask;
        if (result?.success && result?.taskId) {
          setPreviewTaskId(result.taskId);
        } else {
          setTaskError(result?.message ?? 'Failed to start preview task');
        }
      } catch (e: unknown) {
        setTaskError(e instanceof Error ? e.message : 'Failed to start preview task');
      }
    },
    [startTask, playbookId]
  );

  // Derive YAML strings (memoised)
  const mdrYaml = useMemo(() => jsonStringToYaml(preview?.mdrYaml), [preview?.mdrYaml]);
  const domYaml = useMemo(() => jsonStringToYaml(preview?.domYaml), [preview?.domYaml]);

  // Raw YAML edit handlers
  const handleYamlEdit = useCallback((key: string, newYaml: string) => {
    setRawYamlEdits((prev) => {
      if (!newYaml) {
        // Empty string signals "discard" – remove the key
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: newYaml };
    });
  }, []);

  // Overrides handlers
  const handleOverride = useCallback((fieldPath: string, jsonValue: string) => {
    setOverrides((prev) => new Map(prev).set(fieldPath, jsonValue));
  }, []);

  const handleReset = useCallback((fieldPath: string) => {
    setOverrides((prev) => {
      const next = new Map(prev);
      next.delete(fieldPath);
      return next;
    });
  }, []);

  // Reset local state when modal closes
  const handleClose = useCallback(() => {
    stopPolling();
    setOverrides(new Map());
    setRawYamlEdits({});
    setPreviewTaskId(null);
    setTaskError(null);
    setHasStarted(false);
    onClose();
  }, [onClose, stopPolling]);

  // Refresh preview (re-run async preview task with current settings)
  const handleRefresh = useCallback(() => {
    setHasStarted(true);
    triggerTask(useAiEnrichment);
  }, [triggerTask, useAiEnrichment]);

  const loading = loadingLatest || starting || taskStatus === 'PENDING' || taskStatus === 'RUNNING';
  const validationErrors = preview?.validationErrors ?? [];
  const hasValidationErrors = validationErrors.length > 0;
  const overrideCount = overrides.size;
  const yamlEditCount = Object.keys(rawYamlEdits).length;

  // Determine whether a fresh preview has been generated (vs showing persisted data)
  const showingPersistedPreview =
    hasStarted && !previewTaskId && latestPreviewData?.latestOpentidePreview?.result != null;
  // The commit button should be enabled if we have a valid preview (fresh or persisted)
  const hasPreview = preview != null;

  // Continue to the HEF publish flow in the parent workbench UI
  const handleCommit = useCallback(() => {
    if (!preview || hasValidationErrors || loading) {
      return;
    }

    onCommit(useAiEnrichment);
  }, [preview, hasValidationErrors, loading, onCommit, useAiEnrichment]);

  // Build tab items
  const tabItems = useMemo(() => {
    const items = [
      {
        key: 'mdr',
        label: `MDR${rawYamlEdits['mdr'] ? ' ✏️' : ''}`,
        children: (
          <YamlTab
            yamlText={mdrYaml}
            label="MDR"
            editedValue={rawYamlEdits['mdr']}
            onEdit={(v) => handleYamlEdit('mdr', v)}
          />
        ),
      },
      {
        key: 'dom',
        label: `DOM${rawYamlEdits['dom'] ? ' ✏️' : ''}`,
        children: (
          <YamlTab
            yamlText={domYaml}
            label="DOM"
            editedValue={rawYamlEdits['dom']}
            onEdit={(v) => handleYamlEdit('dom', v)}
          />
        ),
      },
    ];

    items.push({
      key: 'fields',
      label: `Field Details ${overrideCount > 0 ? `(${overrideCount} overridden)` : ''}`,
      children: (
        <OpenTideFieldList
          fields={preview?.fieldMetadata ?? []}
          overrides={overrides}
          onOverride={handleOverride}
          onReset={handleReset}
        />
      ),
    });

    return items;
  }, [mdrYaml, domYaml, preview, overrides, overrideCount, handleOverride, handleReset, rawYamlEdits, handleYamlEdit]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const canCommit = !hasValidationErrors && !loading && hasPreview;

  const footerContent = (
    <Space>
      <Button onClick={handleClose}>Cancel</Button>
      {yamlEditCount > 0 && (
        <Tag color="orange" style={{ lineHeight: '30px' }}>
          {yamlEditCount} YAML {yamlEditCount === 1 ? 'object' : 'objects'} edited
        </Tag>
      )}
      <Button
        type="primary"
        onClick={handleCommit}
        disabled={!canCommit}
        style={{ background: '#52c41a', borderColor: '#52c41a' }}
      >
        Continue to HEF Publish
      </Button>
    </Space>
  );

  return (
    <Modal
      open={visible}
      onCancel={handleClose}
      className="opentide-preview-modal"
      title={
        <Space>
          <span>Preview OpenTIDE Metadata</span>
          {loading && <Spin size="small" />}
        </Space>
      }
      width="90%"
      footer={footerContent}
      destroyOnClose
    >
      {/* ---- Controls row ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
          marginBottom: 12,
          padding: '8px 12px',
          background: 'var(--hef-bg-subtle)',
          border: '1px solid var(--hef-border)',
          borderRadius: 6,
        }}
      >
        <Space align="center">
          <Switch
            checked={useAiEnrichment}
            onChange={(v) => {
              setUseAiEnrichment(v);
            }}
            checkedChildren={<RobotOutlined />}
            unCheckedChildren="Off"
            disabled={loading}
          />
          <Text>AI Enrichment</Text>
        </Space>

        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={loading}
          type={hasStarted ? 'default' : 'primary'}
          style={{ marginLeft: 'auto' }}
        >
          {hasStarted ? 'Refresh' : 'Generate Preview'}
        </Button>
      </div>

      {/* ---- Preview task / enrichment errors ---- */}
      {taskError && (
        <Alert
          type="error"
          showIcon
          message="Preview generation failed"
          description={taskError}
          style={{ marginBottom: 12 }}
        />
      )}

      {/* ---- Persisted preview notice ---- */}
      {showingPersistedPreview && !taskError && (
        <Alert
          type="info"
          showIcon
          icon={<EyeOutlined />}
          message="Showing previously generated preview. Click Refresh to regenerate with current settings."
          style={{ marginBottom: 8 }}
          closable
        />
      )}

      {!loading && !taskError && preview && (
        <>
          {/* Validation status */}
          {hasValidationErrors ? (
            <Alert
              type="error"
              showIcon
              message="Validation Errors"
              description={
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {validationErrors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              }
              style={{ marginBottom: 8 }}
            />
          ) : (
            <Alert
              type="success"
              showIcon
              message="Validation Passed – all schema requirements met"
              style={{ marginBottom: 8 }}
            />
          )}

          {/* Statistics */}
          <Row gutter={16} style={{ marginBottom: 12 }}>
            <Col>
              <Statistic title="Total Fields" value={preview.totalFields ?? 0} />
            </Col>
            <Col>
              <Statistic
                title="🤖 AI-Generated"
                value={preview.aiGeneratedCount ?? 0}
                valueStyle={{ color: '#1890ff' }}
              />
            </Col>
            <Col>
              <Statistic
                title="👤 User-Provided"
                value={preview.userProvidedCount ?? 0}
                valueStyle={{ color: '#52c41a' }}
              />
            </Col>
            {overrideCount > 0 && (
              <Col>
                <Statistic
                  title="✏️ Overrides"
                  value={overrideCount}
                  valueStyle={{ color: '#fa8c16' }}
                />
              </Col>
            )}
          </Row>
        </>
      )}

      {/* ---- YAML tabs ---- */}
      {!hasStarted ? (
        loadingLatest ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin tip="Loading previous preview…" size="large" />
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--hef-text-muted)' }}>
            <ReloadOutlined style={{ fontSize: 32, marginBottom: 12, display: 'block' }} />
            <p style={{ margin: 0 }}>
              Click <strong>Generate Preview</strong> to compile the OpenTIDE metadata.
            </p>
          </div>
        )
      ) : loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin tip="Generating OpenTIDE metadata with AI…" size="large" />
        </div>
      ) : (
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          size="small"
        />
      )}
    </Modal>
  );
};

export default OpenTidePreviewModal;
