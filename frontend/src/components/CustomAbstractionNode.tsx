import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';
import { PixelIcon } from './ui/PixelIcon';

type NodeData = {
  id?: string;
  label: string;
  templateData?: { color?: string };
  isEditing?: boolean;
  onRename?: (newName: string) => void;
};

// Lightweight color mapping for node backgrounds
const colorMap: Record<string, string> = {
  blue: '#E6F4FF',   // light blue
  green: '#E6FFED',  // light green
  red: '#FFECEC',    // light red
  yellow: '#FFF9DB', // light yellow
};

const CustomAbstractionNode = ({ data, selected }: NodeProps) => {
  const key = ((data as NodeData)?.templateData?.color || '').toLowerCase();
  const bg = colorMap[key] || '#FFFFFF';

  const [local, setLocal] = React.useState<string>((data as NodeData).label || '');
  React.useEffect(() => setLocal((data as NodeData).label || ''), [(data as NodeData).label]);

  return (
    <div
      className={`p-4 border-2 rounded-md shadow-md transition-all duration-150 ${selected ? 'border-blue-500 ring-2 ring-blue-200' : 'border-hefaistos-border'}`}
      style={{ minWidth: 180, maxWidth: 320, backgroundColor: bg }}
    >
      <div className="flex items-center space-x-2">
        <PixelIcon name="playbook" className="w-5 h-5 text-hefaistos-primary" />
        {(data as NodeData).isEditing ? (
          <input
            className="font-bold text-hefaistos-foreground border rounded px-1 py-[2px]"
            value={local}
            onChange={(e) => setLocal(e.target.value)}
            onBlur={() => (data as NodeData).onRename && (data as NodeData).onRename!(local)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                (data as NodeData).onRename && (data as NodeData).onRename!(local);
              }
            }}
            autoFocus
          />
        ) : (
          <div className="font-bold text-hefaistos-foreground">{(data as NodeData).label}</div>
        )}
      </div>

      <Handle type="target" position={Position.Top} className="w-3 h-3 bg-gray-400" />
      <Handle type="source" position={Position.Bottom} className="w-3 h-3 bg-gray-400" />
    </div>
  );
};

export default CustomAbstractionNode;