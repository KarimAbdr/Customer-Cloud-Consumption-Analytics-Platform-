import data_platform
import ml
import services


def test_packages_importable() -> None:
    assert data_platform and ml and services
