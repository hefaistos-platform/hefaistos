import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import SimpleMDE from 'react-simplemde-editor';
import { message } from 'antd';
import {
  configureMdeInstance,
  createEditorOptions,
  MARKDOWN_PLACEHOLDERS,
} from '../../config/markdownConfig';
import 'easymde/dist/easymde.min.css';

type CodeMirrorLike = {
  getSelection: () => string;
  replaceSelection: (value: string) => void;
  focus: () => void;
};

type EasyMdeLike = {
  codemirror: CodeMirrorLike;
};

interface PlaybookNotesProps {
  notes?: string | null;
  canClearNotes: boolean;
  onSave: (nextNotes: string) => Promise<void>;
}

const getErrorMessage = (error: unknown) => {
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message?: string }).message || 'Failed to save notes');
  }
  return 'Failed to save notes';
};

const wrapSelection = (editor: EasyMdeLike, prefix: string, suffix: string, fallback: string) => {
  const cm = editor.codemirror;
  const selected = cm.getSelection();
  const value = selected || fallback;
  cm.replaceSelection(`${prefix}${value}${suffix}`);
  cm.focus();
};

export const PlaybookNotes: React.FC<PlaybookNotesProps> = ({
  notes,
  canClearNotes,
  onSave,
}) => {
  const initialValue = notes ?? '';
  const [draft, setDraft] = useState(initialValue);
  const [isSaving, setIsSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const lastPersistedRef = useRef(initialValue);
  const requestCounterRef = useRef(0);

  const options = useMemo(() => {
    const base = createEditorOptions('standard', MARKDOWN_PLACEHOLDERS.notes);
    return {
      ...base,
      toolbar: [
        'bold',
        'italic',
        'heading',
        '|',
        {
          name: 'underline',
          action: (editor: EasyMdeLike) => wrapSelection(editor, '<u>', '</u>', 'underlined text'),
          className: 'fa fa-underline',
          title: 'Underline',
        },
        'quote',
        'unordered-list',
        'ordered-list',
        '|',
        'code',
        'table',
        'link',
        '|',
        'preview',
        'side-by-side',
        'fullscreen',
        'guide',
      ] as any,
    };
  }, []);

  const persist = useCallback(
    async (nextValue: string, showToast = false) => {
      if (nextValue === lastPersistedRef.current) return;
      const requestId = ++requestCounterRef.current;
      setIsSaving(true);
      setSaveError(null);

      try {
        await onSave(nextValue);
        if (requestId !== requestCounterRef.current) return;
        lastPersistedRef.current = nextValue;
        setLastSavedAt(new Date());
        if (showToast) {
          message.success('Notes saved');
        }
      } catch (error) {
        if (requestId !== requestCounterRef.current) return;
        setSaveError(getErrorMessage(error));
        if (showToast) {
          message.error(getErrorMessage(error));
        }
      } finally {
        if (requestId === requestCounterRef.current) {
          setIsSaving(false);
        }
      }
    },
    [onSave]
  );

  useEffect(() => {
    const incoming = notes ?? '';
    const isDirty = draft !== lastPersistedRef.current;
    if (!isDirty) {
      lastPersistedRef.current = incoming;
      setDraft(incoming);
    }
  }, [notes, draft]);

  useEffect(() => {
    if (draft === lastPersistedRef.current) return;
    const timer = window.setTimeout(() => {
      void persist(draft);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [draft, persist]);

  const hasUnsavedChanges = draft !== lastPersistedRef.current;
  const hasContent = (draft || '').trim().length > 0 || (lastPersistedRef.current || '').trim().length > 0;

  const handleSaveNow = async () => {
    await persist(draft, true);
  };

  const handleClear = async () => {
    if (!canClearNotes) {
      message.warning('Only the workbench author or an admin can clear notes.');
      return;
    }
    if (!hasContent) return;
    const confirmed = window.confirm('Clear all notes for this workbench?');
    if (!confirmed) return;
    setDraft('');
    await persist('', true);
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <div className="px-3 py-2 bg-white border-b border-gray-200 flex items-center justify-between gap-2">
        <div className="text-[11px] text-gray-500">
          {isSaving
            ? 'Saving notes...'
            : hasUnsavedChanges
              ? 'Unsaved changes'
              : lastSavedAt
                ? `Saved at ${lastSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                : 'All changes saved'}
          {saveError && <span className="text-red-600 ml-2">{saveError}</span>}
        </div>
        <div className="flex items-center gap-2">
          <button
            className="px-2 py-1 text-xs rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-50"
            onClick={() => void handleSaveNow()}
            disabled={isSaving || !hasUnsavedChanges}
            type="button"
          >
            Save
          </button>
          <button
            className="px-2 py-1 text-xs rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-50"
            onClick={() => void handleClear()}
            disabled={isSaving || !hasContent || !canClearNotes}
            title={canClearNotes ? 'Clear notes' : 'Only author/admin can clear notes'}
            type="button"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        <div className="border border-gray-200 rounded-md overflow-hidden bg-white">
          <SimpleMDE
            value={draft}
            onChange={setDraft}
            options={options}
            getMdeInstance={configureMdeInstance}
          />
        </div>
        <p className="mt-2 text-[10px] text-gray-500">
          Notes support Markdown. Use the underline button for <code>{'<u>text</u>'}</code>.
        </p>
      </div>
    </div>
  );
};

export default PlaybookNotes;
