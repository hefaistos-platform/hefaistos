/**
 * MarkdownRenderer Component
 * Provides consistent markdown rendering with proper sanitization
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { MARKDOWN_PROSE_CLASSES } from '../config/markdownConfig';

interface MarkdownRendererProps {
  /** The markdown content to render */
  content: string | undefined;
  /** CSS prose class variant (default, small, compact, inline) */
  variant?: keyof typeof MARKDOWN_PROSE_CLASSES;
  /** Additional CSS classes */
  className?: string;
  /** Skip rendering empty content */
  skipEmpty?: boolean;
}

export function normalizeMarkdownContent(content: string | undefined): string {
  if (!content) {
    return '';
  }

  let normalizedContent = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  if (normalizedContent.includes('\\n') || normalizedContent.includes('\\r\\n')) {
    normalizedContent = normalizedContent.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n');
  }
  if (/\\#{1,6}\s|\\\*\*[^*]+\\\*\*|\\_[^_]+\\_|\\`[^`]+\\`/m.test(normalizedContent)) {
    normalizedContent = normalizedContent.replace(/\\([#*_`])/g, '$1');
  }

  return normalizedContent;
}

export function markdownToPlainText(content: string | undefined): string {
  const normalizedContent = normalizeMarkdownContent(content);
  if (!normalizedContent) {
    return '';
  }

  return normalizedContent
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/^>\s?/gm, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/\n+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Theme-aware colors: MarkdownRenderer content used to hardcode light-mode
// Tailwind grays (text-gray-900, bg-gray-100, etc.) with no dark-theme variant,
// making headings/list text unreadable (dark-on-dark) and code blocks
// unreadable (light-gray-on-white against a dark page) whenever the app's
// [data-theme='dark'] is active. Use the app's CSS custom properties instead
// so every consumer of this shared renderer respects the active theme.
const codeBlockStyle: React.CSSProperties = {
  background: 'var(--hef-bg-subtle)',
  color: 'var(--hef-text-primary)',
  border: '1px solid var(--hef-border)',
};
const inlineCodeStyle: React.CSSProperties = {
  background: 'var(--hef-bg-accent)',
  color: 'var(--hef-text-primary)',
};
const blockquoteStyle: React.CSSProperties = {
  borderLeft: '4px solid var(--hef-border-strong)',
  color: 'var(--hef-text-secondary)',
};
const tableBorderStyle: React.CSSProperties = { borderColor: 'var(--hef-border)' };
const theadStyle: React.CSSProperties = { background: 'var(--hef-bg-subtle)' };
const trStyle: React.CSSProperties = { borderBottom: '1px solid var(--hef-border)' };
const cellStyle: React.CSSProperties = { borderRight: '1px solid var(--hef-border)', color: 'var(--hef-text-primary)' };
const headingStyle: React.CSSProperties = { color: 'var(--hef-text-primary)' };
const textStyle: React.CSSProperties = { color: 'var(--hef-text-primary)' };

/**
 * Renders markdown content with consistent styling and sanitization
 * Replaces all ad-hoc ReactMarkdown usage across the app
 * 
 * Features:
 * - Consistent prose styling across the application
 * - Safe markdown rendering with proper component overrides
 * - Links automatically open in new tabs
 * - Code blocks styled consistently
 * - Blockquotes and tables handled properly
 * - Colors follow the app's light/dark theme CSS variables (no hardcoded grays)
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  variant = 'default',
  className = '',
  skipEmpty = true,
}) => {
  // Skip rendering if content is empty or undefined
  if (skipEmpty && (!content || content.trim().length === 0)) {
    return null;
  }

  // Return null if content is undefined and skipEmpty is false
  if (!content) {
    return null;
  }

  const normalizedContent = normalizeMarkdownContent(content);

  const proseClass = MARKDOWN_PROSE_CLASSES[variant] || MARKDOWN_PROSE_CLASSES.default;
  const combinedClassName = `${proseClass} ${className}`.trim();

  return (
    <div className={combinedClassName} style={textStyle}>
      <ReactMarkdown
        components={{
          // Ensure links open in new tab for security and prevent accidental navigation
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          // Add consistent styling to code blocks with proper contrast
          pre: ({ node, ...props }) => (
            <pre
              className="p-3 rounded overflow-x-auto text-sm"
              style={codeBlockStyle}
              {...props}
            />
          ),
          // Inline code styling
          code: (props: any) => {
            const { node, inline, ...restProps } = props;
            return (
              <code
                className={inline ? 'px-1 py-0.5 rounded text-sm font-mono' : 'font-mono'}
                style={inline ? inlineCodeStyle : undefined}
                {...restProps}
              />
            );
          },
          // Add consistent styling to blockquotes for visual hierarchy
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="pl-4 italic my-2"
              style={blockquoteStyle}
              {...props}
            />
          ),
          // Ensure tables are responsive and styled
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-2">
              <table
                className="border-collapse w-full text-sm"
                style={tableBorderStyle}
                {...props}
              />
            </div>
          ),
          // Style table headers
          thead: ({ node, ...props }) => (
            <thead style={theadStyle} {...props} />
          ),
          // Style table rows with alternating colors
          tbody: ({ node, ...props }) => (
            <tbody {...props} />
          ),
          tr: (props: any) => {
            const { node, isHeader, ...restProps } = props;
            return <tr style={trStyle} {...restProps} />;
          },
          td: ({ node, ...props }) => (
            <td className="px-3 py-2" style={cellStyle} {...props} />
          ),
          th: ({ node, ...props }) => (
            <th className="px-3 py-2 text-left font-semibold" style={cellStyle} {...props} />
          ),
          // Style headings for better hierarchy
          h1: ({ node, ...props }) => (
            <h1 className="text-lg font-bold mt-4 mb-2" style={headingStyle} {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className="text-base font-bold mt-3 mb-2" style={headingStyle} {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className="text-sm font-semibold mt-2 mb-1" style={headingStyle} {...props} />
          ),
          // Ensure lists are properly styled
          ul: ({ node, ...props }) => (
            <ul className="list-disc list-inside space-y-1 my-2" {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol className="list-decimal list-inside space-y-1 my-2" {...props} />
          ),
          li: ({ node, ...props }) => (
            <li style={textStyle} {...props} />
          ),
          p: ({ node, ...props }) => (
            <p style={textStyle} {...props} />
          ),
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
