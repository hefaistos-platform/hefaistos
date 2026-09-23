export function resolveWorkbenchMapTitle(workbenchTitle?: string | null): string {
  const trimmedTitle = (workbenchTitle || '').trim();
  return trimmedTitle || 'New Workbench';
}

export function getNewWorkbenchDefaultTitle(): string {
  return 'New Workbench';
}
