from pydantic import BaseModel, Field


# Pydantic models
class Item(BaseModel):
    """Item model."""

    id: int = Field(..., description="Item ID", examples=[1])
    name: str = Field(..., description="Item name", examples=["Item 1"])
    description: str | None = None
    price: float = Field(..., description="Item price", examples=[9.99])


class ItemUpdate(BaseModel):
    """Item update model."""

    name: str | None = Field(None, description="Item name", examples=["Item 1"])
    description: str | None = None
    price: float | None = Field(None, description="Item price", examples=[12.99])
