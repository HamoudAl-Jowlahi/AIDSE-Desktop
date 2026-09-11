"""
AIDSE Platform — Auth tests package marker.

Fixtures (db, client, auth_headers, ...) are provided by the ROOT
conftest.py at the repository root. This module previously duplicated
the whole fixture stack with a second in-memory engine, whose table
cleanup conflicted with lazily-imported models and broke teardown.
Keep only shared fixtures in the root conftest.
"""
