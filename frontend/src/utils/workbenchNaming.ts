export const DEFAULT_WORKBENCH_TITLE = 'New Workbench';

export function resolveWorkbenchMapTitle(workbenchTitle?: string | null): string {
  const trimmedTitle = (workbenchTitle || '').trim();
  return trimmedTitle || DEFAULT_WORKBENCH_TITLE;
}
