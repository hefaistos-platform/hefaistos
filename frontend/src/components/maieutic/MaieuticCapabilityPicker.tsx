import React from 'react';
import { gql, useQuery } from '@apollo/client';
import { Alert, Select, Tag, Typography } from 'antd';

const { Text, Paragraph } = Typography;

export const CAPABILITIES_QUERY = gql`
  query MaieuticCapabilities($technique: String!) {
    capabilityAbstractions(techniqueId: $technique, includeBaseline: true) {
      id abstractionLayer componentArtifact adversaryPurpose commonEvasions isSharedBaseline
    }
  }
`;

export const LAYERS: { value: string; label: string }[] = [
  { value: 'TOOL', label: 'Tool / Binary' },
  { value: 'API_EXPORT', label: 'API / Export' },
  { value: 'COM_IPC', label: 'COM / IPC' },
  { value: 'REGISTRY_OBJECT', label: 'Registry Object' },
  { value: 'PROTOCOL', label: 'Protocol' },
  { value: 'PROCESS_BEHAVIOR', label: 'Process Behavior' },
  { value: 'NETWORK_BEHAVIOR', label: 'Network Behavior' },
];
const layerLabel = (v: string) => LAYERS.find((l) => l.value === v)?.label ?? v;

/** Library ids the user picked that are not offered for the current technique, so the server will ignore them. */
export const staleRefs = (refs: string[], offered: string[]): string[] => refs.filter((r) => !offered.includes(r));

/**
 * Optional: tell the rule generator which Capability Library entries and which layer to prioritise.
 * It is a pick, nothing is filled in for the user and no evasion question is answered by it.
 */
export const MaieuticCapabilityPicker: React.FC<{
  techniqueId?: string;
  refs: string[];
  focusLayer: string;
  onChange: (next: { capability_refs: string[]; focus_layer: string }) => void;
}> = ({ techniqueId, refs, focusLayer, onChange }) => {
  const { data, loading, error } = useQuery(CAPABILITIES_QUERY, { variables: { technique: techniqueId }, skip: !techniqueId });
  const entries: any[] = Array.isArray(data?.capabilityAbstractions) ? data.capabilityAbstractions : [];
  const offered = entries.map((e) => e.id);
  const loaded = !!techniqueId && !loading && !error && !!data;
  const stale = loaded ? staleRefs(refs, offered) : [];
  const picked = entries.filter((e) => refs.includes(e.id));

  return (
    <div data-testid="capability-picker">
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        Optional. This only tells the rule generator what to prioritise. It does not answer any evasion question for you.
      </Paragraph>

      <div style={{ marginBottom: 12 }}>
        <Text strong style={{ fontSize: 12 }}>Library entries</Text>
        {!techniqueId && (
          <div><Text type="secondary">Entries are offered once you have chosen an ATT&amp;CK technique in step 1.</Text></div>
        )}
        {techniqueId && loading && <div><Text type="secondary">Loading the library…</Text></div>}
        {techniqueId && error && <Alert type="error" showIcon message="Could not load the Capability Library." style={{ marginTop: 4 }} />}
        {loaded && !entries.length && (
          <div><Text type="secondary">The library has no entries for {techniqueId} yet.</Text></div>
        )}
        {loaded && entries.length > 0 && (
          <Select
            mode="multiple" style={{ width: '100%', maxWidth: 700, display: 'block' }} aria-label="Capability Library entries"
            placeholder="Pick the entries that describe how this technique is done"
            value={refs.filter((r) => offered.includes(r))} optionFilterProp="label"
            options={entries.map((e) => ({ value: e.id, label: `${layerLabel(e.abstractionLayer)}: ${e.componentArtifact}` }))}
            onChange={(ids) => onChange({ capability_refs: ids as string[], focus_layer: focusLayer })}
          />
        )}
        {stale.length > 0 && (
          <Alert type="warning" showIcon style={{ marginTop: 6, maxWidth: 700 }}
            message={`${stale.length} earlier pick(s) do not belong to ${techniqueId} and will be ignored. Choose again to remove them.`} />
        )}
      </div>

      {picked.map((e) => (
        <div key={e.id} data-testid={`cap-${e.id}`} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, marginBottom: 6, maxWidth: 700 }}>
          <Tag>{layerLabel(e.abstractionLayer)}</Tag><Text strong>{e.componentArtifact}</Text>
          {e.isSharedBaseline && <Tag color="blue" style={{ marginLeft: 6 }}>shared baseline</Tag>}
          {e.adversaryPurpose && <div><Text type="secondary">Purpose (from the library): {e.adversaryPurpose}</Text></div>}
          {e.commonEvasions && <div><Text type="secondary">Known evasions (from the library): {e.commonEvasions}</Text></div>}
        </div>
      ))}

      <div style={{ marginTop: 8 }}>
        <Text strong style={{ fontSize: 12 }}>Focus layer</Text>
        <Select
          allowClear style={{ width: 260, display: 'block' }} aria-label="Focus layer" placeholder="No preference"
          value={focusLayer || undefined} options={LAYERS}
          onChange={(v) => onChange({ capability_refs: refs, focus_layer: v ?? '' })}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>The rule generator will prefer detecting at this layer.</Text>
      </div>
    </div>
  );
};

export default MaieuticCapabilityPicker;
