# lazypro

Lazy-style terminal UI for navigating monorepo `justfile` commands.

The interface follows a lazygit-style pane layout:

- left pane: just recipes
- top-right pane: selected command details
- bottom-right pane: command log and help
- bottom bar: current path and keybindings

## Usage

```bash
just run
```

Controls:

- `j` / `k` or arrow keys: navigate
- `enter` / `l`: open a variadic delegation recipe or run a recipe
- `?`: show context-aware keybinding hints
- `h` / `backspace`: go up
- `r`: reload
- `q` / `esc`: quit

Recipes with variadic arguments, such as `@projects *args`, are treated as folders.
Opening one runs `just projects --list`, so delegated service justfiles can be browsed.
