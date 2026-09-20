from __future__ import annotations

import json
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL_COMMAND = ROOT / "bin" / "work-bundle-skill"
SKILL_ROOT = ROOT / "skills"


def run_skill(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL_COMMAND), "--home", str(home), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def skill_names() -> list[str]:
    return sorted(path.name for path in SKILL_ROOT.iterdir() if (path / "SKILL.md").is_file())


def load_skill_module():
    name = "work_bundle_skill_test_module"
    loader = importlib.machinery.SourceFileLoader(name, str(SKILL_COMMAND))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def test_list_and_validate_contract_is_preserved(tmp_path: Path) -> None:
    listed = run_skill(tmp_path, "list")
    validated = run_skill(tmp_path, "validate")

    assert listed.returncode == 0, listed.stderr
    assert validated.returncode == 0, validated.stderr
    assert json.loads(listed.stdout)["skills"] == skill_names()
    assert json.loads(validated.stdout)["ok"] is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink behavior")
def test_enable_and_disable_use_exactly_owned_posix_symlink(tmp_path: Path) -> None:
    name = skill_names()[0]
    destination = tmp_path / ".agents" / "skills" / name

    enabled = run_skill(tmp_path, "enable", "--name", name)
    repeated = run_skill(tmp_path, "enable", "--name", name)
    disabled = run_skill(tmp_path, "disable", "--name", name)

    assert enabled.returncode == 0, enabled.stderr
    assert "create symlink" in json.loads(enabled.stdout)["action"]
    assert "already exists" in json.loads(repeated.stdout)["action"]
    assert "remove symlink" in json.loads(disabled.stdout)["action"]
    assert not destination.exists() and not destination.is_symlink()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink behavior")
def test_unowned_symlink_is_rejected_even_with_force(tmp_path: Path) -> None:
    name = skill_names()[0]
    destination = tmp_path / ".agents" / "skills" / name
    destination.parent.mkdir(parents=True)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    destination.symlink_to(unrelated, target_is_directory=True)

    result = run_skill(tmp_path, "enable", "--name", name, "--force")

    assert result.returncode == 1
    assert "unmanaged symlink" in result.stderr
    assert destination.resolve() == unrelated.resolve()


def test_enable_all_validates_every_destination_before_mutation(tmp_path: Path) -> None:
    names = skill_names()
    first = tmp_path / ".agents" / "skills" / names[0]
    blocked = tmp_path / ".agents" / "skills" / names[1]
    blocked.mkdir(parents=True)

    result = run_skill(tmp_path, "enable-all")

    assert result.returncode == 1
    assert "non-link path" in result.stderr
    assert not first.exists() and not first.is_symlink()
    assert blocked.is_dir()


def test_enable_all_dry_run_is_non_mutating(tmp_path: Path) -> None:
    result = run_skill(tmp_path, "enable-all", "--dry-run")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["count"] == len(skill_names())
    assert not (tmp_path / ".agents").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink fixture")
def test_disable_all_validates_every_destination_before_mutation(tmp_path: Path) -> None:
    names = skill_names()
    first = tmp_path / ".agents" / "skills" / names[0]
    first.parent.mkdir(parents=True)
    first.symlink_to(SKILL_ROOT / names[0], target_is_directory=True)
    blocked = tmp_path / ".agents" / "skills" / names[1]
    blocked.mkdir()

    result = run_skill(tmp_path, "disable-all")

    assert result.returncode == 1
    assert "non-link path" in result.stderr
    assert first.is_symlink()
    assert blocked.is_dir()


@pytest.mark.parametrize("kind_name", ["JUNCTION", "REPARSE"])
def test_unowned_windows_link_like_destinations_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind_name: str
) -> None:
    module = load_skill_module()
    name = skill_names()[0]
    destination = module.link_path(name, str(tmp_path))
    kind = getattr(module.PathKind, kind_name)
    monkeypatch.setattr(module, "classify_path", lambda path: kind if path == destination else module.PathKind.ORDINARY)
    monkeypatch.setattr(module, "_resolved_target", lambda path: tmp_path / "unrelated")

    with pytest.raises(FileExistsError, match="unmanaged"):
        module.plan_enable(name, home=str(tmp_path), force=True)


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction behavior")
def test_native_windows_enable_and_disable_use_directory_junction(tmp_path: Path) -> None:
    name = skill_names()[0]
    destination = tmp_path / ".agents" / "skills" / name

    enabled = run_skill(tmp_path, "enable", "--name", name)

    assert enabled.returncode == 0, enabled.stderr
    assert destination.is_junction()
    assert destination.resolve() == (SKILL_ROOT / name).resolve()
    assert "create junction" in json.loads(enabled.stdout)["action"]

    disabled = run_skill(tmp_path, "disable", "--name", name)
    assert disabled.returncode == 0, disabled.stderr
    assert not destination.exists()
