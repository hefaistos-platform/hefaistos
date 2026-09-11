import React, { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { gql, } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, Node, Edge, Connection, addEdge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// --- UI Components (Sprint 0 design) ---
import { Button } from '../components/ui/Button';
import { PixelIcon } from '../components/ui/PixelIcon';

// --- Import SDK and Custom Node ---
import CustomAbstractionNode from '../components/CustomAbstractionNode';
import { useAppStore, AbstractionNodeData } from '../useStore';
import { Sidebar } from '../components/Sidebar';
import { Select, Typography, Input, Space, message } from 'antd';
import { sanitizeCodeFences } from '../utils/sanitize';

const { TextArea } = Input;

// --- New Mutations ---
const CREATE_PLAYBOOK_NODE_MUTATION = gql`
  mutation CreatePlaybookNode($graphId: UUID!, $layerName: String!, $x: Float!, $y: Float!) {
    createPlaybookNode(graphId: $graphId, layerName: $layerName, positionX: $x, positionY: $y) {
      node {
        id
        layerName
        positionX
        positionY
        templateData
        mitreAttackMappings { id }
      }
    }
  }
`;

const CREATE_PLAYBOOK_EDGE_MUTATION = gql`
  mutation CreatePlaybookEdge($graphId: UUID!, $sourceNodeId: UUID!, $targetNodeId: UUID!) {
    createPlaybookEdge(graphId: $graphId, sourceNodeId: $sourceNodeId, targetNodeId: $targetNodeId) {
      edge {
        id
        source
        target
      }
    }
  }
`;

const DELETE_PLAYBOOK_EDGE_MUTATION = gql`
  mutation DeletePlaybookEdge($edgeId: UUID!) {
    deletePlaybookEdge(edgeId: $edgeId) {
      ok
    }
  }
`;

const DELETE_PLAYBOOK_NODE_MUTATION = gql`
  mutation DeletePlaybookNode($nodeId: UUID!) {
    deletePlaybookNode(nodeId: $nodeId) {
      ok
    }
  }
`;

// We now fetch templateData and TTPs
const GET_PLAYBOOK_GRAPH_QUERY = gql`
  query GetPlaybookGraph($id: UUID!) {
    playbookGraph(id: $id) {
      id
      title
      notes
      pngSnapshotUrl
      playbooks {
        id
        title
      }
      nodes {
        id
        layerName
        positionX
        positionY
        templateData
        mitreAttackMappings {
          id
          techniqueId
          name
        }
      }
      edges {
        id
        source
        target
      }
    }
  }
`;

const GET_MY_PLAYBOOKS = gql`
  query GetMyPlaybooksForGraph {
    allPlaybooks {
      id
      title
      status
    }
  }
`;

const UPDATE_NODE_POSITION_MUTATION = gql`
  mutation UpdatePlaybookNodePosition($nodeId: UUID!, $x: Float!, $y: Float!) {
    updatePlaybookNodePosition(nodeId: $nodeId, positionX: $x, positionY: $y) {
      node {
        id
        positionX
        positionY
      }
    }
  }
`;

const UPDATE_GRAPH_METADATA_MUTATION = gql`
  mutation UpdatePlaybookGraphMetadata($graphId: UUID!, $notes: String, $playbookIds: [UUID!]) {
    updatePlaybookGraphMetadata(graphId: $graphId, notes: $notes, playbookIds: $playbookIds) {
      playbookGraph {
        id
        notes
        playbooks { id title }
      }
    }
  }
`;

const SET_GRAPH_SNAPSHOT_MUTATION = gql`
  mutation SetPlaybookGraphSnapshot($graphId: UUID!, $pngBase64: String!) {
    setPlaybookGraphSnapshot(graphId: $graphId, pngBase64: $pngBase64) {
      playbookGraph {
        id
        pngSnapshotUrl
      }
    }
  }
`;

const UPDATE_NODE_TEMPLATE_MUTATION = gql`
  mutation UpdateNodeTemplate($nodeId: UUID!, $template_data: GenericScalar!) {
    updateNodeTemplate(nodeId: $nodeId, template_data: $template_data) {
      node { id templateData }
    }
  }
`;

const UPDATE_NODE_NAME_MUTATION = gql`
  mutation UpdatePlaybookNodeLayerName($nodeId: UUID!, $layerName: String!) {
    updatePlaybookNodeLayerName(nodeId: $nodeId, layerName: $layerName) {
      node { id layerName }
    }
  }
`;

// --- Define the custom node type for React Flow ---
const nodeTypes = {
  abstractionLayer: CustomAbstractionNode,
};

// --- TypeScript types for GraphQL response ---
interface QueryNode {
  id: string;
  layerName: string;
  positionX: number;
  positionY: number;
  templateData: any;
  mitreAttackMappings: Array<{ id: string; techniqueId: string; name: string }>;
}

interface QueryEdge {
  id: string;
  source: string;
  target: string;
}

interface GetPlaybookGraphData {
  playbookGraph: {
    id: string;
    title: string;
    notes?: string | null;
    pngSnapshotUrl?: string | null;
    playbooks?: { id: string; title: string }[];
    nodes: QueryNode[];
    edges: QueryEdge[];
  } | null;
}

interface GetPlaybookGraphVars { id: string }

type FlowNode = Node; // We will cast data when selecting
type FlowEdge = Edge;

interface AllPlaybooksData {
  allPlaybooks: { id: string; title: string; status: string }[];
}

export const PlaybookGraphPage = () => {
  const { graphId } = useParams<{ graphId: string }>();

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>([]);

  // Get the action from our store
  const setSelectedNode = useAppStore((state) => state.setSelectedNode);
  const selectedNode = useAppStore((state) => state.selectedNode);

  const [updateNodePosition] = useMutation(UPDATE_NODE_POSITION_MUTATION);
  // --- ADD NEW MUTATIONS ---
  const [createNode] = useMutation(CREATE_PLAYBOOK_NODE_MUTATION);
  const [createEdge] = useMutation(CREATE_PLAYBOOK_EDGE_MUTATION);
  const [deleteEdge] = useMutation(DELETE_PLAYBOOK_EDGE_MUTATION);
  const [deleteNode] = useMutation(DELETE_PLAYBOOK_NODE_MUTATION);
  const [updateGraphMetadata, { loading: savingMetadata }] = useMutation(UPDATE_GRAPH_METADATA_MUTATION);
  const [setGraphSnapshot, { loading: savingSnapshot }] = useMutation(SET_GRAPH_SNAPSHOT_MUTATION);
  const [updateNodeTemplate] = useMutation(UPDATE_NODE_TEMPLATE_MUTATION);
  const [updateNodeName] = useMutation(UPDATE_NODE_NAME_MUTATION);

  // Local editing state for node name to avoid focus jumps on each keystroke
  const [editNodeName, setEditNodeName] = useState<string>('');
  const [inlineEditId, setInlineEditId] = useState<string>('');
  useEffect(() => {
    if (selectedNode) {
      setEditNodeName(selectedNode.layerName || '');
    } else {
      setEditNodeName('');
    }
  }, [selectedNode?.id]);

  // Fetch graph data (includes refetch for use in handlers)
  const { data, loading, error, refetch } = useQuery<GetPlaybookGraphData, GetPlaybookGraphVars>(GET_PLAYBOOK_GRAPH_QUERY, {
    variables: { id: graphId as string },
    skip: !graphId,
  });

  const { data: playbooksData } = useQuery<AllPlaybooksData>(GET_MY_PLAYBOOKS);

  const [notes, setNotes] = useState<string>('');
  const [attachedPlaybookIds, setAttachedPlaybookIds] = useState<string[]>([]);
  // --- ADD NODE HANDLER ---
  const handleAddNode = useCallback(() => {
    const newNodeName = window.prompt("Enter a name for the new node:", "New Node");
    if (newNodeName) {
      createNode({
        variables: {
          graphId: graphId,
          layerName: newNodeName,
          x: 100,
          y: 100,
        },
        refetchQueries: [{ query: GET_PLAYBOOK_GRAPH_QUERY, variables: { id: graphId } }]
      }).catch(e => console.error("Failed to add node:", e));
    }
  }, [createNode, graphId]);

  // --- ADD EDGE HANDLER ---
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge(connection, eds));
      createEdge({
        variables: {
          graphId: graphId,
          sourceNodeId: connection.source,
          targetNodeId: connection.target,
        },
        refetchQueries: [{ query: GET_PLAYBOOK_GRAPH_QUERY, variables: { id: graphId } }]
      }).catch(e => {
        console.error("Failed to create edge:", e);
        refetch();
      });
    },
    [setEdges, createEdge, graphId, refetch]
  );

  // --- DELETE EDGE HANDLER ---
  const onEdgesDelete = useCallback(
    (edgesToDelete: Edge[]) => {
      edgesToDelete.forEach((edge) => {
        deleteEdge({
          variables: { edgeId: edge.id },
        }).catch((e) => {
          console.error('Failed to delete edge:', e);
          refetch();
        });
      });
    },
    [deleteEdge, refetch]
  );


  useEffect(() => {
    if (data?.playbookGraph) {
      const flowNodes: FlowNode[] = data.playbookGraph.nodes.map((node: QueryNode) => ({
        id: node.id,
        data: {
          label: node.layerName,
          id: node.id,
          graphId: data.playbookGraph!.id,
          layerName: node.layerName,
          templateData: node.templateData,
          mitreAttackMappings: node.mitreAttackMappings,
          isEditing: inlineEditId === node.id,
          onRename: async (newName: string) => {
            const finalName = (newName || '').trim();
            if (!finalName) { message.warning('Name cannot be empty'); return; }
            try {
              await updateNodeName({
                variables: { nodeId: node.id, layerName: finalName },
                optimisticResponse: {
                  updatePlaybookNodeLayerName: { node: { id: node.id, layerName: finalName } }
                }
              });
              setNodes(nds => nds.map(n => n.id === node.id ? { ...n, data: { ...n.data, layerName: finalName, label: finalName, isEditing: false } } : n));
              if (selectedNode && selectedNode.id === node.id) {
                setSelectedNode({ ...selectedNode, layerName: finalName });
              }
              setInlineEditId('');
              message.success('Node renamed');
            } catch (err) {
              console.error(err);
              message.error('Rename failed');
            }
          }
        },
        position: { x: node.positionX, y: node.positionY },
        type: 'abstractionLayer',
      }));
      const flowEdges: FlowEdge[] = data.playbookGraph.edges.map((edge: QueryEdge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        style: { stroke: '#444', strokeWidth: 2 },
      }));
      setNodes(flowNodes);
      setEdges(flowEdges);

      setNotes(data.playbookGraph.notes || '');
      setAttachedPlaybookIds((data.playbookGraph.playbooks || []).map(p => p.id));
    }
  }, [data, setNodes, setEdges, setSelectedNode]);

  const onNodeDragStop = useCallback(
    (event: any, node: any) => {
      try {
        updateNodePosition({
          variables: {
            nodeId: node.id,
            x: node.position.x,
            y: node.position.y,
          },
          optimisticResponse: {
            updatePlaybookNodePosition: {
              node: {
                id: node.id,
                __typename: 'PlaybookNodeType',
                positionX: node.position.x,
                positionY: node.position.y,
              },
            },
          },
        });
      } catch (e) {
        console.error('Failed to save node position:', e);
      }
    },
    [updateNodePosition]
  );


  const handleSaveMetadata = useCallback(async () => {
    if (!graphId) return;
    try {
      await updateGraphMetadata({
        variables: {
          graphId,
          notes,
          playbookIds: attachedPlaybookIds,
        },
        refetchQueries: [{ query: GET_PLAYBOOK_GRAPH_QUERY, variables: { id: graphId } }],
      });
      message.success('Graph notes and links saved');
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error(e);
      message.error(e?.message || 'Failed to save graph metadata');
    }
  }, [graphId, notes, attachedPlaybookIds, updateGraphMetadata]);

  // --- Node Color Palette & Multi-Selection ---
  const colorPalette: Array<{ key: string; label: string; hex: string }> = [
    { key: 'blue', label: 'Light Blue', hex: '#E6F4FF' },
    { key: 'green', label: 'Light Green', hex: '#E6FFED' },
    { key: 'red', label: 'Light Red', hex: '#FFECEC' },
    { key: 'yellow', label: 'Light Yellow', hex: '#FFF9DB' },
  ];

  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);

  const toggleNodeInSelection = useCallback((id: string) => {
    setSelectedNodeIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]);
  }, []);

  const setExclusiveSelection = useCallback((id: string) => {
    setSelectedNodeIds([id]);
  }, []);

  const applyColorToNodes = useCallback(async (colorKey: string) => {
    const targetIds = selectedNodeIds.length ? selectedNodeIds : (selectedNode ? [selectedNode.id] : []);
    if (!targetIds.length) return;
    setNodes(nds => nds.map(n => targetIds.includes(n.id) ? {
      ...n,
      data: { ...n.data, templateData: { ...(n.data as any).templateData, color: colorKey } }
    } : n));
    await Promise.all(targetIds.map(id => updateNodeTemplate({
      variables: { nodeId: id, template_data: { ...(nodes.find(n => n.id === id)?.data as any)?.templateData, color: colorKey } },
      optimisticResponse: { updateNodeTemplate: { node: { id, templateData: { ...(nodes.find(n => n.id === id)?.data as any)?.templateData, color: colorKey } } } }
    }).catch(e => console.error('Color update failed for node', id, e))));
    message.success(`Applied ${colorKey} to ${targetIds.length} node(s)`);
  }, [selectedNode, selectedNodeIds, setNodes, updateNodeTemplate, nodes]);

  const resetColorsForSelection = useCallback(async () => {
    const targetIds = selectedNodeIds.length ? selectedNodeIds : (selectedNode ? [selectedNode.id] : []);
    if (!targetIds.length) return;
    setNodes(nds => nds.map(n => targetIds.includes(n.id) ? {
      ...n,
      data: { ...n.data, templateData: { ...(n.data as any).templateData, color: undefined } }
    } : n));
    await Promise.all(targetIds.map(id => updateNodeTemplate({
      variables: { nodeId: id, template_data: { ...(nodes.find(n => n.id === id)?.data as any)?.templateData, color: undefined } },
      optimisticResponse: { updateNodeTemplate: { node: { id, templateData: { ...(nodes.find(n => n.id === id)?.data as any)?.templateData, color: undefined } } } }
    }).catch(e => console.error('Reset color failed for node', id, e))));
    message.success(`Cleared color for ${targetIds.length} node(s)`);
  }, [selectedNode, selectedNodeIds, updateNodeTemplate, nodes, setNodes]);

  const exportNodeStyling = useCallback(() => {
    const styleMap: Record<string, string> = {};
    nodes.forEach(n => {
      const color = (n.data as any)?.templateData?.color;
      if (color) styleMap[n.id] = color;
    });
    const json = JSON.stringify(styleMap, null, 2);
    try {
      navigator.clipboard.writeText(json);
      message.success('Node styling copied to clipboard');
    } catch {
      message.warning('Clipboard copy failed; showing JSON');
      window.prompt('Node Styling JSON:', json);
    }
  }, [nodes]);

  const importNodeStyling = useCallback(async () => {
    const raw = window.prompt('Paste node styling JSON (nodeId -> color)');
    if (!raw) return;
    try {
      const obj = JSON.parse(raw);
      if (typeof obj !== 'object' || Array.isArray(obj)) throw new Error('JSON must be an object mapping nodeId to color');
      const entries = Object.entries(obj) as Array<[string, string]>;
      setNodes(nds => nds.map(n => {
        const match = entries.find(e => e[0] === n.id);
        return match ? { ...n, data: { ...n.data, templateData: { ...(n.data as any).templateData, color: match[1] } } } : n;
      }));
      await Promise.all(entries.map(([id, color]) => updateNodeTemplate({
        variables: { nodeId: id, template_data: { ...(nodes.find(n => n.id === id)?.data as any)?.templateData, color } },
        optimisticResponse: { updateNodeTemplate: { node: { id, templateData: { ...(nodes.find(n => n.id === id)?.data as any)?.templateData, color } } } }
      }).catch(e => console.error('Failed to import style for node', id, e))));
      message.success(`Imported styling for ${entries.length} node(s)`);
    } catch (e: any) {
      console.error(e);
      message.error(e?.message || 'Invalid JSON');
    }
  }, [nodes, updateNodeTemplate, setNodes]);

  // --- UPDATED: Handle Node Click with multi-selection (Shift) ---
  const onNodeClick = useCallback((event: any, node: FlowNode) => {
    if (event.shiftKey) {
      toggleNodeInSelection(node.id);
    } else {
      setExclusiveSelection(node.id);
    }
    setSelectedNode(node.data as AbstractionNodeData);
  }, [setSelectedNode, toggleNodeInSelection, setExclusiveSelection]);

  // Provide a quick inline rename on double-click without opening extra dialogs
  const onNodeDoubleClick = useCallback((event: any, node: FlowNode) => {
    setExclusiveSelection(node.id);
    setSelectedNode(node.data as AbstractionNodeData);
    setEditNodeName((node.data as any)?.layerName || (node.data as any)?.label || '');
    setInlineEditId(node.id);
    // Focus the input in the sidebar shortly after selection
    setTimeout(() => {
      const el = document.querySelector('#node-rename-input') as HTMLInputElement | null;
      if (el) el.focus();
    }, 50);
  }, [setExclusiveSelection, setSelectedNode]);
  // --- END UPDATED ---

  const handleSetNodeColor = useCallback((key: string) => {
    applyColorToNodes(key);
  }, [applyColorToNodes]);

  const handleCaptureSnapshot = useCallback(async () => {
    if (!graphId) return;
    try {
      // Capture the React Flow renderer (contains nodes and edges)
      const wrapper = document.querySelector('.react-flow__renderer') as HTMLElement | null;
      if (!wrapper) {
        message.error('Unable to find graph wrapper for snapshot');
        return;
      }

      const { toPng } = await import('html-to-image');
      const dataUrl = await toPng(wrapper, {
        backgroundColor: '#ffffff',
        pixelRatio: 2,
        cacheBust: true,
      });

      await setGraphSnapshot({
        variables: {
          graphId,
          pngBase64: dataUrl,
        },
        refetchQueries: [{ query: GET_PLAYBOOK_GRAPH_QUERY, variables: { id: graphId } }],
      });

      message.success('Snapshot saved');
    } catch (e: any) {
      // eslint-disable-next-line no-console
      console.error(e);
      message.error(e?.message || 'Failed to capture snapshot');
    }
  }, [graphId, setGraphSnapshot]);

  if (loading) return <p>Loading graph...</p>;
  if (error) return <p className="text-hefaistos-accent-red">Error: {error.message}</p>;
  if (!data?.playbookGraph) return <p>Playbook graph not found.</p>;

  return (
    // --- NEW FLEX CONTAINER ---
    <div className="flex flex-row w-full h-full" style={{ height: 'calc(100vh - 150px)' }}>

      {/* --- Main Content (Graph) --- */}
      {/* Make the graph area wider for better capability mapping */}
      <div className="flex-[1.25] flex flex-col h-full">
        {/* --- UPDATED HEADER WITH ADD NODE BUTTON --- */}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold">{data.playbookGraph.title}</h2>
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={handleAddNode}>
              <PixelIcon name="add" className="w-5 h-5 mr-2" />
              Add Node
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                const targetIds = selectedNodeIds.length ? selectedNodeIds : (selectedNode ? [selectedNode.id] : []);
                if (!targetIds.length) { message.info('Select a node to delete'); return; }
                try {
                  await Promise.all(targetIds.map(id => deleteNode({ variables: { nodeId: id } })));
                  setInlineEditId('');
                  setSelectedNode(undefined as any);
                  setSelectedNodeIds([]);
                  await refetch();
                  message.success(`Deleted ${targetIds.length} node(s)`);
                } catch (e) {
                  console.error(e);
                  message.error('Failed to delete');
                }
              }}
            >Delete</Button>
            <Button variant="secondary" onClick={handleCaptureSnapshot} disabled={savingSnapshot}>
              <PixelIcon name="camera" className="w-5 h-5 mr-2" />
              {savingSnapshot ? 'Saving...' : 'Snapshot'}
            </Button>
          </div>
        </div>
        <div className="w-full h-full bg-white border-2 border-hefaistos-border rounded-lg shadow-md">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeDragStop={onNodeDragStop}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            nodeTypes={nodeTypes}
            onConnect={onConnect}
            onEdgesDelete={onEdgesDelete}
            fitView
          >
            <Controls />
            <Background />
          </ReactFlow>
        </div>
      </div>

      {/* --- NEW: Sidebar for Abstraction Capability metadata --- */}
      {/* Slightly narrower sidebar to give the canvas more room */}
      <div className="w-80 ml-4 flex flex-col h-full bg-white border-2 border-hefaistos-border rounded-lg shadow-md p-4 overflow-y-auto">
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          Abstraction Capability
        </Typography.Title>
        {selectedNode && (
          <div style={{ marginTop: 8 }}>
            <Typography.Text strong>Selection & Styling</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
              {selectedNodeIds.length > 1 ? (
                <>Apply a highlight color to <strong>{selectedNodeIds.length}</strong> selected nodes for visual grouping.</>
              ) : (
                <>Apply a highlight color to <strong>{selectedNode.layerName}</strong> for visual grouping.</>
              )}
            </Typography.Paragraph>
            {/* Optional: Sanitize pseudo/rule content in the selected node's templateData */}
            {(() => {
              const td = (selectedNode as any)?.templateData || {};
              const ruleCandidate: string | undefined = td?.detectionRule || td?.rule;
              if (!ruleCandidate) return null;
              return (
                <Button
                  variant="secondary"
                  style={{ marginBottom: 8 }}
                  onClick={async () => {
                    const sanitized = sanitizeCodeFences(ruleCandidate);
                    try {
                      await updateNodeTemplate({
                        variables: { nodeId: selectedNode.id, template_data: { ...td, detectionRule: sanitized } },
                        optimisticResponse: { updateNodeTemplate: { node: { id: selectedNode.id, templateData: { ...td, detectionRule: sanitized } } } }
                      });
                      setSelectedNode({ ...(selectedNode as any), templateData: { ...td, detectionRule: sanitized } } as any);
                      message.success('Sanitized rule content');
                    } catch (e) {
                      console.error(e);
                      message.error('Failed to sanitize');
                    }
                  }}
                >Sanitize Rule</Button>
              );
            })()}
            {selectedNodeIds.length === 1 && (
              <div style={{ marginBottom: 12 }}>
                <Typography.Text strong>Node Name</Typography.Text>
                <Input
                  id="node-rename-input"
                  size="small"
                  style={{ marginTop: 4 }}
                  value={editNodeName}
                  onChange={e => {
                    const newName = e.target.value;
                    setEditNodeName(newName);
                  }}
                  onPressEnter={async e => {
                    const finalName = editNodeName.trim();
                    if (!finalName) return;
                    try {
                      await updateNodeName({
                        variables: { nodeId: selectedNode.id, layerName: finalName },
                        optimisticResponse: {
                          updatePlaybookNodeLayerName: { node: { id: selectedNode.id, layerName: finalName } }
                        }
                      });
                      setSelectedNode({ ...selectedNode, layerName: finalName });
                      setNodes(nds => nds.map(n => n.id === selectedNode.id ? { ...n, data: { ...n.data, layerName: finalName, label: finalName } } : n));
                      message.success('Node renamed');
                    } catch (err) {
                      console.error(err);
                      message.error('Rename failed');
                    }
                  }}
                />
                <div className="flex gap-2 mt-2">
                  <Button
                    variant="primary"
                    onClick={async () => {
                      const finalName = editNodeName.trim();
                      if (!finalName) { message.warning('Name cannot be empty'); return; }
                      try {
                        await updateNodeName({
                          variables: { nodeId: selectedNode.id, layerName: finalName },
                          optimisticResponse: {
                            updatePlaybookNodeLayerName: { node: { id: selectedNode.id, layerName: finalName } }
                          }
                        });
                        setSelectedNode({ ...selectedNode, layerName: finalName });
                        setNodes(nds => nds.map(n => n.id === selectedNode.id ? { ...n, data: { ...n.data, layerName: finalName, label: finalName } } : n));
                        message.success('Node renamed');
                      } catch (err) {
                        console.error(err);
                        message.error('Rename failed');
                      }
                    }}
                  >Save</Button>
                  <Button
                    variant="secondary"
                    onClick={() => setEditNodeName(selectedNode.layerName || '')}
                  >Reset</Button>
                </div>
              </div>
            )}
            {selectedNodeIds.length > 0 && (
              <Typography.Paragraph type="secondary" style={{ marginTop: -4 }}>
                Selected IDs: {selectedNodeIds.slice(0, 5).join(', ')}{selectedNodeIds.length > 5 ? '…' : ''}
              </Typography.Paragraph>
            )}
            <Space wrap>
              {colorPalette.map(c => (
                <Button
                  key={c.key}
                  variant="secondary"
                  style={{
                    backgroundColor: c.hex,
                    border: selectedNode.templateData?.color === c.key && selectedNodeIds.length <= 1 ? '2px solid #555' : '1px solid #ccc',
                    padding: '6px 12px'
                  }}
                  onClick={() => handleSetNodeColor(c.key)}
                >
                  {c.label}
                </Button>
              ))}
              <Button variant="secondary" onClick={resetColorsForSelection}>Clear Color</Button>
              <Button variant="secondary" onClick={exportNodeStyling}>Export</Button>
              <Button variant="secondary" onClick={importNodeStyling}>Import</Button>
            </Space>
          </div>
        )}

        <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
          This graph is an abstraction capability enhancement. Use notes and links
          below to attach it to one or more Detection Playbooks.
        </Typography.Paragraph>

        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <Typography.Text strong>Attached Detection Playbooks</Typography.Text>
            <Select
              mode="multiple"
              allowClear
              style={{ width: '100%', marginTop: 4 }}
              placeholder="Select playbooks to attach"
              value={attachedPlaybookIds}
              onChange={setAttachedPlaybookIds}
              options={(playbooksData?.allPlaybooks || []).map(p => ({
                label: p.title,
                value: p.id,
              }))}
            />
          </div>

          <div>
            <Typography.Text strong>Notes</Typography.Text>
            <TextArea
              rows={8}
              style={{ marginTop: 4 }}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Document abstraction logic, assumptions, or mapping between behaviors and detections."
            />
          </div>

          <div>
            <Typography.Text strong>Snapshot</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
              Capture a PNG snapshot of the current graph canvas and attach it to
              linked Detection Playbooks.
            </Typography.Paragraph>
            <Space>
              <Button
                variant="secondary"
                disabled={savingSnapshot}
                onClick={handleCaptureSnapshot}
              >
                <PixelIcon name="camera" className="w-5 h-5 mr-2" />
                {savingSnapshot ? 'Saving...' : 'Capture Snapshot'}
              </Button>
              {data.playbookGraph.pngSnapshotUrl && (
                <Link to={data.playbookGraph.pngSnapshotUrl} target="_blank" rel="noopener noreferrer">
                  View last snapshot
                </Link>
              )}
            </Space>
          </div>

          <div style={{ marginTop: 8 }}>
            <Button
              variant="primary"
              onClick={handleSaveMetadata}
              disabled={savingMetadata}
            >
              <PixelIcon name="save" className="w-5 h-5 mr-2" />
              {savingMetadata ? 'Saving…' : 'Send to detection playbook'}
            </Button>
          </div>
        </Space>
      </div>

    </div>
    // --- END NEW LAYOUT ---
  );
};