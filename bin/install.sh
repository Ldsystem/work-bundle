#!/usr/bin/env bash
set -euo pipefail

force=0
dry_run=0

for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    --dry-run) dry_run=1 ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

bin_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work_bundle_root="$(cd "$bin_dir/.." && pwd)"
work_bundle_config_root="${HOME}/.work-bundle"
registry_root="${work_bundle_config_root}/registry"
template_root="${work_bundle_root}/references/assets/template"

created=()
updated=()
skipped=()
failed=()

record() {
  local bucket="$1"
  local path="$2"
  case "$bucket" in
    created) created+=("$path") ;;
    updated) updated+=("$path") ;;
    skipped) skipped+=("$path") ;;
    failed) failed+=("$path") ;;
  esac
}

ensure_dir() {
  local path="$1"
  if [[ -d "$path" ]]; then
    record skipped "$path"
    return
  fi
  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$path"
  fi
  record created "$path"
}

copy_if_missing() {
  local src="$1"
  local dest="$2"
  if [[ ! -f "$src" ]]; then
    record failed "$src"
    echo "missing template: $src" >&2
    return 1
  fi
  if [[ -e "$dest" && "$force" -eq 0 ]]; then
    record skipped "$dest"
    return
  fi
  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
  if [[ -e "$dest" && "$force" -eq 1 ]]; then
    record updated "$dest"
  else
    record created "$dest"
  fi
}

install_bootstrap() {
  local src="${template_root}/bootstrap.yaml"
  local dest="${work_bundle_config_root}/bootstrap.yaml"
  if [[ ! -f "$src" ]]; then
    record failed "$src"
    echo "missing template: $src" >&2
    return 1
  fi
  if [[ -e "$dest" && "$force" -eq 0 ]]; then
    record skipped "$dest"
    return
  fi
  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$(dirname "$dest")"
    sed "s|__WORK_BUNDLE_ROOT__|${work_bundle_root}|g; s|\\\${PLACEHOLDER} --> replace by install script|${work_bundle_root}|g" "$src" > "$dest"
  fi
  if [[ -e "$dest" && "$force" -eq 1 ]]; then
    record updated "$dest"
  else
    record created "$dest"
  fi
}

ensure_dir "$work_bundle_config_root"
ensure_dir "$registry_root"
install_bootstrap
copy_if_missing "${template_root}/projects.yaml" "${registry_root}/projects.yaml"
copy_if_missing "${template_root}/skill-registry.yaml" "${registry_root}/skill-registry.yaml"

installer="${bin_dir}/install-work-bundle-skills"
if [[ ! -x "$installer" ]]; then
  record failed "$installer"
  echo "missing executable skill installer: $installer" >&2
else
  installer_args=()
  if [[ "$force" -eq 1 ]]; then
    installer_args+=(--force)
  fi
  if [[ "$dry_run" -eq 1 ]]; then
    installer_args+=(--dry-run)
  fi
  if installer_output="$("$installer" "${installer_args[@]}")"; then
    printf '%s\n' "$installer_output"
    record updated "$installer"
  else
    record failed "$installer"
  fi
fi

printf 'created:\n'
printf '  %s\n' "${created[@]:-none}"
printf 'updated:\n'
printf '  %s\n' "${updated[@]:-none}"
printf 'skipped:\n'
printf '  %s\n' "${skipped[@]:-none}"
printf 'failed:\n'
printf '  %s\n' "${failed[@]:-none}"

if [[ "${#failed[@]}" -gt 0 ]]; then
  exit 1
fi
