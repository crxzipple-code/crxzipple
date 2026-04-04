from __future__ import annotations

from pathlib import Path


def write_skill_package(
    root: Path,
    *,
    name: str,
    description: str,
    instructions: str,
    version: str | None = None,
    tags: tuple[str, ...] = (),
    required_tools: tuple[str, ...] = (),
    allowed_tools: tuple[str, ...] = (),
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest_lines = [
        "apiVersion: skills.crxzipple/v1alpha1",
        "kind: Skill",
        "metadata:",
        f"  name: {name}",
        f"  description: {description}",
    ]
    if version is not None:
        manifest_lines.append(f"  version: {version}")
    if tags:
        manifest_lines.append("  tags:")
        manifest_lines.extend(f"    - {tag}" for tag in tags)
    manifest_lines.extend(
        [
            "spec:",
            "  instructions: SKILL.md",
            "  dependencies:",
            "    tools:",
        ],
    )
    if required_tools:
        manifest_lines.append("      required:")
        manifest_lines.extend(f"        - {tool}" for tool in required_tools)
    else:
        manifest_lines.append("      required: []")
    manifest_lines.extend(
        [
            "      optional: []",
            "  runtime:",
        ],
    )
    if allowed_tools:
        manifest_lines.append("    allowed_tools:")
        manifest_lines.extend(f"      - {tool}" for tool in allowed_tools)
    else:
        manifest_lines.append("    allowed_tools: []")
    (root / "skill.yaml").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    (root / "SKILL.md").write_text(instructions, encoding="utf-8")
