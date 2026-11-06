import React, { useEffect, useState } from 'react';
import { gql, useMutation } from '@apollo/client';
import { Alert, Button, Space, Tag, Typography } from 'antd';

const { Text } = Typography;

export const WORDING_MIN_CHARS = 25;

const SUGGEST = gql`
  mutation SuggestMaieuticWording($id: UUID!, $field: String!) {
    suggestMaieuticWording(draftId: $id, field: $field) { suggestion message remaining }
  }
`;
const ACCEPT = gql`
  mutation AcceptMaieuticWording($id: UUID!, $field: String!) {
    acceptMaieuticWording(draftId: $id, field: $field) { value textOrigin }
  }
`;
const RESTORE = gql`
  mutation RestoreMaieuticWording($id: UUID!, $field: String!) {
    restoreMaieuticWording(draftId: $id, field: $field) { value textOrigin }
  }
`;

export type TextOrigin = Record<string, { origin?: string; accepted_text?: string; accepted_at?: string }>;

const norm = (s: string) => s.split(/\s+/).filter(Boolean).join(' ');

/** What the user sees for a field: nothing for their own text, otherwise how much of it is still the AI's. */
export const originLabel = (origins: TextOrigin | undefined, field: string, text: string): string | null => {
  const record = origins?.[field];
  if (!record || !norm(text)) return null;
  // A copy shared from another instance carries only the mark, not the wording, so trust the mark there.
  const reworded = record.accepted_text === undefined ? record.origin === 'AI_REWORDED' : norm(text) === norm(record.accepted_text);
  return reworded ? 'AI reworded' : 'AI reworded, then edited by you';
};

interface Props {
  draftId: string;
  field: string;                       // e.g. 'hypothesis.goal'
  text: string;
  origins: TextOrigin | undefined;
  available: boolean;                  // the user has an AI provider
  locked: boolean;
  flush: () => Promise<boolean>;       // saves the current text first: the server only knows what is saved
  onApply: (field: string, value: string, origins: TextOrigin) => void;
}

/** Optional wording help. The AI only rephrases the user's text; nothing changes until they press Use this. */
export const MaieuticWordingHelp: React.FC<Props> = ({ draftId, field, text, origins, available, locked, flush, onApply }) => {
  const [suggest, { loading }] = useMutation(SUGGEST);
  const [accept] = useMutation(ACCEPT);
  const [restore] = useMutation(RESTORE);
  const [offer, setOffer] = useState<{ suggestion: string; source: string } | null>(null);
  const [note, setNote] = useState('');
  const [remaining, setRemaining] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  // A suggestion belongs to the exact text it was made for. Typing anything makes it obsolete.
  useEffect(() => {
    if (offer && text !== offer.source) setOffer(null);
  }, [text, offer]);

  if (!available || locked) return null;
  const label = originLabel(origins, field, text);
  const tooShort = text.trim().length < WORDING_MIN_CHARS;

  const ask = async () => {
    setNote('');
    setOffer(null);
    if (!(await flush())) { setNote('Your text could not be saved yet, so no wording was requested.'); return; }
    try {
      const res = await suggest({ variables: { id: draftId, field } });
      const out = res.data?.suggestMaieuticWording;
      setRemaining(out?.remaining ?? null);
      if (out?.suggestion) setOffer({ suggestion: out.suggestion, source: text });
      else setNote(out?.message || 'No suggestion this time.');
    } catch (err: any) {
      setNote(err?.message || 'Could not get a suggestion.');
    }
  };

  const run = async (op: typeof accept, key: 'acceptMaieuticWording' | 'restoreMaieuticWording') => {
    setBusy(true);
    setNote('');
    try {
      const res = await op({ variables: { id: draftId, field } });
      const out = res.data?.[key];
      setOffer(null);
      onApply(field, out?.value ?? '', out?.textOrigin ?? {});
    } catch (err: any) {
      setOffer(null);
      setNote(err?.message || 'That did not work.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 6, maxWidth: 700 }}>
      <Space size="small" wrap>
        <Button size="small" onClick={ask} loading={loading} disabled={tooShort || busy || remaining === 0}
          title={tooShort ? `Write at least ${WORDING_MIN_CHARS} characters first. The AI only rewords what you wrote.` : undefined}>
          Help me word this
        </Button>
        {label && <Tag color="purple">{label}</Tag>}
        {label === 'AI reworded' && (
          <Button size="small" type="link" onClick={() => run(restore, 'restoreMaieuticWording')} disabled={busy}>
            Put my text back
          </Button>
        )}
        {remaining !== null && remaining <= 2 && (
          <Text type="secondary">{remaining} suggestion{remaining === 1 ? '' : 's'} left for this field</Text>
        )}
      </Space>
      {offer && (
        <Alert style={{ marginTop: 8 }} type="info" showIcon={false}
          message={<Text strong>Suggested wording (nothing is changed until you use it)</Text>}
          description={(
            <div>
              <div data-testid="wording-suggestion" style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>{offer.suggestion}</div>
              <Space>
                <Button size="small" type="primary" disabled={busy} onClick={() => run(accept, 'acceptMaieuticWording')}>Use this</Button>
                <Button size="small" disabled={busy} onClick={() => setOffer(null)}>Discard</Button>
              </Space>
              <div><Text type="secondary">After using it you can still edit it. It is marked as AI-reworded.</Text></div>
            </div>
          )} />
      )}
      {note && <div style={{ marginTop: 6 }}><Text type="secondary" data-testid="wording-note">{note}</Text></div>}
    </div>
  );
};
