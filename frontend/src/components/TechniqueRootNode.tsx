import React from 'react';
import { Handle, Position } from '@xyflow/react';

type TechniqueRootNodeProps = {
  data: {
    label: string;
  };
};

const TechniqueRootNode: React.FC<TechniqueRootNodeProps> = ({ data }) => {
  return (
    <div className="bg-gray-900 text-white font-bold text-sm rounded-xl shadow-lg min-w-[200px] px-4 py-2 text-center border border-gray-800">
      <div className="text-[10px] text-gray-400 uppercase tracking-widest">ATT&CK Technique</div>
      <div className="mt-0.5">{data.label}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default TechniqueRootNode;
