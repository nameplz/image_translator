from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class DomainModel(BaseModel):
    """Immutable base class for stable domain boundary DTOs."""

    model_config = ConfigDict(frozen=True, extra="forbid")


NonEmptyStr: TypeAlias = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
UnitInterval: TypeAlias = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
PositiveFiniteFloat: TypeAlias = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
FiniteScore: TypeAlias = Annotated[float, Field(ge=1.0, le=5.0, allow_inf_nan=False)]
NonNegativeInt: TypeAlias = Annotated[int, Field(ge=0)]
PositiveInt: TypeAlias = Annotated[int, Field(ge=1)]
