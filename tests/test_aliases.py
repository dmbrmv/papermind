"""Tests for search alias expansion."""

from __future__ import annotations

from papermind.query.fallback import _expand_aliases, _load_aliases


class TestLoadAliases:
    """Loading aliases from YAML file."""

    def test_loads_dict(self) -> None:
        aliases = _load_aliases()
        assert isinstance(aliases, dict)
        assert len(aliases) > 0

    def test_groundwater_alias_exists(self) -> None:
        aliases = _load_aliases()
        assert "groundwater" in aliases
        assert "baseflow" in aliases["groundwater"]

    def test_calibration_alias_exists(self) -> None:
        aliases = _load_aliases()
        assert "calibration" in aliases


class TestExpandAliases:
    """Query expansion using aliases."""

    def test_expands_key(self) -> None:
        expanded = _expand_aliases(["groundwater"])
        assert "baseflow" in expanded
        assert "aquifer" in expanded
        assert "recharge" in expanded

    def test_expands_value(self) -> None:
        """Searching for an alias value should also expand."""
        expanded = _expand_aliases(["baseflow"])
        assert "groundwater" in expanded

    def test_no_expansion_for_unknown(self) -> None:
        expanded = _expand_aliases(["xyzzy"])
        assert expanded == ["xyzzy"]

    def test_preserves_original(self) -> None:
        expanded = _expand_aliases(["groundwater"])
        assert "groundwater" in expanded

    def test_deduplicates(self) -> None:
        expanded = _expand_aliases(["groundwater", "baseflow"])
        # Both map to the same cluster — should not have duplicates
        assert len(expanded) == len(set(expanded))
