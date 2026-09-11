import React from 'react';

export interface ReferenceContextItem {
  title?: string;
  description?: string;
  content?: string;
  source_path?: string;
  source_ref?: string;
  source_branch?: string;
  repository_name?: string;
  language?: string;
  score?: number;
}

interface ReferenceContextPanelProps {
  references: ReferenceContextItem[];
}

export const ReferenceContextPanel: React.FC<ReferenceContextPanelProps> = ({ references }) => {
  if (!references.length) return null;

  return (
    <div>
      <strong>Retrieved grounding context:</strong>
      <div className="mt-2 space-y-2">
        {references.map((ref, index) => (
          <div key={`${ref.source_ref || ref.source_path || ref.title || 'ref'}-${index}`} className="border rounded p-2 text-sm">
            <div className="flex flex-wrap gap-2 items-center mb-1">
              <span className="font-semibold">{ref.title || `Reference ${index + 1}`}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-700">{ref.language || 'KQL'}</span>
              {typeof ref.score === 'number' && (
                <span className="text-xs text-gray-600">score: {ref.score.toFixed(3)}</span>
              )}
            </div>
            {(ref.source_ref || ref.source_path) && (
              <div className="text-xs text-gray-600 mb-1">
                source: {ref.source_ref || ref.source_path}
                {ref.source_branch ? ` @ ${ref.source_branch}` : ''}
                {ref.repository_name ? ` · ${ref.repository_name}` : ''}
              </div>
            )}
            {ref.description && (
              <div className="text-xs text-gray-700 mb-1">{ref.description}</div>
            )}
            {ref.content && (
              <pre className="whitespace-pre-wrap font-sans text-xs bg-gray-50 rounded p-2 max-h-40 overflow-auto">{ref.content}</pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

