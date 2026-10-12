# FREE Format rules

FREE Format lets you manually author a detection rule in any representation,
including YARA, Sigma, YARA-L, XML, YAML, JSON, and custom text.

## Create and edit

1. Open a Workbench and select **Editor** in Part 3: Detection Rules.
2. Select the **FREE Format** tab.
3. Optionally enter a **Format label**, such as `YARA` or `Sigma` (up to 80 characters).
4. Choose **Syntax highlighting**: Plain text, YAML / Sigma, XML, JSON, or SQL.
5. Enter a **File extension**, such as `.yara`, `.yml`, or `.xml`. You may include
   or omit the leading dot. Extensions are saved in lowercase; `.txt` is the default.
6. Write or paste your rule, then select **SAVE FREE FORMAT** or **SAVE ALL**.

One FREE rule can be stored per Workbench, alongside its supported platform rules.
Changing the format label, highlighting choice, or file extension also counts as
an unsaved change. The extension is independent of the label and highlighting.
Extensions accept 1–20 characters: letters, digits, and internal dots, hyphens,
or underscores. Enter an extension without a filename or directory path.
The label appears in the tab, saved-rule picker, and Rule Detail page. It is a
user-defined description; it does not select a supported HEFAISTOS platform.

The editor preserves supplied content, including indentation, tabs, backticks,
and leading/trailing whitespace. FREE saves skip format detection, parsing,
platform schema validation, and metadata/comment injection. A whitespace-only
rule cannot be saved to the Rule Library. Monaco may normalize line endings as
part of its text model; byte-for-byte preservation of an original file is not
provided.

## Saved rules and sharing

FREE saves use the existing Rule Library, organization ownership, and editing
permissions. Workbench metadata is kept separately from the raw content.
Use **Load a saved FREE rule** to reopen library content and its saved label and
highlighting preference. Use **Copy** or **Preview** to inspect the content.
The existing Rule Detail page allows editing, copying, downloading, and deleting
FREE rules; downloads use the saved custom extension. Git pushes also use the
saved extension. Deletion follows existing author/admin and
Workbench deployment-status restrictions. Clearing the editor is separate from
deleting a saved library rule.

Workbench HEX exports include FREE content, its label, highlighting choice, and file extension,
and the active rule format. HEX imports restore that editing state; save the
imported rule to the Rule Library when needed. Metadata refreshes preserve FREE
content. FREE is kept outside the configured deployment platforms.

## Capabilities

| Capability | FREE Format |
|---|---|
| Manual editing, copy, preview | Available |
| Save current format / Save All | Available |
| Custom format label | Available |
| Custom file extension | Available; used for saved filenames, downloads, and Git pushes |
| Syntax highlighting | Visual only |
| AI generation, improvements, similar rules | Unavailable |
| RAG reuse | Unavailable |
| Generate All / platform conversion | Excluded as source and target |
| Backend autocomplete, semantic validation, LSP | Unavailable |
| Supported-platform deployment / native platform export | Unavailable |

Any language may be entered regardless of the selected highlighting mode.
Use Plain text for YARA, YARA-L, or languages without a matching highlighting
choice. Highlighting does not validate the rule or establish official language
support. FREE editing hides platform templates and data-source comment insertion.
Workbench AI generation and sanitization are disabled when the active rule is FREE.

This release does not include local file import or multiple FREE rules per Workbench.

## Deployment and API

Apply migrations with `python manage.py migrate` when updating the backend.
The migrations add `FREE` to DetectionRule formats, add `custom_format_label`
`editor_language`, and `custom_file_extension`, and add the Workbench's `detection_rule_format` field.
Existing `OTHER` rules retain their format.

`saveDetectionRule` accepts `format: "FREE"`, `customFormatLabel`, and
`editorLanguage`, and `customFileExtension`. `saveAllDetectionRules` accepts those preferences on each
`SaveRuleInput`. FREE raw content is persisted unchanged by these mutations.
The Workbench JSON document stores FREE under `freeRule`, separately from
`platforms`; its fields are `content`, `label`, `language`, and `extension`. Existing FREE rules without an
extension use `.txt`.

See [the implementation plan](FREE_FORMAT_IMPLEMENTATION_PLAN.md) for the
selected scope and deferred enhancements.
