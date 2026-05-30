from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from shlex import split


@dataclass(frozen=True)
class RecipeArgument:
    name: str
    token: str
    default: str | None
    is_required: bool
    is_variadic: bool


@dataclass(frozen=True)
class Recipe:
    name: str
    signature: str
    description: str
    is_variadic: bool
    is_namespace: bool
    arguments: tuple[RecipeArgument, ...] = ()
    working_dir: Path | None = None


def list_recipes(cwd: Path, path: list[str] | None = None) -> list[Recipe]:
    just_path = path or []
    level_dir, resolved = current_level_dir(cwd, just_path)
    command = ["just", "--list"] if resolved else ["just", *just_path, "--list"]
    result = subprocess.run(
        command,
        cwd=level_dir if resolved else cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())

    recipes = parse_just_list(result.stdout)
    delegations = parse_working_directories(level_dir)
    return [_with_namespace_status(cwd, just_path, level_dir, delegations, recipe) for recipe in recipes]


def run_recipe(cwd: Path, path: list[str], args: list[str] | None = None) -> int:
    result = subprocess.run(
        ["just", *path, *(args or [])],
        cwd=cwd,
        check=False,
    )
    return result.returncode


def parse_just_list(output: str) -> list[Recipe]:
    recipes: list[Recipe] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Available recipes"):
            continue
        if line.startswith("[") or line.startswith("alias "):
            continue

        signature, description = _split_description(line)
        parts = signature.split()
        if not parts:
            continue

        name = parts[0]
        if not _is_recipe_name(name):
            continue

        arguments = tuple(_parse_argument(part) for part in parts[1:])
        is_variadic = any(argument.is_variadic for argument in arguments)
        recipes.append(
            Recipe(
                name=name,
                signature=signature,
                description=description,
                is_variadic=is_variadic,
                is_namespace=is_variadic,
                arguments=arguments,
            )
        )

    return recipes


def _split_description(line: str) -> tuple[str, str]:
    if " # " not in line:
        return line.strip(), ""

    signature, description = line.split(" # ", maxsplit=1)
    return signature.strip(), description.strip()


def _is_recipe_name(value: str) -> bool:
    return all(char.isalnum() or char in "_-" for char in value)


def _parse_argument(token: str) -> RecipeArgument:
    is_variadic = token.startswith(("*", "+"))
    clean = token.removeprefix("*").removeprefix("+").removeprefix("$")
    name, separator, default = clean.partition("=")
    return RecipeArgument(
        name=name,
        token=token,
        default=_parse_default(default) if separator else None,
        is_required=not separator and not is_variadic,
        is_variadic=is_variadic,
    )


def _parse_default(value: str) -> str:
    try:
        parsed = split(value)
    except ValueError:
        return value
    if not parsed:
        return value
    return parsed[0]


def current_level_dir(cwd: Path, path: list[str]) -> tuple[Path, bool]:
    level_dir = cwd
    for part in path:
        delegations = parse_working_directories(level_dir)
        next_dir = delegations.get(part)
        if next_dir is None:
            guessed_dir = level_dir / part
            if _has_justfile(guessed_dir):
                level_dir = guessed_dir
                continue
            return level_dir, False
        level_dir = next_dir
    return level_dir, True


def parse_working_directories(justfile_dir: Path) -> dict[str, Path]:
    justfile_path = _find_justfile(justfile_dir)
    if justfile_path is None:
        return {}

    pending_working_dir: Path | None = None
    delegations: dict[str, Path] = {}
    try:
        justfile_text = justfile_path.read_text()
    except OSError:
        return {}

    for raw_line in justfile_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            working_dir = _parse_working_directory(line, justfile_dir)
            if working_dir is not None:
                pending_working_dir = working_dir
            continue

        if line.endswith(":"):
            name = _parse_recipe_header(line)
            if name and pending_working_dir is not None:
                delegations[name] = pending_working_dir
            pending_working_dir = None

    return delegations


def _with_namespace_status(
    _cwd: Path,
    _current_path: list[str],
    level_dir: Path,
    delegations: dict[str, Path],
    recipe: Recipe,
) -> Recipe:
    if not recipe.is_variadic:
        return recipe

    working_dir = delegations.get(recipe.name)
    if working_dir is not None:
        return replace(recipe, is_namespace=_has_justfile(working_dir), working_dir=working_dir)

    guessed_dir = level_dir / recipe.name
    if _has_justfile(guessed_dir):
        return replace(recipe, is_namespace=True, working_dir=guessed_dir)

    return replace(recipe, is_namespace=False)


def _parse_working_directory(attribute: str, justfile_dir: Path) -> Path | None:
    if "working-directory" not in attribute:
        return None

    if "(" in attribute and ")" in attribute:
        value = attribute.split("(", maxsplit=1)[1].rsplit(")", maxsplit=1)[0]
    elif ":" in attribute:
        value = attribute.split(":", maxsplit=1)[1].rstrip("]")
    else:
        return None

    try:
        parts = split(value.strip())
    except ValueError:
        return None
    if not parts:
        return None
    return (justfile_dir / parts[0]).resolve()


def _parse_recipe_header(line: str) -> str | None:
    header = line.removesuffix(":").strip()
    if not header:
        return None
    first = header.split()[0].removeprefix("@")
    return first if _is_recipe_name(first) else None


def _find_justfile(directory: Path) -> Path | None:
    for name in ("justfile", "Justfile", ".justfile"):
        path = directory / name
        if path.is_file():
            return path
    return None


def _has_justfile(directory: Path) -> bool:
    return _find_justfile(directory) is not None
