from __future__ import annotations

import curses
from shlex import join, split
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from lib.justfile import Recipe, current_level_dir, has_dotenv_load, list_recipes, run_recipe


PAIR_NAMESPACE = 1
PAIR_BORDER = 2
PAIR_SELECTED = 3
PAIR_DIM = 4
PAIR_FOOTER = 5
PAIR_KEY = 6
PAIR_ERROR = 7
PAIR_MODAL = 8
PAIR_MODAL_SELECTED = 9
PAIR_FOOTER_KEY = 10
PAIR_LOCATION = 11
PAIR_LOCATION_ACTIVE = 12
PAIR_ARGUMENT = 13
PAIR_INPUT = 14
PAIR_ENV_KEY = 15

IMPORTANT_ENV_KEYS = (
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_ACCOUNT_ID",
    "CDK_DEFAULT_ACCOUNT",
    "CDK_DEFAULT_REGION",
    "ENV",
    "STAGE",
    "CLIENT_ID",
)


@dataclass(frozen=True)
class HelpOption:
    key: str
    description: str
    action: str


@dataclass
class AppState:
    cwd: Path
    path: list[str] = field(default_factory=list)
    recipes: list[Recipe] = field(default_factory=list)
    selected: int = 0
    message: str = ""
    output: str = ""
    show_help: bool = False
    help_selected: int = 0
    lower_view: str = "log"
    show_input: bool = False
    input_text: str = ""
    input_error: str = ""
    pending_path: list[str] = field(default_factory=list)
    selected_by_path: dict[tuple[str, ...], int] = field(default_factory=dict)


@dataclass(frozen=True)
class Rect:
    y: int
    x: int
    height: int
    width: int


def run(cwd: Path) -> int:
    return curses.wrapper(_run_curses, cwd)


def _run_curses(stdscr: curses.window, cwd: Path) -> int:
    _set_fast_escape()
    curses.curs_set(0)
    stdscr.keypad(True)
    _init_colors()

    state = AppState(cwd=cwd)
    _reload(state)

    while True:
        _draw(stdscr, state)
        key = stdscr.getch()

        if state.show_input:
            _handle_input_key(state, key)
            continue

        if state.show_help:
            if _handle_help_key(state, key):
                return 0
            continue

        if key == ord("?"):
            state.show_help = True
            state.help_selected = 0
            continue
        if key == ord("q"):
            return 0
        if key in (curses.KEY_UP, ord("k")):
            state.selected = max(0, state.selected - 1)
            continue
        if key in (curses.KEY_DOWN, ord("j")):
            state.selected = min(max(0, len(state.recipes) - 1), state.selected + 1)
            continue
        if key in (curses.KEY_BACKSPACE, 127, 8, ord("h"), 27):
            _go_back(state)
            continue
        if key in (9, ord("e")):
            _toggle_lower_view(state)
            continue
        if key in (ord("r"),):
            _reload(state)
            continue
        if key in (curses.KEY_ENTER, 10, 13, ord("l")):
            _activate(state)
            continue


def _handle_help_key(state: AppState, key: int) -> bool:
    options = _help_options(state)

    if key in (ord("?"), 27):
        state.show_help = False
        return False
    if key in (curses.KEY_UP, ord("k")):
        state.help_selected = max(0, state.help_selected - 1)
        return False
    if key in (curses.KEY_DOWN, ord("j")):
        state.help_selected = min(max(0, len(options) - 1), state.help_selected + 1)
        return False
    if key in (curses.KEY_ENTER, 10, 13, ord("l")) and options:
        return _run_help_action(state, options[state.help_selected].action)
    if key in (curses.KEY_BACKSPACE, 127, 8):
        return _run_help_action(state, "back")

    action_by_key = {
        "h": "back",
        "q": "quit",
        "r": "reload",
        "e": "toggle_env",
    }
    if 0 <= key < 256 and (action := action_by_key.get(chr(key))):
        return _run_help_action(state, action)

    return False


def _run_help_action(state: AppState, action: str) -> bool:
    state.show_help = False

    if action == "activate":
        _activate(state)
        return False
    if action == "select_down":
        state.selected = min(max(0, len(state.recipes) - 1), state.selected + 1)
        return False
    if action == "select_up":
        state.selected = max(0, state.selected - 1)
        return False
    if action == "reload":
        _reload(state)
        return False
    if action == "toggle_env":
        _toggle_lower_view(state)
        return False
    if action == "back":
        _go_back(state)
        return False
    if action == "quit":
        return True
    if action == "close":
        return False

    return False


def _handle_input_key(state: AppState, key: int) -> None:
    if key in (27,):
        _close_input(state)
        return
    if key in (curses.KEY_ENTER, 10, 13):
        _submit_input(state)
        return
    if key in (curses.KEY_BACKSPACE, 127, 8):
        state.input_text = state.input_text[:-1]
        state.input_error = ""
        return
    if key == curses.KEY_DC:
        state.input_text = ""
        state.input_error = ""
        return
    if 32 <= key < 127:
        state.input_text += chr(key)
        state.input_error = ""


def _submit_input(state: AppState) -> None:
    try:
        args = split(state.input_text)
    except ValueError as exc:
        state.input_error = str(exc)
        return

    recipe = _recipe_for_path(state, state.pending_path)
    required_count = len([argument for argument in (recipe.arguments if recipe else ()) if argument.is_required])
    if len(args) < required_count:
        state.input_error = f"expected at least {required_count} argument(s), got {len(args)}"
        return

    pending_path = [*state.pending_path]
    _close_input(state)
    _run_command(state, pending_path, args)


def _close_input(state: AppState) -> None:
    state.show_input = False
    state.input_text = ""
    state.input_error = ""
    state.pending_path = []


def _reload(state: AppState) -> None:
    try:
        state.recipes = list_recipes(state.cwd, state.path)
        state.selected = min(state.selected, max(0, len(state.recipes) - 1))
        state.message = ""
    except RuntimeError as exc:
        state.recipes = []
        state.selected = 0
        state.message = str(exc)


def _toggle_lower_view(state: AppState) -> None:
    state.lower_view = "env" if state.lower_view == "log" else "log"


def _go_back(state: AppState) -> None:
    if state.path:
        state.selected_by_path[_path_key(state.path)] = state.selected
        state.path.pop()
        state.selected = state.selected_by_path.get(_path_key(state.path), 0)
        _reload(state)


def _activate(state: AppState) -> None:
    if not state.recipes:
        return

    recipe = state.recipes[state.selected]
    next_path = [*state.path, recipe.name]

    if recipe.is_namespace:
        state.selected_by_path[_path_key(state.path)] = state.selected
        state.path = next_path
        state.selected = state.selected_by_path.get(_path_key(state.path), 0)
        _reload(state)
        return

    if recipe.arguments:
        state.show_input = True
        state.input_text = ""
        state.input_error = ""
        state.pending_path = next_path
        return

    _run_command(state, next_path, [])


def _run_command(state: AppState, path: list[str], args: list[str]) -> None:
    returncode = _run_interactive(state, path, args)
    command = _format_just_command(path, args)
    state.output = f"Last command: {command}\nExit code: {returncode}"
    state.message = f"exit {returncode}: {command}"


def _run_interactive(state: AppState, path: list[str], args: list[str]) -> int:
    curses.def_prog_mode()
    curses.endwin()

    command = _format_just_command(path, args)
    print(f"\n[lazypro] running {command}\n")
    try:
        returncode = run_recipe(state.cwd, path, args)
    except KeyboardInterrupt:
        returncode = 130
    finally:
        print("\n[lazypro] press enter to return")
        try:
            input()
        except EOFError:
            pass
        curses.reset_prog_mode()
        curses.curs_set(0)

    return returncode


def _draw(stdscr: curses.window, state: AppState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    if height < 11 or width < 50:
        _draw_too_small(stdscr, height, width)
        stdscr.refresh()
        return

    location = Rect(y=0, x=0, height=2, width=width)
    body_y = 2
    body_height = height - body_y - 1
    left_width = max(32, min(48, width // 3))
    left = Rect(y=body_y, x=0, height=body_height, width=left_width)
    right_width = width - left_width
    details_height = max(9, min(12, body_height // 2))
    details = Rect(y=body_y, x=left_width, height=details_height, width=right_width)
    output = Rect(
        y=body_y + details_height,
        x=left_width,
        height=body_height - details_height,
        width=right_width,
    )
    footer = Rect(y=height - 1, x=0, height=1, width=width)

    _draw_location(stdscr, state, location)
    _draw_recipes(stdscr, state, left)
    _draw_details(stdscr, state, details)
    _draw_lower_pane(stdscr, state, output)
    _draw_footer(stdscr, state, footer)
    if state.show_input:
        _draw_input_modal(stdscr, state, height, width)
    if state.show_help:
        _draw_help_modal(stdscr, state, height, width)
    stdscr.refresh()


def _draw_location(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    if rect.height < 2:
        return

    level_dir, _ = current_level_dir(state.cwd, state.path)
    _safe_addstr(stdscr, rect.y, rect.x, " " * rect.width, _color(PAIR_LOCATION))
    _safe_addstr(stdscr, rect.y + 1, rect.x, " " * rect.width, _color(PAIR_LOCATION))

    x = rect.x + 1
    label = " YOU ARE HERE "
    _safe_addstr(stdscr, rect.y, x, label, _color(PAIR_LOCATION_ACTIVE))
    x += len(label) + 1

    parts = ["root", *state.path]
    for index, part in enumerate(parts):
        is_active = index == len(parts) - 1
        attr = _color(PAIR_LOCATION_ACTIVE) if is_active else _color(PAIR_LOCATION)
        text = f" {part} "
        if x + len(text) >= rect.width:
            break
        _safe_addstr(stdscr, rect.y, x, text, attr)
        x += len(text)
        if index < len(parts) - 1 and x + 3 < rect.width:
            _safe_addstr(stdscr, rect.y, x, " > ", _color(PAIR_LOCATION))
            x += 3

    directory = f" DIR {level_dir} "
    _safe_addstr(stdscr, rect.y + 1, rect.x + 1, directory[: max(0, rect.width - 2)], _color(PAIR_LOCATION))


def _draw_recipes(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    _draw_box(stdscr, rect, f"Commands: {_current_level_name(state)}")
    content = _inner(rect)
    list_height = max(0, content.height)
    start = _visible_start(state.selected, list_height, len(state.recipes))

    for row, recipe in enumerate(state.recipes[start : start + list_height], start=content.y):
        recipe_index = start + row - content.y
        label = _recipe_label(recipe)
        attr = _recipe_attr(recipe, recipe_index == state.selected)
        _safe_addstr(
            stdscr,
            row,
            content.x,
            label[: content.width].ljust(content.width),
            attr,
        )

    if not state.recipes and content.height > 0:
        _safe_addstr(stdscr, content.y, content.x, " No recipes found"[: content.width])


def _draw_details(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    _draw_box(stdscr, rect, "Command")
    content = _inner(rect)
    recipe = _selected_recipe(state)

    if not recipe:
        _write_wrapped(stdscr, content, ["No command selected."])
        return

    command_path = [*state.path, recipe.name]
    command = _format_just_command(command_path)
    recipe_type = "namespace" if recipe.is_namespace else "command"
    row = content.y
    row = _write_detail_line(stdscr, content, row, f"Name: {recipe.name}")
    row = _write_detail_line(stdscr, content, row, f"Type: {recipe_type}")
    row = _write_detail_line(stdscr, content, row, f"Command: {command}")
    row = _write_signature_line(stdscr, content, row, recipe)
    if recipe.description:
        row = _write_detail_line(stdscr, content, row, f"Description: {recipe.description}")
    level_dir, _ = current_level_dir(state.cwd, state.path)
    row = _write_detail_line(stdscr, content, row, f"Directory: {level_dir}")
    _write_context_lines(stdscr, content, row, level_dir)


def _write_detail_line(stdscr: curses.window, rect: Rect, row: int, value: str) -> int:
    if row >= rect.y + rect.height:
        return row
    _safe_addstr(stdscr, row, rect.x, value[: rect.width].ljust(rect.width))
    return row + 1


def _write_signature_line(stdscr: curses.window, rect: Rect, row: int, recipe: Recipe) -> int:
    if row >= rect.y + rect.height:
        return row

    label = "Signature: "
    x = rect.x
    _safe_addstr(stdscr, row, x, label)
    x += len(label)
    _safe_addstr(stdscr, row, x, recipe.name[: max(0, rect.width - len(label))])
    x += len(recipe.name)

    for argument in recipe.arguments:
        token = f" {argument.token}"
        if x + len(token) >= rect.x + rect.width:
            break
        _safe_addstr(stdscr, row, x, token, _color(PAIR_ARGUMENT) | curses.A_BOLD)
        x += len(token)

    return row + 1


def _write_context_lines(stdscr: curses.window, rect: Rect, row: int, directory: Path) -> int:
    important_values = _important_env_values(directory)
    warnings = _context_warnings(directory)
    if not important_values and not warnings:
        return row
    if row >= rect.y + rect.height:
        return row

    row = _write_detail_line(stdscr, rect, row + 1, "Context:")
    for warning in warnings:
        if row >= rect.y + rect.height:
            break
        _safe_addstr(stdscr, row, rect.x, warning[: rect.width].ljust(rect.width), _color(PAIR_ERROR))
        row += 1
    for name, value in important_values:
        if row >= rect.y + rect.height:
            break
        _write_key_value_line(stdscr, rect, row, name, value)
        row += 1
    return row


def _context_warnings(directory: Path) -> list[str]:
    if has_dotenv_load(directory):
        return []
    return ["! justfile missing: set dotenv-load := true"]


def _write_key_value_line(
    stdscr: curses.window,
    rect: Rect,
    row: int,
    name: str,
    value: str,
) -> None:
    x = rect.x
    key = f"{name}: "
    _safe_addstr(stdscr, row, x, key[: rect.width], _color(PAIR_ENV_KEY) | curses.A_BOLD)
    x += len(key)
    available = max(0, rect.width - len(key))
    _safe_addstr(stdscr, row, x, value[:available].ljust(available))


def _draw_lower_pane(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    if state.lower_view == "env":
        _draw_env(stdscr, state, rect)
        return
    _draw_log(stdscr, state, rect)


def _draw_log(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    _draw_box(stdscr, rect, "Log  [tab/e: .env]")
    content = _inner(rect)
    lines: list[str] = []
    if state.output:
        lines.extend(state.output.splitlines())
    else:
        lines.extend(
            [
                "Select a command on the left.",
                "Namespaces open another justfile level.",
                "Leaf commands temporarily leave the TUI and run in your terminal.",
            ]
        )

    _write_wrapped(stdscr, content, lines, from_bottom=bool(state.output))


def _draw_env(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    level_dir, resolved = current_level_dir(state.cwd, state.path)
    env_path = level_dir / ".env"
    title = ".env  [tab/e: log]"
    _draw_box(stdscr, rect, title)
    content = _inner(rect)

    if not resolved:
        _write_wrapped(stdscr, content, [f"Could not resolve current directory for: {' '.join(state.path)}"])
        return
    if not env_path.is_file():
        _write_wrapped(stdscr, content, [f"No .env found at {env_path}"])
        return

    try:
        lines = env_path.read_text().splitlines()
    except OSError as exc:
        _write_wrapped(stdscr, content, [f"Could not read {env_path}: {exc}"])
        return

    if not lines:
        _write_wrapped(stdscr, content, [f"{env_path} is empty"])
        return

    _write_env_lines(stdscr, content, lines)


def _draw_footer(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    segments = [
        ("j/k", "move"),
        ("enter", "open/run"),
        ("h/esc", "back"),
        ("tab/e", ".env"),
        ("?", "help"),
        ("r", "reload"),
        ("q", "quit"),
    ]

    message = state.message or _selected_command(state)

    attr = _color(PAIR_ERROR) if state.message and state.message.startswith("exit ") else _color(PAIR_FOOTER)
    _safe_addstr(stdscr, rect.y, rect.x, " " * max(0, rect.width - 1), attr)

    key_text = "  ".join(f"{key} {description}" for key, description in segments)
    key_start = max(rect.x + 1, rect.x + rect.width - len(key_text) - 2)
    message_width = max(0, key_start - rect.x - 2)
    _safe_addstr(stdscr, rect.y, rect.x + 1, message[:message_width], attr)

    x = key_start
    for key, description in segments:
        if x >= rect.width - 1:
            break
        _safe_addstr(stdscr, rect.y, x, key, _color(PAIR_FOOTER_KEY))
        x += len(key)
        text = f" {description}  "
        _safe_addstr(stdscr, rect.y, x, text[: max(0, rect.width - x - 1)], _color(PAIR_FOOTER))
        x += len(text)


def _draw_input_modal(stdscr: curses.window, state: AppState, height: int, width: int) -> None:
    recipe = _recipe_for_path(state, state.pending_path)
    modal_width = min(88, max(56, width - 10))
    modal_height = min(max(12, 8 + len(recipe.arguments if recipe else ())), height - 4)
    rect = Rect(
        y=max(1, (height - modal_height) // 2),
        x=max(0, (width - modal_width) // 2),
        height=modal_height,
        width=modal_width,
    )

    _draw_filled_box(stdscr, rect, "Arguments")
    content = _inner(rect)
    command = _format_just_command(state.pending_path)
    row = content.y
    row = _write_detail_line(stdscr, content, row, f"Command: {command}")
    row = _write_detail_line(stdscr, content, row, "Expected variables:")

    if recipe and recipe.arguments:
        for argument in recipe.arguments:
            if row >= content.y + content.height - 4:
                break
            label = "required" if argument.is_required else "optional"
            if argument.is_variadic:
                label = "variadic"
            default = f" default={argument.default}" if argument.default is not None else ""
            _safe_addstr(stdscr, row, content.x + 2, argument.name, _color(PAIR_ARGUMENT) | curses.A_BOLD)
            suffix = f"  {label}{default}"
            _safe_addstr(stdscr, row, content.x + 2 + len(argument.name), suffix[: max(0, content.width - 2)])
            row += 1
    else:
        row = _write_detail_line(stdscr, content, row, "  none")

    row += 1
    if row < content.y + content.height:
        _safe_addstr(stdscr, row, content.x, "Args:", _color(PAIR_ARGUMENT) | curses.A_BOLD)
        input_x = content.x + 6
        input_width = max(0, content.width - 7)
        _safe_addstr(stdscr, row, input_x, " " * input_width, _color(PAIR_INPUT))
        _safe_addstr(stdscr, row, input_x, state.input_text[-input_width:], _color(PAIR_INPUT))
    if state.input_error and row + 1 < content.y + content.height:
        _safe_addstr(stdscr, row + 1, content.x, state.input_error[: content.width], _color(PAIR_ERROR))
    elif row + 1 < content.y + content.height:
        _safe_addstr(
            stdscr,
            row + 1,
            content.x,
            "Enter runs  Esc cancels  Use shell quoting for values with spaces"[: content.width],
            _color(PAIR_MODAL),
        )


def _draw_help_modal(stdscr: curses.window, state: AppState, height: int, width: int) -> None:
    modal_width = min(78, max(50, width - 8))
    modal_height = min(18, max(12, height - 4))
    rect = Rect(
        y=max(1, (height - modal_height) // 2),
        x=max(0, (width - modal_width) // 2),
        height=modal_height,
        width=modal_width,
    )

    _draw_filled_box(stdscr, rect, "Keybindings")
    content = _inner(rect)
    options = _help_options(state)
    state.help_selected = min(state.help_selected, max(0, len(options) - 1))
    _write_help_options(stdscr, content, options, state.help_selected)


def _help_options(state: AppState) -> list[HelpOption]:
    recipe = _selected_recipe(state)
    options: list[HelpOption] = [
        HelpOption("j / down", "select next command", "select_down"),
        HelpOption("k / up", "select previous command", "select_up"),
        HelpOption("tab / e", "toggle the lower pane between log and .env", "toggle_env"),
        HelpOption("r", "reload commands from the current justfile level", "reload"),
        HelpOption("h / backspace", "go back to the parent command group", "back"),
        HelpOption("q", "quit lazypro", "quit"),
        HelpOption("? / esc", "close this help popup", "close"),
    ]

    if not recipe:
        return options

    if recipe.is_namespace:
        options.insert(0, HelpOption("enter / l", f"open {recipe.name} and list its commands", "activate"))
    else:
        options.insert(0, HelpOption("enter / l", f"run {_format_just_command([*state.path, recipe.name])}", "activate"))

    if recipe.description:
        options.append(HelpOption("selected", recipe.description, "close"))

    return options


def _write_help_options(
    stdscr: curses.window,
    rect: Rect,
    options: list[HelpOption],
    selected: int,
) -> None:
    if rect.height <= 0 or rect.width <= 0:
        return

    key_width = min(18, max((len(option.key) for option in options), default=0) + 2)
    for index, option in enumerate(options[: rect.height]):
        y = rect.y + index
        available = max(0, rect.width - key_width - 1)
        attr = _color(PAIR_MODAL_SELECTED) if index == selected else _color(PAIR_MODAL)
        key_attr = _color(PAIR_MODAL_SELECTED) if index == selected else _color(PAIR_KEY)
        _safe_addstr(stdscr, y, rect.x, " " * rect.width, attr)
        _safe_addstr(stdscr, y, rect.x, option.key.ljust(key_width)[:key_width], key_attr)
        _safe_addstr(
            stdscr,
            y,
            rect.x + key_width + 1,
            option.description[:available].ljust(available),
            attr,
        )


def _write_wrapped(
    stdscr: curses.window,
    rect: Rect,
    lines: list[str],
    *,
    from_bottom: bool = False,
) -> None:
    rendered: list[str] = []
    for line in lines:
        rendered.extend(textwrap.wrap(line, width=max(1, rect.width)) or [""])

    visible = rendered[-rect.height :] if from_bottom else rendered[: rect.height]
    for index, line in enumerate(visible):
        _safe_addstr(stdscr, rect.y + index, rect.x, line[: rect.width].ljust(rect.width))


def _write_env_lines(stdscr: curses.window, rect: Rect, lines: list[str]) -> None:
    for index, line in enumerate(lines[: rect.height]):
        y = rect.y + index
        _safe_addstr(stdscr, y, rect.x, " " * rect.width)
        assignment = _parse_env_assignment(line)
        if assignment is None:
            attr = _color(PAIR_DIM) if line.strip().startswith("#") else curses.A_NORMAL
            _safe_addstr(stdscr, y, rect.x, line[: rect.width], attr)
            continue

        prefix, name, value = assignment
        x = rect.x
        if prefix:
            _safe_addstr(stdscr, y, x, prefix[: rect.width])
            x += len(prefix)
        _safe_addstr(stdscr, y, x, name[: max(0, rect.width - (x - rect.x))], _color(PAIR_ENV_KEY) | curses.A_BOLD)
        x += len(name)
        if x < rect.x + rect.width:
            _safe_addstr(stdscr, y, x, "=")
            x += 1
        if x < rect.x + rect.width:
            _safe_addstr(stdscr, y, x, value[: max(0, rect.width - (x - rect.x))])


def _important_env_values(directory: Path) -> list[tuple[str, str]]:
    env_path = directory / ".env"
    if not env_path.is_file():
        return []

    try:
        lines = env_path.read_text().splitlines()
    except OSError:
        return []

    values: dict[str, str] = {}
    for line in lines:
        assignment = _parse_env_assignment(line)
        if assignment is None:
            continue
        _, name, value = assignment
        if name in IMPORTANT_ENV_KEYS and value:
            values[name] = value

    return [(name, values[name]) for name in IMPORTANT_ENV_KEYS if name in values]


def _parse_env_assignment(line: str) -> tuple[str, str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None

    leading_spaces = line[: len(line) - len(line.lstrip())]
    body = line.strip()
    export_prefix = ""
    if body.startswith("export "):
        export_prefix = "export "
        body = body[len("export ") :].lstrip()

    name, value = body.split("=", maxsplit=1)
    if not name or not all(char.isalnum() or char == "_" for char in name):
        return None

    return leading_spaces + export_prefix, name, value


def _draw_box(stdscr: curses.window, rect: Rect, title: str) -> None:
    if rect.height <= 1 or rect.width <= 1:
        return

    attr = _color(PAIR_BORDER)
    top = "+" + "-" * max(0, rect.width - 2) + "+"
    middle = "|" + " " * max(0, rect.width - 2) + "|"
    bottom = top

    _safe_addstr(stdscr, rect.y, rect.x, top[: rect.width], attr)
    for y in range(rect.y + 1, rect.y + rect.height - 1):
        _safe_addstr(stdscr, y, rect.x, middle[: rect.width], attr)
    _safe_addstr(stdscr, rect.y + rect.height - 1, rect.x, bottom[: rect.width], attr)

    label = f" {title} "
    _safe_addstr(stdscr, rect.y, rect.x + 2, label[: max(0, rect.width - 4)], _color(PAIR_KEY))


def _draw_filled_box(stdscr: curses.window, rect: Rect, title: str) -> None:
    if rect.height <= 1 or rect.width <= 1:
        return

    attr = _color(PAIR_MODAL)
    top = "+" + "-" * max(0, rect.width - 2) + "+"
    middle = "|" + " " * max(0, rect.width - 2) + "|"
    bottom = top

    _safe_addstr(stdscr, rect.y, rect.x, top[: rect.width], _color(PAIR_BORDER))
    for y in range(rect.y + 1, rect.y + rect.height - 1):
        _safe_addstr(stdscr, y, rect.x, middle[: rect.width], attr)
    _safe_addstr(stdscr, rect.y + rect.height - 1, rect.x, bottom[: rect.width], _color(PAIR_BORDER))

    label = f" {title} "
    _safe_addstr(stdscr, rect.y, rect.x + 2, label[: max(0, rect.width - 4)], _color(PAIR_KEY))


def _inner(rect: Rect) -> Rect:
    return Rect(
        y=rect.y + 1,
        x=rect.x + 1,
        height=max(0, rect.height - 2),
        width=max(0, rect.width - 2),
    )


def _selected_recipe(state: AppState) -> Recipe | None:
    if not state.recipes:
        return None
    return state.recipes[state.selected]


def _recipe_for_path(state: AppState, path: list[str]) -> Recipe | None:
    if not path or path[:-1] != state.path:
        return None
    name = path[-1]
    return next((recipe for recipe in state.recipes if recipe.name == name), None)


def _recipe_label(recipe: Recipe) -> str:
    if recipe.is_namespace:
        return f" > {recipe.name}/"
    return f"   {recipe.name}"


def _recipe_attr(recipe: Recipe, selected: bool) -> int:
    if selected:
        return _color(PAIR_SELECTED) | (curses.A_BOLD if recipe.is_namespace else curses.A_NORMAL)
    if recipe.is_namespace:
        return _color(PAIR_NAMESPACE) | curses.A_BOLD
    return curses.A_NORMAL


def _current_level_name(state: AppState) -> str:
    if state.path:
        return state.path[-1]
    return "root"


def _selected_command(state: AppState) -> str:
    recipe = _selected_recipe(state)
    if recipe is None:
        return "no command selected"
    return _format_just_command([*state.path, recipe.name])


def _format_just_command(path: list[str], args: list[str] | None = None) -> str:
    return join(["just", *path, *(args or [])])


def _path_key(path: list[str]) -> tuple[str, ...]:
    return tuple(path)


def _visible_start(selected: int, visible_count: int, total_count: int) -> int:
    if visible_count <= 0 or total_count <= visible_count:
        return 0
    half = visible_count // 2
    return min(max(0, selected - half), total_count - visible_count)


def _draw_too_small(stdscr: curses.window, height: int, width: int) -> None:
    message = "lazypro needs at least 50x11"
    y = max(0, height // 2)
    x = max(0, (width - len(message)) // 2)
    _safe_addstr(stdscr, y, x, message[:width], curses.A_REVERSE)


def _set_fast_escape() -> None:
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)


def _init_colors() -> None:
    curses.use_default_colors()
    if not curses.has_colors():
        return

    curses.init_pair(PAIR_NAMESPACE, curses.COLOR_CYAN, -1)
    curses.init_pair(PAIR_BORDER, curses.COLOR_CYAN, -1)
    curses.init_pair(PAIR_SELECTED, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_DIM, curses.COLOR_BLUE, -1)
    curses.init_pair(PAIR_FOOTER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(PAIR_KEY, curses.COLOR_YELLOW, -1)
    curses.init_pair(PAIR_ERROR, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(PAIR_MODAL, curses.COLOR_WHITE, -1)
    curses.init_pair(PAIR_MODAL_SELECTED, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_FOOTER_KEY, curses.COLOR_YELLOW, curses.COLOR_BLUE)
    curses.init_pair(PAIR_LOCATION, curses.COLOR_WHITE, -1)
    curses.init_pair(PAIR_LOCATION_ACTIVE, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_ARGUMENT, curses.COLOR_MAGENTA, -1)
    curses.init_pair(PAIR_INPUT, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(PAIR_ENV_KEY, curses.COLOR_GREEN, -1)


def _color(pair: int) -> int:
    if not curses.has_colors():
        return (
            curses.A_REVERSE
            if pair
            in {
                PAIR_SELECTED,
                PAIR_FOOTER,
                PAIR_MODAL_SELECTED,
                PAIR_LOCATION_ACTIVE,
                PAIR_INPUT,
            }
            else curses.A_NORMAL
        )
    return curses.color_pair(pair)


def _safe_addstr(
    stdscr: curses.window,
    y: int,
    x: int,
    value: str,
    attr: int = curses.A_NORMAL,
) -> None:
    try:
        stdscr.addstr(y, x, value, attr)
    except curses.error:
        pass
