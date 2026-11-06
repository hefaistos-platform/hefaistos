import React from 'react';
import { Alert } from 'antd';

export interface FrameworkDrift {
  pinnedLabel: string;
  activeLabel: string;
  removed: string[];
  changed: string[];
}

/**
 * A note, nothing more: the ADE framework was updated after this session started answering.
 * Answers are kept and no question is reopened or hidden because of it.
 */
export const MaieuticFrameworkDrift: React.FC<{ drift?: FrameworkDrift | null }> = ({ drift }) => {
  const removed = drift?.removed ?? [];
  const changed = drift?.changed ?? [];
  if (!drift || (!removed.length && !changed.length)) return null;
  return (
    <Alert
      type="info" showIcon data-testid="framework-drift"
      message={`The ADE framework was updated after you started this session (${drift.pinnedLabel} to ${drift.activeLabel}).`}
      description={(
        <div>
          {removed.length > 0 && (
            <div>No longer in the framework: {removed.join(', ')}. Your answers to them are kept and you can still answer them.</div>
          )}
          {changed.length > 0 && (
            <div>Definition changed upstream: {changed.join(', ')}. Your answers are kept. A question is only reopened when its own text changes.</div>
          )}
        </div>
      )}
    />
  );
};

export default MaieuticFrameworkDrift;
