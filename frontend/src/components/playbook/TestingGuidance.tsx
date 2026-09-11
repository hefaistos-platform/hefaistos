import React, { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import { PixelIcon } from '../ui/PixelIcon';
import SimpleMDE from 'react-simplemde-editor';
import { configureMdeInstance, MARKDOWN_EDITOR_OPTIONS } from '../../config/markdownConfig';
import "easymde/dist/easymde.min.css";

interface TestingProps {
  data: {
    testScenario: string;
    expectedOutput: string;
    techniqueId?: string; // e.g. T1003.001
  };
  onChange: (field: string, value: string) => void;
}

const TESTING_STORAGE_KEY = 'wb-testing-guidance-open';

export const TestingGuidance: React.FC<TestingProps> = ({ data, onChange }) => {
  // Persist open/closed state across page refreshes
  const [isOpen, setIsOpen] = useState<boolean>(() => localStorage.getItem(TESTING_STORAGE_KEY) === '1');

  // Local state for immediate UI updates (prevents input lag)
  const [localTestScenario, setLocalTestScenario] = useState(data.testScenario || '');
  const [localExpectedOutput, setLocalExpectedOutput] = useState(data.expectedOutput || '');
  
  // Refs to track debounce timers
  const testScenarioTimerRef = useRef<NodeJS.Timeout | null>(null);
  const expectedOutputTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Sync local state when prop changes (e.g., when loading new data)
  useEffect(() => {
    setLocalTestScenario(data.testScenario || '');
  }, [data.testScenario]);

  useEffect(() => {
    setLocalExpectedOutput(data.expectedOutput || '');
  }, [data.expectedOutput]);

  // Debounced onChange for testScenario
  const handleTestScenarioChange = useCallback((value: string) => {
    setLocalTestScenario(value);
    
    // Clear existing timer
    if (testScenarioTimerRef.current) {
      clearTimeout(testScenarioTimerRef.current);
    }
    
    // Set new timer to update parent after 300ms of no typing
    testScenarioTimerRef.current = setTimeout(() => {
      onChange('testScenario', value);
    }, 300);
  }, [onChange]);

  // Debounced onChange for expectedOutput
  const handleExpectedOutputChange = useCallback((value: string) => {
    setLocalExpectedOutput(value);
    
    // Clear existing timer
    if (expectedOutputTimerRef.current) {
      clearTimeout(expectedOutputTimerRef.current);
    }
    
    // Set new timer to update parent after 300ms of no typing
    expectedOutputTimerRef.current = setTimeout(() => {
      onChange('testExpectedOutput', value);
    }, 300);
  }, [onChange]);

  // Persist open/closed state to localStorage
  useEffect(() => {
    localStorage.setItem(TESTING_STORAGE_KEY, isOpen ? '1' : '0');
  }, [isOpen]);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (testScenarioTimerRef.current) {
        clearTimeout(testScenarioTimerRef.current);
      }
      if (expectedOutputTimerRef.current) {
        clearTimeout(expectedOutputTimerRef.current);
      }
    };
  }, []);

  type AtomicTest = {
    id: string;
    title: string;
    os: 'windows' | 'linux' | 'macos';
    description: string;
  };

  const osPreference = useMemo(() => {
    // Prefer Windows if unspecified; otherwise bias by technique hint
    if ((data.techniqueId || '').startsWith('T1')) return ['windows', 'linux', 'macos'];
    if ((data.techniqueId || '').startsWith('T2')) return ['linux', 'macos', 'windows'];
    return ['windows', 'linux', 'macos'];
  }, [data.techniqueId]);

  const atomicTests: AtomicTest[] = useMemo(() => {
    const tid = data.techniqueId || 'T1059';
    return [
      {
        id: tid,
        title: 'Browse Atomic tests for this technique',
        os: 'windows' as const,
        description: 'Open the Atomic Red Team page and choose the exact test name from the markdown file.',
      },
    ];
  }, [data.techniqueId]);

  const simulationStepsOptions = useMemo(() => ({
    ...MARKDOWN_EDITOR_OPTIONS.standard,
    placeholder: "# Example:\n1. Open PowerShell as Admin\n2. Run: sekurlsa::logonpasswords",
    status: false,
  }), []);

  const [selectedAtomicId, setSelectedAtomicId] = useState<string>(atomicTests[0]?.id || '');
  const [targetPreset, setTargetPreset] = useState<'local' | 'lab' | 'remote'>('local');
  const [customHost, setCustomHost] = useState('lab-win-01');
  const [prereqs, setPrereqs] = useState({ toolkit: false, perms: false, network: false });
  const [validation, setValidation] = useState({ executed: false, fired: false, notes: '' });
  const [atomicTestName, setAtomicTestName] = useState('');

  // Helper to generate Atomic Red Team URL
  const getAtomicUrl = (tid?: string) => {
    if (!tid) return 'https://github.com/redcanaryco/atomic-red-team/tree/master/atomics';
    return `https://github.com/redcanaryco/atomic-red-team/blob/master/atomics/${tid}/${tid}.md`;
  };

  const buildCommand = () => {
    const tid = data.techniqueId || 'TXXXX';
    const baseName = atomicTestName.trim();
    const base = baseName ? `Invoke-AtomicTest ${tid} -AtomicTestName "${baseName}"` : `Invoke-AtomicTest ${tid}`;
    if (targetPreset === 'remote' && customHost) {
      return `${base} -ComputerName ${customHost} -Cred (Get-Credential)`;
    }
    if (targetPreset === 'lab' && customHost) {
      return `${base} -ComputerName ${customHost}`;
    }
    return base;
  };

  const copyCommand = async () => {
    const cmd = buildCommand();
    try {
      await navigator.clipboard.writeText(cmd);
      alert('Command copied');
    } catch {
      alert(cmd);
    }
  };

  return (
    <div className="testing-guidance-section p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full text-xl font-bold text-hefaistos-primary flex items-center justify-between cursor-pointer"
        aria-expanded={isOpen}
      >
        <span className="flex items-center">
          <PixelIcon name="crosshair" className="w-6 h-6 mr-2" />
          Part 5: Testing & Validation
        </span>
        <span className="flex items-center gap-3">
          {data.techniqueId && (
            <a
              href={getAtomicUrl(data.techniqueId)}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-xs font-bold text-red-600 border border-red-200 bg-red-50 px-3 py-1 rounded hover:bg-red-100 flex items-center transition-colors"
            >
              <PixelIcon name="external-link" className="w-3 h-3 mr-2" />
              View Atomic Red Team ({data.techniqueId})
            </a>
          )}
          <span className="text-gray-400 text-sm">{isOpen ? '▲' : '▼'}</span>
        </span>
      </button>

      {isOpen && (
        <div className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Atomic docs + test selector (manual, authoritative) */}
        <div className="lg:col-span-1 border border-gray-200 rounded-lg p-4 bg-gray-50">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-gray-700">Atomic Red Team (authoritative)</span>
            <span className="text-[11px] text-gray-500">{data.techniqueId || 'Technique N/A'}</span>
          </div>
          <p className="text-xs text-gray-700 mb-2">
            Open the Atomic page and copy the exact <strong>AtomicTestName</strong> from the markdown before running.
          </p>
          {data.techniqueId && (
            <a
              href={getAtomicUrl(data.techniqueId)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center text-xs font-semibold text-red-600 border border-red-200 bg-red-50 px-3 py-2 rounded hover:bg-red-100"
            >
              <PixelIcon name="external-link" className="w-3 h-3 mr-2" />
              Open Atomic docs
            </a>
          )}
          <div className="mt-4">
            <label className="block text-[12px] font-semibold text-gray-700 mb-1">Atomic test name (exact)</label>
            <input
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              value={atomicTestName}
              onChange={(e) => setAtomicTestName(e.target.value)}
              placeholder="Copy the AtomicTestName from the markdown"
            />
          </div>
        </div>

        {/* Run helper + prereqs */}
        <div className="lg:col-span-1 border border-gray-200 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-gray-700">Parameterized Run Helper</span>
            <span className="text-[11px] text-gray-500">Safer execution</span>
          </div>
          <label className="block text-[12px] font-semibold text-gray-700 mb-1">Target preset</label>
          <div className="flex gap-2 mb-3">
            {['local','lab','remote'].map((p) => (
              <button
                key={p}
                onClick={() => setTargetPreset(p as any)}
                className={`px-3 py-2 rounded border text-xs font-semibold ${
                  targetPreset === p ? 'border-blue-500 text-blue-700 bg-blue-50' : 'border-gray-200 text-gray-700'
                }`}
              >
                {p === 'local' ? 'Local dev box' : p === 'lab' ? 'Test lab host' : 'Remote (WinRM/SSH)'}
              </button>
            ))}
          </div>
          {(targetPreset === 'lab' || targetPreset === 'remote') && (
            <div className="mb-3">
              <label className="block text-[12px] font-semibold text-gray-700 mb-1">Host / alias</label>
              <input
                className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                value={customHost}
                onChange={(e) => setCustomHost(e.target.value)}
                placeholder="lab-win-01"
              />
            </div>
          )}
          <div className="mb-3">
            <label className="block text-[12px] font-semibold text-gray-700 mb-1">Prerequisites</label>
            <div className="space-y-2 text-sm text-gray-700">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={prereqs.toolkit} onChange={(e) => setPrereqs({ ...prereqs, toolkit: e.target.checked })} />
                Invoke-AtomicRedTeam installed
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={prereqs.perms} onChange={(e) => setPrereqs({ ...prereqs, perms: e.target.checked })} />
                Required permissions (Admin / sudo)
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={prereqs.network} onChange={(e) => setPrereqs({ ...prereqs, network: e.target.checked })} />
                Network access to fetch payloads
              </label>
            </div>
          </div>
          <div className="border border-dashed border-gray-300 rounded p-3 bg-gray-50 text-xs font-mono text-gray-800 mb-3">
            {buildCommand()}
          </div>
          <div className="flex gap-2">
            <button className="px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded" onClick={copyCommand}>Copy command</button>
            <button className="px-4 py-2 bg-white border border-gray-300 text-xs font-semibold rounded" onClick={() => alert('Log run manually after execution')}>Log run</button>
          </div>
        </div>

        {/* Telemetry & validation log */}
        <div className="lg:col-span-1 border border-gray-200 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-gray-700">Expected Telemetry & Validation</span>
            <span className="text-[11px] text-gray-500">Bridge test ↔ detection</span>
          </div>
          <label className="block text-[12px] font-semibold text-gray-700 mb-1">Expected log output / artifact</label>
          <textarea
            className="w-full h-24 p-3 border border-gray-300 rounded text-sm font-mono bg-gray-900 text-green-400"
            placeholder='{"event_id": 1, "image": "mimikatz.exe" ...}'
            value={localExpectedOutput}
            onChange={(e) => handleExpectedOutputChange(e.target.value)}
          />
          <p className="text-[10px] text-gray-500 mt-1">Copy a sample log the rule should match.</p>

          <div className="grid grid-cols-2 gap-2 mt-3 text-sm text-gray-700">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={validation.executed} onChange={(e) => setValidation({ ...validation, executed: e.target.checked })} />
              Test executed
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={validation.fired} onChange={(e) => setValidation({ ...validation, fired: e.target.checked })} />
              Rule fired
            </label>
          </div>
          <textarea
            className="w-full h-20 mt-3 p-3 border border-gray-300 rounded text-sm"
            placeholder="Notes (artifacts observed, rule ID, correlation IDs)"
            value={validation.notes}
            onChange={(e) => setValidation({ ...validation, notes: e.target.value })}
          />
          <p className="text-[10px] text-gray-500 mt-1">Keep a quick audit trail for review.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
        {/* Left: Simulation Steps */}
        <div>
          <label className="block text-sm font-bold text-gray-700 mb-2">Simulation Steps (How to Trigger)</label>
          <SimpleMDE
            value={localTestScenario}
            onChange={handleTestScenarioChange}
            options={simulationStepsOptions}
            getMdeInstance={configureMdeInstance}
          />
          <p className="text-[10px] text-gray-400 mt-1">
            Describe the exact command or tool usage required to trip the alert.
          </p>
        </div>

        {/* Right: Expected Output (legacy entry) */}
        <div>
          <label className="block text-sm font-bold text-gray-700 mb-2">Expected Log Output / Artifact</label>
          <textarea
            className="w-full h-48 p-3 border border-gray-300 rounded text-sm font-mono bg-gray-900 text-green-400"
            placeholder='{"event_id": 1, "image": "mimikatz.exe" ...}'
            value={localExpectedOutput}
            onChange={(e) => handleExpectedOutputChange(e.target.value)}
          />
          <p className="text-[10px] text-gray-400 mt-1">Paste a sample log entry here for validation reference.</p>
        </div>
        </div>
        </div>
      )}
    </div>
  );
};
