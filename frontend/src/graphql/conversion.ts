/**
 * GraphQL queries and mutations for Sigma rule conversion feature.
 * 
 * This module provides operations to:
 * - Fetch available conversion targets (backends)
 * - Fetch output formats for each target
 * - Convert Sigma rules to various formats
 */

import { gql } from '@apollo/client';

/**
 * Query to get available conversion targets (backends).
 * Examples: splunk, elasticsearch, qradar, microsoft365defender
 */
export const GET_CONVERSION_TARGETS = gql`
  query GetConversionTargets {
    conversionTargets {
      name
      description
    }
  }
`;

/**
 * Query to get available output formats.
 * Can be filtered by target backend.
 */
export const GET_CONVERSION_FORMATS = gql`
  query GetConversionFormats($target: String) {
    conversionFormats(target: $target) {
      name
      description
      target
    }
  }
`;

/**
 * Query to get available processing pipelines.
 * Pipelines transform field names and values before conversion.
 */
export const GET_CONVERSION_PIPELINES = gql`
  query GetConversionPipelines {
    conversionPipelines {
      name
      targets
    }
  }
`;

/**
 * Mutation to convert a Sigma detection rule to another format.
 */
export const CONVERT_DETECTION_RULE = gql`
  mutation ConvertDetectionRule(
    $ruleId: ID!
    $target: String!
    $format: String
    $pipeline: [String]
  ) {
    convertDetectionRule(
      ruleId: $ruleId
      target: $target
      format: $format
      pipeline: $pipeline
    ) {
      success
      convertedRule
      errorMessage
      targetFormat
    }
  }
`;

/**
 * TypeScript types for the GraphQL responses
 */

export interface ConversionTarget {
  name: string;
  description?: string;
}

export interface ConversionFormat {
  name: string;
  description?: string;
  target: string;
}

export interface ConversionPipeline {
  name: string;
  targets: string[];
}

export interface ConvertDetectionRuleResult {
  success: boolean;
  convertedRule?: string;
  errorMessage?: string;
  targetFormat?: string;
}

export interface ConvertDetectionRuleVariables {
  ruleId: string;
  target: string;
  format?: string;
  pipeline?: string[];
}
