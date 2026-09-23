import { DEFAULT_WORKBENCH_TITLE, resolveWorkbenchMapTitle } from './workbenchNaming';

describe('workbenchNaming', () => {
  it('uses the workbench title for map title when provided', () => {
    expect(resolveWorkbenchMapTitle('Threat Hunt Workbench')).toBe('Threat Hunt Workbench');
  });

  it('falls back to New Workbench when title is empty', () => {
    expect(resolveWorkbenchMapTitle('')).toBe(DEFAULT_WORKBENCH_TITLE);
    expect(resolveWorkbenchMapTitle('   ')).toBe(DEFAULT_WORKBENCH_TITLE);
    expect(resolveWorkbenchMapTitle(null)).toBe(DEFAULT_WORKBENCH_TITLE);
  });

  it('defaults new workbench naming independent of ATT&CK TTP', () => {
    expect(DEFAULT_WORKBENCH_TITLE).toBe('New Workbench');
  });
});
