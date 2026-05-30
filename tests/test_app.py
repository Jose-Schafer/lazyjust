from pathlib import Path

from lib.app import (
    AppState,
    _activate,
    _current_justfile,
    _go_back,
    _help_options,
    _important_env_values,
    _context_warnings,
    _move_focus,
    _open_namespace,
    _parse_env_assignment,
    _recipe_for_path,
    _search_result_label,
    _selected_command_path,
    _toggle_lower_view,
)
from lib.justfile import Recipe, RecipeArgument, RecipeSearchResult


def test_help_options_show_open_hint_for_namespace() -> None:
    state = AppState(
        cwd=Path("/repo"),
        recipes=[
            Recipe(
                name="projects",
                signature="projects *args",
                description="Project commands",
                is_variadic=True,
                is_namespace=True,
            )
        ],
    )

    options = _help_options(state)

    assert options[0].key == "enter/l"
    assert options[0].description == "open projects and list its commands"
    assert options[0].action == "activate"
    assert any(option.key == "selected" and option.description == "Project commands" for option in options)


def test_help_options_show_run_hint_for_command() -> None:
    state = AppState(
        cwd=Path("/repo"),
        path=["projects"],
        recipes=[
            Recipe(
                name="test",
                signature="test",
                description="Run tests",
                is_variadic=False,
                is_namespace=False,
            )
        ],
    )

    options = _help_options(state)

    assert options[0].key == "enter"
    assert options[0].description == "run just projects test"
    assert options[0].action == "activate"


def test_toggle_lower_view_switches_between_log_and_env() -> None:
    state = AppState(cwd=Path("/repo"))

    assert state.lower_view == "env"


def test_move_focus_cycles_between_panes() -> None:
    state = AppState(cwd=Path("/repo"))

    _move_focus(state, 1)
    assert state.focused_pane == "command"

    _move_focus(state, 1)
    assert state.focused_pane == "lower"

    _move_focus(state, 1)
    assert state.focused_pane == "commands"

    _move_focus(state, -1)
    assert state.focused_pane == "lower"


def test_current_justfile_resolves_current_level(tmp_path) -> None:
    (tmp_path / "projects").mkdir()
    (tmp_path / "justfile").write_text(
        """
[working-directory('projects')]
@projects *args:
    just "$@"
""".strip()
    )
    project_justfile = tmp_path / "projects" / "justfile"
    project_justfile.write_text("run:\n    echo run\n")
    state = AppState(cwd=tmp_path, path=["projects"])

    assert _current_justfile(state) == project_justfile

    _toggle_lower_view(state)
    assert state.lower_view == "log"

    _toggle_lower_view(state)
    assert state.lower_view == "env"


def test_recipe_for_path_returns_current_pending_recipe() -> None:
    recipe = Recipe(
        name="set-client",
        signature='set-client client env=""',
        description="",
        is_variadic=False,
        is_namespace=False,
        arguments=(
            RecipeArgument("client", "client", None, True, False),
            RecipeArgument("env", 'env=""', "", False, False),
        ),
    )
    state = AppState(cwd=Path("/repo"), path=["projects"], recipes=[recipe])

    assert _recipe_for_path(state, ["projects", "set-client"]) == recipe


def test_recipe_for_path_returns_pending_search_recipe() -> None:
    recipe = Recipe(
        name="set-client",
        signature="set-client client",
        description="",
        is_variadic=False,
        is_namespace=False,
        arguments=(RecipeArgument("client", "client", None, True, False),),
    )
    state = AppState(
        cwd=Path("/repo"),
        path=["projects"],
        pending_path=["agent", "set-client"],
        pending_recipe=recipe,
    )

    assert _recipe_for_path(state, ["agent", "set-client"]) == recipe


def test_search_result_selection_uses_full_command_path() -> None:
    recipe = Recipe("aws_login", "aws_login", "", False, False)
    state = AppState(
        cwd=Path("/repo"),
        search_query="aws",
        search_results=[
            RecipeSearchResult(
                path=("projects", "admin", "aws_login"),
                context=("projects", "admin"),
                directory=Path("/repo/projects/admin"),
                recipe=recipe,
            )
        ],
    )

    assert _selected_command_path(state) == ["projects", "admin", "aws_login"]
    assert _search_result_label(state.search_results[0]) == "   aws_login  @ root / projects / admin"


def test_go_back_pops_current_path_level(tmp_path) -> None:
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "justfile").write_text("default:\n    @just --list\n")
    state = AppState(cwd=tmp_path, path=["projects", "admin"])

    _go_back(state)

    assert state.path == ["projects"]


def test_go_back_restores_selection_from_parent_level(tmp_path) -> None:
    (tmp_path / "admin").mkdir()
    (tmp_path / "admin" / "justfile").write_text("deploy:\n    echo deploy\n")
    (tmp_path / "justfile").write_text(
        """
default:
    @just --list

bootstrap:
    echo bootstrap

admin *args:
    just "$@"
""".strip()
    )
    recipes = [
        Recipe("bootstrap", "bootstrap", "", False, False),
        Recipe("admin", "admin *args", "", True, True),
    ]
    state = AppState(cwd=tmp_path, recipes=recipes, selected=1)

    _activate(state)
    _go_back(state)

    assert state.path == []
    assert state.selected == 1


def test_open_namespace_ignores_regular_commands() -> None:
    state = AppState(
        cwd=Path("/repo"),
        recipes=[
            Recipe("run", "run", "", False, False),
        ],
    )

    _open_namespace(state)

    assert state.path == []


def test_parse_env_assignment_handles_export_and_spacing() -> None:
    assert _parse_env_assignment("export AWS_PROFILE=dev") == ("export ", "AWS_PROFILE", "dev")
    assert _parse_env_assignment("  AWS_REGION=us-east-1") == ("  ", "AWS_REGION", "us-east-1")
    assert _parse_env_assignment("# AWS_PROFILE=dev") is None


def test_important_env_values_extracts_priority_keys(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        """
IGNORED=value
AWS_PROFILE=dev-retail-agent-admin
AWS_REGION=us-east-1
""".strip()
    )

    assert _important_env_values(tmp_path) == [
        ("AWS_PROFILE", "dev-retail-agent-admin"),
        ("AWS_REGION", "us-east-1"),
    ]


def test_context_warnings_reports_missing_dotenv_load(tmp_path) -> None:
    (tmp_path / "justfile").write_text("run:\n    echo run\n")

    assert _context_warnings(tmp_path) == ["! justfile missing: set dotenv-load := true"]
