# Workspace Tools

`tools/workspace` contains the bundled filesystem tools that operate on the
current bound workspace.

## Availability

- All workspace tools declare `scope:workspace_bound`.
- They are only visible when the current run has a bound workspace.
- They use the session-bound workspace first.
- If no `session_key` is present, they may fall back to
  `execution_context.workspace_dir`.

## Effects

- `workspace_list`, `workspace_search`, and `read` require `workspace_read`.
- `write`, `edit`, and `apply_patch` require `workspace_write`.
- `write`, `edit`, and `apply_patch` are mutating tools.

## Path Rules

- Paths must be relative to the bound workspace root.
- Absolute paths are rejected.
- Upward traversal with `..` is rejected.
- Symbolic links are rejected.
- Hard-linked files are rejected.
- Text files must be valid UTF-8.

## Tool Contract

### `workspace_list`

Parameters:

- `path` optional relative file or directory to inspect
- `limit` optional

Behavior:

- Lists direct children for a directory.
- Returns a single entry when `path` points to a file.
- Sorts directories before files.
- Skips symbolic links and unsafe paths.
- Useful before `read` or `workspace_search`.

Example:

```text
List the contents of `tools/workspace` and show up to 20 entries.
```

### `workspace_search`

Parameters:

- `query` required
- `limit` optional
- `path` optional relative file or directory to narrow the search scope

Behavior:

- Recursively searches UTF-8 text files in the workspace.
- Returns matching `path`, `line`, and `column` information.
- Skips unreadable, non-UTF-8, oversized, or linked files.
- Useful before `read`, `edit`, or `apply_patch`.

Example:

```text
Search the current workspace for `session_workspace_lookup` and show up to 5 matches.
```

### `read`

Parameters:

- `path` required
- `offset` optional, 1-based starting line
- `limit` optional, maximum line count

Behavior:

- Reads a UTF-8 text file from the workspace.
- Returns a rendered snippet with line numbers.

### `write`

Parameters:

- `path` required
- `content` required

Behavior:

- Writes the full UTF-8 file content.
- Creates missing parent directories inside the workspace.
- Does not allow writing outside the workspace.

Example:

```text
Create `notes/demo.txt` with:
hello
world
```

### `edit`

Parameters:

- `path` required
- `oldText` required
- `newText` required

Behavior:

- Replaces exactly one match inside a UTF-8 text file.
- Fails when the old text is missing.
- Fails when the old text matches more than once.
- `newText` may be empty to delete the matched text.

Example:

```text
Use workspace edit to replace `world` with `codex` in `notes/demo.txt`.
```

### `apply_patch`

Parameters:

- `input` required

Behavior:

- Applies a structured patch in `*** Begin Patch` format.
- Supports `*** Add File`, `*** Update File`, and `*** Delete File`.
- Creates missing parent directories for added files inside the workspace.
- Rejects rename operations such as `*** Move to`.
- Requires exact hunk matching.

Example patch:

```text
*** Begin Patch
*** Add File: notes/new.txt
+hello
*** Update File: notes/demo.txt
@@
 -world
 +codex
*** Delete File: notes/old.txt
*** End Patch
```

## Current Limits

- `apply_patch` does not support rename or move.
- `apply_patch` is text-only and expects UTF-8 files.
- `edit` and `apply_patch` require exact matching rather than fuzzy patching.
