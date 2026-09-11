/**
 * Centralized Markdown Configuration
 * Provides consistent SimpleMDE editor options and markdown rendering utilities
 */

// Fix for SimpleMDE toolbar button double-click issue
// This should be called with getMdeInstance prop in SimpleMDE components

// Type definitions for SimpleMDE/EasyMDE instance
interface CodeMirrorSelection {
  from: any;
  to: any;
  text: string;
}

interface CodeMirrorWithSelection {
  getSelection: () => string;
  getCursor: (where: string) => any;
  setSelection: (from: any, to: any) => void;
  somethingSelected: () => boolean;
  focus: () => void;
}

interface SimpleMDEInstance {
  codemirror: CodeMirrorWithSelection;
  gui?: {
    toolbar?: HTMLElement;
  };
}

// Delay for selection restoration after toolbar action (in milliseconds)
// This allows the toolbar action to complete before restoring selection
const SELECTION_RESTORE_DELAY_MS = 10;

// WeakMap to store selection state without modifying CodeMirror instance
const selectionStateMap = new WeakMap<CodeMirrorWithSelection, CodeMirrorSelection>();

export const configureMdeInstance = (instance: SimpleMDEInstance | null) => {
  if (!instance) return;
  
  // Get the CodeMirror instance
  const cm = instance.codemirror;
  if (!cm) return;
  
  // Store the original getSelection method
  const originalGetSelection = cm.getSelection.bind(cm);
  
  // Override to preserve selection state
  cm.getSelection = function() {
    const selection = originalGetSelection();
    if (selection) {
      // Store selection for restoration using WeakMap
      selectionStateMap.set(cm, {
        from: cm.getCursor('start'),
        to: cm.getCursor('end'),
        text: selection
      });
    }
    return selection;
  };
  
  // Add event listener to handle toolbar button clicks
  const toolbar = instance.gui?.toolbar;
  if (toolbar) {
    const buttons = toolbar.querySelectorAll('button, a');
    buttons.forEach((button) => {
      const htmlButton = button as HTMLElement;
      htmlButton.addEventListener('mousedown', (e) => {
        // Prevent default to avoid focus loss
        e.preventDefault();
        
        // Get current selection before action
        const lastSel = selectionStateMap.get(cm);
        
        // Execute the button action
        setTimeout(() => {
          // Restore selection if it was lost
          if (lastSel && (!cm.somethingSelected() || cm.getSelection() === '')) {
            cm.setSelection(lastSel.from, lastSel.to);
            cm.focus();
          }
        }, SELECTION_RESTORE_DELAY_MS);
      });
    });
  }
};

// SimpleMDE Editor Options - Standard Configuration
export const MARKDOWN_EDITOR_OPTIONS = {
  standard: {
    spellChecker: false,
    status: false,
    toolbar: [
      'bold', 'italic', 'heading', '|',
      'quote', 'unordered-list', 'ordered-list', 'table', 'code', 'link', 'image', 'horizontal-rule', '|',
      'preview', 'side-by-side', 'fullscreen', 'guide'
    ] as const,
  },
  minimal: {
    spellChecker: false,
    status: false,
    toolbar: [
      'bold', 'italic', 'heading', '|',
      'quote', 'unordered-list', 'ordered-list', '|',
      'preview', 'guide'
    ] as const,
  },
  compact: {
    spellChecker: false,
    status: false,
    toolbar: [
      'bold', 'italic', 'heading', 'quote', 'unordered-list', 'ordered-list', '|',
      'preview', 'guide'
    ] as const,
  },
} as const;

// Placeholder texts for different field types
export const MARKDOWN_PLACEHOLDERS = {
  description: 'Describe the content (Markdown supported)...',
  hypothesis: 'The testable question this hunt will answer...',
  technicalContext: 'Explain how the attack works (Markdown supported)...',
  falsePositives: 'Document known benign triggers (Markdown supported)...',
  response: 'Document response and remediation steps (Markdown supported)...',
  triage: 'Step-by-step triage guidance (Markdown supported)...',
  testing: 'Test cases and procedures (Markdown supported)...',
  details: 'Add detailed information (Markdown supported)...',
  notes: 'Add notes or comments (Markdown supported)...',
  content: 'Enter content (Markdown supported)...',
} as const;

// Markdown rendering CSS classes
export const MARKDOWN_PROSE_CLASSES = {
  default: 'prose lg:prose-xl',
  small: 'prose prose-sm',
  compact: 'prose prose-sm max-w-none',
  inline: 'prose prose-sm max-w-none inline',
} as const;

// HTML Sanitization settings (for preventing XSS)
export const MARKDOWN_SANITIZATION = {
  allowedTags: [
    'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'a', 'img', 'hr',
    'table', 'thead', 'tbody', 'tr', 'td', 'th', 'caption', 'del', 'ins'
  ],
  allowedAttributes: {
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    '*': ['className']
  },
  allowedSchemes: ['http', 'https', 'mailto', 'data'],
} as const;

// Helper function to create editor options with custom placeholder
export function createEditorOptions(
  template: keyof typeof MARKDOWN_EDITOR_OPTIONS,
  placeholder?: string
) {
  return {
    ...MARKDOWN_EDITOR_OPTIONS[template],
    placeholder: placeholder || MARKDOWN_PLACEHOLDERS.content,
  };
}

export default {
  MARKDOWN_EDITOR_OPTIONS,
  MARKDOWN_PLACEHOLDERS,
  MARKDOWN_PROSE_CLASSES,
  MARKDOWN_SANITIZATION,
  createEditorOptions,
  configureMdeInstance,
};
