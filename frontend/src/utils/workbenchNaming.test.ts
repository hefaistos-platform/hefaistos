import { getNewWorkbenchDefaultTitle, resolveWorkbenchMapTitle } from './workbenchNaming';

describe('workbenchNaming', () => {
  it('uses the workbench title for map title when provided', () => {
    expect(resolveWorkbenchMapTitle('Threat Hunt Workbench')).toBe('Threat Hunt Workbench');
  });

  it('falls back to New Workbench when title is empty', () => {
    expect(resolveWorkbenchMapTitle('')).toBe('New Workbench');
    expect(resolveWorkbenchMapTitle('   ')).toBe('New Workbench');
    expect(resolveWorkbenchMapTitle(null)).toBe('New Workbench');
  });

  it('defaults new workbench naming independent of ATT&CK TTP', () => {
    expect(getNewWorkbenchDefaultTitle()).toBe('New Workbench');
  });
});
