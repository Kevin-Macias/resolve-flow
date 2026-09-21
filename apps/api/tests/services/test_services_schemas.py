import pytest
from pydantic import ValidationError

from api.services.schemas import Service


def test_service_label_strip() -> None:
    service = Service(code="101", label="   Label text  ")
    assert service.label == "Label text"


def test_service_label_max_length() -> None:
    with pytest.raises(ValidationError):
        Service(code="101", label=f"${'a' * 255}")


def test_service_label_min_length() -> None:
    with pytest.raises(ValidationError):
        Service(code="101", label="1")
