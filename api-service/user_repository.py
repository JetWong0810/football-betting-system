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

    def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """根据手机号获取用户"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE phone = %s",
                    (phone,)
                )
                return cursor.fetchone()

    def get_user_by_openid(self, openid: str) -> Optional[Dict[str, Any]]:
        """根据openid获取用户"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, username, phone, email, nickname, avatar, openid, unionid,
                              wechat_nickname, wechat_avatar, login_type,
                              created_at, last_login_at, status
                       FROM users WHERE openid = %s""",
                    (openid,)
                )
                return cursor.fetchone()

    def create_wechat_user(self, openid: str, unionid: Optional[str] = None,
                          wechat_nickname: Optional[str] = None,
                          wechat_avatar: Optional[str] = None) -> int:
        """创建微信用户"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                # 生成一个唯一的用户名（基于openid）
                username = f"wx_{openid[:12]}"
                # 确保用户名唯一
                counter = 1
                while True:
                    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                    if not cursor.fetchone():
                        break
                    username = f"wx_{openid[:12]}_{counter}"
                    counter += 1
                
                cursor.execute(
                    """INSERT INTO users (username, password_hash, openid, unionid, 
                       wechat_nickname, wechat_avatar, nickname, avatar, login_type)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'wechat')""",
                    (username, '', openid, unionid, wechat_nickname, wechat_avatar,
                     wechat_nickname or username, wechat_avatar)
                )
                user_id = cursor.lastrowid

                # 创建默认配置
                cursor.execute(
                    "INSERT INTO user_configs (user_id) VALUES (%s)",
                    (user_id,)
                )
                return user_id

    def update_wechat_user_info(self, user_id: int, wechat_nickname: Optional[str] = None,
                                wechat_avatar: Optional[str] = None):
        """更新微信用户信息"""
        updates = []
        params = []
        
        if wechat_nickname is not None:
            updates.append("wechat_nickname = %s")
            updates.append("nickname = %s")
            params.append(wechat_nickname)
            params.append(wechat_nickname)
        
        if wechat_avatar is not None:
            updates.append("wechat_avatar = %s")
            updates.append("avatar = %s")
            params.append(wechat_avatar)
            params.append(wechat_avatar)
        
        if not updates:
            return False
        
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
        
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount > 0

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
        """获取用户配置，如果不存在则创建默认配置"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM user_configs WHERE user_id = %s",
                    (user_id,)
                )
                config = cursor.fetchone()
                
                # 如果配置不存在，创建默认配置
                if not config:
                    cursor.execute(
                        """INSERT INTO user_configs (user_id, starting_capital, fixed_ratio, 
                           kelly_factor, stop_loss_limit, target_monthly_return, theme)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (user_id, 10000.00, 0.0300, 0.5000, 3, 0.1000, 'light')
                    )
                    # 重新查询
                    cursor.execute(
                        "SELECT * FROM user_configs WHERE user_id = %s",
                        (user_id,)
                    )
                    config = cursor.fetchone()
                
                return config

    def update_user_config(self, user_id: int, config: Dict[str, Any]) -> bool:
        """更新用户配置，如果不存在则创建"""
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

        with get_db() as conn:
            with conn.cursor() as cursor:
                # 先检查配置是否存在
                cursor.execute(
                    "SELECT id FROM user_configs WHERE user_id = %s",
                    (user_id,)
                )
                exists = cursor.fetchone()
                
                if exists:
                    # 更新现有配置
                    params.append(user_id)
                    sql = f"UPDATE user_configs SET {', '.join(updates)} WHERE user_id = %s"
                    cursor.execute(sql, params)
                    return cursor.rowcount > 0
                else:
                    # 创建新配置（使用传入的值或默认值）
                    insert_fields = ["user_id"]
                    insert_values = [user_id]
                    
                    defaults = {
                        "starting_capital": 10000.00,
                        "fixed_ratio": 0.0300,
                        "kelly_factor": 0.5000,
                        "stop_loss_limit": 3,
                        "target_monthly_return": 0.1000,
                        "theme": "light",
                    }
                    
                    for key, field in field_map.items():
                        if key in config:
                            insert_fields.append(field)
                            insert_values.append(config[key])
                        elif field in defaults:
                            insert_fields.append(field)
                            insert_values.append(defaults[field])
                    
                    placeholders = ", ".join(["%s"] * len(insert_values))
                    fields_str = ", ".join(insert_fields)
                    sql = f"INSERT INTO user_configs ({fields_str}) VALUES ({placeholders})"
                    cursor.execute(sql, insert_values)
                    return cursor.rowcount > 0

    # ==================== 投注记录相关方法 ====================

    def create_bet(self, user_id: int, bet_data: Dict[str, Any], bet_time: str,
                   status: str, stake: float, odds: float,
                   result: Optional[str] = None, profit: Optional[float] = None) -> int:
        """创建投注记录"""
        import json
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO user_bets (user_id, bet_data, bet_time, status, result, stake, odds, profit)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, json.dumps(bet_data, ensure_ascii=False), bet_time, status, result, stake, odds, profit)
                )
                return cursor.lastrowid

    def get_bet(self, bet_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """获取单条投注记录"""
        import json
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, user_id, bet_data, bet_time, status, result, stake, odds, profit,
                              created_at, updated_at
                       FROM user_bets WHERE id = %s AND user_id = %s""",
                    (bet_id, user_id)
                )
                row = cursor.fetchone()
                if row:
                    row["bet_data"] = json.loads(row["bet_data"]) if row.get("bet_data") else {}
                return row

    def list_bets(self, user_id: int, status: Optional[str] = None,
                  page: int = 1, page_size: int = 100) -> Dict[str, Any]:
        """获取投注记录列表"""
        import json
        with get_db() as conn:
            with conn.cursor() as cursor:
                # 构建查询条件
                where_clause = "WHERE user_id = %s"
                params = [user_id]
                
                if status:
                    where_clause += " AND status = %s"
                    params.append(status)
                
                # 获取总数
                count_sql = f"SELECT COUNT(*) as total FROM user_bets {where_clause}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()["total"]
                
                # 获取分页数据
                offset = (page - 1) * page_size
                sql = f"""SELECT id, user_id, bet_data, bet_time, status, result, stake, odds, profit,
                                created_at, updated_at
                         FROM user_bets {where_clause}
                         ORDER BY bet_time DESC, created_at DESC
                         LIMIT %s OFFSET %s"""
                cursor.execute(sql, params + [page_size, offset])
                rows = cursor.fetchall()
                
                # 解析 JSON 数据
                for row in rows:
                    if row.get("bet_data"):
                        row["bet_data"] = json.loads(row["bet_data"])
                
                return {
                    "items": rows,
                    "total": total,
                    "page": page,
                    "page_size": page_size
                }

    def update_bet(self, bet_id: int, user_id: int, updates: Dict[str, Any]) -> bool:
        """更新投注记录"""
        import json
        update_fields = []
        params = []
        
        if "bet_data" in updates:
            update_fields.append("bet_data = %s")
            params.append(json.dumps(updates["bet_data"], ensure_ascii=False))
        if "bet_time" in updates:
            update_fields.append("bet_time = %s")
            params.append(updates["bet_time"])
        if "status" in updates:
            update_fields.append("status = %s")
            params.append(updates["status"])
        if "result" in updates:
            update_fields.append("result = %s")
            params.append(updates["result"])
        if "stake" in updates:
            update_fields.append("stake = %s")
            params.append(updates["stake"])
        if "odds" in updates:
            update_fields.append("odds = %s")
            params.append(updates["odds"])
        if "profit" in updates:
            update_fields.append("profit = %s")
            params.append(updates["profit"])
        
        if not update_fields:
            return False
        
        params.extend([bet_id, user_id])
        sql = f"""UPDATE user_bets SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                  WHERE id = %s AND user_id = %s"""
        
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount > 0

    def delete_bet(self, bet_id: int, user_id: int) -> bool:
        """删除投注记录"""
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM user_bets WHERE id = %s AND user_id = %s",
                    (bet_id, user_id)
                )
                return cursor.rowcount > 0

