from typing import Annotated

from pydantic import BaseModel, StringConstraints

type Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)
]


class Service(BaseModel):
    code: str
    label: Label
