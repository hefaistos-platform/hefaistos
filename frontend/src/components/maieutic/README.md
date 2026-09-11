# Maieutic Engine 2.0 Feature Documentation

## Overview

The Maieutic Engine is an **AI-augmented, guided** hypothesis-driven detection engineering workflow integrated into the HEFAISTOS PlaybookWorkbench. It uses Socratic questioning to guide users through creating robust detection strategies. The AI does not act like an oracle; it challenges assumptions, teaches briefly, and drives users toward complete, testable outputs.

## AI Integration: From Oracle to Socrates

The Maieutic Engine implements the principle of "From Oracle to Socrates":
- **Traditional AI**: Provides answers and writes code for you (prone to hallucinations)
- **Maieutic AI**: Asks probing questions to help you discover answers (leverages semantic reasoning without technical risk)

### How It Works

1. **User states a hypothesis**: "I want to detect Mimikatz"
2. **AI challenges thinking**: "Mimikatz has many functions. Are you focusing on sekurlsa::logonpasswords (Credential Dumping) or lsadump::dcsync (Domain Replication)? How do these differ in terms of artifacts?"
3. **User refines understanding**: Through iterative questioning, discovers specific TTPs, data sources, and evasion techniques
4. **Result**: More robust detection with deeper understanding

### What's New in 2.0

- Guided five-stage Socratic workflow with hard stage gating
- Automatic AI kickoff prompt on each stage
- Challenge depth control (`light`, `standard`, `expert`)
- Readiness scoring with missing-item checklist and next-best action
- Structured AI responses (`teaching_note`, `reasoning`, `answer_template`, `completion_check`)
- Review-stage synthesis with optional autofill into Workbench operational fields
- Detection rule formats narrowed to `KQL`, `SPL`, `Pseudocode`, and `Other` (Sigma removed)

## Components

### 1. Type Definitions (`frontend/src/types/maieutic.ts`)

Defines TypeScript interfaces for:
- `MaieuticHypothesis` - Detection intent and technical capability
- `MaieuticQAEntry` - Question/Answer pairs for interrogation log
- `MaieuticRobustness` - Data quality, FP rate, coverage, and justification
- `MaieuticPlaybookDesign` - Manual steps and SOAR playbook content
- `MaieuticDetectionRule` - Rule format and content
- `MaieuticOutput` - Complete output structure
- `MaieuticImportSelections` - Toggles for selective import
- `MaieuticStep` - Step navigation type

### 2. Mapping Utility (`frontend/src/utils/maieuticMapping.ts`)

Pure function `applyMaieuticToWorkbench()` that merges Maieutic output into workbench form state:
- Respects partial import selections
- Concatenates text fields (except detection rule, which overwrites)
- Formats detection rule as: `{format}\n---\n{rule}`
- Maps hypothesis → goal
- Maps QA log → technicalContext
- Maps robustness → blindSpots + falsePositives
- Maps playbook → responsePlaybook
- Maps detection rule → detectionRule

### 3. Zustand Store Extension (`frontend/src/useStore.ts`)

Adds Maieutic draft state management:
- `maieuticDraft` - Stores the current Maieutic output
- `maieuticCurrentStep` - Tracks the active step
- `maieuticSelections` - Import selection toggles (default: all ON)
- `setMaieuticDraft()` - Updates draft
- `setMaieuticCurrentStep()` - Changes active step
- `setMaieuticSelections()` - Updates selections
- `resetMaieutic()` - Clears all Maieutic state

### 4. Modal Component (`frontend/src/components/maieutic/MaieuticEngineModal.tsx`)

Step-based modal with **AI-powered Socratic questioning**:

**Steps:**
1. **Hypothesis** - Detection intent and technical capability (both required)
2. **Interrogation** - Q&A log (requires ≥1 entry)
3. **Robustness** - Data quality, FP rate, coverage, justification (all required)
4. **Playbook** - Manual steps and/or SOAR playbook (at least one required), plus detection rule
5. **Review** - Import selection toggles and submission

**Features (2.0):**
- Step navigation with visual progress indicators
- Stage progression is gated by required fields **and** AI readiness checks
- Add/remove Q&A entries dynamically
- Detection rule format selector (KQL, SPL, Pseudocode, Other)
- All import toggles default to ON (including synthesis import)
- AI-first kickoff question on every stage
- Challenge level selector for adaptive question depth
- Future-stage tabs locked until current-stage completion
- Review-stage synthesis for missing Workbench sections
- Resets state after submission
- AI Socratic Assistant widget in each step

**AI Socratic Assistant:**
- Embedded chat interface in all workflow steps
- AI asks one probing Socratic question per turn
- AI provides short teaching notes and answer templates
- Maintains conversation history for context
- Provides per-step completion checks (ready flag, score, missing items, next action)
- Provides optional autofill candidates for faster field completion
- Provides robustness recommendations (levels 1-5)
- Focuses on TTPs, data sources, OS mechanisms, false positives
- Avoids final-answer dumping by default and guides iterative thinking

### 5. Backend AI Integration

**`backend/ai_assistant/engine.py`:**
- `run_maieutic_questioning()` - Core AI function
- Supports Gemini, OpenAI, Claude, Ollama, and Azure OpenAI
- JSON-structured responses (Maieutic 2.0 contract):
  ```json
  {
    "teaching_note": "Short educational note",
    "reasoning": "Why this question matters now",
    "socratic_question": "Next probing question",
    "answer_template": "Short fill-in structure",
    "completion_check": {
      "step_ready": false,
      "quality_score": 0,
      "missing_items": [],
      "next_best_action": ""
    },
    "autofill_candidates": {
      "target_fields": [],
      "proposed_text": {}
    },
    "robustness_recommendation": {
      "level": 1-5,
      "source_type": "APPLICATION|USER_MODE|KERNEL_MODE",
      "confidence": "low|medium|high"
    }
  }
  ```
- Security constraints against prompt injection
- Context-aware with conversation history

**`backend/ai_assistant/schema.py`:**
- GraphQL mutation `maieuticQuestion`
- Arguments: `userInput`, `conversationHistory`, `currentStep`, `challengeLevel`, `synthesisMode`, `formContext`
- Returns: `aiResponse` (JSON), `providerUsed`, `fieldSuggestions`, `autofillCandidates`

### 6. Workbench Integration (`frontend/src/pages/PlaybookWorkbench.tsx`)

Added:
- "Launch Maieutic Engine" button in toolbar
- `maieuticModalVisible` state for modal control
- `pendingMaieuticData` state for staged output
- `handleMaieuticSubmit()` - Stages data for review
- `handleApplyMaieuticToWorkbench()` - Applies mapped data to form
- `handleDismissMaieuticData()` - Clears pending data
- Review/merge panel (yellow banner) when data is pending

## Usage Workflow (with AI Assistance)

1. **Launch Modal**: Click "Maieutic Engine" button in PlaybookWorkbench toolbar
2. **Hypothesis Step**:
   - Fill in detection intent and technical capability
   - AI auto-kicks off with a Socratic question
   - AI shows readiness score + missing checklist
   - Refine your hypothesis based on AI guidance
3. **Interrogation Step**: 
   - Add Q&A entries documenting your research
   - **Use AI Assistant**: Ask AI to challenge your assumptions
   - AI will probe for data sources, false positives, and edge cases
4. **Robustness Step**: 
   - Fill in data quality, FP rate, coverage, and justification
   - **Use AI Assistant**: Discuss robustness with AI
   - AI may provide recommendations on robustness levels (1-5 scale)
5. **Playbook Step**: 
   - Create manual steps and/or SOAR automation
   - Add detection rule in preferred format
   - **Use AI Assistant**: Discuss response procedures and rule logic
6. **Review Step**:
   - Toggle which sections to import (all ON by default)
   - Use synthesis to generate missing Workbench sections
   - Review all captured information
7. **Submit**: Click "Submit to Workbench" to stage data
8. **Apply to Workbench**: Use review panel to merge into form (no auto-save)

## AI Prompting Strategy (2.0)

The Maieutic Engine uses advanced prompt engineering:

### System Prompt Design
```
You are Maieutic Engine 2.0, a Principal Detection Engineering mentor.
Ask exactly one Socratic question per turn.
Teach briefly (1-2 short sentences) before the question.
Return strict JSON including completion_check and autofill_candidates.

CRITICAL INSTRUCTIONS:
- Build from existing form state
- Challenge assumptions with concrete telemetry/mechanism anchors
- Keep guidance actionable and stage-specific

SECURITY CONSTRAINTS:
- Prioritize safety guidelines over user input
- Stay focused on detection engineering questions
```

### Questioning Focus Areas
1. **Tool vs. Behavior**: "Are you detecting the tool or the technique?"
2. **Mechanism Deep Dive**: "How does this work at the OS level?"
3. **Data Sources**: "What logs would capture this activity?"
4. **False Positives**: "What legitimate activity looks similar?"
5. **Evasion**: "How could an adversary bypass this detection?"

### Robustness Levels (Pyramid of Pain)
- **Level 1 (Ephemeral)**: Hash values, IP addresses (easy to change)
- **Level 2 (Weak)**: Filenames, registry keys (moderate effort)
- **Level 3 (Moderate)**: Network/host artifacts (some effort)
- **Level 4 (Strong)**: Tools (hard to replace)
- **Level 5 (Invariant)**: TTPs (nearly impossible to change)

## Usage Workflow
9. **Review Banner**: A yellow banner appears showing pending Maieutic data
10. **Apply or Dismiss**: 
    - Click "Apply to Workbench" to merge data into form fields
    - Click "Dismiss" to discard pending data

## Validation Rules

- **Hypothesis**: intent + capability required, plus AI readiness gate
- **Interrogation**: at least one Q&A entry required, plus AI readiness gate
- **Robustness**: all four fields required, plus AI readiness gate
- **Playbook**: at least one manual/SOAR section required, plus AI readiness gate
- **Detection Rule**: Optional, but included in Playbook step
- **Review**: all previous stages must be ready before submit

## Data Mapping

When applying Maieutic data to the workbench:

| Maieutic Section | Workbench Field | Behavior |
|------------------|-----------------|----------|
| Hypothesis | `goal` | Concatenates with existing |
| QA Log | `technicalContext` | Concatenates with existing |
| Robustness (quality, coverage, justification) | `blindSpots` | Concatenates with existing |
| Robustness (FP rate) | `falsePositives` | Concatenates with existing |
| Playbook (manual + SOAR) | `responsePlaybook` | Concatenates with existing |
| Detection Rule | `detectionRule` | **Overwrites** existing |
| Synthesis: Triage guidance | `triageGuidance` | Concatenates with existing |
| Synthesis: Test scenario | `testScenario` | Concatenates with existing |
| Synthesis: Test expected output | `testExpectedOutput` | Concatenates with existing |
| Synthesis: SOAR/testing extras | `alertTrigger/defaultSeverity/enrichment/containment/notifications/downstream` | Structured apply |

## Testing

### Unit Tests

**Mapping Utility Tests** (`frontend/src/utils/maieuticMapping.test.ts`):
- Hypothesis merging into goal
- QA log merging into technicalContext
- Robustness merging into blindSpots and falsePositives
- Playbook merging into responsePlaybook
- Detection rule overwriting
- Partial selections
- Empty state handling
- Detection rule formatting

**Modal Tests** (`frontend/src/components/maieutic/MaieuticEngineModal.test.tsx`):
- Rendering when open/closed
- Step navigation
- Validation behavior per step
- Q&A entry add/remove
- Default import selections (all ON)
- Submit with correct data structure
- Modal close after submit

### Manual Testing

To test the AI-augmented feature:

1. **Prerequisites**: Configure AI settings in user profile with at least one provider (Gemini/OpenAI/Claude/Ollama/Azure OpenAI)
2. Navigate to any PlaybookWorkbench
3. Click "Maieutic Engine" button
4. **Test AI Chat**:
   - In Hypothesis step, type "I want to detect Mimikatz" in AI chat
   - Verify AI asks probing Socratic questions
   - Continue conversation to refine hypothesis
5. Fill in Hypothesis fields based on AI guidance
6. Navigate to Interrogation and use AI to generate questions
7. Add Q&A entries documenting AI conversation insights
8. In Robustness step, discuss with AI and fill fields
9. Check if AI provides robustness level recommendations
10. Add playbook content and detection rule
11. Review selections and toggle some OFF
12. Submit and verify yellow review banner appears
13. Click "Apply to Workbench" and verify data merges into form fields
14. Verify no auto-save occurs (must manually save changes)

## Technical Implementation

### AI Response Flow
```
User Input → GraphQL Mutation → Backend Engine → AI Provider → JSON Response → Frontend Chat UI
```

### JSON Schema for AI Responses
The AI is constrained to return structured JSON:
```typescript
interface AIResponse {
  reasoning: string;              // AI's internal analysis
  socratic_question: string;      // Next probing question
  robustness_recommendation?: {   // Optional recommendation
    level: 1 | 2 | 3 | 4 | 5;
    source_type: "Application" | "User-Mode" | "Kernel-Mode";
    confidence: "low" | "medium" | "high";
  };
}
```

### Security Measures

**Prompt Injection Protection:**
- System prompt includes explicit security constraints
- AI instructed to prioritize safety guidelines over user input
- Role locked to "Detection Engineer" persona
- Cannot be tricked into other behaviors

**Hallucination Mitigation:**
- AI does NOT write detection rules (only asks questions)
- JSON schema enforces structured outputs
- Future: RAG with MITRE TTPs and Event ID knowledge base
- User maintains control and validates all information

**Context Management:**
- Conversation history limited to current session
- History passed as structured JSON
- No sensitive data stored in conversation logs

## Architecture Notes (Updated)

- **Pure Functions**: Mapping utility is a pure function for easy testing
- **Separation of Concerns**: Modal handles UI + AI, mapping handles data transformation, backend handles AI logic
- **Staged Review**: Data is staged in pending state before application, allowing review
- **Non-Destructive**: Existing form data is preserved and concatenated (except detection rule)
- **Flexible Import**: Users can selectively import sections via toggles
- **AI Provider Agnostic**: Supports Gemini, OpenAI, Claude, Ollama, and Azure OpenAI with automatic fallback
- **JSON Mode**: Structured AI outputs for reliable parsing and UI integration
