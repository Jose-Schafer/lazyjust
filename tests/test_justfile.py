from lib.justfile import current_level_dir, list_recipes, parse_just_list, parse_working_directories


def test_parse_just_list_marks_variadic_recipes_as_namespaces() -> None:
    output = """
Available recipes:
    default
    codex
    projects *args # Projects
    lab *arg       # Lab workspace
"""

    recipes = parse_just_list(output)

    assert [recipe.name for recipe in recipes] == ["codex", "projects", "lab"]
    assert recipes[0].is_namespace is False
    assert recipes[1].is_variadic is True
    assert recipes[1].is_namespace is True
    assert recipes[1].description == "Projects"


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


def test_parse_just_list_extracts_recipe_arguments() -> None:
    output = """
Available recipes:
    set-client client env=""
    run-many *args
"""

    recipes = {recipe.name: recipe for recipe in parse_just_list(output)}

    set_client_args = recipes["set-client"].arguments
    assert [argument.name for argument in set_client_args] == ["client", "env"]
    assert set_client_args[0].is_required is True
    assert set_client_args[0].default is None
    assert set_client_args[1].is_required is False
    assert set_client_args[1].default == ""
    assert set_client_args[1].token == 'env=""'

    run_many_args = recipes["run-many"].arguments
    assert run_many_args[0].name == "args"
    assert run_many_args[0].is_variadic is True


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


def test_parse_working_directories_supports_common_just_attribute_forms(tmp_path) -> None:
    (tmp_path / "projects").mkdir()
    (tmp_path / "lab").mkdir()
    (tmp_path / "justfile").write_text(
        """
[working-directory('projects')]
@projects *args:
    just "$@"

[private]
[working-directory: 'lab']
@lab *args:
    just {{ args }}
""".strip()
    )

    delegations = parse_working_directories(tmp_path)

    assert delegations["projects"] == (tmp_path / "projects").resolve()
    assert delegations["lab"] == (tmp_path / "lab").resolve()


def test_current_level_dir_resolves_nested_working_directory_delegations(tmp_path) -> None:
    (tmp_path / "projects" / "project_1").mkdir(parents=True)
    (tmp_path / "justfile").write_text(
        """
[working-directory('projects')]
@projects *args:
    just "$@"
""".strip()
    )
    (tmp_path / "projects" / "justfile").write_text(
        """
[working-directory('project_1')]
@project_1 *args:
    just "$@"
""".strip()
    )
    (tmp_path / "projects" / "project_1" / "justfile").write_text("run:\n    echo run\n")

    level_dir, resolved = current_level_dir(tmp_path, ["projects", "project_1"])

    assert resolved is True
    assert level_dir == (tmp_path / "projects" / "project_1").resolve()
