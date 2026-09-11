GET_USERS_QUERY = """
query GetOrgUsers($orgId: UUID!, $excludeAuthorId: ID!) {
  organization(id: $orgId) {
    members(excludeAuthorId: $excludeAuthorId) { id role }
  }
}
"""


GET_GRAPH_TITLE_QUERY = """
query GetGraphTitle($graphId: UUID!) {
  playbookGraph(id: $graphId) {
    id
    title
    author { id }
    organization { id }
  }
}
"""

GET_ALL_ATTACK_QUERY = """
query GetAllAttack { allAttackTechniques { id techniqueId } }
"""

CREATE_NOTIFICATION_MUTATION = """
mutation CreateNotification(
  $recipientId: ID!, $actorId: ID!, $verb: String!,
  $organizationId: UUID!, $objectId: String!, $contentType: String!
) {
  createNotification(
    recipientId: $recipientId, actorId: $actorId, verb: $verb,
    organizationId: $organizationId, objectId: $objectId, contentType: $contentType
  ) { notification { id } }
}
"""

CREATE_PLAYBOOK_MUTATION = """
mutation CreatePlaybook(
  $title: String!, $description: String, $playbookType: String!, 
  $status: String!, $analyticId: String
) {
  createPlaybook(
    title: $title, description: $description, playbookType: $playbookType, 
    status: $status, analyticId: $analyticId
  ) { playbook { id } }
}
"""

UPDATE_PLAYBOOK_STATUS_MUTATION = """
mutation UpdatePlaybookStatus($playbookId: UUID!, $status: String!) {
  updatePlaybookStatus(id: $playbookId, status: $status) {
    playbook { id status }
  }
}
"""

UPDATE_PLAYBOOK_LINKS_MUTATION = """
mutation UpdatePlaybookLinks($playbookId: UUID!, $mitreAttackIds: [ID]) {
  updatePlaybookLinks(
    playbookId: $playbookId, mitreAttackIds: $mitreAttackIds
  ) { playbook { id } }
}
"""

# --- V2 GRAPH MUTATIONS ---

CREATE_PLAYBOOK_GRAPH_MUTATION = """
mutation CreatePlaybookGraph($title: String!) {
  createPlaybookGraph(title: $title) {
    playbookGraph { id }
  }
}
"""

CREATE_PLAYBOOK_NODE_MUTATION = """
mutation CreatePlaybookNode($graphId: UUID!, $layerName: String!, $x: Float!, $y: Float!) {
  createPlaybookNode(graphId: $graphId, layerName: $layerName, positionX: $x, positionY: $y) {
    node { id }
  }
}
"""

UPDATE_NODE_TEMPLATE_MUTATION = """
mutation UpdateNodeTemplate($nodeId: UUID!, $templateData: JSONString!, $mitreAttackIds: [ID]) {
  updateNodeTemplate(nodeId: $nodeId, templateData: $templateData, mitreAttackIds: $mitreAttackIds) {
    node { id }
  }
}
"""

UPDATE_PLAYBOOK_DETAILS_MUTATION = """
mutation UpdatePlaybookDetails(
  $graphId: UUID!,
  $mitreTechniqueId: String,
  $selectedStrategy: JSONString,
  $detectionRule: String,
  $goal: String,
  $technicalContext: String,
  $blindSpots: String,
  $triageGuidance: String,
  $falsePositives: String,
  $responsePlaybook: String,
  $targetFilePath: String,
  $robustnessLevel: Int,
  $dataSourceRobustness: String,
  $alertTrigger: String,
  $defaultSeverity: String,
  $enrichmentSteps: JSONString,
  $containmentSteps: JSONString,
  $notificationSteps: JSONString,
  $testScenario: String,
  $testExpectedOutput: String,
  $tags: [String]
) {
  updatePlaybookDetails(
    graphId: $graphId,
    mitreTechniqueId: $mitreTechniqueId,
    selectedStrategy: $selectedStrategy,
    detectionRule: $detectionRule,
    goal: $goal,
    technicalContext: $technicalContext,
    blindSpots: $blindSpots,
    triageGuidance: $triageGuidance,
    falsePositives: $falsePositives,
    responsePlaybook: $responsePlaybook,
    targetFilePath: $targetFilePath,
    robustnessLevel: $robustnessLevel,
    dataSourceRobustness: $dataSourceRobustness,
    alertTrigger: $alertTrigger,
    defaultSeverity: $defaultSeverity,
    enrichmentSteps: $enrichmentSteps,
    containmentSteps: $containmentSteps,
    notificationSteps: $notificationSteps,
    testScenario: $testScenario,
    testExpectedOutput: $testExpectedOutput,
    tags: $tags
  ) {
    graph { id }
  }
}
"""

# --- RULES: Repository details + Upsert Rule ---

GET_REPO_DETAILS_QUERY = """
query GetRepoDetails($repoId: ID!) {
  ruleRepository(id: $repoId) {
    id
    name
    url
    username
    token
    ragSyncEnabled
    ragSyncSchedule
    ragDatasetPath
    ragBranch
    ragLastSyncStatus
    ragLastSyncError
    ragLastSynced
    ragLastSyncedTemplates
  }
}
"""

UPSERT_RULE_MUTATION = """
mutation UpsertRule(
  $repoId: ID!, $title: String!, $status: String, $description: String,
  $author: String, $references: [String], $logsource: JSONString,
  $detection: JSONString, $falsePositives: [String], $level: String, $tags: [String],
  $rawContent: String, $format: String
) {
  upsertRule(
    repoId: $repoId, title: $title, status: $status, description: $description,
    author: $author, references: $references, logsource: $logsource,
    detection: $detection, falsePositives: $falsePositives, level: $level, tags: $tags,
    rawContent: $rawContent, format: $format
  ) {
    rule { id }
  }
}
"""

UPDATE_REPO_LAST_SYNC_MUTATION = """
mutation UpdateRepoLastSync($repoId: ID!) {
  updateRuleRepositoryLastSync(id: $repoId) {
    repository { id lastSync }
  }
}
"""

UPDATE_REPO_RAG_SYNC_STATUS_MUTATION = """
mutation UpdateRepoRagSyncStatus(
  $repoId: ID!,
  $status: String!,
  $errorMessage: String,
  $syncedTemplates: Int
) {
  updateRuleRepositoryRagSyncStatus(
    id: $repoId,
    status: $status,
    errorMessage: $errorMessage,
    syncedTemplates: $syncedTemplates
  ) {
    repository {
      id
      ragLastSyncStatus
      ragLastSyncError
      ragLastSynced
      ragLastSyncedTemplates
    }
  }
}
"""

UPDATE_REPO_RAG_FILE_STATUSES_MUTATION = """
mutation UpdateRepoRagFileStatuses(
  $repoId: ID!,
  $files: JSONString!,
  $replaceExisting: Boolean
) {
  updateRuleRepositoryRagFileStatuses(
    id: $repoId,
    files: $files,
    replaceExisting: $replaceExisting
  ) {
    ok
    count
    repository {
      id
    }
  }
}
"""

GET_FULL_PLAYBOOK_DETAILS_QUERY = """
query GetFullPlaybookDetails($id: UUID!) {
  playbook(id: $id) {
    id
    title
    description
    status
    playbookType
    analyticId
    version
    hypothesis
    triageGuidance
    knownFalsePositives
    exclusionStrategy
    falsePositiveRate
    robustnessLevel
    dataSourceRobustness
    operationalPath
    functionCallGraphs
    executionModalities
    testingProcedures
    soarEnrichment
    soarTriage
    soarContainment
    author { username }
    tags { name }
    detectionRules { title rawContent }
    requiredDataSources { name platform }
    mitreAttackMappings { techniqueId name }
    mitreD3fendMappings { d3fendId name }
    mitreEngageMappings { engageId name }
  }
}
"""
