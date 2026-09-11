import React, { useMemo } from 'react';
import { message as antMessage } from 'antd';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import yaml from 'js-yaml';
import { OpenTideRule } from '../types/opentide';
import { useTheme } from '../context/ThemeContext';

interface Props {
  openTideRule: OpenTideRule;
  /** Called when the user clicks "View Full Preview" */
  onOpenFullPreview?: () => void;
}

/**
 * Renders a compact, syntax-highlighted YAML preview of the compiled OpenTide
 * MDR (Managed Detection Rule) directly in the PlaybookWorkbench sidebar.
 *
 * Users can copy the YAML or open the full AI-enriched OpenTidePreviewModal.
 */
const OpenTideMetadataPreview: React.FC<Props> = ({ openTideRule, onOpenFullPreview }) => {
  const { resolvedTheme } = useTheme();
  const yamlText = useMemo(() => {
    try {
      // Build the MDR-style structure: metadata + configurations derived from platforms
      const configurations = Object.entries(openTideRule.platforms || {})
        .filter(([, v]) => v != null && typeof v === 'object')
        .map(([platform, v]) => ({
          platform,
          ...(v as Record<string, unknown>),
        }));

      const mdrObject: Record<string, unknown> = {
        metadata: openTideRule.metadata,
      };
      if (configurations.length > 0) {
        mdrObject.configurations = configurations;
      }

      return yaml.dump(mdrObject, { lineWidth: 120, noRefs: true });
    } catch (err) {
      console.warn('[OpenTideMetadataPreview] Failed to serialize OpenTide rule to YAML:', err);
      return '# Error serializing OpenTide rule to YAML';
    }
  }, [openTideRule]);

  const handleCopy = () => {
    navigator.clipboard.writeText(yamlText).then(
      () => antMessage.success('YAML copied to clipboard'),
      () => antMessage.error('Failed to copy YAML'),
    );
  };

  return (
    <div className="opentide-metadata-preview space-y-2 pt-2">
      {/* Action buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={handleCopy}
          className="opentide-metadata-action flex items-center gap-1 px-2 py-1 text-xs rounded border border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100 transition-colors"
        >
          📋 Copy YAML
        </button>
        {onOpenFullPreview && (
          <button
            type="button"
            onClick={onOpenFullPreview}
            className="opentide-metadata-action opentide-metadata-action-brand flex items-center gap-1 px-2 py-1 text-xs rounded border border-purple-300 text-purple-700 bg-purple-50 hover:bg-purple-100 transition-colors"
          >
            🔍 View Full Preview →
          </button>
        )}
      </div>

      {/* YAML block */}
      <div className="rounded border border-gray-200 overflow-auto max-h-80">
        <SyntaxHighlighter
          language="yaml"
          style={resolvedTheme === 'dark' ? vscDarkPlus : oneLight}
          showLineNumbers
          wrapLines
          customStyle={{
            fontSize: 11,
            margin: 0,
            borderRadius: 4,
            background: 'var(--hef-bg-subtle)',
          }}
        >
          {yamlText || '# (empty)'}
        </SyntaxHighlighter>
      </div>
    </div>
  );
};

export default OpenTideMetadataPreview;
