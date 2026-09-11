// Import GraphQLError type from 'graphql'
import { GraphQLError } from 'graphql';
import { isDevEnvironment } from '../config/env';

// Types for structured error logging
interface FieldError {
  field: string;
  message: string;
  possibleFields?: string[];
}

interface ParsedGraphQLError {
  type: 'FIELD_ERROR' | 'NETWORK_ERROR' | 'AUTH_ERROR' | 'UNKNOWN';
  message: string;
  fields?: FieldError[];
  raw: any;
}

interface GraphQLErrorMessage {
  message: string;
}

// Helper to detect field name mismatches in GraphQL errors
const isFieldNameError = (error: GraphQLErrorMessage): boolean => {
  return (error.message.includes('Cannot query field') ||
         (error.message.includes('Field') && error.message.includes('doesn\'t exist')));
};

// Extract suggested field names from GraphQL error messages
const extractSuggestedFields = (message: string): string[] => {
  const match = message.match(/Did you mean ([^?]+)\?/);
  if (!match) return [];
  return match[1].split(' or ').map(field => field.trim().replace(/['"]/g, ''));
};

// Parse GraphQL errors into a more structured format
export const parseGraphQLError = (error: any): ParsedGraphQLError => {
  // Network or connection errors
  if (error.networkError) {
    return {
      type: 'NETWORK_ERROR',
      message: 'Network error occurred. Please check your connection.',
      raw: error
    };
  }

  // Authentication errors
  if (error.message?.includes('credentials') || error.message?.includes('authentication')) {
    return {
      type: 'AUTH_ERROR',
      message: 'Authentication error. Please log in again.',
      raw: error
    };
  }

  // GraphQL errors (including field mismatches)
  if (error.graphQLErrors?.length) {
    const fieldErrors: FieldError[] = [];

    error.graphQLErrors.forEach((gqlError: GraphQLError) => {
      if (isFieldNameError(gqlError)) {
        const suggestedFields = extractSuggestedFields(gqlError.message);
        const fieldMatch = gqlError.message.match(/Cannot query field ["']([^"']+)["']/);
        if (fieldMatch) {
          fieldErrors.push({
            field: fieldMatch[1],
            message: gqlError.message,
            possibleFields: suggestedFields
          });
        }
      }
    });

    if (fieldErrors.length) {
      return {
        type: 'FIELD_ERROR',
        message: 'GraphQL field name mismatch detected',
        fields: fieldErrors,
        raw: error
      };
    }
  }

  // Unknown errors
  return {
    type: 'UNKNOWN',
    message: error.message || 'An unknown error occurred',
    raw: error
  };
};

// Log error with appropriate level and formatting
export const logGraphQLError = (error: any, componentName: string): void => {
  const parsed = parseGraphQLError(error);

  console.group(`GraphQL Error in ${componentName}`);
  console.error(`Type: ${parsed.type}`);
  console.error(`Message: ${parsed.message}`);

  if (parsed.fields) {
    console.group('Field Errors');
    parsed.fields.forEach(fieldError => {
      console.error(`Field '${fieldError.field}' is invalid`);
      if (fieldError.possibleFields?.length) {
        console.info('Suggested fields:', fieldError.possibleFields.join(', '));
      }
    });
    console.groupEnd();
  }

  if (isDevEnvironment()) {
    console.debug('Raw error:', parsed.raw);
  }

  console.groupEnd();
};

// Hook to use in components for consistent error handling
export const useGraphQLErrorHandling = (componentName: string) => {
  return {
    handleError: (error: any) => {
      logGraphQLError(error, componentName);
      const parsed = parseGraphQLError(error);
      
      // Return user-friendly error message
      if (parsed.type === 'FIELD_ERROR') {
        return 'There is a problem with the data request. Please contact the development team.';
      } else if (parsed.type === 'NETWORK_ERROR') {
        return 'Unable to connect to the server. Please check your connection.';
      } else if (parsed.type === 'AUTH_ERROR') {
        return 'Your session has expired. Please log in again.';
      }
      return parsed.message;
    }
  };
};
