# utils.py — للتوافق الخلفي فقط. كل المنطق صار في config.py
from config import (  # noqa: F401
    data,
    save_data,
    load_data,
    is_owner,
    is_admin,
    can_reply,
    is_banned,
    is_vip,
    save_user,
    update_stats,
    get_smart_reply,
    DEFAULT_DATA,
    DATA_FILE,
)
