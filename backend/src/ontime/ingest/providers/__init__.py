from ontime.ingest.base import Provider
from ontime.ingest.providers.aerodatabox import AeroDataBox

REGISTRY: dict[str, type[Provider]] = {
    AeroDataBox.name: AeroDataBox,
}


def get_provider(name: str) -> Provider:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise SystemExit(f"unknown provider {name!r}; available: {', '.join(REGISTRY)}")
