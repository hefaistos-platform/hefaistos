import React from 'react';
import { LAYER_LABELS } from '../utils/capabilityAbstractionUtils';

type CoverageGapNodeProps = {
  data: {
    layer: string;
  };
};

const CoverageGapNode: React.FC<CoverageGapNodeProps> = ({ data }) => {
  return (
    <div className="border-2 border-dashed border-red-300 rounded-lg px-3 py-1.5 text-[10px] text-red-400 bg-red-50 opacity-60">
      ⚠️ No coverage: {LAYER_LABELS[data.layer] ?? data.layer}
    </div>
  );
};

export default CoverageGapNode;
