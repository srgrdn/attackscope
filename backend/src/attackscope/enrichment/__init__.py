from typing import Protocol, TypedDict


class NetworkEnrichment(TypedDict):
    status: str
    country: str | None
    asn: int | None
    organization: str | None


class EnrichmentProvider(Protocol):
    def lookup(self, ip: str) -> NetworkEnrichment: ...


class UnavailableEnrichment:
    def lookup(self, ip: str) -> NetworkEnrichment:
        return {"status": "unavailable", "country": None, "asn": None, "organization": None}
