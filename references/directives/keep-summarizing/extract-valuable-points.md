# extract-valuable-points

## Intent

Extract durable, reusable engineering insights from a conversation or implementation session, break them down by leaf perspectives, then hand off to `write-knowledge`.

## Trigger phrases

- extract durable points
- what should we save from this session
- summarize what we learned
- valuable takeaways
- map extracted points to perspectives
- break extracted points into note targets

## Use when

Reviewing chat, implementation notes, or reviews for knowledge worth persisting.

## Do not use when

The user only wants to find existing knowledge (`what-is-helpful`) or already gave explicit write instructions (`write-knowledge`).

## Required inputs

- Source material (conversation, PR, design excerpt).
- Optional: project slug and scope.
- `references/assets/keep-summarizing/perspectives.md` for granularity and target leaf perspective mapping.

## Workflow

1. Apply the structural-value test from `references/ks-workflow.md`.
2. Read `references/assets/keep-summarizing/perspectives.md` before proposing targets.
3. Separate durable from temporary material.
4. Split durable findings into atomic units: one durable question per note candidate.
5. Assign each point to the most specific leaf perspective path (not broad container nodes).
6. For each point, propose a target path and whether to update an existing note or create a new one.
7. If source material is implementation- or interface-shaped but contains stable domain semantics, extract the semantic rule into a domain, workflow, data, validation, or source-of-truth target instead of leaving it trapped in the implementation note.
8. If a candidate duplicates an existing note, mark it `duplicate-covered` or propose a canonical note plus a short linked stub.
9. For context-pack source material, extract stable content into atomic notes; do not preserve the pack as the durable unit unless the user explicitly asks to maintain context packs.
10. For open questions, use a separate `open-questions/<lifecycle-stage>/<perspective>` target.
11. When the user asks to extract valuable points for durable knowledge, persist approved durable points before ending the current conversation.
12. If required direction is missing, stop with `Waiting for your direction` and ask the minimum blocking questions.
13. If the agent cannot ask blocking questions mid-work, persist safe durable points, save uncertain valuable points as `draft`, rebuild indexes, then ask remaining questions at the end.
14. Redirect the prepared breakdown result to `write-knowledge` and then rebuild indexes.

## Strict Rules

- Do not output a generic summary as durable knowledge candidates.
- Do not preserve raw conversation order or transcript wording as the note structure.
- Do not create a note candidate without a leaf perspective and a structural-value reason.
- Do not create full duplicate notes across perspectives; choose a canonical perspective and use linked stubs only when useful.
- Do not leave domain rules only in `implementation/` or `interfaces/` candidates.
- Do not treat context packs as canonical durable notes; decompose stable content into perspective notes.
- Do not include temporary bugs, command output, credentials, tokens, or personal data in candidates.
- Do not turn agent-generated uncertainty into a persisted open question without user confirmation.
- If source material is too ambiguous to classify, return non-persisted candidates and `Waiting for your direction`.
- Do not end with only proposed targets when safe persistence is possible.
- Do not skip persistence because the conversation is long or token pressure is high; persist first, then summarize.

## Return

- durable points
- non-durable points to ignore
- possible structural updates
- perspective breakdown per point:
  - target leaf perspective path
  - reason
  - target path
  - update-existing or create-new
- suggested Markdown note title(s)
- confidence level
- source evidence or user quote when available
- written or updated note paths when persistence was safe
- index rebuild status
- blocking questions only when required for safe persistence
