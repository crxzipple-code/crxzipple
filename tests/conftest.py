from __future__ import annotations

import os


os.environ.setdefault("APP_EVENTS_BACKEND", "file")
os.environ.setdefault("APP_CHANNEL_PROFILE_PATHS", os.pathsep)
