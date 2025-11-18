"""用户数据操作模块"""
from typing import Optional, Dict, Any
from datetime import datetime

from database import get_db


class UserRepository:
    """用户数据操作类"""

    def create_user(self, username: str, password_hash: str, phone: Optional[str] = None,
                   email: Optional[str] = None, nickname: Optional[str] = None) -> int:
        """创建用户"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO users (username, password_hash, phone, email, nickname)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (username, password_hash, phone, email, nickname or username)
                )
                user_id = cursor.lastrowid

                cursor.execute(
                    "INSERT INTO user_configs (user_id) VALUES (%s)",
                    (user_id,)
                )
            return user_id

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE username = %s",
                    (username,)
                )
                return cursor.fetchone()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取用户"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, username, phone, email, nickname, avatar,
                              created_at, last_login_at, status
                       FROM users WHERE id = %s""",
                    (user_id,)
                )
                return cursor.fetchone()

    def update_last_login(self, user_id: int):
        """更新最后登录时间"""
        with get_db() as conn:
            now = datetime.utcnow().isoformat()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET last_login_at = %s WHERE id = %s",
                    (now, user_id)
                )

    def update_user_profile(self, user_id: int, nickname: Optional[str] = None,
                           phone: Optional[str] = None, email: Optional[str] = None,
                           avatar: Optional[str] = None) -> bool:
        """更新用户资料"""
        updates = []
        params = []

        if nickname is not None:
            updates.append("nickname = %s")
            params.append(nickname)
        if phone is not None:
            updates.append("phone = %s")
            params.append(phone)
        if email is not None:
            updates.append("email = %s")
            params.append(email)
        if avatar is not None:
            updates.append("avatar = %s")
            params.append(avatar)

        if not updates:
            return False

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"

        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount > 0

    def get_user_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户配置"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM user_configs WHERE user_id = %s",
                    (user_id,)
                )
                return cursor.fetchone()

    def update_user_config(self, user_id: int, config: Dict[str, Any]) -> bool:
        """更新用户配置"""
        updates = []
        params = []

        field_map = {
            "starting_capital": "starting_capital",
            "fixed_ratio": "fixed_ratio",
            "kelly_factor": "kelly_factor",
            "stop_loss_limit": "stop_loss_limit",
            "target_monthly_return": "target_monthly_return",
            "theme": "theme",
        }

        for key, field in field_map.items():
            if key in config:
                updates.append(f"{field} = %s")
                params.append(config[key])

        if not updates:
            return False

        params.append(user_id)
        sql = f"UPDATE user_configs SET {', '.join(updates)} WHERE user_id = %s"

        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount > 0

