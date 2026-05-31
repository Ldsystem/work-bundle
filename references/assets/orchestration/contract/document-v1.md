---
contract: document-v1
---

# Document Contract v1

Reader-facing documents are Markdown files under `.work-bundle/orchestration/docs/`.

Required behavior:

- Write for the requested human audience.
- Use accepted project knowledge or explicitly supplied source material.
- Omit unsupported facts, guesses, raw chat logs, and non-persisted open questions.
- Do not create an index for documents.
- Do not write documents under `.work-bundle/knowledge/`.

Return:

- created document path;
- title;
- source scope used;
- unsupported areas omitted.
