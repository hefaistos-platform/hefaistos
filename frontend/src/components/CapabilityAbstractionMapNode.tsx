import React, { useEffect, useRef, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { CapabilityAbstractionEntry, LAYER_LABELS, getRobustnessColor, getRobustnessLabel } from '../utils/capabilityAbstractionUtils';

type CapabilityAbstractionMapNodeProps = {
  data: {
    entry: CapabilityAbstractionEntry;
    isFocusLayer: boolean;
  };
};

const CapabilityAbstractionMapNode: React.FC<CapabilityAbstractionMapNodeProps> = ({ data }) => {
  const { entry, isFocusLayer } = data;
  const [hovered, setHovered] = useState<boolean>(false);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const robustnessColor = getRobustnessColor(entry.robustnessLevel);
  const borderColor = isFocusLayer ? '#2563eb' : robustnessColor;

  useEffect(() => {
    const wrapper = cardRef.current?.closest('.react-flow__node') as HTMLElement | null;
    if (!wrapper) return;

    // React Flow stacks nodes by wrapper z-index, so raise the wrapper when hovered.
    wrapper.style.overflow = 'visible';
    wrapper.style.zIndex = hovered ? '1000' : '';

    return () => {
      wrapper.style.zIndex = '';
    };
  }, [hovered]);

  return (
    <div
      ref={cardRef}
      className="rounded-lg shadow-md text-xs"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        border: `2px solid ${borderColor}`,
        backgroundColor: isFocusLayer ? '#eff6ff' : '#ffffff',
        minWidth: 220,
        maxWidth: 240,
        padding: '8px 10px',
        transform: hovered ? 'scale(1.6)' : 'scale(1)',
        transformOrigin: 'top left',
        transition: 'transform 150ms ease, box-shadow 150ms ease',
        position: 'relative',
        zIndex: hovered ? 50 : 1,
        boxShadow: hovered ? '0 14px 28px rgba(15, 23, 42, 0.35)' : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} />

      <div className="flex items-center gap-1 mb-1 flex-wrap">
        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-700 uppercase tracking-wide">
          {LAYER_LABELS[entry.abstractionLayer] ?? entry.abstractionLayer}
        </span>
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-bold text-white"
          style={{ backgroundColor: robustnessColor }}
          title={getRobustnessLabel(entry.robustnessLevel)}
        >
          R{entry.robustnessLevel ?? 0}
        </span>
        {isFocusLayer && (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-600 text-white">
            🎯 Focus
          </span>
        )}
        {entry.isSharedBaseline && (
          <span className="px-1.5 py-0.5 rounded text-[10px] text-purple-700 bg-purple-100">
            Baseline
          </span>
        )}
      </div>

      <div className={`font-semibold text-gray-800 text-[11px] mb-1 ${hovered ? '' : 'truncate'}`} title={entry.componentArtifact}>
        {entry.componentArtifact}
      </div>

      {entry.adversaryPurpose && (
        <div className={`text-gray-500 text-[10px] mb-1 ${hovered ? '' : 'line-clamp-2'}`}>
          🎭 {entry.adversaryPurpose}
        </div>
      )}

      {entry.commonEvasions && (
        <div className="text-orange-600 text-[10px] flex items-center gap-1 mb-1">
          <span>⚠️</span>
          <span className={hovered ? '' : 'truncate'}>{entry.commonEvasions}</span>
        </div>
      )}

      {entry.detectionValue && (
        <div className={`text-green-700 text-[10px] ${hovered ? '' : 'truncate'}`}>
          🔍 {entry.detectionValue}
        </div>
      )}

      {hovered && entry.expectedObservables && (
        <div className="text-indigo-700 text-[10px] mt-1">
          👁 {entry.expectedObservables}
        </div>
      )}

      {hovered && entry.applicableTelemetry && (
        <div className="text-sky-700 text-[10px] mt-1">
          📡 {entry.applicableTelemetry}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default CapabilityAbstractionMapNode;
