"""Register Typer commands whose option schema is a request dataclass.

Typer derives a command's options from its callback signature (``inspect.signature``
plus ``typing.get_type_hints``). Declaring a dozen options as function parameters is
exactly what CodeScene's *Excess Number of Function Arguments* rule flags, so the
commands in this package declare their options ONCE, as fields of a frozen request
dataclass (``field(default=..., metadata=option(typer.Option(...)))``). This module
turns such a dataclass into a real Typer command: the generated callback takes only
``**values``, builds the request, and hands it to a single-argument runner. Help text,
``[default: ...]``/``[required]`` markers, ``--flag/--no-flag`` toggles and repeated
options all render exactly as a hand-written Typer signature would, because Typer reads
the signature this module attaches to the callback.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import MISSING, Field, fields
from typing import Annotated, Any, get_type_hints

import typer

OPTION_METADATA_KEY = "option"


def option(info: Any) -> dict[str, Any]:
    """Field metadata attaching a ``typer.Option(...)`` to a request-dataclass field."""
    return {OPTION_METADATA_KEY: info}


def register_request_command(
    app: typer.Typer,
    name: str,
    request_cls: type[Any],
    run: Callable[[Any], None],
) -> None:
    """Register ``name`` on ``app``: one CLI option per field of ``request_cls``.

    ``run`` receives the constructed request; its docstring becomes the command help.
    """
    hints = get_type_hints(request_cls)
    parameters = [_parameter(field, hints[field.name]) for field in fields(request_cls)]

    def callback(**values: Any) -> None:
        run(request_cls(**values))

    entry: Any = callback
    entry.__signature__ = inspect.Signature(parameters, return_annotation=None)
    entry.__annotations__ = {p.name: p.annotation for p in parameters} | {"return": None}
    entry.__name__ = name.replace("-", "_")
    entry.__qualname__ = entry.__name__
    entry.__doc__ = run.__doc__
    app.command(name=name)(entry)


def _parameter(field: Field[Any], hint: Any) -> inspect.Parameter:
    info = field.metadata.get(OPTION_METADATA_KEY)
    if info is None:
        raise TypeError(f"request field {field.name!r} has no typer option metadata")
    default = inspect.Parameter.empty if field.default is MISSING else field.default
    return inspect.Parameter(
        field.name,
        inspect.Parameter.KEYWORD_ONLY,
        default=default,
        annotation=Annotated[hint, info],
    )
