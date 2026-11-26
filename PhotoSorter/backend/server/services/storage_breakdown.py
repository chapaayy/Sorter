"""Compatibility entry point backed by the unified PostgreSQL registry."""
def breakdown():
    from ..storage.reporting import breakdown as registry_breakdown
    return registry_breakdown()
