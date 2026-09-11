import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { App, QRCode, Checkbox } from 'antd';
import { Link } from 'react-router-dom';
import { credentialToJSON, parseRegistrationOptions } from '../utils/webauthn';
import { useAuth } from '../context/AuthContext';
import {
  WORKBENCH_PRESETS,
  WORKBENCH_SECTION_KEYS,
  WorkbenchSectionVisibilityMap,
  normalizeVisibilityLayer,
} from '../utils/workbenchVisibility';
import {
  normalizeSessionTimeoutHours,
  SESSION_TIMEOUT_HOURS_OPTIONS,
} from '../utils/authSession';

// --- TypeScript Interfaces ---
interface CreatedPlaybookLite {
  id: string;
  title: string;
  status: string;
  robustnessLevel: number;
  updatedAt: string;
}

interface UserProfileData {
  id: string;
  username: string;
  email: string;
  role: string;
  bio?: string;
  jobTitle?: string;
  slackHandle?: string;
  sessionTimeoutHours?: number;
  avatarUrl?: string;
  emailNotifyReviewApproved?: boolean;
  emailNotifySystemMessage?: boolean;
  emailNotifyChatMessage?: boolean;
  emailNotifyWorkbenchEdited?: boolean;
  emailNotifyNewsDigest?: boolean;
  workbenchVisibilityDefaults?: string | Record<string, unknown>;
  createdPlaybooks: CreatedPlaybookLite[];
  achAnalyses: AchAnalysisLite[];
  advopsReports: AdvOpsReportLite[];
}

interface GetMyProfileResult { me: UserProfileData | null }
interface UpdateProfileResult {
  updateProfile: {
    user: {
      id: string;
      username: string;
      bio?: string | null;
      jobTitle?: string | null;
      slackHandle?: string | null;
      sessionTimeoutHours?: number | null;
    };
  };
}
interface UpdateProfileVars {
  bio?: string;
  jobTitle?: string;
  slackHandle?: string;
  sessionTimeoutHours?: number;
}
type NotificationPreferenceKey =
  | 'emailNotifyReviewApproved'
  | 'emailNotifySystemMessage'
  | 'emailNotifyChatMessage'
  | 'emailNotifyWorkbenchEdited'
  | 'emailNotifyNewsDigest';

type NotificationPreferencesState = Record<NotificationPreferenceKey, boolean>;

interface UpdateNotificationPrefsResult {
  updateNotificationPreferences: {
    user: {
      id: string;
    } & NotificationPreferencesState;
  };
}

type UpdateNotificationPrefsVars = Partial<Record<NotificationPreferenceKey, boolean>>;

// ACH Analyses summary for profile page
interface AchAnalysisLite {
  id: string;
  title: string;
  status: string;
  updatedAt: string;
}

interface AdvOpsReportLite {
  id: string;
  huntId: string;
  hypothesis: string;
  status: string;
  priority: string;
  createdAt: string;
}

interface MyProfileSummaryData { myProfileSummary: { achAnalyses: AchAnalysisLite[] } }

// Query current user profile (matches new backend fields)
const GET_MY_PROFILE = gql`
  query GetMyProfile {
    me {
      id
      username
      email
      role
      bio
      jobTitle
      slackHandle
      sessionTimeoutHours
      avatarUrl
      emailNotifyReviewApproved
      emailNotifySystemMessage
      emailNotifyChatMessage
      emailNotifyWorkbenchEdited
      emailNotifyNewsDigest
      workbenchVisibilityDefaults
      createdPlaybooks {
        id
        title
        status
        robustnessLevel
        updatedAt
      }
      achAnalyses {
        id
        title
        status
        updatedAt
      }
      advopsReports {
        id
        huntId
        hypothesis
        status
        priority
        createdAt
      }
    }
  }
`;

// Rules created by this user (count via connection)
const MY_RULES_COUNT = gql`
  query MyRulesCount($author: String!) {
    rulesConnection(author: $author, first: 1) {
      totalCount
    }
  }
`;
interface MyRulesCountData { rulesConnection: { totalCount: number } }
interface MyRulesCountVars { author: string }

// Mutation uses snake_case argument names as expected by backend
const UPDATE_PROFILE_MUTATION = gql`
  mutation UpdateProfile(
    $bio: String
    $jobTitle: String
    $slackHandle: String
    $sessionTimeoutHours: Int
  ) {
    updateProfile(
      bio: $bio
      jobTitle: $jobTitle
      slackHandle: $slackHandle
      sessionTimeoutHours: $sessionTimeoutHours
    ) {
      user {
        id
        username
        bio
        jobTitle
        slackHandle
        sessionTimeoutHours
      }
    }
  }
`;

const UPDATE_NOTIFICATION_PREFS = gql`
  mutation UpdateNotificationPreferences(
    $emailNotifyReviewApproved: Boolean,
    $emailNotifySystemMessage: Boolean,
    $emailNotifyChatMessage: Boolean,
    $emailNotifyWorkbenchEdited: Boolean,
    $emailNotifyNewsDigest: Boolean
  ) {
    updateNotificationPreferences(
      emailNotifyReviewApproved: $emailNotifyReviewApproved,
      emailNotifySystemMessage: $emailNotifySystemMessage,
      emailNotifyChatMessage: $emailNotifyChatMessage,
      emailNotifyWorkbenchEdited: $emailNotifyWorkbenchEdited,
      emailNotifyNewsDigest: $emailNotifyNewsDigest
    ) {
      user {
        id
        emailNotifyReviewApproved
        emailNotifySystemMessage
        emailNotifyChatMessage
        emailNotifyWorkbenchEdited
        emailNotifyNewsDigest
      }
    }
  }
`;

const UPDATE_WORKBENCH_VISIBILITY_DEFAULTS = gql`
  mutation UpdateWorkbenchVisibilityDefaults($workbenchVisibilityDefaults: JSONString, $reset: Boolean) {
    updateWorkbenchVisibilityDefaults(workbenchVisibilityDefaults: $workbenchVisibilityDefaults, reset: $reset) {
      user {
        id
        workbenchVisibilityDefaults
      }
    }
  }
`;

interface UpdateWorkbenchVisibilityDefaultsResult {
  updateWorkbenchVisibilityDefaults: {
    user: {
      id: string;
      workbenchVisibilityDefaults?: string | Record<string, unknown> | null;
    };
  };
}

const UPLOAD_AVATAR = gql`
  mutation UploadAvatar($file: Upload!) {
    uploadAvatar(file: $file) {
      user {
        id
        avatarUrl
      }
    }
  }
`;

const CHANGE_PASSWORD = gql`
  mutation ChangePassword($currentPassword: String!, $newPassword: String!) {
    changePassword(currentPassword: $currentPassword, newPassword: $newPassword) {
      ok
      message
    }
  }
`;

const GET_MFA_STATUS = gql`
  query GetMfaStatus {
    mfaStatus {
      enabled
      totpEnabled
      pendingEnrollment
      backupCodesRemaining
      lockedUntil
      webauthnKeys
      adminMfaRequired
    }
    myWebauthnCredentials {
      id
      name
      createdAt
      lastUsedAt
    }
  }
`;

const BEGIN_TOTP_ENROLLMENT = gql`
  mutation BeginTotpEnrollment {
    beginTotpEnrollment {
      secret
      otpauthUri
    }
  }
`;

const CONFIRM_TOTP_ENROLLMENT = gql`
  mutation ConfirmTotpEnrollment($otpCode: String!) {
    confirmTotpEnrollment(otpCode: $otpCode) {
      ok
      backupCodes
    }
  }
`;

const DISABLE_TOTP_MFA = gql`
  mutation DisableTotpMfa($currentPassword: String!, $otpCode: String, $backupCode: String) {
    disableTotpMfa(currentPassword: $currentPassword, otpCode: $otpCode, backupCode: $backupCode) {
      ok
    }
  }
`;

const REGENERATE_BACKUP_CODES = gql`
  mutation RegenerateBackupCodes($currentPassword: String!, $otpCode: String!) {
    regenerateBackupCodes(currentPassword: $currentPassword, otpCode: $otpCode) {
      ok
      backupCodes
    }
  }
`;

const START_WEBAUTHN_REGISTRATION = gql`
  mutation StartWebauthnRegistration($credentialName: String) {
    startWebauthnRegistration(credentialName: $credentialName) {
      challengeId
      optionsJson
    }
  }
`;

const FINISH_WEBAUTHN_REGISTRATION = gql`
  mutation FinishWebauthnRegistration($challengeId: String!, $credential: JSONString!, $credentialName: String) {
    finishWebauthnRegistration(challengeId: $challengeId, credential: $credential, credentialName: $credentialName) {
      ok
      credentialObj {
        id
        name
      }
    }
  }
`;

const DELETE_WEBAUTHN_CREDENTIAL = gql`
  mutation DeleteWebauthnCredential($credentialId: ID!) {
    deleteWebauthnCredential(credentialId: $credentialId) {
      ok
    }
  }
`;

// --- AI Settings ---
const GET_AI_SETTINGS = gql`
  query GetMyAISettings {
    myAiSettings {
      hasOpenai
      hasGemini
      hasClaude
      preferredModel
      useOrgAi
    }
  }
`;
interface AiSettingsShape {
  myAiSettings: {
    hasOpenai: boolean;
    hasGemini: boolean;
    hasClaude: boolean;
    preferredModel: string | null;
    useOrgAi: boolean;
  };
}

const GET_ORG_AI_SETTINGS = gql`
  query GetOrgAISettingsForProfile {
    orgAiSettings {
      ollamaBaseUrl
      ollamaModel
      hasOllama
      hasOpenai
      hasGemini
      hasClaude
      hasAzureOpenai
      hasAnyProvider
      orgPreferredModel
    }
  }
`;
interface OrgAiSettingsShape {
  orgAiSettings: {
    ollamaBaseUrl: string;
    ollamaModel: string;
    hasOllama: boolean;
    hasOpenai: boolean;
    hasGemini: boolean;
    hasClaude: boolean;
    hasAzureOpenai: boolean;
    hasAnyProvider: boolean;
    orgPreferredModel: string;
  } | null;
}

const UPDATE_AI_SETTINGS = gql`
  mutation UpdateAISettings($openaiKey: String, $geminiKey: String, $claudeKey: String, $preferredModel: String, $useOrgAi: Boolean) {
    updateAiSettings(openaiKey: $openaiKey, geminiKey: $geminiKey, claudeKey: $claudeKey, preferredModel: $preferredModel, useOrgAi: $useOrgAi) {
      settings {
        hasOpenai
        hasGemini
        hasClaude
        preferredModel
        useOrgAi
      }
    }
  }
`;
interface UpdateAiSettingsResult {
  updateAiSettings: {
    ok: boolean;
    settings: {
      hasOpenai: boolean;
      hasGemini: boolean;
      hasClaude: boolean;
      preferredModel: string | null;
      useOrgAi: boolean;
    };
  };
}
interface UpdateAiSettingsVars {
  openaiKey?: string;
  geminiKey?: string;
  claudeKey?: string;
  preferredModel?: string;
  useOrgAi?: boolean;
}

const normalizePreferredModel = (value?: string | null) => {
  if (!value) return '';
  return value.trim();
};

const parseWorkbenchDefaults = (raw: unknown): WorkbenchSectionVisibilityMap => {
  const advancedDefaults = { ...WORKBENCH_PRESETS.ADVANCED };
  const normalizedLayer = normalizeVisibilityLayer(raw);
  return {
    ...advancedDefaults,
    ...(normalizedLayer.sectionVisibility || {}),
  };
};

// Query: myProfileSummary for ACH Analyses
const GET_MY_PROFILE_SUMMARY = gql`
  query MyProfileSummary {
    myProfileSummary {
      achAnalyses {
        id
        title
        status
        updatedAt
      }
    }
  }
`;

const SECTION_PAGE_SIZE = 6;

const buildNotificationPreferences = (
  user?: Partial<NotificationPreferencesState> | null,
): NotificationPreferencesState => ({
  emailNotifyReviewApproved: !!user?.emailNotifyReviewApproved,
  emailNotifySystemMessage: !!user?.emailNotifySystemMessage,
  emailNotifyChatMessage: !!user?.emailNotifyChatMessage,
  emailNotifyWorkbenchEdited: !!user?.emailNotifyWorkbenchEdited,
  emailNotifyNewsDigest: !!user?.emailNotifyNewsDigest,
});

export const UserProfile: React.FC = () => {
  const { message } = App.useApp();
  const { sessionTimeoutHours: authSessionTimeoutHours, updateSessionTimeoutHours } = useAuth();
  const { data, loading, refetch } = useQuery<GetMyProfileResult>(GET_MY_PROFILE);
  const { data: myRulesData } = useQuery<MyRulesCountData, MyRulesCountVars>(MY_RULES_COUNT, { skip: !data?.me?.username, variables: { author: data?.me?.username || '' } });
  const { data: summaryData } = useQuery<MyProfileSummaryData>(GET_MY_PROFILE_SUMMARY);
  const [updateProfile] = useMutation<UpdateProfileResult, UpdateProfileVars>(UPDATE_PROFILE_MUTATION);
  const [updateNotificationPrefs] = useMutation<UpdateNotificationPrefsResult, UpdateNotificationPrefsVars>(UPDATE_NOTIFICATION_PREFS);
  const [updateWorkbenchVisibilityDefaults, { loading: savingWorkbenchDefaults }] = useMutation<
    UpdateWorkbenchVisibilityDefaultsResult
  >(UPDATE_WORKBENCH_VISIBILITY_DEFAULTS);
  const [uploadAvatar] = useMutation(UPLOAD_AVATAR);
  const [changePassword, { loading: changingPassword }] = useMutation(CHANGE_PASSWORD);
  const [isEditing, setIsEditing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [avatarLoadError, setAvatarLoadError] = useState(false);
  const [formData, setFormData] = useState<UpdateProfileVars>({});
  const [workbenchesVisible, setWorkbenchesVisible] = useState(SECTION_PAGE_SIZE);
  const [achVisible, setAchVisible] = useState(SECTION_PAGE_SIZE);
  const [advopsVisible, setAdvopsVisible] = useState(SECTION_PAGE_SIZE);
  // Password change state
  const [passwordForm, setPasswordForm] = useState({ currentPassword: '', newPassword: '', confirmPassword: '' });
  const [showPasswordSection, setShowPasswordSection] = useState(false);
  const [enrollmentSecret, setEnrollmentSecret] = useState('');
  const [enrollmentOtpAuthUri, setEnrollmentOtpAuthUri] = useState('');
  const [otpEnrollmentCode, setOtpEnrollmentCode] = useState('');
  const [latestBackupCodes, setLatestBackupCodes] = useState<string[]>([]);
  const [mfaPassword, setMfaPassword] = useState('');
  const [mfaOtpCode, setMfaOtpCode] = useState('');
  const [newSecurityKeyName, setNewSecurityKeyName] = useState('Security Key');
  const [notificationPrefs, setNotificationPrefs] = useState<NotificationPreferencesState>(
    buildNotificationPreferences(data?.me),
  );
  const [savingNotificationKey, setSavingNotificationKey] = useState<NotificationPreferenceKey | null>(null);
  const [workbenchDefaults, setWorkbenchDefaults] = useState<WorkbenchSectionVisibilityMap>({ ...WORKBENCH_PRESETS.ADVANCED });
  // AI settings state (typed)
  const { data: aiData, refetch: refetchAI } = useQuery<AiSettingsShape>(GET_AI_SETTINGS, { fetchPolicy: 'cache-and-network' });
  const { data: orgAiData } = useQuery<OrgAiSettingsShape>(GET_ORG_AI_SETTINGS, { errorPolicy: 'ignore' });
  const [updateAISettings, { loading: savingAI }] = useMutation<UpdateAiSettingsResult, UpdateAiSettingsVars>(UPDATE_AI_SETTINGS);
  const { data: mfaData, refetch: refetchMfa } = useQuery(GET_MFA_STATUS, { fetchPolicy: 'cache-and-network' });
  const [beginTotpEnrollment, { loading: startingTotp }] = useMutation(BEGIN_TOTP_ENROLLMENT);
  const [confirmTotpEnrollment, { loading: confirmingTotp }] = useMutation(CONFIRM_TOTP_ENROLLMENT);
  const [disableTotpMfa, { loading: disablingTotp }] = useMutation(DISABLE_TOTP_MFA);
  const [regenerateBackupCodes, { loading: regeneratingBackup }] = useMutation(REGENERATE_BACKUP_CODES);
  const [startWebauthnRegistration, { loading: startingWebauthn }] = useMutation(START_WEBAUTHN_REGISTRATION);
  const [finishWebauthnRegistration, { loading: finishingWebauthn }] = useMutation(FINISH_WEBAUTHN_REGISTRATION);
  const [deleteWebauthnCredential] = useMutation(DELETE_WEBAUTHN_CREDENTIAL);
  const [aiForm, setAiForm] = useState({ openaiKey: '', geminiKey: '', claudeKey: '', preferredModel: '', useOrgAi: false });
  const user = data?.me;

  // Sync preferredModel and useOrgAi from server once settings load; always reflect server value
  useEffect(() => {
    const serverModel = aiData?.myAiSettings?.preferredModel;
    if (serverModel !== undefined && serverModel !== null) {
      const normalized = normalizePreferredModel(serverModel);
      setAiForm(prev => ({ ...prev, preferredModel: normalized || '' }));
    }
  }, [aiData?.myAiSettings?.preferredModel]);

  useEffect(() => {
    if (aiData?.myAiSettings?.useOrgAi !== undefined) {
      setAiForm(prev => ({ ...prev, useOrgAi: aiData.myAiSettings.useOrgAi }));
    }
  }, [aiData?.myAiSettings?.useOrgAi]);

  useEffect(() => {
    setNotificationPrefs(buildNotificationPreferences(data?.me));
  }, [
    data?.me?.id,
    data?.me?.emailNotifyReviewApproved,
    data?.me?.emailNotifySystemMessage,
    data?.me?.emailNotifyChatMessage,
    data?.me?.emailNotifyWorkbenchEdited,
    data?.me?.emailNotifyNewsDigest,
  ]);

  useEffect(() => {
    setWorkbenchDefaults(parseWorkbenchDefaults(data?.me?.workbenchVisibilityDefaults));
  }, [data?.me?.workbenchVisibilityDefaults]);

  if (loading) return <div className="profile-theme p-8">Loading Profile...</div>;
  if (!user) return <div className="profile-theme p-8">No profile.</div>;
  const currentSessionTimeoutHours = normalizeSessionTimeoutHours(
    user.sessionTimeoutHours ?? authSessionTimeoutHours,
  );
  const isWorkbenchPresetSelected = (preset: keyof typeof WORKBENCH_PRESETS) => WORKBENCH_SECTION_KEYS.every(
    (key) => Boolean(workbenchDefaults[key]) === Boolean(WORKBENCH_PRESETS[preset][key]),
  );
  const isSimpleWorkbenchPresetSelected = isWorkbenchPresetSelected('SIMPLE');
  const isAdvancedWorkbenchPresetSelected = isWorkbenchPresetSelected('ADVANCED');

  const handleNotificationPreferenceChange = async (key: NotificationPreferenceKey, checked: boolean) => {
    const previousValue = notificationPrefs[key];
    setNotificationPrefs(prev => ({ ...prev, [key]: checked }));
    setSavingNotificationKey(key);
    try {
      const result = await updateNotificationPrefs({ variables: { [key]: checked } });
      const updated = result.data?.updateNotificationPreferences?.user;
      if (updated) {
        setNotificationPrefs(buildNotificationPreferences(updated));
      } else {
        await refetch();
      }
    } catch (error: any) {
      setNotificationPrefs(prev => ({ ...prev, [key]: previousValue }));
      message.error(error?.message || 'Failed to update notification preference');
    } finally {
      setSavingNotificationKey(null);
    }
  };

  const notificationPreferenceItems: Array<{ key: NotificationPreferenceKey; label: string }> = [
    { key: 'emailNotifyReviewApproved', label: 'Review approvals' },
    { key: 'emailNotifySystemMessage', label: 'System messages' },
    { key: 'emailNotifyChatMessage', label: 'Chat messages' },
    { key: 'emailNotifyWorkbenchEdited', label: 'Workbench edits' },
    { key: 'emailNotifyNewsDigest', label: 'News digest' },
  ];

  const handleSaveProfile = async () => {
    const requestedTimeoutHours = normalizeSessionTimeoutHours(
      formData.sessionTimeoutHours ?? currentSessionTimeoutHours,
    );
    try {
      const result = await updateProfile({
        variables: {
          bio: formData.bio,
          jobTitle: formData.jobTitle,
          slackHandle: formData.slackHandle,
          sessionTimeoutHours: requestedTimeoutHours,
        },
      });
      if (result.data?.updateProfile?.user) {
        const mutationHours = normalizeSessionTimeoutHours(
          result.data.updateProfile.user.sessionTimeoutHours ?? requestedTimeoutHours,
        );
        updateSessionTimeoutHours(mutationHours);

        const refreshed = await refetch();
        const persistedHours = normalizeSessionTimeoutHours(
          refreshed.data?.me?.sessionTimeoutHours ?? mutationHours,
        );
        updateSessionTimeoutHours(persistedHours);

        if (persistedHours !== requestedTimeoutHours) {
          message.warning(
            `Profile saved, but inactivity timeout remained ${persistedHours}h (requested ${requestedTimeoutHours}h).`,
          );
        } else {
          message.success('Profile updated');
        }
        setIsEditing(false);
      }
    } catch (error: any) {
      message.error(`Profile update error: ${error.message}`);
    }
  };

  const statusColor = (status: string) => {
    switch (status) {
      case 'DEPLOYED': return 'bg-green-100 text-green-800 border-green-200';
      case 'REVIEW': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <div className="profile-theme max-w-7xl mx-auto p-8 space-y-10">
      {/* Header Card */}
      <div className="bg-white rounded-lg shadow-sm border p-8 flex gap-8 items-start">
        <div className="w-32 h-32 rounded-full bg-gray-200 border-4 border-white shadow overflow-hidden flex-shrink-0 relative group">
          {user.avatarUrl && !avatarLoadError ? (
            <img
              src={user.avatarUrl}
              alt="Avatar"
              className="w-full h-full object-cover"
              onError={() => setAvatarLoadError(true)}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-4xl text-gray-400 font-bold bg-gray-100">
              {user.username.charAt(0).toUpperCase()}
            </div>
          )}
          {uploading && (
            <div className="absolute inset-0 bg-white/60 flex items-center justify-center">
              <div className="animate-spin h-10 w-10 border-4 border-blue-500 border-t-transparent rounded-full" />
            </div>
          )}
          <input
            id="avatarUploadInput"
            type="file"
            accept="image/*"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              try {
                setUploading(true);
                setAvatarLoadError(false);
                await uploadAvatar({ variables: { file } });
                await refetch();
                message.success('Avatar updated');
              } catch (err: any) {
                // eslint-disable-next-line no-console
                console.error('Upload failed', err);
                message.error(err?.message || 'Avatar upload failed');
              } finally {
                setUploading(false);
                e.target.value = '';
              }
            }}
          />
          <label
            htmlFor="avatarUploadInput"
            className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-xs cursor-pointer transition-opacity"
          >
            {uploading ? 'Uploading...' : 'Change'}
          </label>
        </div>
        <div className="flex-1">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">{user.username}</h1>
              <div className="flex items-center gap-2 mt-1">
                <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-xs font-bold uppercase tracking-wide">{user.role}</span>
                {user.jobTitle && <span className="text-gray-500 text-sm">| {user.jobTitle}</span>}
              </div>
            </div>
            <button
              className="px-4 py-2 text-sm font-semibold rounded border bg-gray-50 hover:bg-gray-100"
              onClick={() => {
                setFormData({
                  bio: user.bio || '',
                  jobTitle: user.jobTitle || '',
                  slackHandle: user.slackHandle || '',
                  sessionTimeoutHours: currentSessionTimeoutHours,
                });
                setIsEditing(!isEditing);
              }}
            >
              {isEditing ? 'Cancel' : 'Edit Profile'}
            </button>
          </div>
          {isEditing ? (
            <div className="mt-4 grid grid-cols-2 gap-4 bg-gray-50 p-4 rounded">
              <input
                className="p-2 border rounded"
                placeholder="Job Title"
                value={formData.jobTitle || ''}
                onChange={e => setFormData({ ...formData, jobTitle: e.target.value })}
              />
              <input
                className="p-2 border rounded"
                placeholder="Slack Handle (@...)"
                value={formData.slackHandle || ''}
                onChange={e => setFormData({ ...formData, slackHandle: e.target.value })}
              />
              <textarea
                className="col-span-2 p-2 border rounded h-24"
                placeholder="About Me..."
                value={formData.bio || ''}
                onChange={e => setFormData({ ...formData, bio: e.target.value })}
              />
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-gray-600 mb-1">Auto logout after inactivity</label>
                <select
                  className="w-full p-2 border rounded bg-white"
                  value={normalizeSessionTimeoutHours(formData.sessionTimeoutHours ?? currentSessionTimeoutHours)}
                  onChange={(e) => setFormData({
                    ...formData,
                    sessionTimeoutHours: normalizeSessionTimeoutHours(e.target.value),
                  })}
                >
                  {SESSION_TIMEOUT_HOURS_OPTIONS.map((hours) => (
                    <option key={hours} value={hours}>
                      {hours} hours
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-2 text-right">
                <button
                  className="px-4 py-2 text-sm font-semibold rounded bg-blue-600 text-white hover:bg-blue-700"
                  onClick={handleSaveProfile}
                >
                  Save Changes
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              <p className="text-gray-600 leading-relaxed">{user.bio || 'No bio yet.'}</p>
              {user.slackHandle && (
                <div className="text-sm text-gray-500">
                  Slack: <span className="text-blue-600 font-mono ml-1">{user.slackHandle}</span>
                </div>
              )}
              <div className="text-sm text-gray-500">
                Auto logout after inactivity: <span className="font-semibold text-gray-700 ml-1">{currentSessionTimeoutHours} hours</span>
              </div>
              {/* Email Notification Preferences */}
              <div className="mt-4 bg-gray-50 p-4 rounded border">
                <div className="font-semibold text-gray-700 mb-2">Email Notifications</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
                  {notificationPreferenceItems.map(({ key, label }) => (
                    <Checkbox
                      key={key}
                      className="notification-checkbox"
                      checked={notificationPrefs[key]}
                      disabled={savingNotificationKey === key}
                      onChange={(e) => handleNotificationPreferenceChange(key, e.target.checked)}
                    >
                      {label}
                    </Checkbox>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded border shadow-sm flex items-center">
          <div className="p-3 bg-purple-100 rounded-lg text-purple-600 mr-4 text-sm">⚡</div>
          <div>
            <div className="text-2xl font-bold">{(user.createdPlaybooks?.length || 0) + (user.achAnalyses?.length || 0) + (user.advopsReports?.length || 0)}</div>
            <div className="text-xs text-gray-500 uppercase font-bold">TOTAL ANALYSES</div>
          </div>
        </div>
        <div className="bg-white p-4 rounded border shadow-sm flex items-center">
          <div className="p-3 bg-green-100 rounded-lg text-green-600 mr-4 text-sm">🛡️</div>
          <div>
            <div className="text-2xl font-bold">{user.createdPlaybooks.filter((p: any) => p.status === 'DEPLOYED').length}</div>
            <div className="text-xs text-gray-500 uppercase font-bold">Deployed to SIEM</div>
          </div>
        </div>
        <div className="bg-white p-4 rounded border shadow-sm flex items-center">
          <div className="p-3 bg-blue-100 rounded-lg text-blue-600 mr-4 text-sm">📜</div>
          <div>
            <div className="text-2xl font-bold">{myRulesData?.rulesConnection?.totalCount ?? 0}</div>
            <div className="text-xs text-gray-500 uppercase font-bold">Rules Created</div>
          </div>
        </div>
      </div>

      {/* Security Settings - Change Password */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <span>🔐</span>
            <span>Security Settings</span>
          </h2>
          <button
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
            onClick={() => setShowPasswordSection(!showPasswordSection)}
          >
            {showPasswordSection ? 'Cancel' : 'Change Password'}
          </button>
        </div>
        
        {showPasswordSection ? (
          <div className="space-y-4">
            <p className="text-xs text-gray-500 mb-4">
              Enter your current password and choose a new password. Password must be at least 8 characters.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-semibold text-gray-600 block mb-1">Current Password</label>
                <input
                  type="password"
                  className="w-full p-2 text-sm border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Enter current password"
                  value={passwordForm.currentPassword}
                  onChange={e => setPasswordForm({ ...passwordForm, currentPassword: e.target.value })}
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-600 block mb-1">New Password</label>
                <input
                  type="password"
                  className="w-full p-2 text-sm border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Enter new password"
                  value={passwordForm.newPassword}
                  onChange={e => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-600 block mb-1">Confirm New Password</label>
                <input
                  type="password"
                  className="w-full p-2 text-sm border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Confirm new password"
                  value={passwordForm.confirmPassword}
                  onChange={e => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                />
              </div>
            </div>
            {passwordForm.newPassword && passwordForm.confirmPassword && passwordForm.newPassword !== passwordForm.confirmPassword && (
              <p className="text-xs text-red-500">Passwords do not match</p>
            )}
            <div className="flex justify-end">
              <button
                className="px-4 py-2 text-sm font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
                disabled={
                  changingPassword ||
                  !passwordForm.currentPassword ||
                  !passwordForm.newPassword ||
                  !passwordForm.confirmPassword ||
                  passwordForm.newPassword !== passwordForm.confirmPassword ||
                  passwordForm.newPassword.length < 8
                }
                onClick={async () => {
                  try {
                    await changePassword({
                      variables: {
                        currentPassword: passwordForm.currentPassword,
                        newPassword: passwordForm.newPassword,
                      },
                    });
                    message.success('Password changed successfully');
                    setPasswordForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
                    setShowPasswordSection(false);
                  } catch (e: any) {
                    message.error(e.message || 'Failed to change password');
                  }
                }}
              >
                {changingPassword ? 'Changing...' : 'Update Password'}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            Click "Change Password" to update your account password.
          </p>
        )}
      </div>

      {/* MFA and Security Keys */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mt-8">
        <h2 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
          <span>🛡️</span>
          <span>Multi-Factor Authentication</span>
        </h2>
        <p className="text-xs text-gray-500 mb-4">
          MFA is optional for users and required for admin accounts. You can use authenticator app codes and/or security keys.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 text-sm">
          <div className="rounded border p-3 bg-gray-50">
            <div className="text-xs text-gray-500">TOTP MFA</div>
            <div className="font-semibold">{mfaData?.mfaStatus?.enabled ? 'Enabled' : 'Disabled'}</div>
          </div>
          <div className="rounded border p-3 bg-gray-50">
            <div className="text-xs text-gray-500">Backup Codes</div>
            <div className="font-semibold">{mfaData?.mfaStatus?.backupCodesRemaining ?? 0} remaining</div>
          </div>
          <div className="rounded border p-3 bg-gray-50">
            <div className="text-xs text-gray-500">Security Keys</div>
            <div className="font-semibold">{mfaData?.mfaStatus?.webauthnKeys ?? 0} enrolled</div>
          </div>
        </div>

        {!mfaData?.mfaStatus?.totpEnabled && (
          <div className="space-y-3 border rounded p-4 mb-4">
            <div className="font-semibold text-sm">Enroll Authenticator App (TOTP)</div>
            {!enrollmentSecret ? (
              <button
                className="px-4 py-2 text-sm font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                disabled={startingTotp}
                onClick={async () => {
                  try {
                    const res = await beginTotpEnrollment();
                    setEnrollmentSecret(res.data?.beginTotpEnrollment?.secret || '');
                    setEnrollmentOtpAuthUri(res.data?.beginTotpEnrollment?.otpauthUri || '');
                    message.success('TOTP enrollment started');
                  } catch (e: any) {
                    message.error(e.message || 'Failed to start TOTP enrollment');
                  }
                }}
              >
                {startingTotp ? 'Starting...' : 'Start TOTP Enrollment'}
              </button>
            ) : (
              <div className="space-y-2">
                {enrollmentOtpAuthUri && (
                  <div className="flex justify-center">
                    <QRCode value={enrollmentOtpAuthUri} size={180} />
                  </div>
                )}
                <div className="text-xs text-gray-600">Add this secret in Google/Microsoft Authenticator:</div>
                <div className="font-mono text-sm bg-gray-100 border rounded p-2 break-all">{enrollmentSecret}</div>
                <input
                  type="text"
                  className="w-full p-2 text-sm border rounded"
                  placeholder="Enter 6-digit code to confirm"
                  value={otpEnrollmentCode}
                  onChange={e => setOtpEnrollmentCode(e.target.value)}
                />
                <button
                  className="px-4 py-2 text-sm font-semibold rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-60"
                  disabled={!otpEnrollmentCode || confirmingTotp}
                  onClick={async () => {
                    try {
                      const res = await confirmTotpEnrollment({ variables: { otpCode: otpEnrollmentCode } });
                      setLatestBackupCodes(res.data?.confirmTotpEnrollment?.backupCodes || []);
                      setEnrollmentSecret('');
                      setEnrollmentOtpAuthUri('');
                      setOtpEnrollmentCode('');
                      await refetchMfa();
                      message.success('TOTP MFA enabled');
                    } catch (e: any) {
                      message.error(e.message || 'Failed to confirm TOTP');
                    }
                  }}
                >
                  {confirmingTotp ? 'Verifying...' : 'Confirm and Enable'}
                </button>
              </div>
            )}
          </div>
        )}

        {mfaData?.mfaStatus?.totpEnabled && (
          <div className="space-y-2 border rounded p-4 mb-4">
            <div className="font-semibold text-sm">Manage Backup Codes</div>
            <input
              type="password"
              className="w-full p-2 text-sm border rounded"
              placeholder="Current password"
              value={mfaPassword}
              onChange={e => setMfaPassword(e.target.value)}
            />
            <input
              type="text"
              className="w-full p-2 text-sm border rounded"
              placeholder="Current authenticator code"
              value={mfaOtpCode}
              onChange={e => setMfaOtpCode(e.target.value)}
            />
            <div className="flex gap-2">
              <button
                className="px-4 py-2 text-sm font-semibold rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60"
                disabled={!mfaPassword || !mfaOtpCode || regeneratingBackup}
                onClick={async () => {
                  try {
                    const res = await regenerateBackupCodes({ variables: { currentPassword: mfaPassword, otpCode: mfaOtpCode } });
                    setLatestBackupCodes(res.data?.regenerateBackupCodes?.backupCodes || []);
                    await refetchMfa();
                    message.success('Backup codes regenerated');
                  } catch (e: any) {
                    message.error(e.message || 'Failed to regenerate backup codes');
                  }
                }}
              >
                {regeneratingBackup ? 'Regenerating...' : 'Regenerate Backup Codes'}
              </button>
              <button
                className="px-4 py-2 text-sm font-semibold rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-60"
                disabled={!mfaPassword || !mfaOtpCode || disablingTotp}
                onClick={async () => {
                  try {
                    await disableTotpMfa({ variables: { currentPassword: mfaPassword, otpCode: mfaOtpCode } });
                    await refetchMfa();
                    message.success('TOTP MFA disabled');
                  } catch (e: any) {
                    message.error(e.message || 'Failed to disable MFA');
                  }
                }}
              >
                {disablingTotp ? 'Disabling...' : 'Disable TOTP MFA'}
              </button>
            </div>
          </div>
        )}

        {latestBackupCodes.length > 0 && (
          <div className="border border-amber-300 bg-amber-50 rounded p-3 mb-4">
            <div className="text-sm font-semibold text-amber-800 mb-2">Save these backup codes now (shown once):</div>
            <div className="grid grid-cols-2 gap-2 font-mono text-xs">
              {latestBackupCodes.map(code => <div key={code}>{code}</div>)}
            </div>
          </div>
        )}

        <div className="border rounded p-4">
          <div className="font-semibold text-sm mb-2">Security Keys (YubiKey/WebAuthn)</div>
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              className="flex-1 p-2 text-sm border rounded"
              placeholder="Key name (e.g., YubiKey 5)"
              value={newSecurityKeyName}
              onChange={e => setNewSecurityKeyName(e.target.value)}
            />
            <button
              className="px-4 py-2 text-sm font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
              disabled={startingWebauthn || finishingWebauthn}
              onClick={async () => {
                try {
                  const started = await startWebauthnRegistration({ variables: { credentialName: newSecurityKeyName || 'Security Key' } });
                  const challengeId = started.data?.startWebauthnRegistration?.challengeId;
                  const optionsJson = started.data?.startWebauthnRegistration?.optionsJson;
                  if (!challengeId || !optionsJson) return;
                  const credential = await navigator.credentials.create({
                    publicKey: parseRegistrationOptions(optionsJson),
                  }) as PublicKeyCredential | null;
                  if (!credential) return;
                  await finishWebauthnRegistration({
                    variables: {
                      challengeId,
                      credential: JSON.stringify(credentialToJSON(credential)),
                      credentialName: newSecurityKeyName || 'Security Key',
                    },
                  });
                  await refetchMfa();
                  message.success('Security key enrolled');
                } catch (e: any) {
                  message.error(e.message || 'Security key enrollment failed');
                }
              }}
            >
              {startingWebauthn || finishingWebauthn ? 'Waiting...' : 'Add Security Key'}
            </button>
          </div>
          <div className="space-y-2">
            {(mfaData?.myWebauthnCredentials || []).map((cred: any) => (
              <div key={cred.id} className="flex items-center justify-between border rounded p-2 text-sm">
                <div>
                  <div className="font-medium">{cred.name || 'Security Key'}</div>
                  <div className="text-xs text-gray-500">Added: {new Date(cred.createdAt).toLocaleString()}</div>
                </div>
                <button
                  className="text-red-600 hover:text-red-800 text-xs font-semibold"
                  onClick={async () => {
                    await deleteWebauthnCredential({ variables: { credentialId: cred.id } });
                    await refetchMfa();
                  }}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* AI Settings */}
      <div className="bg-white rounded-lg shadow-sm border p-6 mt-8">
        <h2 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
          <span>AI Assistant Settings</span>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-purple-100 text-purple-700 border border-purple-200">Experimental</span>
        </h2>
        <p className="text-xs text-gray-500 mb-4">Store provider keys (never shown again) and set a default model used for AI rule generation. You can type any model identifier supported by your provider.</p>

        {/* Organization AI toggle (always shown; disabled when org has no providers configured) */}
        <div className={`mb-5 p-4 rounded-lg border ${orgAiData?.orgAiSettings?.hasAnyProvider ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className={`text-sm font-semibold ${orgAiData?.orgAiSettings?.hasAnyProvider ? 'text-blue-900' : 'text-gray-600'}`}>Use Organization AI</p>
              {orgAiData?.orgAiSettings?.hasAnyProvider ? (
                <p className="text-xs text-blue-700 mt-0.5">
                  Your organization has configured the following AI providers:{' '}
                  {[
                    orgAiData.orgAiSettings.hasOllama && `Ollama (${orgAiData.orgAiSettings.ollamaModel})`,
                    orgAiData.orgAiSettings.hasOpenai && 'OpenAI',
                    orgAiData.orgAiSettings.hasAzureOpenai && 'Azure OpenAI',
                    orgAiData.orgAiSettings.hasGemini && 'Gemini',
                    orgAiData.orgAiSettings.hasClaude && 'Claude',
                  ].filter(Boolean).join(', ')}.
                  Enable this to use them instead of your personal API keys.
                </p>
              ) : (
                <p className="text-xs text-gray-500 mt-0.5">
                  Your organization has not configured any AI providers yet. Ask your administrator to set up organization-wide AI in the System Settings.
                </p>
              )}
            </div>
            <label className={`relative inline-flex items-center ml-4 flex-shrink-0 ${orgAiData?.orgAiSettings?.hasAnyProvider ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'}`}>
              <input
                type="checkbox"
                className="sr-only peer"
                checked={aiForm.useOrgAi}
                onChange={e => setAiForm({ ...aiForm, useOrgAi: e.target.checked })}
                disabled={!orgAiData?.orgAiSettings?.hasAnyProvider}
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>
        </div>

        <div className={`grid grid-cols-1 md:grid-cols-2 gap-4 ${aiForm.useOrgAi ? 'opacity-50 pointer-events-none' : ''}`}>
          <div>
            <label className="text-xs font-semibold text-gray-600 block mb-1">OpenAI Key</label>
            <input
              type="password"
              className="w-full p-2 text-sm border rounded"
              placeholder={aiData?.myAiSettings?.hasOpenai ? '•••••••• (set)' : 'sk-...'}
              value={aiForm.openaiKey}
              onChange={e => setAiForm({ ...aiForm, openaiKey: e.target.value })}
              disabled={aiForm.useOrgAi}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 block mb-1">Gemini Key</label>
            <input
              type="password"
              className="w-full p-2 text-sm border rounded"
              placeholder={aiData?.myAiSettings?.hasGemini ? '•••••••• (set)' : '...' }
              value={aiForm.geminiKey}
              onChange={e => setAiForm({ ...aiForm, geminiKey: e.target.value })}
              disabled={aiForm.useOrgAi}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 block mb-1">Claude Key</label>
            <input
              type="password"
              className="w-full p-2 text-sm border rounded"
              placeholder={aiData?.myAiSettings?.hasClaude ? '•••••••• (set)' : '...' }
              value={aiForm.claudeKey}
              onChange={e => setAiForm({ ...aiForm, claudeKey: e.target.value })}
              disabled={aiForm.useOrgAi}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 block mb-1">Preferred Model</label>
            <input
              type="text"
              className="w-full p-2 text-sm border rounded"
              value={aiForm.preferredModel}
              onChange={e => setAiForm({ ...aiForm, preferredModel: e.target.value })}
              placeholder="e.g. GPT-5.5, GEMINI-3.5-FLASH, CLAUDE-SONNET-4.6, llama3.1"
              disabled={aiForm.useOrgAi}
            />
            <p className="text-xs text-gray-500 mt-1">Leave blank to let HEFAISTOS auto-select based on configured providers.</p>
          </div>
        </div>
        {aiForm.useOrgAi && (
          <p className="text-xs text-blue-600 mt-2">
            Personal API keys are disabled while using the organization AI model.
          </p>
        )}
        <div className="mt-4 flex justify-end">
          <button
            className="px-4 py-2 text-sm font-semibold rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-60"
            disabled={savingAI}
            onClick={async () => {
              try {
                const skipPersonal = aiForm.useOrgAi;
                const personalVal = (v: string | undefined) => skipPersonal ? undefined : (v || undefined);
                await updateAISettings({ variables: {
                  openaiKey: personalVal(aiForm.openaiKey),
                  geminiKey: personalVal(aiForm.geminiKey),
                  claudeKey: personalVal(aiForm.claudeKey),
                  preferredModel: personalVal(normalizePreferredModel(aiForm.preferredModel)),
                  useOrgAi: aiForm.useOrgAi,
                }});
                setAiForm({ ...aiForm, openaiKey: '', geminiKey: '', claudeKey: '' });
                await refetchAI();
                message.success('AI settings saved');
              } catch (e: any) {
                message.error(e.message || 'Failed to save AI settings');
              }
            }}
          >
            {savingAI ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm border p-6 mt-8">
        <h2 className="text-lg font-bold text-gray-800 mb-2">Workbench Layout Defaults</h2>
        <p className="text-xs text-gray-500 mb-4">
          Configure which optional sections are visible by default when you open a workbench.
        </p>
        <div className="flex gap-2 mb-4">
          <button
            className={`workbench-defaults-button px-3 py-1.5 text-xs font-semibold rounded border bg-gray-50 hover:bg-gray-100 ${isSimpleWorkbenchPresetSelected ? 'workbench-defaults-button-active' : ''}`}
            aria-pressed={isSimpleWorkbenchPresetSelected}
            onClick={() => {
              setWorkbenchDefaults({ ...WORKBENCH_PRESETS.SIMPLE });
              message.success('Simple mode deployed successfully');
            }}
          >
            Simple Mode
          </button>
          <button
            className={`workbench-defaults-button px-3 py-1.5 text-xs font-semibold rounded border bg-gray-50 hover:bg-gray-100 ${isAdvancedWorkbenchPresetSelected ? 'workbench-defaults-button-active' : ''}`}
            aria-pressed={isAdvancedWorkbenchPresetSelected}
            onClick={() => {
              setWorkbenchDefaults({ ...WORKBENCH_PRESETS.ADVANCED });
              message.success('Advanced mode deployed successfully');
            }}
          >
            Advanced Mode
          </button>
        </div>
        <div className="space-y-2 text-sm mb-4">
          <label className="flex items-center justify-between">
            <span>Capability Abstraction Map</span>
            <input
              type="checkbox"
              className="workbench-defaults-checkbox"
              checked={Boolean(workbenchDefaults.capabilityMap)}
              onChange={(e) => setWorkbenchDefaults((prev) => ({ ...prev, capabilityMap: e.target.checked }))}
            />
          </label>
          <label className="flex items-center justify-between">
            <span>Capability Abstraction Library</span>
            <input
              type="checkbox"
              className="workbench-defaults-checkbox"
              checked={Boolean(workbenchDefaults.capabilityLibrary)}
              onChange={(e) => setWorkbenchDefaults((prev) => ({ ...prev, capabilityLibrary: e.target.checked }))}
            />
          </label>
          <label className="flex items-center justify-between">
            <span>Activity Overview</span>
            <input
              type="checkbox"
              className="workbench-defaults-checkbox"
              checked={Boolean(workbenchDefaults.activityOverview)}
              onChange={(e) => setWorkbenchDefaults((prev) => ({ ...prev, activityOverview: e.target.checked }))}
            />
          </label>
          <label className="flex items-center justify-between">
            <span>Part 4: SOAR Configuration</span>
            <input
              type="checkbox"
              className="workbench-defaults-checkbox"
              checked={Boolean(workbenchDefaults.part4)}
              onChange={(e) => setWorkbenchDefaults((prev) => ({ ...prev, part4: e.target.checked }))}
            />
          </label>
          <label className="flex items-center justify-between">
            <span>Part 5: Testing & Validation</span>
            <input
              type="checkbox"
              className="workbench-defaults-checkbox"
              checked={Boolean(workbenchDefaults.part5)}
              onChange={(e) => setWorkbenchDefaults((prev) => ({ ...prev, part5: e.target.checked }))}
            />
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <button
            className="workbench-defaults-button px-3 py-2 text-xs font-semibold rounded border bg-white hover:bg-gray-50"
            disabled={savingWorkbenchDefaults}
            onClick={async () => {
              try {
                await updateWorkbenchVisibilityDefaults({ variables: { reset: true } });
                await refetch();
                message.success('Workbench defaults reset');
              } catch (error: any) {
                message.error(error?.message || 'Failed to reset workbench defaults');
              }
            }}
          >
            Reset
          </button>
          <button
            className="workbench-defaults-primary-button px-3 py-2 text-xs font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
            disabled={savingWorkbenchDefaults}
            onClick={async () => {
              try {
                await updateWorkbenchVisibilityDefaults({
                  variables: {
                    workbenchVisibilityDefaults: JSON.stringify({ sectionVisibility: workbenchDefaults }),
                    reset: false,
                  },
                });
                await refetch();
                message.success('Workbench defaults saved');
              } catch (error: any) {
                message.error(error?.message || 'Failed to save workbench defaults');
              }
            }}
          >
            {savingWorkbenchDefaults ? 'Saving...' : 'Save Defaults'}
          </button>
        </div>
      </div>

      {/* Playbooks */}
      <h2 className="text-xl font-bold text-gray-800 mt-8 mb-4 flex items-center gap-2">My Workbenches</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {user.createdPlaybooks.slice(0, workbenchesVisible).map((pb: any) => (
          <Link key={pb.id} to={`/playbooks/${pb.id}`} className="bg-white p-5 rounded-lg border shadow-sm hover:shadow-md transition-shadow group">
            <div className="flex justify-between items-start mb-2">
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${statusColor(pb.status)}`}>{pb.status}</span>
              <span className="text-xs text-gray-400">{new Date(pb.updatedAt).toLocaleDateString()}</span>
            </div>
            <h3 className="font-bold text-lg text-gray-900 mb-2 group-hover:text-blue-600 transition-colors">{pb.title || 'Untitled Playbook'}</h3>
            {pb.robustnessLevel > 0 && (
              <div className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded inline-block">Robustness: {pb.robustnessLevel}/5</div>
            )}
          </Link>
        ))}
        <Link to="/playbooks/list" className="border-2 border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center p-6 text-gray-400 hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50 transition-all">
          <span className="text-4xl mb-2">＋</span>
          <span className="font-bold">Create New Playbook</span>
        </Link>
      </div>
      {user.createdPlaybooks.length > workbenchesVisible && (
        <div className="flex justify-center mt-2">
          <button
            className="px-6 py-2 text-sm font-semibold rounded border bg-gray-50 hover:bg-gray-100"
            onClick={() => setWorkbenchesVisible(v => v + SECTION_PAGE_SIZE)}
          >
            LOAD MORE ({user.createdPlaybooks.length - workbenchesVisible} remaining)
          </button>
        </div>
      )}

      {/* ACH Analyses */}
      <h2 className="text-xl font-bold text-gray-800 mt-8 mb-4 flex items-center gap-2">My ACH</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {(user.achAnalyses || []).slice(0, achVisible).map((an: any) => (
          <Link key={an.id} to={`/tools/ach/${an.id}`} className="bg-white p-5 rounded-lg border shadow-sm hover:shadow-md transition-shadow group">
            <div className="flex justify-between items-start mb-2">
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${statusColor(an.status)}`}>{an.status}</span>
              <span className="text-xs text-gray-400">{new Date(an.updatedAt).toLocaleDateString()}</span>
            </div>
            <h3 className="font-bold text-lg text-gray-900 mb-2 group-hover:text-blue-600 transition-colors">{an.title || 'Untitled Analysis'}</h3>
          </Link>
        ))}
        <Link to="/tools/ach" className="border-2 border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center p-6 text-gray-400 hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50 transition-all">
          <span className="text-4xl mb-2">＋</span>
          <span className="font-bold">Create New ACH Analysis</span>
        </Link>
      </div>
      {(user.achAnalyses || []).length > achVisible && (
        <div className="flex justify-center mt-2">
          <button
            className="px-6 py-2 text-sm font-semibold rounded border bg-gray-50 hover:bg-gray-100"
            onClick={() => setAchVisible(v => v + SECTION_PAGE_SIZE)}
          >
            LOAD MORE ({(user.achAnalyses || []).length - achVisible} remaining)
          </button>
        </div>
      )}

      {/* AdvOps Reports */}
      <h2 className="text-xl font-bold text-gray-800 mt-8 mb-4 flex items-center gap-2">My AdvOps</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {(user.advopsReports || []).slice(0, advopsVisible).map((rep: any) => (
          <Link key={rep.id} to={`/advops?id=${rep.id}`} className="bg-white p-5 rounded-lg border shadow-sm hover:shadow-md transition-shadow group">
            <div className="flex justify-between items-start mb-2">
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${statusColor(rep.status)}`}>{rep.status}</span>
              <span className="text-xs text-gray-400">{new Date(rep.createdAt).toLocaleDateString()}</span>
            </div>
            <h3 className="font-bold text-lg text-gray-900 mb-2 group-hover:text-blue-600 transition-colors">{rep.huntId}</h3>
            <p className="text-sm text-gray-600 line-clamp-2">{rep.hypothesis}</p>
          </Link>
        ))}
        <Link to="/advops" className="border-2 border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center p-6 text-gray-400 hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50 transition-all">
          <span className="text-4xl mb-2">＋</span>
          <span className="font-bold">Create AdvOps Hunt</span>
        </Link>
      </div>
      {(user.advopsReports || []).length > advopsVisible && (
        <div className="flex justify-center mt-2">
          <button
            className="px-6 py-2 text-sm font-semibold rounded border bg-gray-50 hover:bg-gray-100"
            onClick={() => setAdvopsVisible(v => v + SECTION_PAGE_SIZE)}
          >
            LOAD MORE ({(user.advopsReports || []).length - advopsVisible} remaining)
          </button>
        </div>
      )}
    </div>
  );
};

export default UserProfile;
