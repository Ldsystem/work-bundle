---
id: ks-off-switches
applies_when:
  - user disables persistence or asks draft only
enforcement: must
load: conditional
requires: []
---

# Ks Off Switches

## Purpose

- Define how keep-summarizing pauses or exits when the user disables persistence.
- Ensure the agent stops durable writes immediately while continuing the requested non-persistence work.

## Must

- Recognize these pause commands exactly:
  - `pause keep-summarizing`
  - `do not persist knowledge for now`
  - `draft only`
- When paused:
  - stop writing durable notes;
  - continue normal work;
  - keep temporary notes outside durable knowledge only if the user requests them;
  - resume only when the user says `resume keep-summarizing` or explicitly asks to persist knowledge.
- Recognize these exit commands exactly:
  - `stop keep-summarizing`
  - `exit keep-summarizing`
  - `normal mode`
  - `do not persist knowledge for this conversation`
- When exited:
  - stop applying keep-summarizing for the current conversation;
  - do not write notes, indexes, or Git commits through keep-summarizing;
  - continue as a normal agent unless the user reactivates keep-summarizing.
- Acknowledge the new paused or exited mode clearly when one of these commands applies.

## Must Not

- Do not persist durable knowledge after a pause command.
- Do not write notes, indexes, or keep-summarizing Git commits after an exit command.
- Do not treat `draft only` as permission to persist durable notes.
- Do not resume persistence without an explicit resume or persist instruction.

## Validation

- Confirm the user message matches a pause or exit command before changing mode.
- Confirm no durable note write, index rebuild, or keep-summarizing Git action runs while paused or exited.
- Confirm the response explicitly acknowledges whether keep-summarizing is paused or exited.

## On Violation

- Stop all keep-summarizing persistence actions immediately.
- Report which off-switch command was ignored, switch to the correct mode, and continue only with non-persistence work unless the user re-enables persistence.
