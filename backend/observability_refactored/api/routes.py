# THIS FILE HAS BEEN RETIRED.
#
# All endpoints have been migrated to the modular routers under api/routers/:
#
#   api/routers/auth.py        — /register, /login
#   api/routers/traces.py      — /traces, /observations, /spans, /llm-spans
#   api/routers/dashboard.py   — /dashboard/*
#   api/routers/users.py       — /users/*
#   api/routers/evaluation.py  — /api/evaluation/*
#
# This file is no longer imported by main.py and can be safely deleted.
# It is kept here only so that any open IDE tabs don't cause import errors.