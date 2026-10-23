# Rule Hub authoring and Git publishing

Rule Hub supports independent rule authoring without creating a Workbench or completing capability abstraction, review, SOAR, or testing sections.

## Create and edit

Select **New Rule** in Rule Hub. The full editor opens on a dedicated page and shares the platform editor and tools used by Workbench. Use the **Metadata** tab to enter a title, description, author, MITRE technique, severity, status, and comma-separated tags. Optional telemetry context or sample events ground AI generation and template reuse assessments for the current editing session.

Platform tabs support KQL, Elastic EQL, SPL, Wazuh, QRadar AQL, and FREE/custom content. Supported platforms retain the existing autocomplete, language validation, templates, AI generation, suggestions, variations, RAG reuse, and Generate All behavior. FREE remains manual-only.

**Save Draft** saves one independent rule, including all configured platforms, in the internal Rule Repo library. A Git repository is not required. Drafts may have incomplete metadata or empty platform content. Each rule has a stable UUID; editing retains it. **Duplicate** creates a new UUID and an independent copy without a Workbench link.

Select **Open full editor** from a rule detail page to edit existing standalone/native rules. Existing Workbench-owned rules continue to use their original Workbench editor; select **Duplicate into Rule Hub** to make an independent alternative. Legacy OpenTIDE MDR/bundle documents are preserved as FREE YAML when their structure differs from the standalone schema.

## Publish to Git

Select **Publish to Git**. The editor saves the latest draft first, then opens publishing controls. Choose a repository already configured in **Configuration → Rules**, an existing branch, a repository-relative `.yaml` or `.yml` path, and a commit message.

Select **Preview** to inspect the exact OpenTIDE YAML and the diff against the destination file. Select **Publish to Git** to commit that reviewed document. This supports the existing GitHub, GitLab, and Gitea provider connections, including configured API URLs and TLS settings. Tokens remain on the backend.

Publishing writes one rule document with `metadata` and `platforms`. It does not create TVM/DOM/MDR bundles, invoke Export/Import Playbook, deploy to detection platforms, or change Workbench review status. Metadata must satisfy the existing strict standalone OpenTIDE schema: title, description of at least 10 characters, author, severity, MITRE technique, UUIDv4, and supported maturity status. At least one supported platform must contain content.

FREE/custom content cannot be represented by that schema and blocks publishing if present, even when supported platforms are also configured. It is never silently omitted. Keep custom rules as drafts or use existing native download/export tools.

A preview expires after 15 minutes and is tied to the user, rule content, destination, and branch commit. If the rule or branch changes, preview again. Destination changes also invalidate the preview. Provider conflict checks protect updates. Publishing errors preserve the saved draft. An unchanged destination has nothing to publish.

## Link an alternative to a Workbench

Use **Add to Workbench** from the editor or **Linked Rules → Add existing rule** in Workbench. Linking references the same saved Rule Hub rule; edits are visible when reopened from either location. Its metadata stays independent. Unlinking retains the rule in Rule Hub.

A rule can have one additional Workbench association. Unlink before moving it to another Workbench. Multiple independent rules in the same language can attach to one Workbench without replacing its primary rule.

Additional links are separate from the legacy Workbench-owned rule relationship. Workbench's primary editor, review, export, and deployment continue to use the existing rules. Additional links are reference material and are not automatically included in those actions. Publish them independently from Rule Hub.

Analysts and administrators can create drafts. Only a rule author or administrator can edit/publish their rule. Link changes also require Workbench author/admin permissions. All rule, repository, and Workbench operations are restricted to the user's organization.

## Upgrade existing installations

The additive `rules.0029_rule_hub_authoring` migration adds nullable authoring-document and Workbench-link fields. Existing rules and Workbench content remain intact. There are no new environment variables, credentials, dependencies, or worker services.

From the installation's repository root after pulling the changes:

```bash
docker compose build backend frontend
docker compose run --rm --no-deps --entrypoint python backend manage.py migrate --noinput
docker compose up -d --no-deps --force-recreate backend frontend
docker compose --profile workers up -d --no-deps --force-recreate ai_generation_worker
docker compose exec backend python manage.py showmigrations rules
docker compose exec backend python manage.py check
```

Keep the database running for the migration command. Restart the AI worker if your installation uses standalone AI generation. Backend startup also runs migrations, but the explicit migration step applies them before serving the new frontend. Confirm `[X] 0029_rule_hub_authoring` in `showmigrations` output.

For a non-Docker installation, activate its existing Python environment, run `python manage.py migrate --noinput` from `backend`, rebuild the frontend with `npm ci` and `npm run build` from `frontend`, deploy the generated assets, and restart backend and AI worker services using the installation's service manager.

## API additions

- `saveRuleDraft(document: JSONString!, ruleId: ID)` creates/updates standalone authoring state.
- `duplicateRule(ruleId: ID!)` creates an independent copy.
- `linkRuleWorkbench(ruleId: ID!, workbenchId: UUID)` attaches or unlinks; omit/null the Workbench ID to unlink.
- `workbenchRuleLinks(workbenchId: UUID!)` lists additional rules.
- `previewRulePublish(ruleId: ID!, repositoryId: ID!, branch: String!, path: String!)` returns YAML, diff, unchanged flag, and a signed preview token.
- `publishRuleToGit(previewToken: String!, commitMessage: String)` returns commit SHA and file URL.
- Rule fields include `editorDocument`, `canEdit`, `workbenchOwned`, `workbenchId`, and `workbenchTitle`.
- `startGenerateRuleTask` and `recommendReusableRuleFromRag` accept optional standalone description and telemetry context when no Workbench ID is supplied. Existing Workbench callers remain supported.
