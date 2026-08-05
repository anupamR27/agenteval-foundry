from pathlib import Path

import pytest

from evaluation.taxonomy.catalog import FailureTaxonomyCatalog, TaxonomyCatalogError


def test_default_taxonomy_loads_and_resolves_known_path() -> None:
    catalog = FailureTaxonomyCatalog.load()
    path = catalog.resolve("EXECUTION", "API_TOOL_FAILURE", "TIMEOUT")
    assert catalog.version == "1.0.0"
    assert path.identifiers == ("EXECUTION", "API_TOOL_FAILURE", "TIMEOUT")
    assert path.taxonomy_version == catalog.version


def test_invalid_path_fails_clearly() -> None:
    with pytest.raises(TaxonomyCatalogError, match="Unknown taxonomy path"):
        FailureTaxonomyCatalog.load().resolve("NO", "SUCH", "PATH")


def test_duplicate_identifiers_are_rejected(tmp_path: Path) -> None:
    taxonomy = tmp_path / "duplicate.yaml"
    taxonomy.write_text(
        """
name: duplicate
version: "1"
description: duplicate test
categories:
  - identifier: ROOT
    description: root
    categories:
      - identifier: CHILD
        description: child
        categories:
          - identifier: LEAF
            description: first
          - identifier: LEAF
            description: second
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(TaxonomyCatalogError, match="Duplicate Level 3"):
        FailureTaxonomyCatalog.load(taxonomy)


def test_valid_path_order_is_deterministic() -> None:
    catalog = FailureTaxonomyCatalog.load()
    first = [path.identifiers for path in catalog.list_paths()]
    second = [path.identifiers for path in catalog.list_paths()]
    assert first == second
    assert first[0] == ("PLANNING", "MISSING_STEP", "TOOL_OMISSION")
