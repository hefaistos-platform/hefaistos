import React, { useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useLazyQuery, useMutation } from '@apollo/client/react';
import { Button } from '../ui/Button';
import { App } from 'antd';
import { useNavigate } from 'react-router-dom';

// --- QUERIES ---

// 1. Search Techniques (for the dropdown)
const SEARCH_TECHNIQUES_QUERY = gql`
  query SearchTechniques($search: String!) {
    searchTechniques(search: $search) {
      id
      techniqueId
      name
    }
  }
`;

// 2. Get Suggestions (Updated for v18 Strategy Model)
const GET_SUGGESTIONS_QUERY = gql`
  query GetSuggestions($techniqueId: String!) {
    detectionSuggestions(techniqueId: $techniqueId) {
      technique {
        id
        techniqueId
        name
      }
      # We use STRATEGIES now, as Data Components are not linked in the Excel export
      strategies {
        id
        defId
        name
        url
        analytics {
          id
          name
          description
        }
      }
    }
  }
`;

const ENRICH_ANALYTIC_QUERY = gql`
  query EnrichAnalytic($url: String!, $analyticId: String!) {
    enrichAnalyticData(strategyUrl: $url, analyticId: $analyticId)
  }
`;

// Fetch JSON Data for interactive table
const ENRICH_ANALYTIC_JSON_QUERY = gql`
  query EnrichAnalyticJson($url: String!, $analyticId: String!) {
    enrichAnalyticJson(strategyUrl: $url, analyticId: $analyticId) {
      dataComponent
      logProvider
      channel
    }
  }
`;

const GET_CATALOG_RESOURCES_QUERY = gql`
  query GetCatalogResourcesForMitreMatch {
    allDataSources {
      id
      name
      description
      fields {
        fieldName
        exampleValue
      }
    }
  }
`;

// Add Data Source directly to Data Catalog (visible in catalog UI)
const CREATE_SOURCE_MUTATION = gql`
  mutation AddDataSource($name: String!, $platform: String, $description: String) {
    createDataSource(name: $name, platform: $platform, description: $description) {
      dataSource { id name }
    }
  }
`;

// Add structured fields to the newly created Data Source
const ADD_DATA_SOURCE_FIELD_MUTATION = gql`
  mutation AddField($dataSourceId: ID!, $fieldName: String!, $dataType: String, $description: String, $exampleValue: String) {
    addDataSourceField(
      dataSourceId: $dataSourceId,
      fieldName: $fieldName,
      dataType: $dataType,
      description: $description,
      exampleValue: $exampleValue
    ) {
      dataSourceField { id fieldName }
    }
  }
`;

interface Technique {
  id: string;
  techniqueId: string;
  name: string;
}

interface Analytic {
  id: string;
  name: string;
  description: string;
}

interface Strategy {
  id: string;
  defId: string;
  name: string;
  url: string;
  analytics: Analytic[];
}

interface SearchTechniquesData {
  searchTechniques: Technique[];
}

interface DetectionSuggestionsData {
  detectionSuggestions: {
    technique: Technique;
    strategies: Strategy[];
  } | null;
}

interface EnrichAnalyticData {
  enrichAnalyticData: string;
}

interface LiveLogSource {
  dataComponent: string;
  logProvider: string;
  channel: string;
}

interface EnrichAnalyticJsonData {
  enrichAnalyticJson: LiveLogSource[];
}

interface CatalogField {
  fieldName: string;
  exampleValue: string | null;
}

interface CatalogDataSource {
  id: string;
  name: string;
  description: string | null;
  fields: CatalogField[];
}

interface CatalogResourcesData {
  allDataSources: CatalogDataSource[];
}

interface StrategyProps {
  selectedTechniqueId: string | null;
  onTechniqueChange: (t: any) => void;
  onStrategyChange: (strategy: any) => void; // Passes data back to parent
  ruleFormat?: 'KQL' | 'WAZUH' | 'SPL' | 'AQL';
}

// Simple UUID generator for non-secure contexts
const generateUUID = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0, v = c === 'x' ? r : ((r & 0x3) | 0x8);
    return v.toString(16);
  });
};

const normalizeToken = (value: string | null | undefined) =>
  (value || '').trim().replace(/\s+/g, ' ').toLowerCase();

const normalizeFieldName = (fieldName: string | null | undefined) =>
  normalizeToken(fieldName).replace(/[^a-z0-9]+/g, '');

const buildProviderChannelKey = (provider: string | null | undefined, channel: string | null | undefined) => {
  const normalizedProvider = normalizeToken(provider);
  const normalizedChannel = normalizeToken(channel);
  if (!normalizedProvider || !normalizedChannel) return '';
  return `${normalizedProvider}||${normalizedChannel}`;
};

const parseMitreDescription = (value: string | null | undefined) => {
  if (!value) return null;
  const match = value.match(/Auto-added from MITRE strategy:\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$/i);
  if (!match) return null;
  return {
    dataComponent: match[1],
    provider: match[2],
    channel: match[3],
  };
};

export const DetectionStrategy = React.memo<StrategyProps>(({ selectedTechniqueId, onTechniqueChange, onStrategyChange, ruleFormat = 'KQL' }) => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  
  // Track the last used technique to prevent UI reset during async operations
  const lastTechniqueRef = React.useRef<string | null>(selectedTechniqueId);
  const isProcessingRef = React.useRef(false);
  
  // Persist selected strategy and analytic across re-renders
  const selectedStrategyRef = React.useRef<string | null>(null);
  const selectedAnalyticRef = React.useRef<string | null>(null);
  
  // Update ref when strategy selection changes
  React.useEffect(() => {
    selectedStrategyRef.current = selectedStrategyId;
  }, [selectedStrategyId]);
  
  // Update ref when technique changes from parent (but not during processing)
  React.useEffect(() => {
    if (!isProcessingRef.current && selectedTechniqueId) {
      lastTechniqueRef.current = selectedTechniqueId;
    }
  }, [selectedTechniqueId]);
  
  // Use the stable technique ID (prevents flicker during async ops)
  const stableTechniqueId = selectedTechniqueId || lastTechniqueRef.current;
  
  // New State for the Live Data Table - use ref to persist across re-renders
  const [liveLogSources, setLiveLogSources] = useState<LiveLogSource[]>([]);
  const liveLogSourcesRef = React.useRef<LiveLogSource[]>([]);
  
  // Sync ref with state
  React.useEffect(() => {
    liveLogSourcesRef.current = liveLogSources;
  }, [liveLogSources]);
  
  // Restore liveLogSources from ref if state was cleared during re-render
  React.useEffect(() => {
    if (isProcessingRef.current && liveLogSources.length === 0 && liveLogSourcesRef.current.length > 0) {
      setLiveLogSources(liveLogSourcesRef.current);
    }
  }, [liveLogSources]);

  // 1. Technique Search
  const { data: techData } = useQuery<SearchTechniquesData>(SEARCH_TECHNIQUES_QUERY, {
    variables: { search: searchTerm },
    skip: searchTerm.length < 3
  });

  // 2. Get Suggestions based on selected technique (use stable ID to prevent flicker)
  const { data: suggestionData } = useQuery<DetectionSuggestionsData>(GET_SUGGESTIONS_QUERY, {
    variables: { techniqueId: stableTechniqueId },
    skip: !stableTechniqueId
  });
  
  // Restore selectedStrategyId from ref if it was cleared during re-render
  // NOTE: This must be after suggestionData is declared
  React.useEffect(() => {
    if (isProcessingRef.current && selectedStrategyId === null && selectedStrategyRef.current !== null) {
      // Check if the strategy still exists in the data
      const strategyExists = suggestionData?.detectionSuggestions?.strategies?.some(
        (s: any) => s.id === selectedStrategyRef.current
      );
      if (strategyExists) {
        setSelectedStrategyId(selectedStrategyRef.current);
      }
    }
  }, [selectedStrategyId, suggestionData]);

  // Use Lazy Query (triggered manually)
  const [enrichAnalytic, { loading: enriching }] = useLazyQuery<EnrichAnalyticData>(ENRICH_ANALYTIC_QUERY);
  
  // Lazy Query for JSON data (for interactive table)
  const [getLiveJson] = useLazyQuery<EnrichAnalyticJsonData>(ENRICH_ANALYTIC_JSON_QUERY);
  
  // Mutation to add source to Data Catalog
  interface CreateDataSourceResult { createDataSource: { dataSource: { id: string, name: string } } }
  interface CreateDataSourceVars { name: string; platform?: string; description?: string }
  const [addSource] = useMutation<CreateDataSourceResult, CreateDataSourceVars>(CREATE_SOURCE_MUTATION);
  const [addField] = useMutation(ADD_DATA_SOURCE_FIELD_MUTATION);
  const { data: catalogResourcesData, refetch: refetchCatalogResources } = useQuery<CatalogResourcesData>(GET_CATALOG_RESOURCES_QUERY);

  const existingCatalogIndex = useMemo(() => {
    const names = new Set<string>();
    const providerChannel = new Set<string>();
    const components = new Set<string>();

    for (const source of catalogResourcesData?.allDataSources || []) {
      const nameKey = normalizeToken(source.name);
      if (nameKey) names.add(nameKey);

      const fieldMap: Record<string, string> = {};
      for (const field of source.fields || []) {
        const normalizedField = normalizeFieldName(field.fieldName);
        const normalizedValue = normalizeToken(field.exampleValue);
        if (!normalizedField || !normalizedValue) continue;
        if (!fieldMap[normalizedField]) {
          fieldMap[normalizedField] = normalizedValue;
        }
      }

      if (fieldMap.provider && fieldMap.channel) {
        const key = buildProviderChannelKey(fieldMap.provider, fieldMap.channel);
        if (key) providerChannel.add(key);
      }
      if (fieldMap.datacomponent) {
        components.add(fieldMap.datacomponent);
      }

      const parsed = parseMitreDescription(source.description);
      if (parsed) {
        const parsedProviderChannel = buildProviderChannelKey(parsed.provider, parsed.channel);
        if (parsedProviderChannel) providerChannel.add(parsedProviderChannel);
        const parsedComponent = normalizeToken(parsed.dataComponent);
        if (parsedComponent) components.add(parsedComponent);
      }
    }

    return { names, providerChannel, components };
  }, [catalogResourcesData]);

  const isResourceAlreadyAdded = (row: LiveLogSource) => {
    const byName = existingCatalogIndex.names.has(normalizeToken(`${row.logProvider} - ${row.channel}`));
    const byProviderChannel = existingCatalogIndex.providerChannel.has(
      buildProviderChannelKey(row.logProvider, row.channel)
    );
    const byComponent = existingCatalogIndex.components.has(normalizeToken(row.dataComponent));
    return byName || byProviderChannel || byComponent;
  };

  // Handler for the "+ Add" button in the table
    const handleAddFromMitre = async (row: LiveLogSource) => {
        if (isResourceAlreadyAdded(row)) {
          message.info('Resource already added');
          return;
        }

        const name = `${row.logProvider} - ${row.channel}`;
        const providerLc = (row.logProvider || '').toLowerCase();
        let platformGuess: string | undefined;
        if (providerLc.includes('wineventlog') || providerLc.includes('sysmon') || providerLc.includes('windows')) {
          platformGuess = 'Windows';
        } else if (providerLc.includes('auditd') || providerLc.includes('syslog') || providerLc.includes('journald') || providerLc.includes('systemd')) {
          platformGuess = 'Linux';
        } else if (providerLc.includes('osquery') || providerLc.includes('endpointsecurity') || providerLc.includes('unified log') || providerLc.includes('macos') || providerLc.includes('darwin')) {
          platformGuess = 'macOS';
        }

        const description = `Auto-added from MITRE strategy: ${row.dataComponent} | ${row.logProvider} | ${row.channel}`;
        try {
            const { data } = await addSource({
                variables: {
                    name,
                    platform: platformGuess,
                    description,
                }
            });
            const id = data?.createDataSource?.dataSource?.id;
            if (id) {
              // Store the structured MITRE row as fields on the Data Source
              const metaDesc = 'Imported from MITRE live data via Detection Strategy';
              await Promise.all([
                addField({ variables: { dataSourceId: id, fieldName: 'data_component', dataType: 'string', description: metaDesc, exampleValue: row.dataComponent } }),
                addField({ variables: { dataSourceId: id, fieldName: 'provider', dataType: 'string', description: metaDesc, exampleValue: row.logProvider } }),
                addField({ variables: { dataSourceId: id, fieldName: 'channel', dataType: 'string', description: metaDesc, exampleValue: row.channel } }),
              ]);
            }
            message.success({
              content: (
                <span>
                  Added "{name}" to Data Catalog.{' '}
                  <button type="button" className="text-blue-600 underline" onClick={() => navigate(id ? `/catalog/${id}` : '/catalog')}>
                    View in Catalog
                  </button>
                </span>
              ),
              duration: 4,
            });
            refetchCatalogResources().catch(() => undefined);
        } catch (e: any) {
          const raw = e?.message || '';
          let reason = '';
          if (/already exists|duplicate/i.test(raw)) reason = 'Object already exists';
          else if (/unique|conflict/i.test(raw)) reason = 'Event already added';
          else if (/permission|forbidden|denied/i.test(raw)) reason = 'Permission denied';
          message.error(`Failed to add source to Data Catalog.${reason ? ` ${reason}.` : ''}`);
          if (/already exists|duplicate|unique|conflict/i.test(raw)) {
            refetchCatalogResources().catch(() => undefined);
          }
        }
    };

  // Logic to handle Analytic Selection
  const handleAnalyticSelect = async (analytic: any, strategy: any, technique: any) => {
     isProcessingRef.current = true; // Prevent UI reset during async operation
     selectedAnalyticRef.current = analytic.id; // Track selected analytic
     
     // Don't clear liveLogSources immediately - wait until we have new data
     let richContext = "# Fetching live data from MITRE...";
     let logSourcesForEditor = "# Fetching live data...";
     let fetchedRows: LiveLogSource[] = [];
     
     // 1. Fetch Live Data
     // Robust ID extraction: "Analytic 0016" -> "AN0016"
     const analyticCode = analytic.name.replace("Analytic ", "AN"); 
     
     if (strategy.url) {
         try {
             // Fetch text data for the editor
             const result = await enrichAnalytic({
                 variables: {
                     url: strategy.url,
                     analyticId: analyticCode
                 }
             });
             if (result.data?.enrichAnalyticData) {
                 richContext = result.data.enrichAnalyticData;
             }
             
             // Fetch JSON data for the interactive table
             const jsonResult = await getLiveJson({
                 variables: { url: strategy.url, analyticId: analyticCode }
             });
             
             if (jsonResult.data?.enrichAnalyticJson) {
                 fetchedRows = jsonResult.data.enrichAnalyticJson;
                 // Don't set state here - we'll set it after onStrategyChange completes
                 
                 // Build text string for the Editor
                 if (fetchedRows.length > 0) {
                     logSourcesForEditor = "# [LIVE DATA: LOG SOURCES]\n" + 
                     `# ${'Data Component'.padEnd(30)} | ${'Log Provider'.padEnd(20)} | Channel\n` +
                     `# ${'-'.repeat(30)} | ${'-'.repeat(20)} | ${'-'.repeat(15)}\n` +
                     fetchedRows.map((r) => `# ${r.dataComponent.padEnd(30)} | ${r.logProvider.padEnd(20)} | ${r.channel}`).join('\n');
                 } else {
                     logSourcesForEditor = "# No specific log sources found on MITRE page.";
                 }
             }
         } catch (e) {
             richContext = "# [ERROR] Failed to fetch live data.";
             logSourcesForEditor = "# [ERROR] Failed to fetch live data.";
         }
     }

     // 2. Generate the "Perfect" Template based on selected format
     const cmt = ruleFormat === 'SPL' ? '`' : (ruleFormat === 'AQL' ? '--' : '//');
     const ruleTitle = `${strategy.name} - ${analytic.name}`;
     const ruleDesc = analytic.description.replace(/\n/g, ' ');
     const ruleDate = new Date().toISOString().split('T')[0];

     // Re-prefix context/log-source lines for non-KQL formats
     const pfx = (text: string) => {
       if (ruleFormat === 'WAZUH') {
         const stripped = text.replace(/^# ?/gm, '').trim();
         return stripped ? `<!-- ${stripped.replace(/\n/g, '\n     ')} -->` : '';
       }
       return text.replace(/^# /gm, `${cmt} `).replace(/^#$/gm, cmt);
     };

     const headerLines = [
       `----------------------------------------------------------------------`,
       `MITRE ATT&CK DETECTION LOGIC`,
       `----------------------------------------------------------------------`,
       `Strategy:       ${strategy.name}`,
       `Analytic:       ${analytic.name}`,
       `Technique:      ${technique.name} (${technique.techniqueId})`,
       `URL:            ${strategy.url}#${analyticCode}`,
       ``,
       `[DESCRIPTION]`,
       `${analytic.description.replace(/\n/g, `\n`)}`,
     ];

     let headerBlock: string;
     if (ruleFormat === 'WAZUH') {
       headerBlock = `<!-- ${headerLines.join('\n     ')} -->`;
     } else {
       headerBlock = headerLines.map(l => l ? `${cmt} ${l}` : cmt).join('\n');
     }

     let ruleBody: string;

     if (ruleFormat === 'KQL') {
       ruleBody = `${cmt} ----------------------------------------------------------------------
${cmt} DETECTION RULE (KQL)
${cmt} ----------------------------------------------------------------------
${cmt} Rule name: ${ruleTitle}
${cmt} Description: ${ruleDesc}
${cmt} Author: HEFAISTOS Automation
${cmt} Date: ${ruleDate}
${cmt} Severity: Medium
${cmt}
${cmt} TODO: Adjust table name and field mappings based on your log sources.
${cmt} CHECK "LIVE DATA" ABOVE for correct table and column names.
${cmt} ----------------------------------------------------------------------
let lookback = 1h;
SecurityEvent
| where TimeGenerated > ago(lookback)
// TODO: Map the 'Channel' fields from LIVE DATA above to KQL filters
// Example: | where EventID == 1
| where EventID == 0  // <-- Replace with actual EventID
| project TimeGenerated, Computer, Account, EventID, Activity
| sort by TimeGenerated desc`;
     } else if (ruleFormat === 'SPL') {
       ruleBody = `\` ----------------------------------------------------------------------
\` DETECTION RULE (SPL)
\` ----------------------------------------------------------------------
\` Rule name: ${ruleTitle}
\` Description: ${ruleDesc}
\` Author: HEFAISTOS Automation
\` Date: ${ruleDate}
\` Severity: Medium
\`
\` TODO: Adjust index, sourcetype, and field mappings based on your log sources.
\` CHECK "LIVE DATA" ABOVE for correct source types and fields.
\` ----------------------------------------------------------------------
index=main sourcetype=WinEventLog:Security
| search EventCode=0
\` TODO: Replace EventCode with actual value from LIVE DATA above
| table _time, host, user, EventCode, Message
| sort -_time`;
     } else if (ruleFormat === 'WAZUH') {
       ruleBody = `<!-- ----------------------------------------------------------------------
     DETECTION RULE (WAZUH)
     ----------------------------------------------------------------------
     Rule name: ${ruleTitle}
     Description: ${ruleDesc}
     Author: HEFAISTOS Automation
     Date: ${ruleDate}
     Severity: Medium

     TODO: Adjust decoder, rule ID, and field mappings based on your log sources.
     CHECK "LIVE DATA" ABOVE for correct field names.
     ---------------------------------------------------------------------- -->
<group name="custom_detection,">
  <rule id="100001" level="6">
    <decoded_as>json</decoded_as>
    <field name="EventID">^0$</field>
    <!-- TODO: Replace EventID with actual value from LIVE DATA above -->
    <description>${ruleTitle}</description>
    <options>no_full_log</options>
  </rule>
</group>`;
     } else if (ruleFormat === 'AQL') {
       ruleBody = `-- ----------------------------------------------------------------------
-- DETECTION RULE (AQL / QRadar)
-- ----------------------------------------------------------------------
-- Rule name: ${ruleTitle}
-- Description: ${ruleDesc}
-- Author: HEFAISTOS Automation
-- Date: ${ruleDate}
-- Severity: Medium
--
-- TODO: Adjust event category/type and field mappings based on your log sources.
-- CHECK "LIVE DATA" ABOVE for correct QID / category / property names.
-- ----------------------------------------------------------------------
SELECT
  starttime,
  sourceip,
  destinationip,
  username,
  qidname(qid) AS qid_name
FROM events
WHERE
  devicetype IS NOT NULL
  AND qid IS NOT NULL
  -- TODO: Replace with conditions from LIVE DATA above
ORDER BY starttime DESC
LAST 1 HOURS`;
     } else {
       // KQL (default fallback)
       ruleBody = `// ----------------------------------------------------------------------
// DETECTION RULE (KQL)
// ----------------------------------------------------------------------
// Rule name: ${ruleTitle}
// Description: ${ruleDesc}
// Author: HEFAISTOS Automation
// Date: ${ruleDate}
// Severity: Medium
//
// TODO: Adjust table name and field mappings based on your log sources.
// CHECK "LIVE DATA" ABOVE for correct table and column names.
// ----------------------------------------------------------------------
let lookback = 1h;
SecurityEvent
| where TimeGenerated > ago(lookback)
// TODO: Map the 'Channel' fields from LIVE DATA above to KQL filters
// Example: | where EventID == 1
| where EventID == 0  // <-- Replace with actual EventID
| project TimeGenerated, Computer, Account, EventID, Activity
| sort by TimeGenerated desc`;
     }

     const logicTemplate = `${headerBlock}
${pfx(richContext)}
${pfx(logSourcesForEditor)}
${ruleBody}
`;

     // 1. Auto-Guess Data Source Code
     let sourceCode = "";
     const dsName = analytic.dataComponent?.dataSource?.name?.toLowerCase() || "";
     // const dcName = analytic.dataComponent?.name?.toLowerCase() || "";

     if (dsName.includes("sysmon") || dsName.includes("etw")) sourceCode = "K"; // Kernel
     else if (dsName.includes("powershell")) sourceCode = "A"; // Application
     else if (dsName.includes("network")) sourceCode = "H"; // Network Header (Safe default)
     else sourceCode = "U"; // Default to User-Mode for generic Windows logs

     // 2. Auto-Guess Logic Level (Heuristic)
     let level = 3; // Default to LOLBin/Tool level
     const desc = analytic.description.toLowerCase();
     
     if (desc.includes("hash") || desc.includes("ip address") || desc.includes("domain")) {
         level = 1; // Ephemeral
     } else if (desc.includes("pipe") || desc.includes("flag") || desc.includes("string")) {
         level = 2; // Tool Artifact
     } else if (desc.includes("api") || desc.includes("rpc") || desc.includes("call")) {
         level = 4; // Behavior
     } else if (desc.includes("invariant") || desc.includes("always")) {
         level = 5; // Invariant
     }

     // 3. Update Parent
     onStrategyChange({
         detectionRule: logicTemplate,
         technicalContext: `Implemented based on ${strategy.name} (${analyticCode}).`,
         techniqueId: selectedTechniqueId,
         robustnessLevel: level,        // <--- Send Guess
         dataSourceRobustness: sourceCode // <--- Send Guess
     });
     
     // 4. Update live log sources AFTER parent update to ensure they persist
     // Use setTimeout to ensure state update happens after mutation completes
     setTimeout(() => {
       setLiveLogSources(fetchedRows);
       liveLogSourcesRef.current = fetchedRows;
     }, 100);
     
     // 5. Reset processing flag after a longer delay to allow mutation and re-renders to complete
     setTimeout(() => {
       isProcessingRef.current = false;
     }, 1500);
  };

  return (
    <div className="p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm h-full overflow-y-auto">
       <h2 className="text-xl font-bold mb-4 text-hefaistos-primary">Part 1: Detection Strategy</h2>
       
       {/* --- A. The Anchor --- */}
       <div className="mb-6">
         <label className="block text-sm font-bold mb-2">MITRE ATT&CK Technique</label>
         <input 
           type="text" 
           className="w-full p-2 border border-gray-300 rounded"
           placeholder="Search (e.g. T1003)..."
           onChange={(e) => setSearchTerm(e.target.value)}
         />
         {/* Simple dropdown for results */}
         {techData?.searchTechniques && techData.searchTechniques.length > 0 && (
            <ul className="mt-2 border border-gray-200 rounded max-h-40 overflow-y-auto">
              {techData.searchTechniques.map((t: any) => (
                <li 
                  key={t.id} 
                  className="p-2 hover:bg-blue-50 cursor-pointer"
                  onClick={() => {
                      onTechniqueChange(t);
                      setSearchTerm(''); // Clear search
                  }}
                >
                  <strong>{t.techniqueId}</strong>: {t.name}
                </li>
              ))}
            </ul>
         )}
         {stableTechniqueId && <div className="mt-2 font-mono text-green-600">Selected: {stableTechniqueId}</div>}
       </div>

       {/* B. Detection Strategy Suggestions */}
       {(suggestionData?.detectionSuggestions?.strategies?.length ?? 0) > 0 ? (
         <div className="mb-6">
           <h3 className="font-bold text-gray-700 mb-2">Recommended Detection Strategies</h3>
           <div className="flex flex-col gap-3">
             {suggestionData?.detectionSuggestions?.strategies.map((strat: any) => (
                <div key={strat.id} className={`border rounded transition-all ${selectedStrategyId === strat.id ? 'border-blue-500 bg-blue-50 shadow-md' : 'border-gray-200 hover:border-blue-300'}`}>
                    
                    {/* Strategy Header */}
                    <div className="p-3 flex items-center justify-between cursor-pointer" onClick={() => setSelectedStrategyId(strat.id)}>
                        <div>
                            <span className="font-mono font-bold text-blue-800 text-sm">{strat.defId}</span>
                            <span className="ml-2 font-semibold text-gray-800">{strat.name}</span>
                        </div>
                        <Button variant={selectedStrategyId === strat.id ? "primary" : "secondary"}>
                            {selectedStrategyId === strat.id ? "Active" : "Select"}
                        </Button>
                    </div>
                    
                    {/* C. Analytics List (Expanded) */}
                    {selectedStrategyId === strat.id && (
                        <div className="border-t border-blue-200 bg-white p-3">
                            <h4 className="text-xs uppercase text-gray-500 font-bold mb-2">Available Analytics</h4>
                            {strat.analytics.length > 0 ? (
                                <ul className="space-y-4">
                                    {strat.analytics.map((ana: any) => (
                                        <li key={ana.id} className="text-sm border border-gray-100 rounded p-3 hover:bg-gray-50">
                                            <div className="flex justify-between items-start mb-2">
                                                <span className="font-bold text-gray-900">{ana.name}</span>
                                                <button 
                                                    className="text-white bg-green-600 hover:bg-green-700 px-2 py-1 rounded text-xs disabled:opacity-50"
                                                    disabled={enriching}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleAnalyticSelect(ana, strat, suggestionData?.detectionSuggestions?.technique);
                                                    }}
                                                >
                                                    {enriching ? "Loading..." : "Use Logic"}
                                                </button>
                                            </div>
                                            {/* --- THE FIX: Display the Description --- */}
                                            <p className="text-gray-600 text-xs leading-relaxed">
                                                {ana.description}
                                            </p>
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-xs text-gray-400 italic">No specific analytics found.</p>
                            )}
                        </div>
                    )}
                </div>
             ))}
           </div>
         </div>
       ) : (
         stableTechniqueId && <p className="text-gray-400 italic mt-4">No strategies found.</p>
       )}

       {/* --- NEW: Data Requirements Panel --- */}
       {liveLogSources.length > 0 && (
           <div className="mt-6 border-t-2 border-gray-100 pt-4 animate-fade-in">
               <h3 className="font-bold text-gray-700 mb-3 flex items-center">
                   <span className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded mr-2">LIVE</span>
                   Required Data Sources
               </h3>
               
               <div className="overflow-x-auto border rounded-lg">
                   <table className="min-w-full text-xs text-left">
                       <thead className="bg-gray-50 border-b">
                           <tr>
                               <th className="p-2 font-semibold">Data Component</th>
                               <th className="p-2 font-semibold">Provider</th>
                               <th className="p-2 font-semibold">Channel / Event</th>
                               <th className="p-2 font-semibold text-right">Action</th>
                           </tr>
                       </thead>
                       <tbody className="divide-y divide-gray-100">
                           {liveLogSources.map((row, i) => {
                             const alreadyAdded = isResourceAlreadyAdded(row);
                             return (
                               <tr key={i} className="hover:bg-gray-50">
                                 <td className="p-2">{row.dataComponent}</td>
                                 <td className="p-2 font-mono text-gray-600">{row.logProvider}</td>
                                 <td className="p-2 font-mono text-blue-600">{row.channel}</td>
                                 <td className="p-2 text-right">
                                   <button
                                     type="button"
                                     className={`${alreadyAdded ? 'text-gray-500 bg-gray-200 cursor-not-allowed' : 'text-white bg-blue-600 hover:bg-blue-700'} px-2 py-1 rounded shadow-sm transition-colors flex items-center ml-auto`}
                                     onClick={() => handleAddFromMitre(row)}
                                     disabled={alreadyAdded}
                                     title={alreadyAdded ? 'Resource already added' : 'Add resource to Data Catalog'}
                                   >
                                     + Add
                                   </button>
                                 </td>
                               </tr>
                             );
                           })}
                       </tbody>
                   </table>
               </div>
               <p className="text-[10px] text-gray-400 mt-2 text-center">
                   Click "+ Add" to create a tracker in your Data Catalog for this log source.
               </p>
           </div>
       )}
    </div>
  );
});

DetectionStrategy.displayName = 'DetectionStrategy';
