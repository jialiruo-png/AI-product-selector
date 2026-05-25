# Material Collection To Writing Bridge Design

## Goal

Build a low-intrusion bridge between the material collection workspace and the self-media writing workspace.

The first phase has two responsibilities:

1. Make the self-media assistant use replaceable account packages.
2. Let writing projects reference collected Markdown materials without modifying the original material library.

This phase deliberately avoids rebuilding the whole platform. The design should be easy to migrate when the larger platform is reconstructed later.

## Current State

The repository currently has two mostly separate systems:

- `采集工作台/` collects materials from WeChat, Xiaohongshu, Zhihu, and GitHub, then writes Markdown files to `采集工作台/素材库/`.
- `自媒体助手/` runs a project-based writing workflow with fixed global `skills/`, `memory/`, `materials/profile/`, `materials/compliance/`, and other context files.

The gap is that writing projects cannot directly select collected materials, and the writing assistant's style, skills, and memory are not packaged as a replaceable unit.

## Decisions

### Account Package Unit

Use account packages as the replacement unit.

Each account package owns its complete writing context:

- profile
- memory
- skills
- ideas
- facts
- compliance rules
- material usage preferences

The first implementation should create a default account package from the existing self-media assistant assets.

Proposed structure:

```text
自媒体助手/accounts/default/
├── account.yaml
├── profile/
├── memory/
├── skills/
├── ideas/
├── facts/
└── compliance/
```

`account.yaml` should identify the package and define stable relative paths:

```yaml
id: default
name: Default Self-Media Account
description: Migrated default account package
profile_dir: profile
memory_file: memory/content_memory.md
skills_dir: skills
ideas_dir: ideas
facts_dir: facts
compliance_dir: compliance
```

For backward compatibility, the existing top-level self-media directories can remain in place during this phase. The workflow should prefer the selected account package when present, then fall back to legacy paths if needed.

### Project Account Selection

Each writing project should explicitly record which account package it uses.

Add this file to new and existing project structures:

```text
自媒体助手/projects/<slug>/context/account.yaml
```

Minimal shape:

```yaml
account_id: default
account_path: ../../accounts/default
```

This keeps each project reproducible: later, when multiple accounts exist, old projects still know which writing context they were created with.

### Material Reference Only

The first phase only references collected materials.

Original collected Markdown files under `采集工作台/素材库/` must not be edited by the writing workflow.

Each writing project gets:

```text
自媒体助手/projects/<slug>/input/material_refs.json
自媒体助手/projects/<slug>/input/selected_materials.md
```

`material_refs.json` is the structured source of truth:

```json
{
  "created_at": "2026-05-25T00:00:00+08:00",
  "material_root": "../../采集工作台/素材库",
  "items": [
    {
      "id": "sha1-or-stable-slug",
      "title": "Material title",
      "path": "../../采集工作台/素材库/example/article.md",
      "source": "https://example.com/article",
      "platform": "weixin",
      "selected_at": "2026-05-25T00:00:00+08:00"
    }
  ]
}
```

`selected_materials.md` is the human-readable and AI-readable project input. It should include:

- selected material list
- source path and source URL when available
- short excerpt or full linked content depending on size
- notes that the original material is referenced, not modified

## Workflow Changes

### New Project Creation

`自媒体助手/scripts/new_project.sh` should create:

```text
projects/<slug>/context/account.yaml
projects/<slug>/input/material_refs.json
projects/<slug>/input/selected_materials.md
```

The default account should be `default`.

### Material Selection

Add a helper script in the self-media assistant:

```text
自媒体助手/scripts/link_materials.py
```

Responsibilities:

- accept a project slug
- accept one or more material Markdown paths
- resolve paths relative to the repository root
- extract title and common metadata from each Markdown file
- write `material_refs.json`
- generate `selected_materials.md`

Suggested command:

```bash
python3 自媒体助手/scripts/link_materials.py \
  --project 2026-05-25-example \
  --material "采集工作台/素材库/some-run/article.md"
```

This can later be used by a GUI or a redesigned platform without changing the project file contract.

### Workflow Skill Loading

`自媒体助手/skills/media-workflow/SKILL.md` should be updated so the workflow:

1. Reads `projects/<slug>/context/account.yaml`.
2. Loads account package profile, memory, skills, facts, ideas, and compliance files.
3. Loads `projects/<slug>/input/selected_materials.md` when present.
4. Treats selected materials as context and evidence candidates, not as source text to copy.
5. Keeps final outputs in `final/` and process notes in `process/` as before.

`自媒体助手/skills/content-production/SKILL.md` should be updated so required inputs are project-relative and account-package-relative instead of hardcoded to legacy global paths.

## Data Flow

```text
采集工作台/素材库/*.md
        |
        | link_materials.py references selected files
        v
自媒体助手/projects/<slug>/input/material_refs.json
自媒体助手/projects/<slug>/input/selected_materials.md
        |
        | media-workflow loads selected account package and selected materials
        v
自媒体助手/projects/<slug>/process/*.md
自媒体助手/projects/<slug>/final/voiceover.md
自媒体助手/projects/<slug>/final/subtitle.md
```

## Error Handling

The material linking helper should fail clearly when:

- the project does not exist
- a material path does not exist
- a material path points outside the repository
- `selected_materials.md` cannot be written

If no selected materials exist, the writing workflow should continue with the original script workflow and mention that no external materials were loaded.

If `context/account.yaml` is missing, the workflow should fall back to `accounts/default` when it exists, then fall back to legacy paths.

## Testing

Add focused checks for the bridge behavior:

- create a new project and verify the new account/material files exist
- link one collected Markdown file and verify both `material_refs.json` and `selected_materials.md`
- verify the helper does not modify the original material file
- verify legacy projects without `context/account.yaml` still have a fallback path

Manual verification should include creating a sample project, linking one existing collected material, then reading the resulting selected materials file.

## Out Of Scope

This phase does not include:

- editing collected materials from the writing assistant
- writing tags, summaries, or rewrite results back to `采集工作台/素材库/`
- building a new GUI
- redesigning the entire platform
- supporting component-level mixing of style, memory, and skills

Those are intentionally deferred until the larger platform reconstruction.
