from pathlib import Path

from lib.app import AppState, _help_options
from lib.justfile import Recipe


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
