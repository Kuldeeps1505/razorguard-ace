"""
Protocol adapter registry.

Adding a new buyer protocol = register one ProtocolAdapter subclass.
Nothing in the authorization chain changes.

STUB adapters (ACP, AP2) are blocked when app_env=production (PA-06).
"""

from razorguard.interfaces.protocol_adapters.acp_stub import ACPStubAdapter
from razorguard.interfaces.protocol_adapters.ap2_stub import AP2StubAdapter
from razorguard.interfaces.protocol_adapters.base import ProtocolAdapter
from razorguard.interfaces.protocol_adapters.native import NativeAdapter
from razorguard.interfaces.protocol_adapters.unknown import UnknownProtocolAdapter
from razorguard.shared.config import get_settings
from razorguard.shared.enums import ProtocolSource
from razorguard.shared.errors import StubAdapterBlockedError

_ADAPTERS: dict[ProtocolSource, type[ProtocolAdapter]] = {
    ProtocolSource.RAZORGUARD: NativeAdapter,
    ProtocolSource.ACP: ACPStubAdapter,
    ProtocolSource.AP2: AP2StubAdapter,
    ProtocolSource.UNKNOWN: UnknownProtocolAdapter,
    ProtocolSource.UAP: UnknownProtocolAdapter,
}


def parse_protocol_source(value: str) -> ProtocolSource:
    try:
        return ProtocolSource(value.strip().upper())
    except ValueError:
        return ProtocolSource.UNKNOWN


def get_adapter(
    protocol: ProtocolSource,
    *,
    allow_stubs: bool | None = None,
) -> ProtocolAdapter:
    """
    Return an adapter instance for the given protocol.

    Stub adapters are blocked in production unless allow_stubs=True
    (reserved for explicit demo scripts).
    """
    adapter_cls = _ADAPTERS.get(protocol, UnknownProtocolAdapter)
    adapter = adapter_cls()
    is_stub = bool(getattr(adapter_cls, "IS_STUB", False))
    if is_stub:
        settings = get_settings()
        stubs_ok = allow_stubs if allow_stubs is not None else not settings.is_production
        if not stubs_ok:
            raise StubAdapterBlockedError(protocol.value)
    return adapter
