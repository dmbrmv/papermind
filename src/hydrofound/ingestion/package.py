"""Package ingestion — griffe API extraction + markdown rendering."""

from __future__ import annotations

from dataclasses import dataclass, field

import griffe
from jinja2 import Template


@dataclass
class ModuleAPI:
    """Extracted API for one module."""

    name: str
    docstring: str = ""
    functions: list[dict] = field(default_factory=list)  # {name, signature, docstring}
    classes: list[dict] = field(default_factory=list)  # {name, docstring, methods}


@dataclass
class PackageAPI:
    """Extracted API for a whole package."""

    modules: list[ModuleAPI] = field(default_factory=list)


def _extract_module(member: object) -> ModuleAPI:
    """Extract API from a single griffe Module object.

    Args:
        member: A griffe Module object.

    Returns:
        Populated ModuleAPI dataclass.
    """
    mod = ModuleAPI(
        name=member.path,  # type: ignore[attr-defined]
        docstring=member.docstring.value if member.docstring else "",  # type: ignore[attr-defined]
    )
    sub_members: dict = getattr(member, "members", {})
    for sub_name, sub_member in sub_members.items():
        kind = getattr(sub_member, "kind", None)
        if kind is None:
            continue
        kind_name: str = kind.name
        if kind_name == "FUNCTION":
            params = ", ".join(p.name for p in getattr(sub_member, "parameters", []))
            mod.functions.append(
                {
                    "name": sub_name,
                    "signature": f"{sub_name}({params})",
                    "docstring": (
                        sub_member.docstring.value if sub_member.docstring else ""
                    ),
                }
            )
        elif kind_name == "CLASS":
            methods = [
                method_name
                for method_name, method in getattr(sub_member, "members", {}).items()
                if getattr(getattr(method, "kind", None), "name", "") == "FUNCTION"
            ]
            mod.classes.append(
                {
                    "name": sub_name,
                    "docstring": (
                        sub_member.docstring.value if sub_member.docstring else ""
                    ),
                    "methods": methods,
                }
            )
    return mod


def extract_api(package_name: str) -> PackageAPI:
    """Extract API structure from an installed Python package.

    Loads the package with griffe (static analysis), then walks all
    top-level module members to collect functions, classes, and
    docstrings.

    Args:
        package_name: Import name of the installed package (e.g. "hydrofound").

    Returns:
        PackageAPI containing one ModuleAPI per top-level module member.

    Raises:
        griffe.LoadingError: If the package cannot be found or loaded.
    """
    pkg = griffe.load(package_name)
    result = PackageAPI()

    for member in pkg.members.values():
        kind = getattr(member, "kind", None)
        if kind is None:
            continue
        # Only recurse into modules; skip aliases, attributes, etc.
        if kind.name == "MODULE":
            result.modules.append(_extract_module(member))

    return result


_API_TEMPLATE_SRC = """\
# {{ package_name }} API Reference

{% for mod in api.modules %}
## {{ mod.name }}

{% if mod.docstring %}{{ mod.docstring }}

{% endif %}
{% for func in mod.functions %}
### `{{ func.signature }}`

{% if func.docstring %}{{ func.docstring }}

{% endif %}
{% endfor %}
{% for cls in mod.classes %}
### class `{{ cls.name }}`

{% if cls.docstring %}{{ cls.docstring }}

{% endif %}
{% if cls.methods %}**Methods:** {{ cls.methods | join(', ') }}

{% endif %}
{% endfor %}
{% endfor %}
"""

API_TEMPLATE = Template(_API_TEMPLATE_SRC)


def render_api_markdown(api: PackageAPI, package_name: str) -> str:
    """Render PackageAPI into a markdown string.

    Args:
        api: Extracted package API structure.
        package_name: Package name used as the document title.

    Returns:
        Rendered markdown string.
    """
    return API_TEMPLATE.render(api=api, package_name=package_name)
