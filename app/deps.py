from app.core.db import get_session
from app.auth import get_current_user, require_admin

get_db = get_session
get_user = get_current_user
get_admin = require_admin
