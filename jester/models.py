"""Pydantic request models for the programmatic API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TypeCreate(BaseModel):
    name: str
    description: str = ""
    # 'schema' is a reserved-ish name on BaseModel; expose it over the wire as
    # "schema" but reference it as `json_schema` in code.
    json_schema: dict = Field(alias="schema")
    model_config = ConfigDict(populate_by_name=True)


class TypeUpdate(BaseModel):
    description: str | None = None
    json_schema: dict | None = Field(default=None, alias="schema")
    model_config = ConfigDict(populate_by_name=True)


class ItemSubmit(BaseModel):
    type: str
    payload: Any
    metadata: dict = Field(default_factory=dict)


class AckRequest(BaseModel):
    ids: list[str]
