# ARCH-002: App-First Core/UI Boundaries

Status: Accepted

Date: 2026-04-02

Related beads:
- `ko2-tools-6kp` — App-first core/UI architecture and wiring
- `ko2-tools-6kp.1` — Define app-first architecture boundaries

## Context

`src/app` is the primary product under development, not a throwaway prototype. CLI and TUI remain first-class, maintained frontends. The architecture must support all three without making the app depend on TUI-owned orchestration or reducing CLI/TUI functionality.

The current code also mixes several kinds of responsibility:

- transport concerns
- protocol/session concerns
- user-facing device workflows
- UI state, background execution, and rendering

This is most visible in two places:

- `src/core/client.py` currently owns both protocol/session behavior and some higher-level workflow and file policy
- `src/tui/worker.py` currently owns reusable application workflows that the main app will also need

At the same time, the app UI in `src/app` was designed separately and now needs to be wired into shared functionality without forcing UI code to own protocol mechanics.

The product also requires a dedicated internal debug surface for command workflows, protocol exploration, and performance measurement.

## Decision Summary

What is decided now:

1. `src/app` is the primary product surface; CLI and TUI remain first-class, maintained frontends.
2. UI code must not own protocol/session mechanics.
3. Shared user-facing device workflows must live outside `src/app` screens and outside `DeviceWorker`.
4. `DeviceWorker` should shrink toward an execution adapter.
5. The app will include a first-class Debug tab/view built on the same shared workflow/event backbone.

What is not decided yet:

1. Whether the protocol/session object keeps the name `EP133Client`.
2. The exact class/module layout for the shared workflow layer.
3. The final event/executor pattern consumed by app, TUI, and CLI.

Recommended direction for next work:

1. Keep transport injection runtime-driven, not screen-driven.
2. Review `EP133Client` into a protocol/session object first.
3. Extract shared workflows as explicit use-case objects with a small shared event model.
4. Give app, TUI, and CLI frontend-appropriate execution adapters over the same workflows.

### 1. `src/app` is the primary product surface

The repository should optimize its architecture for the BeeWare/Toga app in `src/app`.

`src/cli` and `src/tui` remain first-class, maintained frontends for automation, reverse-engineering, and power-user workflows. App-first sets product direction, not permission to neglect them. Shared architecture must support all three; migrations must preserve CLI/TUI commands, interactive behavior, output contracts, and test coverage. Frontend-specific presentation need not be identical.

### 2. Core responsibilities are divided into four conceptual layers

#### Transport

Transport owns platform MIDI I/O only:

- device discovery
- connect/disconnect lifecycle
- send/receive SysEx bytes
- platform-specific transport implementations

Transport must not absorb protocol semantics or user-facing workflow policy.

Transport selection is a runtime/platform concern, not a frontend concern.

Examples:

- the app on iOS should use the iOS/CoreMIDI transport
- the app on macOS dev builds may use the desktop transport
- the CLI and TUI on desktop typically use the desktop transport

The important boundary is this: a frontend should depend on a protocol/session
entry point plus a transport factory or injected transport instance. Screens
should not choose transport types individually.

#### Protocol/session

Protocol/session owns device conversation correctness:

- initialization and recovery sequences
- request/response matching
- sequence numbers and paging rules
- protocol framing and unpacking
- invariants required to keep the device in a valid session state

This responsibility currently lives mostly in `EP133Client`. That boundary is under active redesign, but the protocol/session responsibility itself must remain concentrated in one coherent place.

UI code must not own protocol/session mechanics.

#### Application workflows

Application workflows own user-visible device operations:

- inventory refresh and metadata hydration
- upload/download flows
- move/copy/delete
- optimize/squash
- waveform fetch and caching coordination
- progress, cancellation, and event surfaces consumed by UI

These workflows currently exist in fragmented form across `src/core/ops.py` and `src/tui/worker.py`. They should move toward a shared, frontend-neutral workflow layer consumed by `src/app`, `src/tui`, and `src/cli`. Extract incrementally while preserving existing frontend behavior; do not require a big-bang rewrite.

#### UI state and rendering

UI owns:

- tab/screen layout
- view state
- widget rendering
- user interaction
- binding to shared workflow events/results

UI should request workflows and render results. It should not reconstruct orchestration ad hoc in each screen.

## Shared Workflow Model Options

Three reasonable options exist for the shared user-facing workflow layer.

### Option A: Functional modules plus executor adapters

Shape:

- module-level functions for each workflow
- simple dataclasses for parameters/results/events
- app/TUI executors run those functions in background tasks; CLI can call them synchronously

Pros:

- lowest ceremony
- easy to migrate incrementally from `core.ops.py`
- good fit for pure transformations and small flows

Cons:

- can become a new bag of loosely related functions
- weaker ownership once progress, cancellation, and event streaming become important

### Option B: Explicit use-case objects per workflow family

Shape:

- one object owns the state required for one coherent workflow family
- dependencies injected in the constructor
- each workflow exposes a small public API and emits typed progress/events

Example shape:

```text
core/application/
  device_facade.py
  inventory_workflows.py
  transfer_workflows.py
  maintenance_workflows.py
  waveform_workflows.py
  events.py
```

Possible classes:

- `DeviceFacade` or `DeviceSessionFacade`: stable app-facing entry point over protocol/session
- `InventoryWorkflows`: refresh inventory, hydrate metadata, preload details
- `TransferWorkflows`: upload, download, move, copy, delete, rename
- `MaintenanceWorkflows`: optimize, optimize-all, squash
- `WaveformWorkflows`: fetch waveform bytes/bins/fingerprint, manage preload policy

Pros:

- strong ownership
- good fit for progress/cancellation/event surfaces
- clear seam for app, TUI, and CLI reuse
- avoids forcing one giant god object

Cons:

- requires discipline to avoid vague names
- requires a slightly larger initial extraction

### Option C: One session-scoped application facade

Shape:

- one higher-level app-facing object that exposes most user workflows
- subordinate objects stay internal

Example:

- `AppDeviceService` with methods for inventory, transfer, maintenance, debug, waveform

Pros:

- simple for frontends to consume
- easy to inject into app state

Cons:

- high risk of becoming the next god object
- tends to collapse workflow families back into one place

### Preferred Direction

Option B is preferred.

Use explicit workflow objects by responsibility, plus a small stable facade if a
single app-facing entry point is needed. Avoid a giant `*Manager`/`*Service`
bucket. Keep pure conversion helpers as module functions.

## High-Level Class Design Direction

The likely target shape is:

```text
transport
  MIDITransport
  DesktopMIDITransport
  IOSMIDITransport

protocol/session
  EP133Client or renamed successor
  owns init/recovery, request/response matching, paging, sequencing

application workflows
  InventoryWorkflows
  TransferWorkflows
  MaintenanceWorkflows
  WaveformWorkflows
  WorkflowEvent / ProgressEvent / Result objects

frontend adapters
  TUI DeviceWorker
  app background task / executor adapter
  CLI synchronous adapter
```

Design rules:

- transport is injected at the protocol/session boundary
- workflows depend on the protocol/session object, not on raw transport
- UI depends on workflows, not directly on protocol/session except in dedicated debug tooling
- debug tooling may expose lower-level protocol/session operations, but still through a deliberate surface

### 3. `EP133Client` is no longer described as a thin transport wrapper

Existing docs that describe `EP133Client` as transport-only are inaccurate.

For now, treat `EP133Client` as the current protocol/session entry point. The redesign work may keep that name or replace it with a more precise abstraction, but the design rule is stable:

- keep protocol/session invariants together
- move higher-level application workflows above that boundary
- do not scatter protocol correctness into frontends

### 4. `DeviceWorker` is not the long-term home of business workflows

`DeviceWorker` currently contains reusable application behavior because the TUI needed an execution model first.

Going forward:

- shared workflows should live outside `DeviceWorker`
- `DeviceWorker` should shrink toward an execution adapter for background work, progress, cancellation, and event delivery
- the app should consume the shared workflow layer directly rather than copying TUI orchestration patterns screen by screen

### 5. The app includes a first-class Debug surface

The app needs a dedicated Debug tab/view for:

- command workflows
- protocol exploration
- trace inspection
- performance measurement
- reverse-engineering support

This is an intentional internal product surface, not a temporary script bucket.

The Debug surface should sit on the same shared workflow/event backbone as the rest of the app.

## Consequences

### Short term

- documentation must stop calling `src/app` a prototype or secondary surface
- direct screen-to-client wiring in `src/app` should be treated as transitional
- architecture work should precede broad UI wiring so the app does not harden the wrong boundaries

### Medium term

- protocol/session behavior should be reviewed method-by-method in `src/core/client.py`
- reusable workflows should be extracted from `src/tui/worker.py`
- app tabs should be wired onto shared workflow abstractions
- the Debug tab should be added on top of the same event model
- CLI/TUI adapters and regression coverage must remain part of each shared-workflow migration

### Long term

- frontends can diverge in presentation while sharing the same underlying device workflows
- protocol correctness remains centralized
- the main product can evolve without treating the TUI as the only mature execution model

## Implementation Guidance

- Prefer objects that own real state over helper/manager classes.
- Keep pure transformations as module-level functions.
- Do not invent abstractions before naming the state they own.
- When extracting from `DeviceWorker`, separate workflow ownership from thread/executor ownership.
- When redesigning `EP133Client`, preserve protocol invariants first and move convenience/workflow behavior second.
- Use runtime/platform factories for transport selection; do not let individual screens choose transports.
- Validate shared changes against app, CLI, and TUI contracts; retain CLI output modes and TUI progress/cancellation behavior.

## References

- [README.md](../../README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [AGENTS.md](../../AGENTS.md)
- [docs/AGENTS.md](../AGENTS.md)
