# WorkBundle toolkit contributors

This repository is the WorkBundle toolkit source, not an installed workspace entry point. The installed managed `AGENTS.md` section comes only from `references/assets/template/AGENTS.md`.

- Keep changes small and in the existing owner. Remove obsolete paths when replacing behavior; do not add speculative compatibility or recovery layers.
- Ground meaning in the user purpose and accepted decisions. Current code, tests, indexes, and helper output are evidence, not semantic authority. Agents judge product correctness and acceptance; scripts and schemas enforce declared mechanics.
- Check necessary constraints before an authoritative write. Afterward, use light integrity checks and focused behavior tests. Review the actual product against its obligations before claiming completion.
- Preserve unrelated source and user content. Do not rewrite another task's files or treat another task's source changes as accepted merely because it reports success.
- Follow the applicable indexed toolkit, global user, and workspace rules for the operation. Resolve toolkit and registry paths through `~/.work-bundle/bootstrap.yaml`; locate a managed workspace from its `.work-bundle/project.yaml` and select the member repository before source work.
- Never inspect or expose a workspace credential store. A credential requirement goes through `wb-credential-use` with a credential ID and non-secret context.
