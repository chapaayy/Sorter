"""Permission-scope lattice; explicit report grants never imply all or own."""


def allowed_for(scope, *, own, granted):
    return scope == 'all' or (scope == 'own' and own) or (scope == 'granted' and granted)


def covers(have, want):
    return want == 'none' or have == 'all' or (have == want and want != 'granted')


def may_delegate(key, have, want):
    return want == 'none' or (
        (not key.startswith(('accounts.', 'storage.', 'system.')) or key in (
            'system.models', 'system.processing_view', 'system.performance_view'
        )) and covers(have, want)
    )
