from pathlib import Path

import yaml
from pydantic import ValidationError

from evaluation.taxonomy.models import FailureTaxonomyDefinition, FailureTaxonomyPath

DEFAULT_TAXONOMY_PATH = Path(__file__).with_name("taxonomy.yaml")


class TaxonomyCatalogError(ValueError):
    pass


class FailureTaxonomyCatalog:
    def __init__(self, definition: FailureTaxonomyDefinition) -> None:
        self._definition = definition.model_copy(deep=True)
        self._paths = self._build_paths(self._definition)

    @classmethod
    def load(cls, path: Path = DEFAULT_TAXONOMY_PATH) -> "FailureTaxonomyCatalog":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            definition = FailureTaxonomyDefinition.model_validate(raw)
            return cls(definition)
        except OSError as exc:
            raise TaxonomyCatalogError(f"Could not read taxonomy file {path}: {exc}") from exc
        except (yaml.YAMLError, ValidationError, TypeError) as exc:
            raise TaxonomyCatalogError(f"Invalid taxonomy file {path}: {exc}") from exc

    @property
    def version(self) -> str:
        return self._definition.version

    @property
    def name(self) -> str:
        return self._definition.name

    def resolve(self, level1: str, level2: str, level3: str) -> FailureTaxonomyPath:
        key = (level1, level2, level3)
        try:
            return self._paths[key].model_copy(deep=True)
        except KeyError as exc:
            raise TaxonomyCatalogError(f"Unknown taxonomy path: {' / '.join(key)}") from exc

    def list_paths(self) -> list[FailureTaxonomyPath]:
        return [path.model_copy(deep=True) for path in self._paths.values()]

    @staticmethod
    def _build_paths(
        definition: FailureTaxonomyDefinition,
    ) -> dict[tuple[str, str, str], FailureTaxonomyPath]:
        paths: dict[tuple[str, str, str], FailureTaxonomyPath] = {}
        seen_level1: set[str] = set()
        for level1 in definition.categories:
            if level1.identifier in seen_level1:
                raise TaxonomyCatalogError(f"Duplicate Level 1 identifier: {level1.identifier}")
            seen_level1.add(level1.identifier)
            seen_level2: set[str] = set()
            for level2 in level1.categories:
                if level2.identifier in seen_level2:
                    raise TaxonomyCatalogError(
                        f"Duplicate Level 2 identifier in {level1.identifier}: {level2.identifier}"
                    )
                seen_level2.add(level2.identifier)
                seen_level3: set[str] = set()
                for level3 in level2.categories:
                    if level3.identifier in seen_level3:
                        raise TaxonomyCatalogError(
                            f"Duplicate Level 3 identifier in {level1.identifier}/"
                            f"{level2.identifier}: {level3.identifier}"
                        )
                    seen_level3.add(level3.identifier)
                    key = (level1.identifier, level2.identifier, level3.identifier)
                    if key in paths:
                        raise TaxonomyCatalogError(f"Duplicate taxonomy path: {' / '.join(key)}")
                    paths[key] = FailureTaxonomyPath(
                        level1=key[0],
                        level2=key[1],
                        level3=key[2],
                        taxonomy_version=definition.version,
                        description=level3.description,
                    )
        return paths
