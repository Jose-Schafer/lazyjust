---
name: justfile-config
description: Configure justfile recipes for optimal lazyjust compatibility. Handles delegation patterns, working directories, variadic recipes, and namespace hierarchies for monorepo justfile navigation.
---

# Justfile Configuration for lazyjust

Configure justfile recipes that work correctly with lazyjust, a lazy-style TUI for navigating monorepo justfiles.

## Core Concepts

lazyjust treats justfiles as navigable hierarchies:
- **Variadic recipes** (`*args` or `+args`) act as folders/namespaces when they delegate to sub-justfiles
- **Working directories** tell lazyjust where delegated justfiles live
- **Namespace detection** happens automatically via `just <recipe> --list` or `[working-directory: "path"]` attributes

## Delegation Pattern (Most Common)

For monorepo navigation, use variadic recipes with working directories:

```just
# Parent justfile
[working-directory: "services/api"]
@api *args:
    just {{ args }}

[working-directory: "services/web"]
@web *args:
    just {{ args }}
```

**Why this works:**
- `*args` marks recipe as variadic → lazyjust treats as folder
- `[working-directory: "..."]` tells lazyjust where the sub-justfile lives
- Running `just api --list` or opening in lazyjust navigates to `services/api/justfile`

## Fallback: Directory Guessing

If no `[working-directory]` attribute, lazyjust guesses `<parent-dir>/<recipe-name>`:

```just
# Parent justfile at repo root
@api *args:
    cd api && just {{ args }}
```

lazyjust checks if `./api/justfile` exists and treats `api` as namespace if found.

## Non-Namespace Variadic Recipes

Not all variadic recipes are namespaces. Mark as non-namespace by NOT having sub-justfile:

```just
# This is a normal command that takes args, not a folder
run *args:
    cargo run -- {{ args }}
```

lazyjust checks: no `./run/justfile` → treats as regular command, not namespace.

## Recipe Requirements

### Names
- Alphanumeric, underscore, hyphen only: `build-api`, `test_all`, `deploy2`
- No special chars: `@`, `$`, spaces break parsing

### Descriptions
Use `# comment` after signature:

```just
build: # Build all services
    cargo build --workspace

test *args: # Run tests with optional filter
    cargo test {{ args }}
```

### Arguments
Supported formats:
- Required: `deploy target`
- Optional with default: `build mode="dev"`
- Variadic: `run *args` or `run +args` (+ means at least one)

### Attributes
Place directly before recipe (no blank lines):

```just
[working-directory: "path/to/dir"]
@recipe *args:
    just {{ args }}
```

Supported `working-directory` syntaxes:
- `[working-directory: "path"]`
- `[working-directory("path")]`

Paths resolve relative to justfile location.

## Common Patterns

### Monorepo Services

```just
# Root justfile
set dotenv-load := true

default:
    @just --list

# Service delegation
[working-directory: "services/api"]
@api *args:
    just {{ args }}

[working-directory: "services/web"]
@web *args:
    just {{ args }}

[working-directory: "services/worker"]
@worker *args:
    just {{ args }}
```

Each service has own `justfile` with local recipes.

### Tool Delegation

```just
# Delegate to tool-specific justfiles
[working-directory: "tools/docker"]
@docker *args:
    just {{ args }}

[working-directory: "tools/k8s"]
@k8s *args:
    just {{ args }}
```

### Mixed Namespace and Commands

```just
# Root justfile with both
default:
    @just --list

# Regular command
test:
    cargo test

# Namespace
[working-directory: "services"]
@services *args:
    just {{ args }}

# Another regular command
lint:
    cargo clippy
```

## Environment Files

lazyjust shows `.env` files when `set dotenv-load := true`:

```just
set dotenv-load := true

# Now tab key in lazyjust shows current level .env
```

Place `.env` at each justfile level for context-specific variables.

## Anti-Patterns

### DON'T: Mix cd and working-directory

```just
# BAD: Redundant and confusing
[working-directory: "api"]
@api *args:
    cd api && just {{ args }}  # cd unnecessary with working-directory
```

Use one or the other, not both.

### DON'T: Absolute paths

```just
# BAD: Breaks portability
[working-directory: "/Users/you/project/api"]
@api *args:
    just {{ args }}
```

Use relative paths from justfile location.

### DON'T: Complex argument parsing

```just
# BAD: lazyjust can't introspect this
@run *args:
    #!/usr/bin/env bash
    if [[ "$1" == "test" ]]; then
        shift
        cargo test "$@"
    else
        cargo run "$@"
    fi
```

Keep recipes simple. Split into separate recipes instead.

### DON'T: Skip descriptions

```just
# BAD: No context in lazyjust
build:
    cargo build

# GOOD: Clear purpose
build: # Build all workspace crates
    cargo build
```

Descriptions show in lazyjust's detail pane.

## Debugging in lazyjust

When recipes don't appear as expected:

1. **Check `just --list` output** — lazyjust parses this
2. **Verify working-directory paths** — must point to existing justfile
3. **Test delegation manually** — `just <namespace> --list` should work
4. **Check recipe names** — must be valid identifiers
5. **Reload** — press `r` in lazyjust to refresh

## Recipe Execution

lazyjust runs recipes as:
```bash
just <path-segment-1> <path-segment-2> ... <recipe-name> [args]
```

Example navigation: `root → services → api → build`
Executes: `just services api build`

For working-directory recipes, lazyjust automatically resolves the correct directory.

## Quick Reference

| Pattern | Syntax | Use Case |
|---------|--------|----------|
| Namespace with working-directory | `[working-directory: "path"]` + `*args` | Explicit sub-justfile location |
| Namespace with guessing | Just `*args`, sub-dir has justfile | Let lazyjust find it |
| Regular variadic | `*args` but no sub-justfile | Command that takes args |
| Required args | `recipe arg1 arg2:` | Force argument input |
| Optional args | `recipe arg="default":` | Default value provided |
| Description | `recipe: # text` | Shows in detail pane |
| Environment | `set dotenv-load := true` | Enable .env display |

## Example: Full Monorepo Setup

```just
# Root justfile
set dotenv-load := true

default:
    @just --list

# Workspace commands
test: # Run all tests
    cargo test --workspace

lint: # Run linter
    cargo clippy --workspace

# Service namespaces
[working-directory: "services/api"]
@api *args:
    just {{ args }}

[working-directory: "services/web"]
@web *args:
    just {{ args }}

# Tool namespaces
[working-directory: "tools/docker"]
@docker *args:
    just {{ args }}
```

```just
# services/api/justfile
set dotenv-load := true

default:
    @just --list

dev: # Start dev server
    cargo run

test: # Run API tests
    cargo test

build: # Build API binary
    cargo build --release
```

This creates hierarchy:
```
root
├── test
├── lint
├── api/
│   ├── dev
│   ├── test
│   └── build
├── web/
└── docker/
```

Navigate with `j`/`k`, enter namespaces with `enter`, run commands with `enter`.
