from pydantic import BaseModel, Field
class PersonInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    note: str = Field(default='', max_length=300)
class BindingInput(BaseModel):
    person_id: int
    warehouse: str = Field(min_length=1, max_length=60)
    work_id: str = Field(min_length=1, max_length=60)
    valid_from: str = Field(min_length=10, max_length=10)
    valid_to: str | None = Field(default=None, max_length=10)
class MergeInput(BaseModel):
    into_id: int
class ConfirmInput(BaseModel):
    resolutions: dict[str, str] = Field(default_factory=dict)
