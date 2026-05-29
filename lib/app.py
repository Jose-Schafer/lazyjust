from __future__ import annotations

import curses
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from lib.justfile import Recipe, list_recipes, run_recipe


PAIR_HEADER = 1
PAIR_BORDER = 2
PAIR_SELECTED = 3
PAIR_DIM = 4
PAIR_FOOTER = 5
PAIR_KEY = 6
PAIR_ERROR = 7
PAIR_MODAL = 8
PAIR_MODAL_SELECTED = 9
PAIR_FOOTER_KEY = 10


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

        if state.show_help:
            if _handle_help_key(state, key):
                return 0
            continue

        if key == ord("?"):
            state.show_help = True
            state.help_selected = 0
            continue
        if key in (ord("q"), 27):
            return 0
        if key in (curses.KEY_UP, ord("k")):
            state.selected = max(0, state.selected - 1)
            continue
        if key in (curses.KEY_DOWN, ord("j")):
            state.selected = min(max(0, len(state.recipes) - 1), state.selected + 1)
            continue
        if key in (curses.KEY_BACKSPACE, 127, 8, ord("h")):
            if state.path:
                state.path.pop()
                _reload(state)
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
    if action == "back":
        if state.path:
            state.path.pop()
            _reload(state)
        return False
    if action == "quit":
        return True
    if action == "close":
        return False

    return False


def _reload(state: AppState) -> None:
    try:
        state.recipes = list_recipes(state.cwd, state.path)
        state.selected = min(state.selected, max(0, len(state.recipes) - 1))
        state.message = ""
    except RuntimeError as exc:
        state.recipes = []
        state.selected = 0
        state.message = str(exc)


def _activate(state: AppState) -> None:
    if not state.recipes:
        return

    recipe = state.recipes[state.selected]
    next_path = [*state.path, recipe.name]

    if recipe.is_namespace:
        state.path = next_path
        state.selected = 0
        _reload(state)
        return

    returncode = _run_interactive(state, next_path)
    command = f"just {' '.join(next_path)}"
    state.output = f"Last command: {command}\nExit code: {returncode}"
    state.message = f"exit {returncode}: {command}"


def _run_interactive(state: AppState, path: list[str]) -> int:
    curses.def_prog_mode()
    curses.endwin()

    command = f"just {' '.join(path)}"
    print(f"\n[lazypro] running {command}\n")
    try:
        returncode = run_recipe(state.cwd, path)
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

    if height < 10 or width < 50:
        _draw_too_small(stdscr, height, width)
        stdscr.refresh()
        return

    header = Rect(y=0, x=0, height=1, width=width)
    body_height = height - 2
    left_width = max(32, min(48, width // 3))
    left = Rect(y=1, x=0, height=body_height, width=left_width)
    right_width = width - left_width
    details_height = max(9, min(12, body_height // 2))
    details = Rect(y=1, x=left_width, height=details_height, width=right_width)
    output = Rect(
        y=1 + details_height,
        x=left_width,
        height=body_height - details_height,
        width=right_width,
    )
    footer = Rect(y=height - 1, x=0, height=1, width=width)

    _draw_header(stdscr, state, header)
    _draw_recipes(stdscr, state, left)
    _draw_details(stdscr, state, details)
    _draw_output(stdscr, state, output)
    _draw_footer(stdscr, state, footer)
    if state.show_help:
        _draw_help_modal(stdscr, state, height, width)
    stdscr.refresh()


def _draw_header(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    crumb = " / ".join(["root", *state.path])
    selected = _selected_recipe(state)
    command = f"just {' '.join([*state.path, selected.name])}" if selected else "no command"
    title = f" lazypro | {crumb} | {command} "
    _safe_addstr(stdscr, rect.y, rect.x, title[: rect.width].ljust(rect.width), _color(PAIR_HEADER))


def _draw_recipes(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    _draw_box(stdscr, rect, "Commands")
    content = _inner(rect)
    list_height = max(0, content.height)
    start = _visible_start(state.selected, list_height, len(state.recipes))

    for row, recipe in enumerate(state.recipes[start : start + list_height], start=content.y):
        recipe_index = start + row - content.y
        marker = ">" if recipe.is_namespace else " "
        label = f" {marker} {recipe.name}"
        attr = _color(PAIR_SELECTED) if recipe_index == state.selected else curses.A_NORMAL
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
    command = f"just {' '.join(command_path)}"
    recipe_type = "namespace" if recipe.is_namespace else "command"
    lines = [
        f"Name: {recipe.name}",
        f"Type: {recipe_type}",
        f"Command: {command}",
        f"Signature: {recipe.signature}",
    ]
    if recipe.description:
        lines.append(f"Description: {recipe.description}")
    lines.append(f"Root: {state.cwd}")
    _write_wrapped(stdscr, content, lines)


def _draw_output(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    _draw_box(stdscr, rect, "Log")
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


def _draw_footer(stdscr: curses.window, state: AppState, rect: Rect) -> None:
    segments = [
        ("j/k", "move"),
        ("enter", "open/run"),
        ("h", "back"),
        ("?", "help"),
        ("r", "reload"),
        ("q", "quit"),
    ]

    message = state.message or str(state.cwd)
    if state.path:
        message = f"{message} | {' / '.join(state.path)}"

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
        options.insert(
            0,
            HelpOption("enter / l", f"run just {' '.join([*state.path, recipe.name])}", "activate"),
        )

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


def _visible_start(selected: int, visible_count: int, total_count: int) -> int:
    if visible_count <= 0 or total_count <= visible_count:
        return 0
    half = visible_count // 2
    return min(max(0, selected - half), total_count - visible_count)


def _draw_too_small(stdscr: curses.window, height: int, width: int) -> None:
    message = "lazypro needs at least 50x10"
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

    curses.init_pair(PAIR_HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(PAIR_BORDER, curses.COLOR_CYAN, -1)
    curses.init_pair(PAIR_SELECTED, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_DIM, curses.COLOR_BLUE, -1)
    curses.init_pair(PAIR_FOOTER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(PAIR_KEY, curses.COLOR_YELLOW, -1)
    curses.init_pair(PAIR_ERROR, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(PAIR_MODAL, curses.COLOR_WHITE, -1)
    curses.init_pair(PAIR_MODAL_SELECTED, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_FOOTER_KEY, curses.COLOR_YELLOW, curses.COLOR_BLUE)


def _color(pair: int) -> int:
    if not curses.has_colors():
        return (
            curses.A_REVERSE
            if pair in {PAIR_HEADER, PAIR_SELECTED, PAIR_FOOTER, PAIR_MODAL_SELECTED}
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
