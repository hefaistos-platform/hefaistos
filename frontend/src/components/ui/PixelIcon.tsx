import React from 'react';

interface PixelIconProps {
  name: string;
  className?: string;
}

// Lightweight emoji fallback; avoids bundler warnings for missing third-party icon packs.
export const PixelIcon: React.FC<PixelIconProps> = ({ name, className }) => {
  const glyphMap: Record<string, string> = {
    edit: '✏️',
    'edit-2': '✏️',
    add: '➕',
    delete: '🗑️',
    trash: '🗑️',
    task: '📌',
    playbook: '📘',
    folder: '📁',
    bell: '🔔',
    download: '📥',
    'download-off': '🚫',
    upload: '📤',
    copy: '📋',
    'file-text': '📄',
    eye: '👁️',
    camera: '📷',
    github: '🐙',
    save: '💾',
    share: '🔗',
    lock: '🔒',
    zap: '⚡',
    lightbulb: '💡',
    crystal: '🔮',
  };
  const glyph = glyphMap[name] || '🔧';
  return (
    <span className={className} aria-label={name} role="img">
      {glyph}
    </span>
  );
};
