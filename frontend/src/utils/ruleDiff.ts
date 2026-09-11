export const normalize = (s: string | undefined | null): string =>
  (s ?? '').replace(/\r\n/g, '\n').replace(/\s+$/gm, '').trim();

export const isDirty = (current: string, saved: string): boolean =>
  normalize(current) !== normalize(saved);
