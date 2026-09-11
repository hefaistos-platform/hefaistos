import React, { useState } from 'react';
import { PlaybookNotes } from './PlaybookNotes';

interface SidebarProps {
  playbook: {
    customId: string;
    version: number;
    minorVersion: number;
    status: string;
    author: { username: string };
    robustnessLevel: number;
    dataSourceRobustness: string;
    selectedStrategy?: string;
    tags: string[];
    createdAt: string;
    notes?: string | null;
    nodes?: Array<{ id: string; mitreAttackMappings?: Array<{ id: string; techniqueId: string; name: string }> }>;
  };
  onUpdate: (field: string, value: any) => void;
  onUpdateNodeMappings?: (techniqueIds: string[]) => void;
  selectedNodeId?: string | null;
  canClearNotes: boolean;
  activeTab: 'DETAILS' | 'NOTES';
  onTabChange: (tab: 'DETAILS' | 'NOTES') => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

export const PlaybookSidebar: React.FC<SidebarProps> = ({
  playbook,
  onUpdate,
  onUpdateNodeMappings,
  selectedNodeId,
  canClearNotes,
  activeTab,
  onTabChange,
  collapsed,
  onCollapsedChange,
}) => {
    // Local state for the tag input field
    const [tagInput, setTagInput] = useState("");
  
    // Handler: Add Tag
    const handleAddTag = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && tagInput.trim()) {
            e.preventDefault();
            const newTag = tagInput.trim().toLowerCase();
            const currentTags = playbook.tags || [];
            if (!currentTags.includes(newTag)) {
                const newTags = [...currentTags, newTag];
                onUpdate('tags', newTags);
            }
            setTagInput("");
        }
    };

    // Handler: Remove Tag
    const handleRemoveTag = (tagToRemove: string) => {
        const newTags = (playbook.tags || []).filter(t => t !== tagToRemove);
        onUpdate('tags', newTags);
    };
  
  // 1. Helper for Logic Level Color & Description
  const getLevelInfo = (level: number) => {
      switch (level) {
          case 1: return { color: 'bg-red-100 text-red-800', label: 'Ephemeral', desc: 'Hash, IP, Domain' };
          case 2: return { color: 'bg-orange-100 text-orange-800', label: 'Tool Artifact', desc: 'Default flags, pipe names' };
          case 3: return { color: 'bg-yellow-100 text-yellow-800', label: 'LOLBin / Tool', desc: 'powershell.exe, reg.exe' };
          case 4: return { color: 'bg-blue-100 text-blue-800', label: 'Behavioral', desc: 'API calls, Access rights' };
          case 5: return { color: 'bg-green-100 text-green-800', label: 'Invariant', desc: 'Technique choke point' };
          default: return { color: 'bg-gray-100 text-gray-800', label: 'Not Set', desc: 'Select logic level' };
      }
  };

  const levelInfo = getLevelInfo(playbook.robustnessLevel);

  // 2. Calculate Final Summiting Score (e.g. "4K")
    const summitScore = `${playbook.robustnessLevel > 0 ? playbook.robustnessLevel : '?'}${playbook.dataSourceRobustness || '?'}`;
    const parsedStrategy = (() => {
        try { return playbook.selectedStrategy ? JSON.parse(playbook.selectedStrategy as any) : {}; } catch { return {}; }
    })();
    const currentFPR = typeof (parsedStrategy as any).falsePositiveRate === 'number' ? (parsedStrategy as any).falsePositiveRate : 0;

  /* ── Collapsed strip ── */
  if (collapsed) {
    return (
      <div className="workbench-sidebar relative flex flex-col items-center bg-white border-l border-gray-200 shadow-lg h-full" style={{ width: '100%' }}>
        {/* Toggle button at top */}
        <button
          onClick={() => onCollapsedChange(false)}
          title="Expand sidebar"
          className="mt-3 mb-2 p-1.5 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-800 transition-colors"
        >
          {/* Double-chevron pointing left (expand) */}
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="11 17 6 12 11 7" />
            <polyline points="18 17 13 12 18 7" />
          </svg>
        </button>

        {/* Rotated label */}
        <span
          className="text-[10px] font-bold text-gray-400 uppercase tracking-widest select-none mt-4"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          {activeTab === 'NOTES' ? 'Notes' : 'Details'}
        </span>

        {/* Notes indicator */}
        {activeTab === 'NOTES' && (playbook.notes || '').trim().length > 0 && (
          <span className="mt-2 bg-blue-500 text-white text-[9px] px-1 py-0.5 rounded-full">
            •
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="workbench-sidebar w-full bg-white border-l border-gray-200 flex flex-col h-full shadow-lg">
      
      {/* 1. Tab Switcher + Collapse button */}
      <div className="flex border-b border-gray-200">
          <button 
             className={`flex-1 py-3 text-sm font-bold text-center ${activeTab === 'DETAILS' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
             onClick={() => onTabChange('DETAILS')}
          >
             Details
          </button>
          <button 
             className={`flex-1 py-3 text-sm font-bold text-center flex items-center justify-center gap-2 ${activeTab === 'NOTES' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
             onClick={() => onTabChange('NOTES')}
          >
             Notes
             {(playbook.notes || '').trim().length > 0 && (
                 <span className="bg-gray-200 text-gray-700 text-[9px] px-1.5 py-0.5 rounded-full">
                     •
                 </span>
             )}
          </button>
          {/* Collapse button */}
          <button
            onClick={() => onCollapsedChange(true)}
            title="Collapse sidebar"
            className="px-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors border-l border-gray-200"
          >
            {/* Double-chevron pointing right (collapse) */}
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="13 17 18 12 13 7" />
              <polyline points="6 17 11 12 6 7" />
            </svg>
          </button>
      </div>

      {/* 2. Content Area */}
      <div className="flex-1 overflow-hidden">
          
          {activeTab === 'DETAILS' ? (
              <div className="h-full overflow-y-auto">
                  {/* 1. METADATA SECTION */}
                  <div className="p-4 border-b border-gray-100">
                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">Metadata</h3>
                    
                    <div className="space-y-4">
                        {/* Custom ID */}
                        <div>
                            <label className="text-xs text-gray-500">Playbook ID</label>
                            <div className="font-mono font-bold text-gray-800 text-sm">
                                {playbook.customId || "Pending..."}
                            </div>
                        </div>

                        {/* Version & Author */}
                        <div className="flex justify-between">
                            <div>
                                <label className="text-xs text-gray-500">Version</label>
                                <div className="font-bold text-gray-800">v{playbook.version}.{playbook.minorVersion ?? 0}</div>
                            </div>
                            <div className="text-right">
                                <label className="text-xs text-gray-500">Author</label>
                                <div className="text-sm text-gray-800 flex items-center justify-end">
                                     <div className="w-4 h-4 bg-blue-500 rounded-full text-white text-[9px] flex items-center justify-center mr-1">
                                         {playbook.author?.username?.charAt(0).toUpperCase()}
                                     </div>
                                     {playbook.author?.username}
                                </div>
                            </div>
                        </div>

                        {/* Status */}
                        <div>
                             <label className="text-xs text-gray-500">Status</label>
                             <div className="mt-1">
                                 <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-800`}>
                                    {playbook.status}
                                 </span>
                             </div>
                        </div>
                    </div>
                  </div>

                  {/* VALUATION SECTION (Updated) */}
                  <div className="p-4 bg-gray-50 border-b border-gray-200">
                    <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center justify-between">
                        VALUATION
                        {/* The Summit Score Badge */}
                        <span className="text-lg font-black text-gray-800 border-2 border-gray-800 px-2 rounded bg-white">
                            {summitScore}
                        </span>
                    </h3>
                    
                    <div className="space-y-6">
                        
                        {/* 1. Logic Robustness (1-5) */}
                        <div>
                            <label className="text-xs font-bold text-gray-700 block mb-1">
                                Analytic Logic Level
                            </label>
                            <select 
                                className={`w-full p-2 text-sm border rounded font-medium focus:ring-2 focus:ring-blue-500 ${levelInfo.color}`}
                                value={playbook.robustnessLevel}
                                onChange={(e) => onUpdate('robustnessLevel', parseInt(e.target.value))}
                            >
                                <option value="0">Select Level...</option>
                                <option value="1">Level 1: Ephemeral (Hash/IP)</option>
                                <option value="2">Level 2: Tool Artifact (String/Flag)</option>
                                <option value="3">Level 3: LOLBin (CommandLine)</option>
                                <option value="4">Level 4: Behavior (API/RPC)</option>
                                <option value="5">Level 5: Invariant (Choke Point)</option>
                            </select>
                            <p className="text-[10px] text-gray-500 mt-1 italic leading-tight">
                                {levelInfo.desc}
                            </p>
                        </div>

                        {/* 2. Data Source Robustness (K/U/A/H/P) */}
                        <div>
                            <label className="text-xs font-bold text-gray-700 block mb-1">
                                Event Robustness
                            </label>
                            <select 
                                className="w-full p-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                                value={playbook.dataSourceRobustness}
                                onChange={(e) => onUpdate('dataSourceRobustness', e.target.value)}
                            >
                                <option value="">Select Source Type...</option>
                                <optgroup label="Host-Based">
                                    <option value="K">Kernel-Mode (K) - Sysmon/ETW</option>
                                    <option value="U">User-Mode (U) - APIs</option>
                                    <option value="A">Application (A) - App Logs</option>
                                </optgroup>
                                <optgroup label="Network-Based">
                                    <option value="H">Protocol Header (H)</option>
                                    <option value="P">Protocol Payload (P)</option>
                                </optgroup>
                            </select>
                            <p className="text-[10px] text-gray-500 mt-1 leading-tight">
                               {playbook.dataSourceRobustness === 'K' && "Hardest to tamper (OS Kernel)."}
                               {playbook.dataSourceRobustness === 'U' && "Vulnerable to user-mode hooks."}
                               {playbook.dataSourceRobustness === 'A' && "Application specific (bypassable)."}
                               {playbook.dataSourceRobustness === 'H' && "Hard to spoof metadata."}
                               {playbook.dataSourceRobustness === 'P' && "Vulnerable to encryption."}
                            </p>
                        </div>

                                                                                                {/* 3. False Positive Rate (0-100%) */}
                                                <div>
                                                        <label className="text-xs font-bold text-gray-700 block mb-1">
                                                                False Positive Rate
                                                        </label>
                                                        <div className="flex items-center gap-2">
                                                                <input
                                                                        type="number"
                                                                        min={0}
                                                                        max={100}
                                                                        value={currentFPR}
                                                                        onChange={(e) => {
                                                                                const v = Math.max(0, Math.min(100, Number(e.target.value || 0)));
                                                                                const next = { ...parsedStrategy, falsePositiveRate: v };
                                                                                onUpdate('selectedStrategy', JSON.stringify(next));
                                                                        }}
                                                                        className="w-24 p-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500"
                                                                />
                                                                <span className="text-xs text-gray-500">%</span>
                                                        </div>
                                                        {/* Meter */}
                                                        <div className="mt-2 flex items-center gap-2">
                                                                <div className="flex-1 h-2 rounded bg-gray-200 overflow-hidden">
                                                                        <div
                                                                            className="h-full transition-all"
                                                                            style={{
                                                                                width: `${currentFPR}%`,
                                                                                backgroundColor: ((): string => {
                                                                                    const val = currentFPR;
                                                                                    if (val >= 80) return 'var(--hef-success-text)';
                                                                                    if (val >= 50) return 'var(--hef-warning-text)';
                                                                                    return 'var(--hef-danger-text)';
                                                                                })()
                                                                            }}
                                                                        />
                                                                </div>
                                                                <span
                                                                    className="px-2 py-0.5 rounded text-[11px]"
                                                                    style={{
                                                                        backgroundColor: ((): string => {
                                                                            const val = currentFPR;
                                                                            if (val >= 80) return 'var(--hef-success-bg)';
                                                                            if (val >= 50) return 'var(--hef-warning-bg)';
                                                                            return 'var(--hef-danger-bg)';
                                                                        })(),
                                                                        color: ((): string => {
                                                                            const val = currentFPR;
                                                                            if (val >= 80) return 'var(--hef-success-text)';
                                                                            if (val >= 50) return 'var(--hef-warning-text)';
                                                                            return 'var(--hef-danger-text)';
                                                                        })()
                                                                    }}
                                                                >
                                                                    {currentFPR}%
                                                                </span>
                                                        </div>
                                                        <p className="text-[10px] text-gray-500 mt-1 leading-tight">
                                                                0% = worst (very noisy), 100% = best (ideal)
                                                        </p>
                                                </div>

                                                {/* 4. Tags (now under Valuation) */}
                                                <div>
                                                    <label className="text-xs font-bold text-gray-700 block mb-1">
                                                        Tags
                                                    </label>
                                                    <input
                                                        type="text"
                                                        className="w-full p-2 text-xs border border-gray-300 rounded mb-2 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                                                        placeholder="Add tag (Press Enter)..."
                                                        value={tagInput}
                                                        onChange={(e) => setTagInput(e.target.value)}
                                                        onKeyDown={handleAddTag}
                                                    />
                                                    <div className="flex flex-wrap gap-2 min-h-[28px]">
                                                        {(playbook.tags || []).map((tag, idx) => (
                                                            <span key={idx} className="inline-flex items-center px-2 py-1 rounded text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-100 group">
                                                                #{tag}
                                                                <button
                                                                    onClick={() => handleRemoveTag(tag)}
                                                                    className="ml-1 text-blue-300 hover:text-red-500 focus:outline-none opacity-0 group-hover:opacity-100 transition-opacity"
                                                                    aria-label={`Remove tag ${tag}`}
                                                                >
                                                                    ×
                                                                </button>
                                                            </span>
                                                        ))}
                                                        {(!playbook.tags || playbook.tags.length === 0) && (
                                                            <span className="text-xs text-gray-400 italic py-1">No tags yet.</span>
                                                        )}
                                                    </div>
                                                </div>

                        {/* 5. Node ATT&CK Mappings (when a node is selected) */}
                        <div className="mt-6">
                            <label className="text-xs font-bold text-gray-700 block mb-1">
                                Node ATT&CK Mappings
                            </label>
                            {!selectedNodeId ? (
                                <p className="text-[11px] text-gray-400">Select a node on the map to assign ATT&CK techniques.</p>
                            ) : (
                                <div className="space-y-2">
                                            {(() => {
                                                const selectedNode = (playbook.nodes || []).find((n) => n.id === selectedNodeId);
                                                const mappings = selectedNode?.mitreAttackMappings || [];
                                                return mappings.length ? (
                                                    <div className="flex flex-wrap gap-2 text-[11px]">
                                                        {mappings.map((m) => (
                                                            <span key={m.id} className="px-2 py-1 rounded bg-purple-50 text-purple-700 border border-purple-200">
                                                                {m.techniqueId}
                                                            </span>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="text-[11px] text-gray-400">No mappings yet.</p>
                                                );
                                            })()}
                                    <input
                                        type="text"
                                        className="w-full p-2 text-xs border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:outline-none"
                                        placeholder="Enter comma-separated technique IDs (e.g., T1059,T1003.001)"
                                        onBlur={(e) => {
                                            const raw = (e.target.value || '').trim();
                                            const ids = raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : [];
                                            onUpdateNodeMappings && onUpdateNodeMappings(ids);
                                        }}
                                    />
                                    <p className="text-[10px] text-gray-500">Tip: Include sub-techniques like T1003.001 when relevant.</p>
                                </div>
                            )}
                        </div>

                    </div>
                  </div>
              </div>
          ) : (
              <PlaybookNotes
                  notes={playbook.notes || ''}
                  canClearNotes={canClearNotes}
                  onSave={async (nextNotes: string) => {
                    await onUpdate('notes', nextNotes);
                  }}
              />
          )}

      </div>
    </div>
  );
};
