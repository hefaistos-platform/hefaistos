import { isDirty, normalize } from './ruleDiff';

describe('ruleDiff', () => {
  it('normalizes CRLF and trailing whitespace', () => {
    expect(normalize('a\r\nb  \n')).toBe('a\nb');
  });

  it('treats equivalent content as clean after normalization', () => {
    expect(isDirty('line1\r\nline2  \n', 'line1\nline2')).toBe(false);
  });

  it('detects semantic content changes', () => {
    expect(isDirty('line1\nlineX', 'line1\nline2')).toBe(true);
  });
});
