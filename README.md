# lazyjust

Lazy-style terminal UI for navigating monorepo `justfile` commands.

![lazyjust demo](gif/example.gif)

The interface follows a lazygit-style pane layout:

- left pane: just recipes
- top-right pane: selected command details
- bottom-right pane: command log and help
- bottom bar: current path and keybindings

## Installation

### From GitHub

```bash
uv tool install git+https://github.com/Jose-Schafer/lazyjust.git
```

### From local clone

```bash
uv tool install /path/to/lazyjust
```

After local changes, reinstall:

```bash
uv tool install --reinstall /path/to/lazyjust
```

## Usage

Run from any project root with a justfile:

```bash
lazyjust
```

Or during development:

```bash
just run
```

Controls:

- `j` / `k` or arrow keys: navigate
- `/`: search commands across nested justfiles
- `enter`: open a variadic delegation recipe or run a recipe
- `l`: open a variadic delegation recipe only; never runs commands
- `[` / `]`: move focus between panes
- `tab`: switch the lower pane between logs and the current level `.env`
- `e`: open the current level `justfile` in Zed
- `?`: show context-aware keybinding hints
- `h` / `esc` / `backspace`: go up
- `r`: reload
- `q`: quit

Recipes with variadic arguments, such as `@projects *args`, are treated as folders.
Opening one runs `just projects --list`, so delegated service justfiles can be browsed.

## Claude Code Skill

A comprehensive skill for configuring justfiles compatible with lazyjust is available at `skills/justfile-config/skill.md`.

Use it in Claude Code to:
- Set up delegation patterns with `[working-directory]` attributes
- Configure variadic recipes as navigable namespaces
- Structure monorepo justfile hierarchies
- Avoid common anti-patterns

The skill includes examples, best practices, and debugging tips for optimal lazyjust integration.
