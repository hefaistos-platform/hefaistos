# Workbench Query Editor: Languages, Autocomplete, and Validation

The Workbench detection-rule editor uses Monaco with per-language providers.

## Supported languages

| Language | Format value | Monaco mode | Autocomplete source | Syntax validation source |
|---|---|---|---|---|
| KQL | `KQL` | `kql` | Backend KQL autocomplete engine (`getAutocompleteOptions`) | Backend KQL validator (`validateRuleContent`) |
| Elastic EQL | `EQL` | `eql` | Backend EQL autocomplete engine (keyword/snippet + category suggestions) | Backend EQL validator (`validateRuleContent`) |
| Splunk SPL | `SPL` | `spl` | Backend SPL autocomplete engine | Backend SPL validator (`validateRuleContent`) |
| Wazuh XML | `WAZUH` | `xml` | Backend Wazuh autocomplete engine | Backend Wazuh XML/content validator (`validateRuleContent`) |
| QRadar AQL | `AQL` | `aql` | Backend AQL autocomplete engine (keyword/snippet/function suggestions) | Backend AQL validator (`validateRuleContent`) |

## Trigger behavior

- Manual autocomplete trigger: `Ctrl+Space` / `Cmd+Space` (all languages).
- Automatic triggers:
  - KQL/SPL: `|`, `.`, `,`
  - WAZUH: `<`
  - EQL/AQL: `.`, `,`, `(`
- Validation runs after editor changes (debounced) when content is non-empty.

## Capability scope and fallback

- KQL/SPL/WAZUH can use LSP wiring where available.
- EQL/AQL currently run without LSP and use backend deterministic autocomplete + validation.
- If autocomplete provider/network is unavailable, Monaco falls back to no server suggestions (manual retry via `Ctrl+Space`).
- If validation request fails, existing markers are cleared and editing continues.

## Troubleshooting

### Autocomplete not appearing

1. Confirm cursor is in a supported language tab (KQL/EQL/SPL/WAZUH/AQL).
2. Try manual trigger (`Ctrl+Space` / `Cmd+Space`).
3. Check authentication/session token in the browser (GraphQL autocomplete call requires auth).
4. Check browser console for `Autocomplete` GraphQL/network errors.

### Syntax checks not running

1. Ensure rule content is not empty.
2. Confirm language tab maps to one of the supported formats above.
3. Check browser console for `Validation` GraphQL/network errors.
4. If backend validation endpoint is unreachable, syntax markers will not be shown until connectivity is restored.
