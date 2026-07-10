from datetime import date

from sqlmodel import Field, SQLModel


class FamilyLink(SQLModel, table=True):
    __tablename__ = "family_links"

    id: int | None = Field(default=None, primary_key=True)
    family_name: str


class UserTable(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    family_id: int = Field(foreign_key="family_links.id")
    role: str


class BaselineTable(SQLModel, table=True):
    __tablename__ = "baselines"

    id: int | None = Field(default=None, primary_key=True)
    family_id: int = Field(foreign_key="family_links.id")
    epoch_start_date: date
    starting_parent: str


class OverrideTable(SQLModel, table=True):
    __tablename__ = "overrides"

    id: int | None = Field(default=None, primary_key=True)
    family_id: int = Field(foreign_key="family_links.id")
    override_date: date
    assigned_parent: str
    override_type: str
    description: str
    is_active: bool = True
