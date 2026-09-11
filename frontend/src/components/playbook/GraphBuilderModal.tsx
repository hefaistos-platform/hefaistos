import React, { useCallback, useState } from 'react';
import { 
  ReactFlow, 
  Background, 
  Controls, 
  useNodesState, 
  useEdgesState,
  addEdge,
  Connection,
  Edge,
  MarkerType
} from '@xyflow/react';
import { toPng } from 'html-to-image';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { PixelIcon } from '../ui/PixelIcon';
import '@xyflow/react/dist/style.css';

interface GraphBuilderProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (imageFile: File) => Promise<void>; // Callback to upload image
}

export const GraphBuilderModal: React.FC<GraphBuilderProps> = ({ isOpen, onClose, onSave }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([
    { id: '1', position: { x: 250, y: 50 }, data: { label: 'Tool: Mimikatz' }, type: 'default' },
    { id: '2', position: { x: 250, y: 150 }, data: { label: 'API: ReadProcessMemory' }, type: 'default' },
  ]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([
    { id: 'e1-2', source: '1', target: '2', animated: true }
  ]);
  const [isSaving, setIsSaving] = useState(false);

  const handleExport = async () => {
    setIsSaving(true);
    const flowElement = document.querySelector('.react-flow__viewport') as HTMLElement;

    if (flowElement) {
      try {
         const dataUrl = await toPng(flowElement, {
            backgroundColor: '#fff',
            width: flowElement.scrollWidth,
            height: flowElement.scrollHeight,
            style: { transform: 'translate(0,0) scale(1)' }
         });
         const res = await fetch(dataUrl);
         const blob = await res.blob();
         const file = new File([blob], "capability_map.png", { type: "image/png" });

         await onSave(file);
         onClose();
      } catch (e) {
         console.error(e);
         alert("Failed to generate image.");
      }
    }
    setIsSaving(false);
  };

  // 1. Handle Connections (Draw Edge)
  const onConnect = useCallback(
    (params: Connection) => {
      // Creates a new edge with an arrow at the end
      setEdges((eds) => addEdge({
        ...params,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed },
        animated: true
      } as Edge, eds));
    },
    [setEdges],
  );

  // 2. Handle Delete key (and button)
  // React Flow handles 'Delete' keypress by default if we pass the hooks right,
  // but we want a manual button too.
  const deleteSelected = () => {
    // Remove selected nodes
    setNodes((nds) => nds.filter((node) => !(node as any).selected));
    // Remove selected edges
    setEdges((eds) => eds.filter((edge) => !(edge as any).selected));
  };

  // Simple "Add Node" for demo purposestion)
  const addNode = () => {
    const id = Math.random().toString();
    setNodes((nds) => nds.concat({ 
      id, 
      position: { x: 50 + (nds.length * 20), y: 50 + (nds.length * 20) }, // Stagger
      data: { label: 'New Layer' },
      type: 'default'
    }));
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Capability Abstraction Builder">
       <div className="h-[600px] w-[800px] bg-gray-50 border border-gray-200 relative">
          {/* Toolbar */}
          <div className="absolute top-2 right-2 z-10 flex gap-2">
             <Button variant="secondary" onClick={addNode}>+ Node</Button>
             
             {/* --- DELETE BUTTON --- */}
             <Button variant="danger" onClick={deleteSelected}>
                <PixelIcon name="trash" className="w-4 h-4" />
             </Button>
             {/* ---------------------- */}
             
             <Button variant="primary" onClick={handleExport} disabled={isSaving}>
                {isSaving ? 'Attaching...' : 'Attach to Playbook'}
             </Button>
          </div>
          
          <ReactFlow
             nodes={nodes} 
             edges={edges}
             onNodesChange={onNodesChange} 
             onEdgesChange={onEdgesChange}
             onConnect={onConnect} // <--- CONNECT HANDLER
             fitView
          >
             <Background />
             <Controls />
          </ReactFlow>
       </div>
    </Modal>
  );
};