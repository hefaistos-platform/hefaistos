import { gql } from '@apollo/client';

export const GET_AI_PROMPTS = gql`
  query GetAIPrompts {
    aiPrompts {
      id
      title
      description
      category
      requiredRole
      order
    }
  }
`;

export const EXECUTE_AI_PROMPT = gql`
  mutation ExecuteAIPrompt(
    $promptId: UUID!
    $customInput: String
    $customContext: JSONString
  ) {
    executeAiPrompt(
      promptId: $promptId
      customInput: $customInput
      customContext: $customContext
    ) {
      success
      message
      resultMarkdown
      renderedPrompt
      providerUsed
    }
  }
`;

export const EXPORT_AI_PROMPT_RESULT_PDF = gql`
  mutation ExportAIPromptResultPdf($title: String!, $resultMarkdown: String!) {
    exportAiPromptResultPdf(title: $title, resultMarkdown: $resultMarkdown) {
      success
      message
      fileData
      filename
      contentType
    }
  }
`;

export const EXPORT_REPORT_EXCEL = gql`
  mutation ExportReportExcel($sections: [String]) {
    exportReportExcel(sections: $sections) {
      success
      message
      fileData
      filename
      contentType
    }
  }
`;

export const GET_MONTHLY_TRENDS = gql`
  query GetMonthlyTrends($months: Int) {
    monthlyTrends(months: $months) {
      year
      month
      label
      stats
    }
  }
`;

export const GET_MAILING_LIST = gql`
  query GetMailingList {
    mailingListMembers {
      id
      username
      email
      role
      isSubscribed
      subscribedAt
      unsubscribedAt
    }
  }
`;

export const UPDATE_MAILING_LIST_MEMBER = gql`
  mutation UpdateMailingListMember($username: String!, $subscribe: Boolean!) {
    updateMailingListMember(username: $username, subscribe: $subscribe) {
      success
      message
    }
  }
`;

export interface AIPrompt {
  id: string;
  title: string;
  description: string;
  category: string;
  requiredRole: string;
  order: number;
}

export interface MonthlySnapshot {
  year: number;
  month: number;
  label: string;
  stats: string; // JSON string
}

export interface MailingListMember {
  id: string;
  username: string;
  email: string;
  role: string;
  isSubscribed: boolean;
  subscribedAt: string;
  unsubscribedAt: string | null;
}
