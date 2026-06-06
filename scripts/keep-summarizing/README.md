# Keep-Summarizing Scripts

Implementation modules in this directory are the manual maintenance surface for keep-summarizing helpers.

The top-level `../ks.py` entrypoint remains for compatibility with existing agent instructions. Implementation is split by maintenance area (`core.py`, `registry.py`, `project.py`, `notes.py`, `indexes.py`, `questions.py`, `query.py`, `migration.py`, `doctor.py`), with `dispatcher.py` only wiring commands.

Command examples:

```bash
python3 scripts/ks.py breakdown-design --project <slug> --input <file>
python3 scripts/ks.py index --project <slug>
python3 scripts/ks.py query --project <slug> --target implementation_plan --query "<query>"
```
