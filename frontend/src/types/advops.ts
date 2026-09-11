export type ADVOPSStatus = 'IDEA' | 'RESEARCH' | 'DEVELOPMENT' | 'APPROVED' | 'TESTING' | 'DEPLOYED' | 'TUNING';
export type ADVOPSPriority = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export interface ADVOPSReport {
  id: string;
  huntId: string;
  hypothesis: string;
  status: ADVOPSStatus;
  priority: ADVOPSPriority;
  allowRemotePull?: boolean;
  author?: { id?: string; username?: string } | null;
  organization?: { id?: string; name?: string } | null;
  createdAt?: string;
  updatedAt?: string;
  verificationSummary?: string;
  infrastructureSummary?: string;
  pivotSummary?: string;
  falsePositiveSummary?: string;
  mitreSummary?: string;
  detectionLogicSummary?: string;
}
