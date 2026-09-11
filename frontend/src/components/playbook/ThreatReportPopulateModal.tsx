import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { gql } from '@apollo/client';
import { useLazyQuery, useMutation } from '@apollo/client/react';
import { message } from 'antd';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { PixelIcon } from '../ui/PixelIcon';

const START_POPULATE_WORKBENCH_FROM_THREAT_REPORT_TASK_MUTATION = gql`
  mutation StartPopulateWorkbenchFromThreatReportTask(
    $playbookId: UUID!
    $fileContent: String!
    $filename: String!
  ) {
    startPopulateWorkbenchFromThreatReportTask(
      playbookId: $playbookId
      fileContent: $fileContent
      filename: $filename
    ) {
      taskId
      success
      message
    }
  }
`;

const AI_GENERATION_TASK_STATUS_QUERY = gql`
  query AiGenerationTaskStatus($taskId: UUID!) {
    aiGenerationTaskStatus(taskId: $taskId) {
      id
      taskType
      status
      resultData
      errorMessage
      createdAt
      startedAt
      completedAt
    }
  }
`;

const LATEST_THREAT_REPORT_TASK_QUERY = gql`
  query LatestThreatReportTaskForPlaybook($playbookId: UUID!) {
    latestThreatReportTaskForPlaybook(playbookId: $playbookId) {
      id
      taskType
      status
      resultData
      errorMessage
      createdAt
      startedAt
      completedAt
    }
  }
`;

const APPLY_THREAT_REPORT_POPULATE_RESULT_MUTATION = gql`
  mutation ApplyThreatReportPopulateResult(
    $playbookId: UUID!
    $payload: JSONString!
    $mode: String!
  ) {
    applyThreatReportPopulateResult(
      playbookId: $playbookId
      payload: $payload
      mode: $mode
    ) {
      success
      message
      appliedFields
      capabilitiesAdded
    }
  }
`;

interface StartTaskResponse {
  startPopulateWorkbenchFromThreatReportTask: {
    taskId: string | null;
    success: boolean;
    message: string;
  };
}

interface StartTaskVars {
  playbookId: string;
  fileContent: string;
  filename: string;
}

interface TaskStatusResponse {
  aiGenerationTaskStatus: {
    id: string;
    taskType: string;
    status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
    resultData: string | null;
    errorMessage: string | null;
  };
}

interface LatestTaskResponse {
  latestThreatReportTaskForPlaybook: {
    id: string;
    taskType: string;
    status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
    resultData: string | null;
    errorMessage: string | null;
  } | null;
}

interface ApplyResultResponse {
  applyThreatReportPopulateResult: {
    success: boolean;
    message: string;
    appliedFields: string[];
    capabilitiesAdded: number;
  };
}

interface ApplyResultVars {
  playbookId: string;
  payload: string;
  mode: 'OVERWRITE' | 'APPEND';
}

interface StagedResult {
  parsedPayload: Record<string, unknown>;
  parseWarnings: string[];
  providerUsed: string;
  rawResponse: string;
}

interface ThreatReportPopulateModalProps {
  isOpen: boolean;
  onClose: () => void;
  playbookId: string;
  onApplied?: () => Promise<void> | void;
}

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;
const MESSAGE_KEY = 'workbench-threat-report-populate';

const normalizeKey = (value: string) => (value || '').toLowerCase().replace(/[^a-z0-9]/g, '');

const resolvePart = (source: Record<string, unknown>, aliases: string[]): Record<string, unknown> => {
  const lookup = Object.entries(source || {}).reduce<Record<string, unknown>>((acc, [key, val]) => {
    acc[normalizeKey(key)] = val;
    return acc;
  }, {});
  for (const alias of aliases) {
    const aliasKey = normalizeKey(alias);
    const direct = lookup[aliasKey];
    if (direct && typeof direct === 'object' && !Array.isArray(direct)) {
      return direct as Record<string, unknown>;
    }
    for (const [actualKey, value] of Object.entries(lookup)) {
      if (
        aliasKey &&
        (actualKey.startsWith(aliasKey) || actualKey.includes(aliasKey)) &&
        value &&
        typeof value === 'object' &&
        !Array.isArray(value)
      ) {
        return value as Record<string, unknown>;
      }
    }
  }
  return {};
};

const resolveValue = (source: Record<string, unknown>, aliases: string[]): unknown => {
  const lookup = Object.entries(source || {}).reduce<Record<string, unknown>>((acc, [key, val]) => {
    acc[normalizeKey(key)] = val;
    return acc;
  }, {});
  for (const alias of aliases) {
    const aliasKey = normalizeKey(alias);
    if (aliasKey in lookup) {
      return lookup[aliasKey];
    }
    for (const [actualKey, value] of Object.entries(lookup)) {
      if (aliasKey && (actualKey.startsWith(aliasKey) || actualKey.includes(aliasKey))) {
        return value;
      }
    }
  }
  return undefined;
};

const toPreviewText = (value: unknown, maxChars = 280): string => {
  let text = '';
  if (typeof value === 'string') {
    text = value;
  } else if (value !== null && value !== undefined) {
    try {
      text = JSON.stringify(value, null, 2);
    } catch {
      text = String(value);
    }
  }
  const normalized = text.trim();
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars).trimEnd()}...`;
};

const extractCodes = (source: unknown, regex: RegExp) => {
  const found: string[] = [];
  const walk = (node: unknown) => {
    if (!node) return;
    if (typeof node === 'string') {
      const matches = node.match(regex) || [];
      for (const raw of matches) {
        const value = raw.toUpperCase();
        if (!found.includes(value)) found.push(value);
      }
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node === 'object') {
      Object.values(node as Record<string, unknown>).forEach(walk);
    }
  };
  walk(source);
  return found;
};

const readAsDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string) || '');
    reader.onerror = () => reject(new Error('Failed to read file.'));
    reader.readAsDataURL(file);
  });

export const ThreatReportPopulateModal: React.FC<ThreatReportPopulateModalProps> = ({
  isOpen,
  onClose,
  playbookId,
  onApplied,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<'PENDING' | 'RUNNING' | null>(null);
  const [stagedResult, setStagedResult] = useState<StagedResult | null>(null);
  const [applyingMode, setApplyingMode] = useState<'OVERWRITE' | 'APPEND' | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [startTask, { loading: startingTask }] = useMutation<StartTaskResponse, StartTaskVars>(
    START_POPULATE_WORKBENCH_FROM_THREAT_REPORT_TASK_MUTATION
  );
  const [pollTaskStatus] = useLazyQuery<TaskStatusResponse>(AI_GENERATION_TASK_STATUS_QUERY, {
    fetchPolicy: 'network-only',
  });
  const [fetchLatestTask] = useLazyQuery<LatestTaskResponse>(LATEST_THREAT_REPORT_TASK_QUERY, {
    fetchPolicy: 'network-only',
  });
  const [applyResult, { loading: applying }] = useMutation<ApplyResultResponse, ApplyResultVars>(
    APPLY_THREAT_REPORT_POPULATE_RESULT_MUTATION
  );

  const clearPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const resetState = useCallback(() => {
    clearPolling();
    setSelectedFile(null);
    setTaskId(null);
    setTaskStatus(null);
    setStagedResult(null);
    setApplyingMode(null);
    message.destroy(MESSAGE_KEY);
  }, [clearPolling]);

  useEffect(() => {
    if (!isOpen) {
      resetState();
    }
  }, [isOpen, resetState]);

  useEffect(() => clearPolling, [clearPolling]);

  const stageCompletedTask = useCallback((resultData: string | null) => {
    let parsedData: Record<string, unknown> = {};
    try {
      if (resultData) {
        parsedData = JSON.parse(resultData);
      }
    } catch {
      message.error({
        content: 'AI finished, but returned malformed JSON payload.',
        key: MESSAGE_KEY,
      });
      return false;
    }
    const payload = parsedData.parsed_payload;
    if (!payload || typeof payload !== 'object') {
      message.error({
        content: 'AI finished, but returned an invalid staged payload.',
        key: MESSAGE_KEY,
      });
      return false;
    }
    setStagedResult({
      parsedPayload: payload as Record<string, unknown>,
      parseWarnings: Array.isArray(parsedData.parse_warnings)
        ? (parsedData.parse_warnings as string[])
        : [],
      providerUsed: String(parsedData.provider_used || 'AI'),
      rawResponse: String(parsedData.raw_response || ''),
    });
    message.success({
      content: 'Threat report analyzed. Review staged data and choose APPEND or OVERWRITE.',
      key: MESSAGE_KEY,
    });
    return true;
  }, []);

  useEffect(() => {
    if (!isOpen || taskId || stagedResult) return;
    let cancelled = false;

    const hydrate = async () => {
      try {
        const response = await fetchLatestTask({ variables: { playbookId } });
        if (cancelled) return;
        const task = response.data?.latestThreatReportTaskForPlaybook;
        if (!task) return;
        if (task.status === 'PENDING' || task.status === 'RUNNING') {
          setTaskId(task.id);
          setTaskStatus(task.status);
          message.loading({
            content: 'Resumed tracking existing threat-report analysis task...',
            key: MESSAGE_KEY,
            duration: 0,
          });
          return;
        }
        if (task.status === 'COMPLETED') {
          stageCompletedTask(task.resultData);
          return;
        }
        if (task.status === 'FAILED' && task.errorMessage) {
          message.error({
            content: task.errorMessage,
            key: MESSAGE_KEY,
          });
        }
      } catch {
        // ignore hydrate errors
      }
    };

    hydrate();
    return () => {
      cancelled = true;
    };
  }, [isOpen, playbookId, fetchLatestTask, stageCompletedTask, taskId, stagedResult]);

  useEffect(() => {
    if (!taskId) return;

    const poll = async () => {
      try {
        const response = await pollTaskStatus({ variables: { taskId } });
        const task = response.data?.aiGenerationTaskStatus;
        if (!task) return;
        if (task.status === 'PENDING' || task.status === 'RUNNING') {
          setTaskStatus(task.status);
        }
        if (task.status === 'FAILED') {
          clearPolling();
          setTaskId(null);
          setTaskStatus(null);
          message.error({
            content: task.errorMessage || 'Threat report analysis failed.',
            key: MESSAGE_KEY,
          });
          return;
        }
        if (task.status === 'COMPLETED') {
          clearPolling();
          setTaskId(null);
          setTaskStatus(null);
          stageCompletedTask(task.resultData);
        }
      } catch {
        // Ignore transient polling errors.
      }
    };

    poll();
    pollingRef.current = setInterval(poll, 2000);
    return clearPolling;
  }, [taskId, pollTaskStatus, clearPolling, stageCompletedTask]);

  const isBusy = startingTask || !!taskId || applying;

  const preview = useMemo(() => {
    if (!stagedResult?.parsedPayload) {
      return null;
    }
    const payload = stagedResult.parsedPayload;
    const part1 = resolvePart(payload, ['part1', 'part 1', 'detection strategy']);
    const part2 = resolvePart(payload, ['part2', 'part 2', 'deep dive']);

    const techniques = extractCodes(part1, /\bT\d{4}(?:\.\d{3})?\b/g);
    const strategyCodes = extractCodes(part1, /\bDET\d{3,}\b/g);
    const capabilityLibrary = part1['capability abstraction library'] || part1.capability_abstraction_library;
    const primaryChokePoint = extractCodes(
      resolveValue(part1, [
        'primary choke point (mitre att&ck technique)',
        'primary choke point',
      ]),
      /\bT\d{4}(?:\.\d{3})?\b/g
    )[0] || '';
    const capabilityCount = Array.isArray(capabilityLibrary)
      ? capabilityLibrary.length
      : (typeof capabilityLibrary === 'object' && capabilityLibrary
          ? Object.keys(capabilityLibrary as Record<string, unknown>).length
          : 0);
    const strategicGoal = toPreviewText(
      resolveValue(part2, ['strategic goal']),
      220
    );
    const technicalContext = toPreviewText(
      resolveValue(part2, ['technical context']),
      360
    );

    return {
      techniques,
      primaryChokePoint,
      strategyCodes,
      capabilityCount,
      strategicGoal,
      technicalContext,
    };
  }, [stagedResult]);

  const handleAnalyze = useCallback(async () => {
    if (!selectedFile) {
      message.error('Select a PDF threat report first.');
      return;
    }
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      message.error('Only PDF files are supported.');
      return;
    }
    if (selectedFile.size > MAX_FILE_SIZE_BYTES) {
      message.error('File exceeds 10 MB limit.');
      return;
    }

    setStagedResult(null);
    message.loading({
      content: 'Analyzing threat report with AI. This can take several minutes.',
      key: MESSAGE_KEY,
      duration: 0,
    });
    try {
      const fileContent = await readAsDataUrl(selectedFile);
      const response = await startTask({
        variables: {
          playbookId,
          fileContent,
          filename: selectedFile.name,
        },
      });
      const result = response.data?.startPopulateWorkbenchFromThreatReportTask;
      if (!result?.success || !result.taskId) {
        message.error({
          content: result?.message || 'Failed to queue threat report analysis.',
          key: MESSAGE_KEY,
        });
        return;
      }
      setTaskId(result.taskId);
      setTaskStatus('PENDING');
    } catch (error: any) {
      message.error({
        content: error?.message || 'Failed to start threat report analysis.',
        key: MESSAGE_KEY,
      });
    }
  }, [playbookId, selectedFile, startTask]);

  const handleApply = useCallback(async (mode: 'OVERWRITE' | 'APPEND') => {
    if (!stagedResult?.parsedPayload) return;
    setApplyingMode(mode);
    message.loading({
      content: `Applying staged payload (${mode})...`,
      key: MESSAGE_KEY,
      duration: 0,
    });
    try {
      const response = await applyResult({
        variables: {
          playbookId,
          payload: JSON.stringify(stagedResult.parsedPayload),
          mode,
        },
      });
      const result = response.data?.applyThreatReportPopulateResult;
      if (!result?.success) {
        message.error({
          content: result?.message || 'Failed to apply staged payload.',
          key: MESSAGE_KEY,
        });
        return;
      }
      const appliedCount = Array.isArray(result.appliedFields) ? result.appliedFields.length : 0;
      message.success({
        content: `${result.message} Updated ${appliedCount} field groups, added ${result.capabilitiesAdded || 0} capability abstractions.`,
        key: MESSAGE_KEY,
      });
      if (onApplied) {
        await onApplied();
      }
      onClose();
      resetState();
    } catch (error: any) {
      message.error({
        content: error?.message || 'Failed to apply staged payload.',
        key: MESSAGE_KEY,
      });
    } finally {
      setApplyingMode(null);
    }
  }, [applyResult, onApplied, onClose, playbookId, resetState, stagedResult]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!isBusy) onClose();
      }}
      disableClose={isBusy}
      title="Populate Workbench from Threat Report"
      size="2xl"
    >
      <div className="threat-report-populate space-y-4">
        <div className="rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
          <p className="font-semibold">Feature summary</p>
          <p>
            AI parses a threat report PDF and stages structured Workbench data for Detection Strategy, Capability
            Abstraction, Deep Dive, SOAR configuration, and Testing. It enforces ATT&amp;CK/DET code mapping and
            native detection engineering focus.
          </p>
        </div>

        <div className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900">
          <p className="font-semibold">Cost and compute warning</p>
          <p>
            This workflow uses a very large prompt and can be computationally intensive. It may take longer and can
            significantly increase AI usage cost.
          </p>
        </div>

        <div className="rounded border border-gray-200 bg-white p-4 space-y-3">
          <label className="block text-sm font-medium text-gray-700">Threat report PDF</label>
          <input
            type="file"
            accept=".pdf,application/pdf"
            disabled={isBusy}
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              setSelectedFile(file);
            }}
          />
          {selectedFile && (
            <div className="text-xs text-gray-600">
              Selected: <strong>{selectedFile.name}</strong> ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
            </div>
          )}
          <div className="flex gap-2">
            <Button variant="primary" onClick={handleAnalyze} disabled={!selectedFile || isBusy}>
              <PixelIcon name="zap" className="w-4 h-4 mr-1" />
              {taskId ? 'Analyzing...' : 'Analyze Threat Report'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setSelectedFile(null);
                setStagedResult(null);
              }}
              disabled={isBusy}
            >
              Clear
            </Button>
          </div>
          {taskId && (
            <div className="rounded border border-blue-300 bg-blue-50 p-2 text-xs text-blue-900">
              Status:{' '}
              {taskStatus === 'PENDING' ? 'queued for AI worker...' : 'analyzing with AI...'}
              {' '}Task ID: <span className="font-mono">{taskId}</span>
            </div>
          )}
        </div>

        {stagedResult && (
          <div className="rounded border border-green-300 bg-green-50 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-green-900">Staged AI extraction ready for review</h4>
              <span className="text-xs text-green-700">Provider: {stagedResult.providerUsed}</span>
            </div>

            {stagedResult.parseWarnings.length > 0 && (
              <div className="rounded border border-yellow-300 bg-yellow-50 p-2 text-xs text-yellow-900">
                {stagedResult.parseWarnings.join(' ')}
              </div>
            )}

            {preview && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-gray-800">
                <div className="rounded border bg-white p-2">
                  <p className="font-semibold mb-1">Primary choke point</p>
                  <p>{preview.primaryChokePoint || 'Not provided'}</p>
                </div>
                <div className="rounded border bg-white p-2">
                  <p className="font-semibold mb-1">Mapped ATT&amp;CK techniques</p>
                  <p>{preview.techniques.length ? preview.techniques.join(', ') : 'None detected'}</p>
                </div>
                <div className="rounded border bg-white p-2">
                  <p className="font-semibold mb-1">Detection strategy codes</p>
                  <p>{preview.strategyCodes.length ? preview.strategyCodes.join(', ') : 'None detected'}</p>
                </div>
                <div className="rounded border bg-white p-2">
                  <p className="font-semibold mb-1">Capability abstractions</p>
                  <p>{preview.capabilityCount}</p>
                </div>
                <div className="rounded border bg-white p-2">
                  <p className="font-semibold mb-1">Strategic goal (preview)</p>
                  <p>{preview.strategicGoal || 'Not provided'}</p>
                </div>
                <div className="rounded border bg-white p-2 md:col-span-2">
                  <p className="font-semibold mb-1">Technical context (preview)</p>
                  <p className="whitespace-pre-wrap">{preview.technicalContext || 'Not provided'}</p>
                </div>
              </div>
            )}

            <details className="rounded border bg-white p-2 text-xs">
              <summary className="cursor-pointer font-semibold">Raw AI response (truncated)</summary>
              <pre className="mt-2 whitespace-pre-wrap text-[11px] max-h-40 overflow-auto">{stagedResult.rawResponse}</pre>
            </details>

            <div className="rounded border border-orange-300 bg-orange-50 p-2 text-xs text-orange-900">
              Confirm how to apply staged data:
              <strong> APPEND</strong> merges with existing content. <strong>OVERWRITE</strong> replaces fields.
            </div>

            <div className="flex gap-2">
              <Button
                variant="primary"
                onClick={() => handleApply('APPEND')}
                disabled={applying}
              >
                {applyingMode === 'APPEND' ? 'Applying APPEND...' : 'Apply as APPEND'}
              </Button>
              <Button
                variant="danger"
                onClick={() => handleApply('OVERWRITE')}
                disabled={applying}
              >
                {applyingMode === 'OVERWRITE' ? 'Applying OVERWRITE...' : 'Apply as OVERWRITE'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
