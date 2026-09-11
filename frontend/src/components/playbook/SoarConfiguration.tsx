import React, { useState, useEffect } from 'react';
import { Button } from '../ui/Button';
import { PixelIcon } from '../ui/PixelIcon';

// ──────────────────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────────────────

export interface ThreatActor {
  name: string;
  aliases?: string[];
  sighting?: string;
  references?: string[];
}

interface DownstreamCorrelationRequirements {
  correlationScope: string[];
  temporalLogic: {
    windowSize: string;
    windowUnit: 'seconds' | 'minutes' | 'hours';
    sequenceType: 'strict' | 'loose';
  };
  joinKeys: {
    requiredFields: string[];
    joinLogic: string;
  };
  stateManagement: {
    ttl: string;
    expiryCondition: string;
  };
  falsePositiveMitigation: {
    exclusionRules: string;
  };
}

interface SoarData {
    trigger: string;
    severity: string;
    enrichment: any[];
    containment: any[];
    notifications: any[];
    // OpenTide v2.1 fields
    tlpClassification?: string;
    publicReferences?: string[];
    internalReferences?: string[];
    threatActors?: ThreatActor[];
    threatSurface?: string[];
    downstreamCorrelationRequirements?: DownstreamCorrelationRequirements;
}

interface SoarProps {
  data: SoarData;
  onSave: (data: SoarData) => void;
}

// ──────────────────────────────────────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────────────────────────────────────

const TLP_OPTIONS = [
  { value: 'CLEAR', label: 'TLP:CLEAR — Public disclosure', color: 'text-gray-700 bg-gray-100' },
  { value: 'GREEN', label: 'TLP:GREEN — Community sharing', color: 'text-green-700 bg-green-100' },
  { value: 'AMBER', label: 'TLP:AMBER — Limited disclosure', color: 'text-amber-700 bg-amber-100' },
  { value: 'AMBER+STRICT', label: 'TLP:AMBER+STRICT — Organization only', color: 'text-orange-700 bg-orange-100' },
  { value: 'RED', label: 'TLP:RED — Personal for named recipients', color: 'text-red-700 bg-red-100' },
];

/** Threat surface taxonomy (mirrors SURFACE_KEYWORD_MAP in opentide_compiler.py). */
const SURFACE_TAXONOMY: { group: string; items: string[] }[] = [
  {
    group: 'Operating System',
    items: ['OS::Windows', 'OS::Linux', 'OS::macOS', 'OS::iOS', 'OS::Android'],
  },
  {
    group: 'Cloud',
    items: ['Cloud::Azure', 'Cloud::AWS', 'Cloud::GCP'],
  },
  {
    group: 'Identity',
    items: [
      'Identity::Active Directory',
      'Identity::Azure AD',
      'Identity::Okta',
      'Identity::Ping',
    ],
  },
  {
    group: 'Network',
    items: ['Network::Firewall', 'Network::VPN', 'Network::Proxy', 'Network::DNS'],
  },
  {
    group: 'Application',
    items: [
      'Application::Office 365',
      'Application::Salesforce',
      'Application::SAP',
    ],
  },
  {
    group: 'Endpoint',
    items: ['Endpoint::Workstation', 'Endpoint::Server', 'Endpoint::Mobile'],
  },
  {
    group: 'Container / Orchestration',
    items: ['Container::Kubernetes', 'Container::Docker'],
  },
];

const DEFAULT_DCR: DownstreamCorrelationRequirements = {
  correlationScope: [],
  temporalLogic: { windowSize: '', windowUnit: 'seconds', sequenceType: 'strict' },
  joinKeys: { requiredFields: [], joinLogic: '' },
  stateManagement: { ttl: '', expiryCondition: '' },
  falsePositiveMitigation: { exclusionRules: '' },
};

const normalizeSoarData = (data: SoarData): SoarData => ({
  ...data,
  downstreamCorrelationRequirements: {
    correlationScope: data.downstreamCorrelationRequirements?.correlationScope ?? [],
    temporalLogic: {
      ...DEFAULT_DCR.temporalLogic,
      ...(data.downstreamCorrelationRequirements?.temporalLogic ?? {}),
    },
    joinKeys: {
      ...DEFAULT_DCR.joinKeys,
      ...(data.downstreamCorrelationRequirements?.joinKeys ?? {}),
      requiredFields: data.downstreamCorrelationRequirements?.joinKeys?.requiredFields ?? [],
    },
    stateManagement: {
      ...DEFAULT_DCR.stateManagement,
      ...(data.downstreamCorrelationRequirements?.stateManagement ?? {}),
    },
    falsePositiveMitigation: {
      ...DEFAULT_DCR.falsePositiveMitigation,
      ...(data.downstreamCorrelationRequirements?.falsePositiveMitigation ?? {}),
    },
  },
});

// ──────────────────────────────────────────────────────────────────────────────
// Helper sub-component: collapsible section header
// ──────────────────────────────────────────────────────────────────────────────

const CollapsibleSection: React.FC<{
  title: React.ReactNode;
  defaultOpen?: boolean;
  storageKey?: string;
  children: React.ReactNode;
  badge?: string;
}> = ({ title, defaultOpen = false, storageKey, children, badge }) => {
  const [open, setOpen] = useState<boolean>(() => {
    if (storageKey) {
      const stored = localStorage.getItem(storageKey);
      if (stored !== null) return stored === '1';
    }
    return defaultOpen;
  });

  useEffect(() => {
    if (storageKey) {
      localStorage.setItem(storageKey, open ? '1' : '0');
    }
  }, [open, storageKey]);
  return (
    <div className="border rounded-lg mb-4 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="w-full flex justify-between items-center px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left font-semibold text-gray-700 transition-colors"
      >
        <span className="flex items-center gap-2">
          {title}
          {badge && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full text-xs font-bold bg-hefaistos-primary text-white">
              {badge}
            </span>
          )}
        </span>
        <span className="text-gray-400 text-sm">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-4 py-4">{children}</div>}
    </div>
  );
};

// ──────────────────────────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────────────────────────

export const SoarConfiguration: React.FC<SoarProps> = ({ data, onSave }) => {
  const [localData, setLocalData] = useState<SoarData>(() => normalizeSoarData(data));
  const [isDirty, setIsDirty] = useState(false);

  // --- Reference input state ---
  const [newPublicRef, setNewPublicRef] = useState('');
  const [newInternalRef, setNewInternalRef] = useState('');

  // --- Threat actor form state ---
  const [actorForm, setActorForm] = useState<ThreatActor>({ name: '' });
  const [actorAliasInput, setActorAliasInput] = useState('');
  const [actorRefInput, setActorRefInput] = useState('');

  // --- Threat surface custom tag input ---
  const [surfaceInput, setSurfaceInput] = useState('');

  // --- Downstream Correlation Requirements state ---
  const [joinFieldInput, setJoinFieldInput] = useState('');

  // Sync local state when prop data changes (e.g. initial load / refetch)
  useEffect(() => {
      setLocalData(normalizeSoarData(data));
  }, [data]);

  // ── Generic list helpers ──────────────────────────────────────────────────

  const updateField = (field: keyof SoarData, value: any) => {
      setLocalData(prev => ({ ...prev, [field]: value }));
      setIsDirty(true);
  };

  const dcr = localData.downstreamCorrelationRequirements ?? DEFAULT_DCR;

  const updateDCR = <K extends keyof DownstreamCorrelationRequirements>(
    subKey: K,
    value: DownstreamCorrelationRequirements[K]
  ) => {
    updateField('downstreamCorrelationRequirements', { ...dcr, [subKey]: value });
  };

  const toggleCorrelationScope = (scope: string, checked: boolean) => {
    const current = dcr.correlationScope ?? [];
    updateDCR('correlationScope', checked ? [...current, scope] : current.filter((s: string) => s !== scope));
  };

  const commitJoinField = () => {
    const val = joinFieldInput.trim();
    if (!val) return;
    updateDCR('joinKeys', {
      ...dcr.joinKeys,
      requiredFields: [...(dcr.joinKeys.requiredFields ?? []), val],
    });
    setJoinFieldInput('');
  };

  const removeJoinField = (idx: number) => {
    updateDCR('joinKeys', {
      ...dcr.joinKeys,
      requiredFields: dcr.joinKeys.requiredFields.filter((_: string, i: number) => i !== idx),
    });
  };

  const addItem = (field: keyof SoarData, template: any) => {
    const currentList = (localData[field] as any[]) || [];
    const newList = [...currentList, template];
    updateField(field, newList);
  };

  const removeItem = (field: keyof SoarData, index: number) => {
    const list = (localData[field] as any[]) || [];
    const newList = list.filter((_: any, i: number) => i !== index);
    updateField(field, newList);
  };

  const updateItem = (field: keyof SoarData, index: number, key: string, value: any) => {
    const list = [...((localData[field] as any[]) || [])];
    list[index] = { ...list[index], [key]: value };
    updateField(field, list);
  };

  // ── References helpers ────────────────────────────────────────────────────

  const addReference = (field: 'publicReferences' | 'internalReferences', value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    const current = (localData[field] as string[]) || [];
    if (!current.includes(trimmed)) {
      updateField(field, [...current, trimmed]);
    }
    if (field === 'publicReferences') setNewPublicRef('');
    else setNewInternalRef('');
  };

  const removeReference = (field: 'publicReferences' | 'internalReferences', index: number) => {
    const current = (localData[field] as string[]) || [];
    updateField(field, current.filter((_: string, i: number) => i !== index));
  };

  // ── Threat surface helpers ────────────────────────────────────────────────

  const addSurface = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    const current = localData.threatSurface || [];
    if (!current.includes(trimmed)) {
      updateField('threatSurface', [...current, trimmed]);
    }
    setSurfaceInput('');
  };

  const removeSurface = (index: number) => {
    const current = localData.threatSurface || [];
    updateField('threatSurface', current.filter((_: string, i: number) => i !== index));
  };

  // ── Threat actor helpers ──────────────────────────────────────────────────

  const commitActorAlias = () => {
    const trimmed = actorAliasInput.trim();
    if (!trimmed) return;
    setActorForm(prev => ({ ...prev, aliases: [...(prev.aliases || []), trimmed] }));
    setActorAliasInput('');
  };

  const removeActorAlias = (idx: number) => {
    setActorForm(prev => ({
      ...prev,
      aliases: (prev.aliases || []).filter((_, i) => i !== idx),
    }));
  };

  const commitActorRef = () => {
    const trimmed = actorRefInput.trim();
    if (!trimmed) return;
    setActorForm(prev => ({ ...prev, references: [...(prev.references || []), trimmed] }));
    setActorRefInput('');
  };

  const removeActorRef = (idx: number) => {
    setActorForm(prev => ({
      ...prev,
      references: (prev.references || []).filter((_, i) => i !== idx),
    }));
  };

  const addActor = () => {
    const name = actorForm.name.trim();
    if (!name) return;
    const actor: ThreatActor = { name };
    if (actorForm.aliases && actorForm.aliases.length > 0) actor.aliases = actorForm.aliases;
    if (actorForm.sighting?.trim()) actor.sighting = actorForm.sighting.trim();
    if (actorForm.references && actorForm.references.length > 0) actor.references = actorForm.references;
    const current = localData.threatActors || [];
    updateField('threatActors', [...current, actor]);
    setActorForm({ name: '' });
    setActorAliasInput('');
    setActorRefInput('');
  };

  const removeActor = (index: number) => {
    const current = localData.threatActors || [];
    updateField('threatActors', current.filter((_: ThreatActor, i: number) => i !== index));
  };

  const handleSave = () => {
      onSave(localData);
      setIsDirty(false);
  };

  const selectedTlp = TLP_OPTIONS.find(o => o.value === (localData.tlpClassification || 'AMBER'));
  const hasDownstreamData = dcr.correlationScope.length > 0
    || Boolean(dcr.temporalLogic.windowSize)
    || dcr.joinKeys.requiredFields.length > 0
    || Boolean(dcr.joinKeys.joinLogic)
    || Boolean(dcr.stateManagement.ttl)
    || Boolean(dcr.stateManagement.expiryCondition)
    || Boolean(dcr.falsePositiveMitigation.exclusionRules);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-hefaistos-primary flex items-center">
             <PixelIcon name="zap" className="w-6 h-6 mr-2" />
             Part 4: SOAR Configuration
          </h2>
          {isDirty && (
              <Button variant="primary" onClick={handleSave}>
                  Save Changes
              </Button>
          )}
      </div>

      {/* ── Section 1: Trigger & Severity ──────────────────────────────────── */}
      <CollapsibleSection title="🚨 Trigger &amp; Severity" storageKey="wb-soar-trigger">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-bold mb-1">Alert Trigger</label>
            <input className="w-full p-2 border rounded" value={localData.trigger}
                   onChange={(e) => updateField('trigger', e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-bold mb-1">Default Severity</label>
            <select className="w-full p-2 border rounded" value={localData.severity}
                   onChange={(e) => updateField('severity', e.target.value)}>
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Critical</option>
            </select>
          </div>
        </div>
      </CollapsibleSection>

      {/* ── Section 2: Enrichment Steps ────────────────────────────────────── */}
      <CollapsibleSection
        title="🔍 Enrichment Steps (Data Gathering)"
        storageKey="wb-soar-enrichment"
        badge={localData.enrichment.length > 0 ? String(localData.enrichment.length) : undefined}
      >
        <div className="flex justify-end mb-2">
          <Button variant="secondary" onClick={() => addItem('enrichment', { action: '', input: '', output: '' })}>+ Add Step</Button>
        </div>
        {localData.enrichment.map((step: any, idx: number) => (
            <div key={idx} className="flex gap-2 mb-2 items-start">
                <input className="flex-1 p-2 border rounded text-sm" placeholder="Action (e.g. Get-User)"
                       value={step.action} onChange={(e) => updateItem('enrichment', idx, 'action', e.target.value)} />
                <input className="flex-1 p-2 border rounded text-sm" placeholder="Input (e.g. event.user)"
                       value={step.input} onChange={(e) => updateItem('enrichment', idx, 'input', e.target.value)} />
                <input className="flex-1 p-2 border rounded text-sm" placeholder="Output (e.g. user.dept)"
                       value={step.output} onChange={(e) => updateItem('enrichment', idx, 'output', e.target.value)} />
                <Button variant="danger" onClick={() => removeItem('enrichment', idx)}>x</Button>
            </div>
        ))}
        {localData.enrichment.length === 0 && <p className="text-sm text-gray-400 italic">No enrichment steps defined.</p>}
      </CollapsibleSection>

      {/* ── Section 3: Containment ─────────────────────────────────────────── */}
      <CollapsibleSection
        title="🛡️ Containment (Response Actions)"
        storageKey="wb-soar-containment"
        badge={localData.containment.length > 0 ? String(localData.containment.length) : undefined}
      >
        <div className="flex justify-end mb-2">
          <Button variant="secondary" onClick={() => addItem('containment', { description: '', critical: false })}>+ Add Action</Button>
        </div>
        {localData.containment.map((step: any, idx: number) => (
            <div key={idx} className={`flex gap-2 mb-2 items-center p-2 rounded ${step.critical ? 'bg-red-50 border border-red-200' : 'bg-gray-50'}`}>
                <input className="flex-1 p-2 border rounded text-sm bg-white" placeholder="Description (e.g. Isolate Host)"
                       value={step.description} onChange={(e) => updateItem('containment', idx, 'description', e.target.value)} />
                <label className="flex items-center space-x-2 text-sm text-gray-600 px-2 cursor-pointer">
                    <input type="checkbox" checked={step.critical}
                           onChange={(e) => updateItem('containment', idx, 'critical', e.target.checked)} />
                    <span className={step.critical ? "text-red-600 font-bold" : ""}>Manual Approval?</span>
                </label>
                <Button variant="danger" onClick={() => removeItem('containment', idx)}>x</Button>
            </div>
        ))}
      </CollapsibleSection>

      {/* ── Section 4: Notifications ───────────────────────────────────────── */}
      <CollapsibleSection
        title="🔔 Notifications"
        storageKey="wb-soar-notifications"
        badge={localData.notifications.length > 0 ? String(localData.notifications.length) : undefined}
      >
        <div className="flex justify-end mb-2">
          <Button variant="secondary" onClick={() => addItem('notifications', { channel: 'Jira', target: '' })}>+ Add Alert</Button>
        </div>
        {localData.notifications.map((step: any, idx: number) => (
            <div key={idx} className="flex gap-2 mb-2 items-center">
                <select className="p-2 border rounded text-sm" value={step.channel} onChange={(e) => updateItem('notifications', idx, 'channel', e.target.value)}>
                    <option>Jira</option>
                    <option>ServiceNow</option>
                    <option>Email</option>
                    <option>Slack/Teams</option>
                </select>
                <input className="flex-1 p-2 border rounded text-sm" placeholder="Target (e.g. SOC-Queue)"
                       value={step.target} onChange={(e) => updateItem('notifications', idx, 'target', e.target.value)} />
                <Button variant="danger" onClick={() => removeItem('notifications', idx)}>x</Button>
            </div>
        ))}
      </CollapsibleSection>

      {/* ── Section 5: OpenTide Classification & References ────────────────── */}
      <CollapsibleSection title="🔒 OpenTide Classification &amp; References" storageKey="wb-soar-opentide">
        {/* TLP Classification */}
        <div className="mb-4">
          <label className="block text-sm font-bold mb-1">TLP Classification</label>
          <select
            className="w-full p-2 border rounded"
            value={localData.tlpClassification || 'AMBER'}
            onChange={(e) => updateField('tlpClassification', e.target.value)}
          >
            {TLP_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          {selectedTlp && (
            <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-semibold ${selectedTlp.color}`}>
              {selectedTlp.value}
            </span>
          )}
        </div>

        {/* Public References */}
        <div className="mb-4">
          <label className="block text-sm font-bold mb-1">Public References</label>
          <p className="text-xs text-gray-500 mb-2">URLs, research papers, blog posts used as evidence.</p>
          <div className="flex gap-2 mb-2">
            <input
              className="flex-1 p-2 border rounded text-sm"
              placeholder="https://..."
              value={newPublicRef}
              onChange={(e) => setNewPublicRef(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addReference('publicReferences', newPublicRef); } }}
            />
            <Button variant="secondary" onClick={() => addReference('publicReferences', newPublicRef)}>Add</Button>
          </div>
          {(localData.publicReferences || []).map((ref: string, idx: number) => (
            <div key={idx} className="flex items-center gap-2 mb-1 bg-gray-50 rounded p-1.5">
              <span className="flex-1 text-xs font-mono truncate text-blue-700">{ref}</span>
              <button className="text-red-400 hover:text-red-600 text-xs" onClick={() => removeReference('publicReferences', idx)}>✕</button>
            </div>
          ))}
          {(localData.publicReferences || []).length === 0 && (
            <p className="text-xs text-gray-400 italic">No public references added.</p>
          )}
        </div>

        {/* Internal References */}
        <div>
          <label className="block text-sm font-bold mb-1">Internal References</label>
          <p className="text-xs text-gray-500 mb-2">Internal ticket IDs, case numbers, or documentation links.</p>
          <div className="flex gap-2 mb-2">
            <input
              className="flex-1 p-2 border rounded text-sm"
              placeholder="JIRA-1234, CASE-5678, ..."
              value={newInternalRef}
              onChange={(e) => setNewInternalRef(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addReference('internalReferences', newInternalRef); } }}
            />
            <Button variant="secondary" onClick={() => addReference('internalReferences', newInternalRef)}>Add</Button>
          </div>
          {(localData.internalReferences || []).map((ref: string, idx: number) => (
            <div key={idx} className="flex items-center gap-2 mb-1 bg-gray-50 rounded p-1.5">
              <span className="flex-1 text-xs font-mono truncate">{ref}</span>
              <button className="text-red-400 hover:text-red-600 text-xs" onClick={() => removeReference('internalReferences', idx)}>✕</button>
            </div>
          ))}
          {(localData.internalReferences || []).length === 0 && (
            <p className="text-xs text-gray-400 italic">No internal references added.</p>
          )}
        </div>
      </CollapsibleSection>

      {/* ── Section 6: Threat Surface Taxonomy ─────────────────────────────── */}
      <CollapsibleSection
        title="🌐 Threat Surface Taxonomy"
        storageKey="wb-soar-surface"
        badge={(localData.threatSurface || []).length > 0
          ? String((localData.threatSurface || []).length)
          : undefined}
      >
        <p className="text-xs text-gray-500 mb-3">
          Specify which surfaces this threat targets. Surfaces are automatically detected from the
          technical context and can be extended or overridden here. These values populate the{' '}
          <code className="px-1 bg-gray-100 rounded">threat.surface</code> field in the TVM.
        </p>

        {/* Quick-pick grid */}
        <div className="mb-3">
          <p className="text-xs font-semibold text-gray-600 mb-2">Quick-pick from taxonomy:</p>
          <div className="space-y-2">
            {SURFACE_TAXONOMY.map(group => (
              <div key={group.group}>
                <p className="text-xs text-gray-500 font-medium mb-1">{group.group}</p>
                <div className="flex flex-wrap gap-1">
                  {group.items.map(item => {
                    const active = (localData.threatSurface || []).includes(item);
                    return (
                      <button
                        key={item}
                        type="button"
                        onClick={() => {
                          if (active) {
                            const idx = (localData.threatSurface || []).indexOf(item);
                            removeSurface(idx);
                          } else {
                            addSurface(item);
                          }
                        }}
                        className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                          active
                            ? 'bg-hefaistos-primary text-white border-hefaistos-primary'
                            : 'bg-white text-gray-600 border-gray-300 hover:border-hefaistos-primary hover:text-hefaistos-primary'
                        }`}
                      >
                        {item}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Custom surface entry */}
        <div className="flex gap-2 mb-2">
          <input
            className="flex-1 p-2 border rounded text-sm"
            placeholder="Custom surface (e.g. Database::PostgreSQL)"
            value={surfaceInput}
            onChange={(e) => setSurfaceInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addSurface(surfaceInput); } }}
          />
          <Button variant="secondary" onClick={() => addSurface(surfaceInput)}>Add</Button>
        </div>

        {/* Active surfaces */}
        {(localData.threatSurface || []).length > 0 ? (
          <div className="mt-2">
            <p className="text-xs font-semibold text-gray-600 mb-1">Active surfaces:</p>
            <div className="flex flex-wrap gap-1">
              {(localData.threatSurface || []).map((s: string, idx: number) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-50 border border-blue-200 text-xs text-blue-700"
                >
                  {s}
                  <button
                    type="button"
                    className="text-blue-400 hover:text-red-500 ml-0.5"
                    onClick={() => removeSurface(idx)}
                  >✕</button>
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-gray-400 italic mt-1">
            No surfaces selected. Surfaces will be auto-detected from the technical context.
          </p>
        )}
      </CollapsibleSection>

      {/* ── Section 7: Threat Actor Attribution ────────────────────────────── */}
      <CollapsibleSection
        title="🎭 Threat Actor Attribution"
        storageKey="wb-soar-actors"
        badge={(localData.threatActors || []).length > 0
          ? String((localData.threatActors || []).length)
          : undefined}
      >
        <p className="text-xs text-gray-500 mb-3">
          Record known threat actors that use this technique. Attribution data is written to the{' '}
          <code className="px-1 bg-gray-100 rounded">threat.actors</code> field in the TVM.
        </p>

        {/* Existing actors list */}
        {(localData.threatActors || []).length > 0 && (
          <div className="mb-4 space-y-2">
            {(localData.threatActors || []).map((actor: ThreatActor, idx: number) => (
              <div key={idx} className="bg-gray-50 border rounded p-3 text-sm relative">
                <button
                  type="button"
                  className="absolute top-2 right-2 text-red-400 hover:text-red-600 text-xs"
                  onClick={() => removeActor(idx)}
                  title="Remove actor"
                >✕</button>
                <div className="font-semibold text-gray-800">{actor.name}</div>
                {actor.aliases && actor.aliases.length > 0 && (
                  <div className="mt-0.5 text-gray-500 text-xs">
                    Aliases: {actor.aliases.join(', ')}
                  </div>
                )}
                {actor.sighting && (
                  <div className="mt-0.5 text-gray-500 text-xs">
                    Sighting: {actor.sighting}
                  </div>
                )}
                {actor.references && actor.references.length > 0 && (
                  <div className="mt-0.5 text-xs">
                    {actor.references.map((ref, rIdx) => (
                      <a
                        key={rIdx}
                        href={ref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline mr-2 font-mono"
                      >
                        [{rIdx + 1}]
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Add new actor form */}
        <div className="border rounded p-3 bg-blue-50 space-y-2">
          <p className="text-xs font-semibold text-gray-700 mb-1">Add Threat Actor</p>

          {/* Name */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              className="w-full p-1.5 border rounded text-sm"
              placeholder="e.g. APT29, Cozy Bear, Lazarus Group"
              value={actorForm.name}
              onChange={(e) => setActorForm(prev => ({ ...prev, name: e.target.value }))}
            />
          </div>

          {/* Aliases */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">Aliases</label>
            <div className="flex gap-1 mb-1">
              <input
                className="flex-1 p-1.5 border rounded text-sm"
                placeholder="Add alias and press Enter"
                value={actorAliasInput}
                onChange={(e) => setActorAliasInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commitActorAlias(); } }}
              />
              <Button variant="secondary" onClick={commitActorAlias}>+</Button>
            </div>
            <div className="flex flex-wrap gap-1">
              {(actorForm.aliases || []).map((alias, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white border text-xs text-gray-600"
                >
                  {alias}
                  <button type="button" className="text-gray-400 hover:text-red-500" onClick={() => removeActorAlias(i)}>✕</button>
                </span>
              ))}
            </div>
          </div>

          {/* Sighting */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">Sighting / Campaign</label>
            <input
              className="w-full p-1.5 border rounded text-sm"
              placeholder="e.g. SolarWinds supply chain attack"
              value={actorForm.sighting || ''}
              onChange={(e) => setActorForm(prev => ({ ...prev, sighting: e.target.value }))}
            />
          </div>

          {/* References */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">References (URLs)</label>
            <div className="flex gap-1 mb-1">
              <input
                className="flex-1 p-1.5 border rounded text-sm"
                placeholder="https://..."
                value={actorRefInput}
                onChange={(e) => setActorRefInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commitActorRef(); } }}
              />
              <Button variant="secondary" onClick={commitActorRef}>+</Button>
            </div>
            <div className="flex flex-wrap gap-1">
              {(actorForm.references || []).map((ref, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white border text-xs font-mono text-blue-600"
                >
                  {ref.length > 30 ? ref.slice(0, 30) + '…' : ref}
                  <button type="button" className="text-gray-400 hover:text-red-500" onClick={() => removeActorRef(i)}>✕</button>
                </span>
              ))}
            </div>
          </div>

          <Button variant="primary" onClick={addActor} className="w-full mt-1">
            + Add Actor
          </Button>
        </div>

        {(localData.threatActors || []).length === 0 && (
          <p className="text-xs text-gray-400 italic mt-2">No threat actors added.</p>
        )}
      </CollapsibleSection>

      <CollapsibleSection
        title="🔗 Downstream Correlation Requirements"
        storageKey="wb-soar-downstream-correlation"
        badge={hasDownstreamData ? '✓' : undefined}
      >
        <p className="text-xs text-gray-500 mb-4">
          Defines the correlation logic for detections requiring multiple events to be joined over time.
        </p>

        <div className="mb-4">
          <p className="text-sm font-semibold text-gray-700 mb-2">1. Correlation Scope</p>
          <p className="text-xs text-gray-500 mb-2">Specifies the scope in which the correlation should be evaluated.</p>
          {['Host-Based', 'Network-Wide', 'Account-Based'].map(scope => (
            <label key={scope} className="flex items-center gap-2 mb-1 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={dcr.correlationScope.includes(scope)}
                onChange={e => toggleCorrelationScope(scope, e.target.checked)}
                className="rounded"
              />
              <span>
                {scope === 'Host-Based' && 'Host-Based — correlation on a single endpoint (Source IP + Target Host)'}
                {scope === 'Network-Wide' && 'Network-Wide — tracking movement across multiple hosts'}
                {scope === 'Account-Based' && 'Account-Based — correlation across machines under a single account'}
              </span>
            </label>
          ))}
        </div>

        <div className="mb-4">
          <p className="text-sm font-semibold text-gray-700 mb-2">2. Temporal Logic</p>
          <p className="text-xs text-gray-500 mb-2">The time window within which the events must occur.</p>
          <div className="flex gap-2 mb-2 items-center">
            <label className="text-xs text-gray-600 whitespace-nowrap">Window Size:</label>
            <input
              type="number"
              min="1"
              className="w-24 p-1.5 border rounded text-sm"
              placeholder="60"
              value={dcr.temporalLogic.windowSize}
              onChange={e => updateDCR('temporalLogic', { ...dcr.temporalLogic, windowSize: e.target.value })}
            />
            <select
              className="p-1.5 border rounded text-sm"
              value={dcr.temporalLogic.windowUnit}
              onChange={e => updateDCR('temporalLogic', {
                ...dcr.temporalLogic,
                windowUnit: e.target.value as DownstreamCorrelationRequirements['temporalLogic']['windowUnit'],
              })}
            >
              <option value="seconds">seconds</option>
              <option value="minutes">minutes</option>
              <option value="hours">hours</option>
            </select>
          </div>
          <div className="flex gap-4">
            {[
              { value: 'strict', label: 'Strict Order — A must precede B' },
              { value: 'loose', label: 'Loose Order — order does not matter' },
            ].map(opt => (
              <label key={opt.value} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="sequenceType"
                  value={opt.value}
                  checked={dcr.temporalLogic.sequenceType === opt.value}
                  onChange={() => updateDCR('temporalLogic', {
                    ...dcr.temporalLogic,
                    sequenceType: opt.value as DownstreamCorrelationRequirements['temporalLogic']['sequenceType'],
                  })}
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div className="mb-4">
          <p className="text-sm font-semibold text-gray-700 mb-2">3. Join Keys</p>
          <p className="text-xs text-gray-500 mb-1">Required Fields (fields used to join events):</p>
          <div className="flex flex-wrap gap-1 mb-2">
            {dcr.joinKeys.requiredFields.map((field, i) => (
              <span key={i} className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs">
                {field}
                <button type="button" onClick={() => removeJoinField(i)} className="text-blue-500 hover:text-red-500">×</button>
              </span>
            ))}
          </div>
          <div className="flex gap-2 mb-3">
            <input
              className="flex-1 p-1.5 border rounded text-sm"
              placeholder="e.g. TargetHostName, LogonID..."
              value={joinFieldInput}
              onChange={e => setJoinFieldInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commitJoinField(); } }}
            />
            <Button variant="secondary" onClick={commitJoinField}>+</Button>
          </div>
          <p className="text-xs text-gray-500 mb-1">Join Logic:</p>
          <textarea
            className="w-full p-2 border rounded text-sm"
            rows={2}
            placeholder="e.g. Source_LogonID in Event 4624 == Target_LogonID in Event 7045"
            value={dcr.joinKeys.joinLogic}
            onChange={e => updateDCR('joinKeys', { ...dcr.joinKeys, joinLogic: e.target.value })}
          />
        </div>

        <div className="mb-4">
          <p className="text-sm font-semibold text-gray-700 mb-2">4. State Management</p>
          <p className="text-xs text-gray-500 mb-1">TTL (Time-To-Live) — how long to keep the record in memory:</p>
          <textarea
            className="w-full p-2 border rounded text-sm mb-2"
            rows={2}
            placeholder="e.g. Keep record of LogonType 3 for 5 minutes if no execution occurs"
            value={dcr.stateManagement.ttl}
            onChange={e => updateDCR('stateManagement', { ...dcr.stateManagement, ttl: e.target.value })}
          />
          <p className="text-xs text-gray-500 mb-1">Expiry Condition — what clears the state:</p>
          <textarea
            className="w-full p-2 border rounded text-sm"
            rows={2}
            placeholder="e.g. Clear after execution is detected or after TTL expires"
            value={dcr.stateManagement.expiryCondition}
            onChange={e => updateDCR('stateManagement', { ...dcr.stateManagement, expiryCondition: e.target.value })}
          />
        </div>

        <div className="mb-2">
          <p className="text-sm font-semibold text-gray-700 mb-2">5. False Positive Mitigation</p>
          <p className="text-xs text-gray-500 mb-1">Exclusion Rules — entities/processes to ignore:</p>
          <textarea
            className="w-full p-2 border rounded text-sm"
            rows={3}
            placeholder="e.g. Ignore: ServiceName = 'WMI_Monitoring_Agent'"
            value={dcr.falsePositiveMitigation.exclusionRules}
            onChange={e => updateDCR('falsePositiveMitigation', { ...dcr.falsePositiveMitigation, exclusionRules: e.target.value })}
          />
        </div>
      </CollapsibleSection>
    </div>
  );
};
