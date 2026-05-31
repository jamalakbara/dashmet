import math
import uuid
from datetime import date, datetime
from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")

DATE_PRESETS = Literal[
    "today",
    "yesterday",
    "last_7d",
    "last_14d",
    "last_28d",
    "last_30d",
    "last_90d",
    "this_month",
    "last_month",
    "this_year",
    "lifetime",
]


class Meta(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cached: bool = False
    cached_at: Optional[datetime] = None


class Pagination(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class DataResponse(BaseModel, Generic[T]):
    data: T
    meta: Meta = Field(default_factory=Meta)


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination
    meta: Meta = Field(default_factory=Meta)


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    details: Optional[list[ErrorDetail]] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def build_pagination(total: int, page: int, per_page: int) -> Pagination:
    per_page = min(per_page, 200)
    total_pages = math.ceil(total / per_page) if per_page > 0 and total > 0 else 0
    return Pagination(total=total, page=page, per_page=per_page, total_pages=total_pages)


def calculate_offset(page: int, per_page: int) -> int:
    return (page - 1) * per_page


class DateRangeParams(BaseModel):
    date_preset: Optional[DATE_PRESETS] = None
    date_start: Optional[date] = None
    date_end: Optional[date] = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "DateRangeParams":
        has_preset = self.date_preset is not None
        has_custom = self.date_start is not None or self.date_end is not None

        if has_preset and has_custom:
            raise ValueError("Provide date_preset OR date_start+date_end, not both")

        if not has_preset and not has_custom:
            raise ValueError("Provide either date_preset or date_start+date_end")

        if has_custom:
            if self.date_start is None or self.date_end is None:
                raise ValueError("Both date_start and date_end are required for a custom range")
            if self.date_end < self.date_start:
                raise ValueError("date_end must be on or after date_start")

        return self
