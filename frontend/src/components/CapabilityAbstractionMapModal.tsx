import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { Modal, message } from 'antd';
import {
  Background,
  Connection,
  Controls,
  Edge,
  EdgeChange,
  Node,
  NodeChange,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from '@xyflow/react';
import { toPng } from 'html-to-image';
import { Button } from './ui/Button';
import { PixelIcon } from './ui/PixelIcon';
import { GraphToolbar } from './playbook/GraphToolbar';
import CapabilityAbstractionLayerBands from './CapabilityAbstractionLayerBands';
import { LayerBand } from '../utils/capabilityAbstractionUtils';

interface CapabilityAbstractionMapModalProps {
  isOpen: boolean;
  onClose: () => void;
  derivedNodes: Node[];
  derivedEdges: Edge[];
  manualNodes: Node[];
  manualEdges: Edge[];
  isAutoMode: boolean;
  onToggleAutoMode: () => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  onNodesDelete: (nodes: Node[]) => void;
  onEdgesDelete: (edges: Edge[]) => void;
  onNodeDragStop: (event: React.MouseEvent, node: Node) => void;
  onCapabilityMapNodeClick: (event: React.MouseEvent, node: Node) => void;
  onNodeClick: (event: React.MouseEvent, node: Node) => void;
  onNodeDoubleClick: (event: React.MouseEvent, node: Node) => void;
  coverageSummary: { total: number; avgRobustness: number; layerCount: Record<string, number> };
  focusLayer: string;
  layerBands: LayerBand[];
  nodeTypes: Record<string, any>;
  onAddNode: () => void;
  onDeleteSelected: () => void;
  hasSelection: boolean;
  onColorChange: (color: string) => void;
}

type CapabilityAbstractionMapModalInnerProps = CapabilityAbstractionMapModalProps;

const CapabilityAbstractionMapModalInner: React.FC<CapabilityAbstractionMapModalInnerProps> = ({
  isOpen,
  onClose,
  derivedNodes,
  derivedEdges,
  manualNodes,
  manualEdges,
  isAutoMode,
  onToggleAutoMode,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodesDelete,
  onEdgesDelete,
  onNodeDragStop,
  onCapabilityMapNodeClick,
  onNodeClick,
  onNodeDoubleClick,
  coverageSummary,
  focusLayer,
  layerBands,
  nodeTypes,
  onAddNode,
  onDeleteSelected,
  hasSelection,
  onColorChange,
}) => {
  const { fitView } = useReactFlow();
  const flowContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => fitView({ padding: 0.2 }), 100);
    return () => clearTimeout(timer);
  }, [fitView, isOpen, isAutoMode, derivedNodes, manualNodes, derivedEdges, manualEdges]);

  const activeNodes = useMemo(() => (isAutoMode ? derivedNodes : manualNodes), [isAutoMode, derivedNodes, manualNodes]);
  const activeEdges = useMemo(() => (isAutoMode ? derivedEdges : manualEdges), [isAutoMode, derivedEdges, manualEdges]);
  const isDarkTheme =
    typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'dark';

  const handleDownloadPng = useCallback(async () => {
    const container = flowContainerRef.current;
    if (!container) {
      message.error('Graph container not found');
      return;
    }

    const viewport = container.querySelector('.react-flow__viewport') as HTMLElement | null;
    try {
      const dataUrl = await toPng(viewport ?? container, {
        backgroundColor: isDarkTheme ? '#0f172a' : '#f9fafb',
        cacheBust: true,
      });
      const link = document.createElement('a');
      link.href = dataUrl;
      link.download = 'capability-abstraction-map.png';
      link.click();
    } catch {
      message.error('Failed to generate PNG');
    }
  }, [isDarkTheme]);

  return (
    <Modal
      open={isOpen}
      onCancel={onClose}
      footer={null}
      width="100vw"
      style={{ top: 0 }}
      className="fullscreen-modal workbench-map-modal"
      styles={{ body: { padding: 0, height: 'calc(100vh - 55px)' } }}
      destroyOnClose={false}
    >
      <div className="h-full bg-white">
        <div className="flex items-center justify-between px-4 py-2 bg-gray-100 border-b border-gray-200">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center gap-2 text-xs font-bold text-gray-600 uppercase tracking-wider">
              <PixelIcon name="share-2" className="w-4 h-4" />
              Capability Abstraction Map
            </div>
            {coverageSummary.total > 0 && (
              <div className="hidden lg:flex items-center gap-2 text-[10px] text-gray-500 normal-case">
                <span>{coverageSummary.total} abstraction{coverageSummary.total !== 1 ? 's' : ''}</span>
                <span>·</span>
                <span>Avg robustness: {coverageSummary.avgRobustness.toFixed(1)}</span>
                {Object.entries(coverageSummary.layerCount).map(([layer, count]) => (
                  <span key={layer} className="px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 uppercase tracking-wide">
                    {layer.replace(/_/g, ' ')}: {count}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={`text-[10px] px-2 py-1 rounded border ${
                isAutoMode ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-gray-300 text-gray-600'
              }`}
              onClick={onToggleAutoMode}
            >
              {isAutoMode ? 'Auto (from Library)' : 'Manual'}
            </button>
            <Button variant="secondary" onClick={handleDownloadPng} className="flex items-center gap-1">
              <PixelIcon name="camera" className="w-4 h-4" />
              Download PNG
            </Button>
          </div>
        </div>

        <div ref={flowContainerRef} className="relative h-[calc(100vh-120px)]">
          <ReactFlow
            nodes={activeNodes}
            edges={activeEdges}
            onNodesChange={isAutoMode ? undefined : onNodesChange}
            onEdgesChange={isAutoMode ? undefined : onEdgesChange}
            onConnect={isAutoMode ? undefined : onConnect}
            onNodesDelete={isAutoMode ? undefined : onNodesDelete}
            onEdgesDelete={isAutoMode ? undefined : onEdgesDelete}
            onNodeDragStop={isAutoMode ? undefined : onNodeDragStop}
            onNodeClick={isAutoMode ? onCapabilityMapNodeClick : onNodeClick}
            onNodeDoubleClick={isAutoMode ? undefined : onNodeDoubleClick}
            nodesDraggable={!isAutoMode}
            nodeTypes={nodeTypes}
            fitView
          >
            {isAutoMode && <CapabilityAbstractionLayerBands focusLayer={focusLayer} bands={layerBands} />}
            <Background color={isDarkTheme ? '#243246' : '#f1f5f9'} gap={20} />
            <Controls />
          </ReactFlow>

          {!isAutoMode && (
            <GraphToolbar
              onAddNode={onAddNode}
              onDeleteSelected={onDeleteSelected}
              hasSelection={hasSelection}
              onColorChange={onColorChange}
            />
          )}
        </div>
      </div>
    </Modal>
  );
};

const CapabilityAbstractionMapModal: React.FC<CapabilityAbstractionMapModalProps> = (props) => (
  <ReactFlowProvider>
    <CapabilityAbstractionMapModalInner {...props} />
  </ReactFlowProvider>
);

export default CapabilityAbstractionMapModal;
