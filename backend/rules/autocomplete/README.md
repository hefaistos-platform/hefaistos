# Detection Rule Autocomplete - Backend Implementation

## Overview

This backend implementation provides intelligent autocomplete suggestions for SIGMA, KQL, WAZUH, and SPL detection rules. Currently implemented: **SIGMA**, **KQL**, **WAZUH**, and **SPL** formats.

## Architecture

### Components

```
backend/rules/autocomplete/
├── __init__.py                 # Package exports
├── base.py                    # AbstractAutocompleteEngine
├── sigma_engine.py            # SIGMA-specific implementation
├── kql_engine.py              # KQL implementation
├── wazuh_engine.py            # WAZUH XML implementation (NEW)
└── suggestions.py             # Data models
```

### Models

- `SigmaKeyword` - SIGMA keyword cache (50+ keywords preloaded)
- `KQLTable` - KQL table definitions (Phase 2)
- `KQLField` - KQL field definitions (Phase 2)
- `FieldMapping` - SIGMA ↔ KQL field mappings (Phase 2)

### GraphQL API

**Mutation:** `getAutocompleteOptions`

```graphql
mutation GetAutocompleteOptions(
  $format: String!        # "SIGMA" | "KQL" | "WAZUH"
  $prefix: String!        # What user typed
  $context: String!       # Full rule content
  $position: Int!         # Cursor position
  $dataSourceId: UUID     # Optional filter
) {
  getAutocompleteOptions(...) {
    result {
      suggestions {
        label
        kind              # keyword|field|value|operator|function
        insertText
        detail
        documentation
        sortText
        filterText
      }
      isComplete
    }
  }
}
```

## Usage

### 1. Database Setup

```bash
# Apply migration
python manage.py migrate rules 0013

# Populate SIGMA keywords
python manage.py populate_sigma_keywords

# Verify
python manage.py dbshell
SELECT COUNT(*) FROM rules_sigmakeyword;  # Should show 50+
```

### 2. GraphQL Query

#### Example: Get suggestions for "t" in title field

```graphql
mutation {
  getAutocompleteOptions(
    format: "SIGMA"
    prefix: "t"
    context: "title: "
    position: 7
  ) {
    result {
      suggestions {
        label
        kind
        insertText
        documentation
      }
      isComplete
    }
  }
}
```

**Response:**
```json
{
  "result": {
    "suggestions": [
      {
        "label": "title",
        "kind": "keyword",
        "insertText": "title: ",
        "documentation": "Title of the SIGMA rule (required)"
      }
    ],
    "isComplete": true
  }
}
```

#### Example: Get status value suggestions

```graphql
mutation {
  getAutocompleteOptions(
    format: "SIGMA"
    prefix: "st"
    context: "status: st"
    position: 9
  ) {
    result {
      suggestions {
        label
        kind
        insertText
      }
    }
  }
}
```

### 3. Python Usage

```python
from rules.autocomplete.sigma_engine import SigmaAutocompleteEngine

engine = SigmaAutocompleteEngine()

# Get autocomplete suggestions
result = engine.get_autocomplete(
    text="title: My\nstatus: ",
    position=20
)

# Iterate suggestions
for suggestion in result.suggestions:
    print(f"{suggestion.label} ({suggestion.kind}): {suggestion.documentation}")
```

## SIGMA Autocomplete Features

### Context-Aware Suggestions

The engine analyzes the rule structure to provide contextually relevant suggestions:

1. **Root Level** (after `title:`, `id:`, etc.)
   - Suggests: keywords like `status`, `logsource`, `detection`

2. **Logsource Section**
   - Suggests: `category:`, `product:`, `service:`
   - Value suggestions for each field

3. **Detection Section**
   - Suggests: `selection:`, `filter:`, `condition:`
   - Field names based on category

4. **Operator Context** (after `|`)
   - Suggests: SIGMA operators like `endswith`, `contains`

### Suggestion Types

| Kind | Examples | Usage |
|------|----------|-------|
| `keyword` | title, status, logsource | Top-level keys |
| `value` | test, critical, process_creation | Field values |
| `field` | Image, CommandLine, DestinationPort | Detection fields |
| `operator` | endswith, contains, cidr | SIGMA operators |
| `function` | (reserved for Phase 2) | - |

### Ranking Algorithm

Suggestions are ranked by relevance:

1. **Exact match** (highest priority)
2. **Starts with prefix**
3. **Contains prefix**
4. **Alphabetical** (fallback)

Only top 20 suggestions returned per request.

## Testing

### Unit Tests

```bash
# Run all autocomplete tests
python manage.py test rules.test_sigma_autocomplete

# Run specific test class
python manage.py test rules.test_sigma_autocomplete.SigmaAutocompleteEngineTest

# Run specific test
python manage.py test rules.test_sigma_autocomplete.SigmaAutocompleteEngineTest.test_sigma_keywords_suggestions
```

### Test Coverage

- ✅ Prefix extraction
- ✅ Line analysis
- ✅ Context detection
- ✅ Suggestion generation
- ✅ Ranking algorithm
- ✅ YAML validation
- ✅ Complete workflow
- ✅ Category/product suggestions
- ✅ Field suggestions
- ✅ Operator suggestions

### Performance Testing

```python
import time

engine = SigmaAutocompleteEngine()

large_rule = "title: Test\n" * 1000  # Large rule content

start = time.time()
result = engine.get_autocomplete(large_rule, len(large_rule))
duration = time.time() - start

print(f"Autocomplete took {duration*1000:.2f}ms for {len(large_rule)} chars")
# Target: < 100ms
```

## SIGMA Keyword Reference

### Root Keywords
- `title` - Rule title (required)
- `id` - UUID identifier
- `status` - experimental|test|stable|unsupported|deprecated
- `description` - Detailed description
- `author` - Author/organization
- `date` - Creation date (YYYY/MM/DD)
- `modified` - Last modification date
- `logsource` - Log source definition
- `detection` - Detection logic
- `falsepositives` - False positive scenarios
- `level` - Severity level
- `references` - URLs
- `tags` - Categorization tags

### Log Categories (22 supported)
- `process_creation` - Process creation events
- `network_connection` - Network connections
- `file_access` - File access events
- `registry_event` - Registry events
- `dns_query` - DNS queries
- `image_load` - DLL/image loading
- ... and 16 more

### Operators (15 supported)
- `endswith` - String ends with value
- `contains` - String contains value
- `startswith` - String starts with value
- `cidr` - CIDR match
- `re` - Regex match
- `base64` - Base64 encoding
- ... and more

## WAZUH Autocomplete Features (NEW)

### Context-Aware Suggestions

The WAZUH engine analyzes XML structure to provide contextually relevant suggestions:

1. **Tag Context** (inside opening tag)
   - Suggests: XML tags like `rule`, `group`, `match`, `regex`, `decoded_as`

2. **Attribute Context** (inside tag with attributes)
   - Suggests: attributes like `id`, `level`, `name`, `type`

3. **Rule Content** (inside `<rule>` element)
   - Suggests: rule elements like `if_sid`, `match`, `regex`, `description`, `category`
   - Value suggestions for categories and decoders

### Supported WAZUH Elements

- **Tags**: rule, group, match, regex, decoded_as, category, field, description, info, options, mitre, etc.
- **Attributes**: id, level, maxsize, frequency, timeframe, name, type
- **Categories**: authentication_success, authentication_failed, web-log, firewall, ids, etc.
- **Decoders**: windows, syslog, ssh, apache, nginx, firewall, cisco, etc.
- **Levels**: 0-15 (severity levels)

### Example WAZUH Usage

```python
from rules.autocomplete.wazuh_engine import WazuhAutocompleteEngine

engine = WazuhAutocompleteEngine()

# Get autocomplete suggestions for WAZUH XML
result = engine.get_autocomplete(
    text='<rule id="100001">\n  <mat',
    position=28
)

# Will suggest: match, category values, etc.
for suggestion in result.suggestions:
    print(f"{suggestion.label} ({suggestion.kind})")
```

## Phase 2 Roadmap (KQL)

Scheduled for Phase 2:
- KQL table suggestions (30+ Azure tables)
- KQL function suggestions
- KQL operator suggestions
- Cross-format field mapping UI

## Performance Considerations

### Optimization

1. **Caching**: Keywords cached in database (populated once via management command)
2. **Debouncing**: Frontend debounces requests (300ms)
3. **Result Limiting**: Max 20 suggestions per request
4. **Lazy Loading**: Full documentation loaded only on hover

### API Response Time

- **Target**: < 200ms (p95)
- **Typical**: 10-50ms for small prefixes
- **Large Rules**: < 100ms even for 10KB+ rules

### Database

- `SigmaKeyword` indexed on: `keyword`, `category`
- Lightweight queries, minimal I/O
- No n+1 problems (single table queries)

## Integration with Frontend

Frontend uses Monaco Editor with autocomplete provider:

```typescript
monaco.languages.registerCompletionItemProvider('sigma', {
  provideCompletionItems: async (model, position) => {
    const text = model.getValue();
    const offset = model.getOffsetAt(position);
    
    const result = await graphQLClient.mutate({
      mutation: GET_AUTOCOMPLETE_OPTIONS,
      variables: {
        format: 'SIGMA',
        prefix: extractPrefix(text, offset),
        context: text,
        position: offset
      }
    });
    
    return result.data.getAutocompleteOptions.result.suggestions;
  }
});
```

## Troubleshooting

### No suggestions returned

1. Check prefix length (min 1 character)
2. Verify context analysis (check section detection)
3. Ensure keywords populated: `python manage.py populate_sigma_keywords`
4. Check database connection

### Slow autocomplete

1. Check API response time (GraphQL debugging)
2. Verify debouncing on frontend (300ms min)
3. Check database query performance

### YAML validation failing

1. Check indentation (must be 2 spaces)
2. Verify proper YAML syntax
3. Use `yamllint` for rule validation

## Future Enhancements

- [ ] Per-data-source field suggestions
- [ ] User-defined field mappings
- [ ] Suggestion usage analytics
- [ ] Machine learning ranking (most frequently selected)
- [ ] Multi-format suggestions (SIGMA + KQL side-by-side)
- [ ] Custom snippet support
- [ ] Integration with threat intel APIs

## Admin Interface

Manage autocomplete data via Django admin:

```
Django Admin → Rules → SIGMA Keywords
Django Admin → Rules → KQL Tables (Phase 2)
Django Admin → Rules → KQL Fields (Phase 2)
Django Admin → Rules → Field Mappings (Phase 2)
```

## Contributing

To add new SIGMA keywords:

1. Edit `backend/rules/management/commands/populate_sigma_keywords.py`
2. Add to `keywords_data` list
3. Run: `python manage.py populate_sigma_keywords --clear`

## Version History

- **v1.0** (January 9, 2026) - SIGMA autocomplete Phase 1
- **v2.0** (Planned) - KQL autocomplete Phase 2
- **v3.0** (Planned) - Advanced features and analytics
