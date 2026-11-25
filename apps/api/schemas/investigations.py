"""Investigation request schemas."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class StartReview(BaseModel):
    line_id: Annotated[str, Field(pattern=r"^CLM-[A-Z0-9]+-[1-9][0-9]*$", max_length=40)]


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    note: Annotated[str, Field(min_length=1, max_length=2000)]
