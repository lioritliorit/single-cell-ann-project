import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash


class AuthError(RuntimeError):
    """Raised when authentication or authorization fails."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthManager:
    """SQLite-backed user, session and dataset-permission manager."""

    VALID_ROLES = {"user", "admin"}
    VALID_VISIBILITY = {"public", "private", "liver_disease"}

    def __init__(self, db_path: str = "auth.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    email TEXT DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'user',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS dataset_permissions (
                    dataset_id TEXT PRIMARY KEY,
                    visibility TEXT NOT NULL DEFAULT 'public',
                    owner_user_id INTEGER,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE SET NULL
                );
                """
            )

    def ensure_admin(self, username: str, password: str, email: str = "") -> None:
        if self.get_user_by_username(username):
            return
        self.create_user(username, password, email=email, role="admin")

    def create_user(
        self,
        username: str,
        password: str,
        *,
        email: str = "",
        role: str = "user",
    ) -> Dict[str, Any]:
        username = (username or "").strip()
        if not username:
            raise AuthError("username is required", 400)
        if len(password or "") < 6:
            raise AuthError("password must contain at least 6 characters", 400)
        if role not in self.VALID_ROLES:
            raise AuthError(f"invalid role: {role}", 400)

        now = self._now()
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO users (username, password_hash, email, role, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (username, generate_password_hash(password), email or "", role, now, now),
                )
                user_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise AuthError("username already exists", 409) from exc
        return self.get_user(user_id)

    def authenticate(self, username: str, password: str, ttl_seconds: int = 86400) -> Dict[str, Any]:
        user = self.get_user_by_username(username)
        if not user or not user["is_active"]:
            raise AuthError("invalid username or password", 401)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
            ).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password or ""):
            raise AuthError("invalid username or password", 401)

        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + ttl_seconds
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user["id"], self._now(), expires_at),
            )
        return {"token": token, "expires_at": expires_at, "user": user}

    def logout(self, token: str) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            row = conn.execute(
                """
                SELECT users.id, users.username, users.email, users.role, users.is_active,
                       users.created_at, users.updated_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND sessions.expires_at >= ?
                """,
                (token, now),
            ).fetchone()
        if row is None or not row["is_active"]:
            return None
        return self._public_user(row)

    def list_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, username, email, role, is_active, created_at, updated_at FROM users ORDER BY id"
            ).fetchall()
        return [self._public_user(row) for row in rows]

    def get_user(self, user_id: int) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, email, role, is_active, created_at, updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise AuthError(f"unknown user_id: {user_id}", 404)
        return self._public_user(row)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, email, role, is_active, created_at, updated_at FROM users WHERE username = ?",
                ((username or "").strip(),),
            ).fetchone()
        return self._public_user(row) if row else None

    def update_user(self, user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {}
        if "email" in updates:
            allowed["email"] = updates.get("email") or ""
        if "role" in updates:
            role = updates["role"]
            if role not in self.VALID_ROLES:
                raise AuthError(f"invalid role: {role}", 400)
            allowed["role"] = role
        if "is_active" in updates:
            allowed["is_active"] = 1 if updates["is_active"] else 0
        if "password" in updates and updates["password"]:
            if len(updates["password"]) < 6:
                raise AuthError("password must contain at least 6 characters", 400)
            allowed["password_hash"] = generate_password_hash(updates["password"])
        if not allowed:
            return self.get_user(user_id)

        allowed["updated_at"] = self._now()
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        values = list(allowed.values()) + [user_id]
        with self._connect() as conn:
            cursor = conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", values)
            if cursor.rowcount == 0:
                raise AuthError(f"unknown user_id: {user_id}", 404)
        return self.get_user(user_id)

    def delete_user(self, user_id: int) -> None:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if cursor.rowcount == 0:
                raise AuthError(f"unknown user_id: {user_id}", 404)

    def get_dataset_policy(self, dataset_id: str, dataset: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT dataset_id, visibility, owner_user_id, updated_at FROM dataset_permissions WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
        if row:
            return dict(row)
        visibility = self.default_visibility(dataset or {"id": dataset_id})
        return {
            "dataset_id": dataset_id,
            "visibility": visibility,
            "owner_user_id": None,
            "updated_at": None,
        }

    def set_dataset_policy(
        self,
        dataset_id: str,
        *,
        visibility: str,
        owner_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if visibility not in self.VALID_VISIBILITY:
            raise AuthError(f"invalid visibility: {visibility}", 400)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dataset_permissions (dataset_id, visibility, owner_user_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    visibility = excluded.visibility,
                    owner_user_id = excluded.owner_user_id,
                    updated_at = excluded.updated_at
                """,
                (dataset_id, visibility, owner_user_id, now),
            )
        return self.get_dataset_policy(dataset_id)

    def list_dataset_policies(self, datasets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.get_dataset_policy(dataset["id"], dataset) for dataset in datasets]

    def can_view_dataset(
        self,
        user: Optional[Dict[str, Any]],
        dataset: Dict[str, Any],
    ) -> bool:
        if user and user.get("role") == "admin":
            return True
        policy = self.get_dataset_policy(dataset["id"], dataset)
        visibility = policy["visibility"]
        if visibility == "public":
            return True
        if visibility == "liver_disease":
            return user is not None
        return user is not None and policy.get("owner_user_id") == user.get("id")

    def can_manage_dataset(
        self,
        user: Optional[Dict[str, Any]],
        dataset: Dict[str, Any],
    ) -> bool:
        if not user:
            return False
        if user.get("role") == "admin":
            return True
        policy = self.get_dataset_policy(dataset["id"], dataset)
        return policy.get("owner_user_id") == user.get("id")

    @staticmethod
    def default_visibility(dataset: Dict[str, Any]) -> str:
        if dataset.get("group") == "liver_disease":
            return "liver_disease"
        if dataset.get("id") == "default" or dataset.get("kind") == "joint":
            return "public"
        return "private"

    @staticmethod
    def _public_user(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "username": row["username"],
            "email": row["email"] or "",
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
