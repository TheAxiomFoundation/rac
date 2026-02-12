"""Entity schema and data model for the RAC engine.

Handles relational data with primary keys, foreign keys, and reverse relations.
"""

from typing import Any

from pydantic import BaseModel, model_validator


class Field(BaseModel):
    """A field on an entity."""

    name: str
    dtype: str  # int, float, str, bool, date
    nullable: bool = False
    default: Any = None


class ForeignKey(BaseModel):
    """A foreign key relationship to another entity."""

    name: str
    target: str
    target_field: str = "id"


class ReverseRelation(BaseModel):
    """A reverse relation (one-to-many) from another entity."""

    name: str
    source: str
    source_field: str


class Entity(BaseModel):
    """An entity type in the schema."""

    name: str
    primary_key: str = "id"
    fields: dict[str, Field] = {}
    foreign_keys: dict[str, ForeignKey] = {}
    reverse_relations: dict[str, ReverseRelation] = {}


class Schema(BaseModel):
    """Complete schema for a ruleset."""

    entities: dict[str, Entity] = {}

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.name] = entity

    def infer_reverse_relations(self) -> None:
        """Auto-generate reverse relations from foreign keys."""
        for entity_name, entity in self.entities.items():
            for fk_name, fk in entity.foreign_keys.items():
                if fk.target in self.entities:
                    target = self.entities[fk.target]
                    reverse_name = f"{entity_name}s"
                    if reverse_name not in target.reverse_relations:
                        target.reverse_relations[reverse_name] = ReverseRelation(
                            name=reverse_name,
                            source=entity_name,
                            source_field=fk_name,
                        )


class Data(BaseModel):
    """Input data: entity tables with rows."""

    tables: dict[str, list[dict[str, Any]]]
    _index: dict[str, dict[Any, dict]] = {}

    @model_validator(mode="after")
    def build_index(self) -> "Data":
        """Build primary key index for fast lookups."""
        object.__setattr__(self, "_index", {})
        for entity_name, rows in self.tables.items():
            self._index[entity_name] = {}
            for row in rows:
                pk = row.get("id")
                if pk is not None:
                    self._index[entity_name][pk] = row
        return self

    def get_row(self, entity: str, pk: Any) -> dict | None:
        return self._index.get(entity, {}).get(pk)

    def get_rows(self, entity: str) -> list[dict]:
        return self.tables.get(entity, [])

    def get_related(self, entity: str, fk_field: str, fk_value: Any) -> list[dict]:
        return [row for row in self.tables.get(entity, []) if row.get(fk_field) == fk_value]
