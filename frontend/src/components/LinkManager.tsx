import React, { useEffect, useMemo, useState } from 'react';
import { gql, DocumentNode } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Select, message } from 'antd';
// Removed dependency on deprecated PlaybookDetailPage query

// Define the update mutation
const UPDATE_PLAYBOOK_LINKS_MUTATION = gql`
  mutation UpdatePlaybookLinks(
    $playbookId: UUID!,
    $detectionRuleIds: [ID!],
    $dataSourceIds: [ID!],
    $mitreAttackIds: [ID!],
    $mitreEngageIds: [ID!],
    $mitreIcsIds: [ID!],
    $mitreMobileIds: [ID!]
  ) {
    updatePlaybookLinks(
      playbookId: $playbookId,
      detectionRuleIds: $detectionRuleIds,
      dataSourceIds: $dataSourceIds,
      mitreAttackIds: $mitreAttackIds,
      mitreEngageIds: $mitreEngageIds,
      mitreIcsIds: $mitreIcsIds,
      mitreMobileIds: $mitreMobileIds
    ) {
      playbook {
        id
        detectionRules { id title }
        requiredDataSources { id name }
        mitreAttackMappings { id techniqueId name url }
        mitreEngageMappings { id engageId name url }
        mitreIcsMappings { id techniqueId name url }
        mitreMobileMappings { id techniqueId name url }
      }
    }
  }
`;

// --- TypeScript Interfaces ---
interface Option {
  value: string;
  label: string;
}

interface LinkableItem {
  id: string;
  name?: string; // For DataSources and techniques
  title?: string; // For Rules
  // Framework-specific identifiers (optional)
  techniqueId?: string;
  d3fendId?: string;
  engageId?: string;
}

interface LinkManagerProps {
  playbookId: string;
  linkType: 'rules' | 'dataSources' | 'attack' | 'engage' | 'ics' | 'mobile';
  availableItemsQuery: DocumentNode;
  queryDataKey: string; // The key in the query response, e.g., 'searchRules' or 'allDataSources'
  buildVariables?: (search?: string) => Record<string, any>; // Optional variables builder for remote search
  currentItems: LinkableItem[]; // Corrected to be an array of LinkableItem
}

export const LinkManager: React.FC<LinkManagerProps> = ({
  playbookId,
  linkType,
  availableItemsQuery,
  queryDataKey,
  currentItems,
  buildVariables,
}) => {
  // Use a proper type for data if possible, for now keeping it simple
  const { data: allItemsData, loading: itemsLoading, refetch } = useQuery<{ [key: string]: LinkableItem[] }>(
    availableItemsQuery,
    { variables: buildVariables ? buildVariables() : undefined }
  );

  const [updatePlaybookLinks, { loading: updateLoading }] = useMutation(UPDATE_PLAYBOOK_LINKS_MUTATION);

  // Compute options and current values
  const itemOptions: Option[] = useMemo(() => (
    allItemsData?.[queryDataKey]?.map((item: LinkableItem) => {
      const code = item.techniqueId || item.engageId;
      const text = item.title || item.name || 'Unknown';
      return {
        value: item.id,
        label: code ? `${code}: ${text}` : text,
      };
    }) || []
  ), [allItemsData, queryDataKey]);

  const initialValues: string[] = useMemo(() => (
    currentItems.map(item => item.id)
  ), [currentItems]);

  // Local selection state so selection feels responsive even before refetch completes
  const [selectedValues, setSelectedValues] = useState<string[]>(initialValues);

  // Keep local selection in sync when props change (after refetch)
  useEffect(() => {
    setSelectedValues(initialValues);
  }, [initialValues]);

  const handleLinkChange = (itemIds: string[]) => {
    setSelectedValues(itemIds);
    const variables: {
      playbookId: string;
      detectionRuleIds?: string[];
      dataSourceIds?: string[];
      mitreAttackIds?: string[];
      mitreD3fendIds?: string[];
      mitreEngageIds?: string[];
      mitreIcsIds?: string[];
      mitreMobileIds?: string[];
    } = { playbookId };
    if (linkType === 'rules') variables.detectionRuleIds = itemIds;
    else if (linkType === 'dataSources') variables.dataSourceIds = itemIds;
    else if (linkType === 'attack') variables.mitreAttackIds = itemIds;
    // d3fend support removed
    else if (linkType === 'engage') variables.mitreEngageIds = itemIds;
    else if (linkType === 'ics') variables.mitreIcsIds = itemIds;
    else if (linkType === 'mobile') variables.mitreMobileIds = itemIds;

    updatePlaybookLinks({ variables })
      .then(() => message.success('Links updated'))
      .catch((e) => {
        // eslint-disable-next-line no-console
        console.error(e);
        message.error('Failed to update links');
      });
  };

  const handleSearch = async (value: string) => {
    if (!buildVariables) return; // No-op if not provided
    try {
      await refetch(buildVariables(value));
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <Select
      mode="multiple"
      loading={itemsLoading || updateLoading}
      onChange={handleLinkChange}
      onSearch={handleSearch}
      options={itemOptions}
      value={selectedValues}
      placeholder={`Link ${linkType}...`}
      style={{ minWidth: 280 }}
      allowClear
      showSearch
      optionFilterProp="label"
    />
  );
};
