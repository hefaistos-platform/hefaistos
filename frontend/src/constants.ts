export const PLAYBOOK_STATUS_CHOICES = [
  { value: 'IDEA', label: 'Idea/Hypothesis' },
  { value: 'RESEARCH', label: 'In Research' },
  { value: 'DEVELOPMENT', label: 'In Development' },
  { value: 'REVIEW', label: 'Peer Review' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'TESTING', label: 'Testing/Validation' },
  { value: 'DEPLOYED', label: 'Deployed' },
  { value: 'TUNING', label: 'Tuning/Maintenance' },
];

export const PLAYBOOK_TYPE_CHOICES = [
  { value: 'HUNT', label: 'Hunt' },
  { value: 'DETECTION', label: 'Detection' },
];

// Centralized Robustness choices (mirror Django DetectionPlaybook choices)
export const ROBUSTNESS_CHOICES = [
  { value: 1, label: 'Level 1: Ephemeral (IP, Domain, Hash)' },
  { value: 2, label: 'Level 2: Core to Adversary-Brought Tool' },
  { value: 3, label: 'Level 3: Core to Pre-Existing Tool (LOLBin)' },
  { value: 4, label: 'Level 4: Core to Some Implementations' },
  { value: 5, label: 'Level 5: Core to Technique (Invariant)' },
];

export const EVENT_ROBUSTNESS_CHOICES = [
  { value: 'N', label: 'N/A' },
  { value: 'A', label: 'Application (A)' },
  { value: 'U', label: 'User-Mode (U)' },
  { value: 'K', label: 'Kernel-Mode (K)' },
  { value: 'P', label: 'Protocol Payload (P)' },
  { value: 'H', label: 'Protocol Header (H)' },
];