from __future__ import annotations

from pathlib import Path

import yaml


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
    supported_platforms: tuple[str, ...] = (),
    frontmatter: bool = True,
    legacy_manifest: bool = False,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if frontmatter:
        payload: dict[str, object] = {
            "apiVersion": "skills.crxzipple/v1alpha1",
            "kind": "Skill",
            "name": name,
            "description": description,
            "instructions_path": "SKILL.md",
        }
        if version is not None:
            payload["version"] = version
        if tags:
            payload["tags"] = list(tags)
        if required_tools:
            payload["required_tools"] = list(required_tools)
        if allowed_tools:
            payload["suggested_tools"] = list(allowed_tools)
        if supported_platforms:
            payload["supported_platforms"] = list(supported_platforms)
        rendered_frontmatter = yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
        ).strip()
        (root / "SKILL.md").write_text(
            f"---\n{rendered_frontmatter}\n---\n\n{instructions.strip()}\n",
            encoding="utf-8",
        )
        if not legacy_manifest:
            return

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
    if supported_platforms:
        manifest_lines.append("    supported_platforms:")
        manifest_lines.extend(f"      - {item}" for item in supported_platforms)
    (root / "skill.yaml").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    if not frontmatter:
        (root / "SKILL.md").write_text(instructions, encoding="utf-8")
