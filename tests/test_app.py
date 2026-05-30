from pathlib import Path

from lib.app import (
    AppState,
    _go_back,
    _help_options,
    _important_env_values,
    _parse_env_assignment,
    _recipe_for_path,
    _toggle_lower_view,
)
from lib.justfile import Recipe, RecipeArgument


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

    assert options[0].key == "enter / l"
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

    assert options[0].key == "enter / l"
    assert options[0].description == "run just projects test"
    assert options[0].action == "activate"


def test_toggle_lower_view_switches_between_log_and_env() -> None:
    state = AppState(cwd=Path("/repo"))

    _toggle_lower_view(state)
    assert state.lower_view == "env"

    _toggle_lower_view(state)
    assert state.lower_view == "log"


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


def test_go_back_pops_current_path_level(tmp_path) -> None:
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "justfile").write_text("default:\n    @just --list\n")
    state = AppState(cwd=tmp_path, path=["projects", "admin"])

    _go_back(state)

    assert state.path == ["projects"]


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
