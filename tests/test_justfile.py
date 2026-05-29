from lib.justfile import list_recipes, parse_just_list


def test_parse_just_list_marks_variadic_recipes_as_namespaces() -> None:
    output = """
Available recipes:
    default
    codex
    projects *args # Projects
    lab *arg       # Lab workspace
"""

    recipes = parse_just_list(output)

    assert [recipe.name for recipe in recipes] == ["default", "codex", "projects", "lab"]
    assert recipes[0].is_namespace is False
    assert recipes[2].is_variadic is True
    assert recipes[2].is_namespace is True
    assert recipes[2].description == "Projects"


def test_parse_just_list_ignores_non_recipe_lines() -> None:
    output = """
Available recipes:
    [private]
    alias b := build
    build # Build project
"""

    recipes = parse_just_list(output)

    assert len(recipes) == 1
    assert recipes[0].name == "build"
    assert recipes[0].description == "Build project"


def test_list_recipes_only_marks_variadic_delegates_as_namespaces(tmp_path) -> None:
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "justfile").write_text(
        """
default:
    @just --list

project_1:
    @echo project_1
""".strip()
    )
    (tmp_path / "justfile").write_text(
        """
set positional-arguments := true

default:
    @just --list

uv *args:
    @echo uv "$@"

projects *args:
    @cd projects && just "$@"
""".strip()
    )

    recipes = {recipe.name: recipe for recipe in list_recipes(tmp_path)}

    assert recipes["uv"].is_variadic is True
    assert recipes["uv"].is_namespace is False
    assert recipes["projects"].is_variadic is True
    assert recipes["projects"].is_namespace is True
