# Git Sync and Push

## Purpose
Describe inbound rule synchronization and outbound rule export/Git push workflows.

## Audience
Detection engineers and maintainers integrating HEFAISTOS with rule repositories.

## Prerequisites
Repository integration configured with credentials and branch/path settings.

## Steps / Workflow
1. Configure inbound repository pull and parsing settings.
2. Optionally configure RAG dataset synchronization.
3. Export approved workbench content through git-push workflow.
4. Optionally open pull requests in connected Git platforms.

## Validation / Expected result
Rules import correctly from repositories and exports produce expected commits/PR artifacts.

## Troubleshooting
If sync or push fails, verify branch/path mapping, connector tokens, and repository access permissions.

## Related pages
- [Connectors Overview](connectors-overview.md)
- [RAG Grounding](../features/rag-grounding.md)
- [Release CI Version Flow](../release/ci-version-flow.md)
