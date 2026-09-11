# Layered Workbench Visibility (Feature Documentation)

## Overview

PR #7 introduces a **canonical section-visibility model** for Workbench and connects it across frontend, profile settings, and backend persistence.

The goal is to keep required Workbench sections always visible, while allowing controlled customization of optional sections through a clear precedence model.

---

## What was implemented

### 1) Layered visibility resolution

Workbench visibility now resolves from four layers (highest precedence first):

1. **System policy**
2. **Organization policy**
3. **User default**
4. **Local state**

This means stricter/global policy can override user or local preferences where needed.

### 2) Mandatory section enforcement

The following sections are always visible and cannot be hidden:

- Part 1
- Part 2
- Part 3
- Part 6

These sections are rendered as locked in the UI.

### 3) Workbench UI controls

Workbench now supports:

- Optional section toggles (Part 4 and Part 5)
- Lock state + lock reason display
- Preset actions:
  - **Simple Mode**
  - **Advanced Mode**
- **Save current layout as my default** action

### 4) Profile defaults management

User profile now includes controls to:

- View current Workbench default visibility
- Edit defaults
- Reset defaults

### 5) Backend persistence fields

Policy/default fields were added for persistence:

- `CustomUser.workbench_visibility_defaults`
- `Organization.workbench_visibility_policy`
- `WorkbenchIdCounter.workbench_visibility_policy` (system-level singleton foundation)

### 6) GraphQL updates

GraphQL schema/exposure was updated to include the new visibility data and mutation support, including:

- `updateWorkbenchVisibilityDefaults` mutation

---

## How it works (end-to-end)

1. Visibility inputs are collected from system, org, user defaults, and local state.
2. A single resolver computes the final section visibility.
3. Mandatory sections are force-enabled and locked.
4. Workbench renders resolved state and lock reasons.
5. User can save current layout to profile defaults.
6. Defaults are persisted and reused in future sessions.

---

## Why this matters

- Prevents accidental hiding of critical Workbench sections.
- Provides predictable and centralized precedence behavior.
- Enables organization/system governance without removing user flexibility.
- Establishes backend foundation for future admin policy UX.

---

## Testing coverage

Included tests for:

- Frontend resolver logic and Workbench UI behavior
- Backend GraphQL persistence/reset behavior
- Org/system policy exposure through GraphQL

---

## Summary

PR #7 delivers a governed visibility system for Workbench with mandatory-section safety, layered policy precedence, user default persistence, and consistent frontend/backend integration.
