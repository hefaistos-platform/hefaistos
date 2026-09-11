import React, { createContext, useContext, useEffect, useState, useMemo } from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';

const PLAYBOOK_META_QUERY = gql`
  query GetPlaybookMeta { playbookMeta }
`;

export interface PlaybookChoice { value: string | number; label: string }
export interface TechniqueItem { id: string; techniqueId?: string; d3fendId?: string; engageId?: string; name: string }
export interface PlaybookMetaData {
  robustnessLevels: PlaybookChoice[];
  eventRobustness: PlaybookChoice[];
  statuses: PlaybookChoice[];
  playbookTypes: PlaybookChoice[];
  attackTechniques: TechniqueItem[];
  d3fendTechniques: TechniqueItem[];
  engageTechniques: TechniqueItem[];
  icsTechniques: TechniqueItem[];
  mobileTechniques: TechniqueItem[];
}

interface MetaContextValue {
  loading: boolean;
  error?: Error;
  data?: PlaybookMetaData;
  byRobustness?: Record<number, string>;
  byEventRobustness?: Record<string, string>;
  byStatus?: Record<string, string>;
  byType?: Record<string, string>;
  refresh: () => void;
}

const PlaybookMetaContext = createContext<MetaContextValue | undefined>(undefined);

export const PlaybookMetaProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { data, loading, error, refetch } = useQuery<{ playbookMeta: string }>(PLAYBOOK_META_QUERY, { fetchPolicy: 'cache-first' });
  const [parsed, setParsed] = useState<PlaybookMetaData | undefined>(undefined);

  useEffect(() => {
    if (!data?.playbookMeta) return;
    try {
      const json = JSON.parse(data.playbookMeta);
      setParsed(json);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Failed to parse playbookMeta JSON', e);
    }
  }, [data]);

  const maps = useMemo(() => {
    if (!parsed) {
      return {
        byRobustness: {},
        byEventRobustness: {},
        byStatus: {},
        byType: {},
      };
    }
    const byRobustness: Record<number, string> = {};
    (parsed.robustnessLevels || []).forEach(c => { if (typeof c.value === 'number') byRobustness[c.value] = c.label; });
    const byEventRobustness: Record<string, string> = {};
    (parsed.eventRobustness || []).forEach(c => { byEventRobustness[String(c.value)] = c.label; });
    const byStatus: Record<string, string> = {};
    (parsed.statuses || []).forEach(c => { byStatus[String(c.value)] = c.label; });
    const byType: Record<string, string> = {};
    (parsed.playbookTypes || []).forEach(c => { byType[String(c.value)] = c.label; });
    return { byRobustness, byEventRobustness, byStatus, byType };
  }, [parsed]);

  const value: MetaContextValue = {
    loading,
    error: error as Error | undefined,
    data: parsed,
    ...maps,
    refresh: () => { refetch(); },
  };

  return <PlaybookMetaContext.Provider value={value}>{children}</PlaybookMetaContext.Provider>;
};

export const usePlaybookMeta = () => {
  const ctx = useContext(PlaybookMetaContext);
  if (!ctx) throw new Error('usePlaybookMeta must be used within PlaybookMetaProvider');
  return ctx;
};
