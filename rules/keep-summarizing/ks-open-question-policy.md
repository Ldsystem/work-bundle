---
id: ks-open-question-policy
applies_when:
  - future work or unresolved question is handled
  - open-question persistence is proposed or requested
enforcement: must
load: conditional
requires: []
---

# Keep-Summarizing Open Question Policy

## Purpose

Define when unresolved questions may be persisted as accepted future-work watchpoints. Open questions are tracking artifacts, not durable facts, and weak confirmation must not silently promote them into the knowledge base.

## Must

- treat persisted open questions as standalone watchpoints under open-questions rather than facts inside notes
- persist an open question only when the user provides it as future work, the user explicitly asks to persist open questions, or the agent proposes it and the user explicitly confirms tracking value
- label persisted open questions as accepted future work rather than settled facts
- ask for explicit tracking confirmation when the user's response is weak or ambiguous
- keep open-question watch context separate from implementation facts, runtime rules, and reader-facing document conclusions

## Must Not

- treat open questions as settled facts
- write an open question when it is only the agent's uncertainty
- write an open question when it is a weak guess
- write an open question when it is only a missing fact discovered while preparing reader-facing output
- treat weak confirmation such as sure good suggestion or sounds good as approval to persist a tracked watchpoint
- silently embed accepted open questions into curated notes as if they were current knowledge

## Validation

- every persisted open question has an explicit future-work or explicit tracking signal from the user
- weak or ambiguous confirmations are rejected for persistence until clarified
- persisted questions remain clearly separated from durable facts and implementation constraints
- retrieval and reporting treat open questions as watch context rather than authority

## On Violation

Stop persistence, report whether the problem is missing confirmation, fact promotion, or watch-context leakage, and either ask for explicit tracking approval or keep the question only in the response.
