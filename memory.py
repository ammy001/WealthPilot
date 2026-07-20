"""User memory accessor.

Reads/writes the synthetic seed (data/profiles/users.json) so a stated preference
survives across sessions (and app restarts) without standing up Postgres yet. The
runtime store (Postgres wp_user_profile / wp_user_holding, see docs/memory-schema.md)
can back this later with the same get_user/list_users/update_preferences API.
"""
import json
import os

_USERS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "data", "profiles", "users.json")

# Top-level user fields vs. nested `preferences` fields — update_preferences()
# routes each kwarg to the right place.
_TOP_LEVEL_FIELDS = {"risk_tolerance", "goals", "monthly_investment_inr"}


def _load():
    with open(_USERS, encoding="utf-8") as f:
        return json.load(f)


def _save(users):
    with open(_USERS, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def get_user(user_id: str):
    key = str(user_id).strip().lower()
    for u in _load():
        if u["user_id"].lower() == key or u["name"].lower() == key:
            return u
    return None


def list_users():
    return [(u["user_id"], u["name"], u["risk_tolerance"]) for u in _load()]


def update_preferences(user_id: str, **fields):
    """Write one or more stated profile/preference fields for a user and persist them.

    e.g. update_preferences("U001", risk_tolerance="aggressive", crypto_cap_pct=10)

    Known top-level fields (risk_tolerance, goals, monthly_investment_inr) are set
    directly on the user record; anything else is written into the nested
    `preferences` dict (crypto_cap_pct, base_currency, ...). Returns the updated
    user record, or None if user_id is unknown.
    """
    users = _load()
    key = str(user_id).strip().lower()
    for u in users:
        if u["user_id"].lower() == key or u["name"].lower() == key:
            for name, value in fields.items():
                if name in _TOP_LEVEL_FIELDS:
                    u[name] = value
                else:
                    u.setdefault("preferences", {})[name] = value
            _save(users)
            return u
    return None
