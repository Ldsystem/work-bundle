from core import *

PROFILE = '''id: project-domain-profile
status: deprecated
authority: compatibility-reference
canonical_metadata: .work-bundle/project.yaml
migration_owner: /wb-initialize-project
doctor_flow: /wb-initialize-project doctor
migrate_flow: /wb-initialize-project migrate
version: 1
generated_by: wb-initialize-project
updated_at: 2026-05-25
industry: agent-workflow-tooling
business_context: Local-first agent knowledge and orchestration workflow tooling.
core_domain_objects: [work-bundle, durable-knowledge, orchestration-artifact, skill, runtime-rule]
core_lifecycles: [spec -> plan -> phase -> task -> execute -> handoff -> review]
domain_constraints: [keep durable knowledge separate from orchestration artifacts, compact runtime files first]
common_misunderstandings: [do not treat open questions as facts, do not let execute-plan retrieve knowledge]
current_lifecycle_stage: development-design
stage_specific_authority:
  tender: weak input unless confirmed later
  investigation: discovery findings; useful for scope and clarification
  customer-design: customer-visible intent, not engineering authority by default
  bidding: commercial commitment; not implementation design by default
  development-design: primary authority for specs and plans
  implementation: verified behavior from code, handoff, review, or tests
  deployment: runtime and rollout authority
  go-live-delivery: delivery and acceptance authority
  operation: production/runtime authority
role_positioning:
  default: selected role profiles must apply this domain profile before producing domain-sensitive output
source_knowledge:
  - path: explicit-source
    role: authority
    reason: input context
warnings: []
'''


def cmd_domain_profile(args: list[str], merge: bool = False, validate: bool = False) -> int:
    if validate:
        parser = argparse.ArgumentParser(prog='wb.py validate-domain-profile')
        parser.add_argument('profile')
        parsed = parser.parse_args(args)
        text = read(Path(parsed.profile))
        failures = [token for token in ['id:', 'status:', 'industry:', 'business_context:', 'source_knowledge:', 'role_positioning:', 'warnings:'] if token not in text]
        if len(text.splitlines()) > 120:
            failures.append('prose_heavy')
        out({'path': parsed.profile, 'status': 'passed' if not failures else 'issues-found', 'failures': failures, 'line_count': len(text.splitlines())})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py merge-domain-profile' if merge else 'wb.py generate-domain-profile')
    if merge:
        parser.add_argument('--current')
        parser.add_argument('--incoming', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(args)
        write(Path(parsed.output), read(Path(parsed.incoming)))
    else:
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(args)
        write(Path(parsed.output), PROFILE.replace('explicit-source', parsed.input))
    out({'status': 'passed', 'output': parsed.output})
    return 0
