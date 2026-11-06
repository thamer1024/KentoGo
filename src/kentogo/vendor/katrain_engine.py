"""Code copied unchanged from KaTrain 1.20.0 (https://github.com/sanderland/katrain).

Only the constant and the function below are copied, letter for letter, from katrain/core/engine.py;
nothing else of KaTrain is here.
- ENGINE_BACKENDS and resolve_engine_backend: which kind of engine KaTrain's settings choose.

Copyright 2020 Sander Land and/or other authors of KaTrain.
Released under the MIT License (see THIRD_PARTY_NOTICES.md, "1. KaTrain").
"""

ENGINE_BACKENDS = ("local", "remote", "custom")


def resolve_engine_backend(config) -> str:
    """Which engine backend to use: 'local', 'remote' or 'custom'.

    Uses the explicit `engine/backend` setting when present (set by the engine
    settings tabs). Falls back to deriving it from the legacy fields so older
    configs keep working: a remote_url means remote, an altcommand means custom.
    """
    backend = (config.get("backend") or "").strip().lower()
    if backend in ENGINE_BACKENDS:
        return backend
    if (config.get("remote_url") or "").strip():
        return "remote"
    if (config.get("altcommand") or "").strip():
        return "custom"
    return "local"
