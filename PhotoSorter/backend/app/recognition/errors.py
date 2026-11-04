"""User cancellation is not a model error."""

class JobCancelled(Exception):
    """Raised when an active run was stopped by the user."""
