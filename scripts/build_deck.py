#!/usr/bin/env python3
"""Compile scene JSON into PPTX with the built-in Artifact Tool."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scene_defaults import write_expanded

PRESENTATIONS_SKILL = Path("/root/.codex/skills/builtins/presentations")


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def initialize_artifact_workspace(run_dir: Path, env: dict[str, str]) -> None:
    """Use the built-in initializer, with an equivalent runtime-link fallback."""
    setup = PRESENTATIONS_SKILL / "container_tools/setup_artifact_tool_workspace.mjs"
    proc = subprocess.run(
        [shutil.which("node") or "node", str(setup), "--workspace", str(run_dir)],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return

    runtime_modules = env.get("CODEX_PRIMARY_RUNTIME_NODE_MODULES")
    if not runtime_modules:
        raise RuntimeError("Artifact Tool workspace setup failed and runtime modules are unknown")
    source = Path(runtime_modules) / "@oai" / "artifact-tool"
    if not (source / "package.json").exists():
        raise RuntimeError(f"Artifact Tool package is unavailable at {source}")

    package_json = run_dir / "package.json"
    if not package_json.exists():
        package_json.write_text(
            json.dumps({"private": True, "type": "module"}, indent=2) + "\n",
            encoding="utf-8",
        )
    target_parent = run_dir / "node_modules" / "@oai"
    target_parent.mkdir(parents=True, exist_ok=True)
    target = target_parent / "artifact-tool"
    if not target.exists():
        target.symlink_to(source, target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--fontconfig-file", type=Path)
    parser.add_argument(
        "--stage",
        choices=("baseboard", "semantic", "final"),
        default="final",
    )
    args = parser.parse_args()

    source_scene = args.scene.resolve()
    output = args.output.resolve()
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    skill_dir = Path(__file__).resolve().parent
    scene = write_expanded(source_scene, run_dir / "scene-expanded.json")
    lint_report = run_dir / "scene-lint.json"
    lint = subprocess.run(
        [
            sys.executable,
            str(skill_dir / "scene_lint.py"),
            str(scene),
            "--report",
            str(lint_report),
        ],
        check=False,
    )
    if lint.returncode:
        return lint.returncode

    env = os.environ.copy()
    if args.fontconfig_file:
        env["FONTCONFIG_FILE"] = str(args.fontconfig_file.resolve())
    initialize_artifact_workspace(run_dir, env)

    compiler = run_dir / "scene_to_pptx.mjs"
    shutil.copy2(skill_dir / "scene_to_pptx.mjs", compiler)
    run(
        [
            shutil.which("node") or "node",
            str(compiler),
            str(scene),
            str(output),
            args.stage,
        ],
        cwd=run_dir,
        env=env,
    )

    scene_data = json.loads(scene.read_text(encoding="utf-8"))
    policy = scene_data.get("font_policy", {})
    run(
        [
            sys.executable,
            str(skill_dir / "patch_pptx_fonts.py"),
            str(output),
            "--latin",
            policy.get("latin", "Arial"),
            "--east-asian",
            policy.get("east_asian", "Noto Sans CJK SC"),
            "--complex-script",
            policy.get("complex_script", "Arial"),
            "--scene",
            str(scene),
        ],
        cwd=run_dir,
        env=env,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
