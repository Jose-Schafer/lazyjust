from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Recipe:
    name: str
    signature: str
    description: str
    is_variadic: bool
    is_namespace: bool


def list_recipes(cwd: Path, path: list[str] | None = None) -> list[Recipe]:
    just_path = path or []
    command = ["just", *just_path, "--list"]
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())

    recipes = parse_just_list(result.stdout)
    return [_with_namespace_status(cwd, just_path, recipe) for recipe in recipes]


def run_recipe(cwd: Path, path: list[str]) -> int:
    result = subprocess.run(
        ["just", *path],
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

        is_variadic = any(part.startswith("*") for part in parts[1:])
        recipes.append(
            Recipe(
                name=name,
                signature=signature,
                description=description,
                is_variadic=is_variadic,
                is_namespace=is_variadic,
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


def _with_namespace_status(cwd: Path, current_path: list[str], recipe: Recipe) -> Recipe:
    if not recipe.is_variadic:
        return recipe

    next_path = [*current_path, recipe.name]
    result = subprocess.run(
        ["just", *next_path, "--list"],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    is_namespace = result.returncode == 0 and "Available recipes:" in result.stdout
    return replace(recipe, is_namespace=is_namespace)
