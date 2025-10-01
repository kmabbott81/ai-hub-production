"""
Database module for AI Hub
Handles PostgreSQL connection and all database operations
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json
import bcrypt
import pyotp
from typing import Optional, Dict, List

class Database:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        """Connect to PostgreSQL database"""
        try:
            # Try DATABASE_URL first
            database_url = os.getenv('DATABASE_URL') or os.getenv('database_url')

            if database_url:
                self.conn = psycopg2.connect(database_url)
            else:
                # Try Railway's individual Postgres variables
                pghost = os.getenv('PGHOST')
                pgdatabase = os.getenv('PGDATABASE') or os.getenv('POSTGRES_DB')
                pguser = os.getenv('PGUSER') or os.getenv('POSTGRES_USER')
                pgpassword = os.getenv('PGPASSWORD') or os.getenv('POSTGRES_PASSWORD')
                pgport = os.getenv('PGPORT', '5432')

                if pghost and pgdatabase and pguser and pgpassword:
                    self.conn = psycopg2.connect(
                        host=pghost,
                        database=pgdatabase,
                        user=pguser,
                        password=pgpassword,
                        port=pgport
                    )
                else:
                    # Final fallback
                    self.conn = psycopg2.connect(
                        host=os.getenv('DB_HOST', 'localhost'),
                        database=os.getenv('DB_NAME', 'aihub'),
                        user=os.getenv('DB_USER', 'postgres'),
                        password=os.getenv('DB_PASSWORD', '')
                    )

            self.conn.autocommit = True
            self.init_tables()
            print("Database connected successfully!")
        except Exception as e:
            print(f"Database connection failed: {e}")
            self.conn = None

    def init_tables(self):
        """Initialize database tables"""
        if not self.conn:
            return

        with self.conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    mfa_enabled BOOLEAN DEFAULT FALSE,
                    mfa_secret VARCHAR(32),
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)

            # Projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    folder_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Files table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    path TEXT,
                    relative_path TEXT,
                    file_type VARCHAR(100),
                    size INTEGER,
                    content TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Chat threads table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                    title VARCHAR(500) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Messages table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    thread_id INTEGER REFERENCES chat_threads(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    # User management
    def create_user(self, username: str, email: str, password: str) -> Optional[int]:
        """Create a new user"""
        if not self.conn:
            return None

        try:
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                    (username, email, password_hash)
                )
                user_id = cur.fetchone()[0]
                return user_id
        except psycopg2.IntegrityError:
            return None  # Username or email already exists
        except Exception as e:
            print(f"Error creating user: {e}")
            return None

    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE username = %s AND is_active = TRUE",
                    (username,)
                )
                user = cur.fetchone()

                if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                    # Update last login
                    cur.execute(
                        "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                        (user['id'],)
                    )
                    return dict(user)
                return None
        except Exception as e:
            print(f"Error verifying user: {e}")
            return None

    def enable_mfa(self, user_id: int) -> str:
        """Enable MFA for user and return secret"""
        if not self.conn:
            return None

        secret = pyotp.random_base32()

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET mfa_enabled = TRUE, mfa_secret = %s WHERE id = %s",
                    (secret, user_id)
                )
            return secret
        except Exception as e:
            print(f"Error enabling MFA: {e}")
            return None

    def verify_mfa(self, user_id: int, token: str) -> bool:
        """Verify MFA token"""
        if not self.conn:
            return False

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT mfa_secret FROM users WHERE id = %s AND mfa_enabled = TRUE",
                    (user_id,)
                )
                user = cur.fetchone()

                if user and user['mfa_secret']:
                    totp = pyotp.TOTP(user['mfa_secret'])
                    return totp.verify(token, valid_window=1)
                return False
        except Exception as e:
            print(f"Error verifying MFA: {e}")
            return False

    # Project management
    def create_project(self, user_id: int, name: str, description: str = "") -> Optional[int]:
        """Create a new project"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO projects (user_id, name, description) VALUES (%s, %s, %s) RETURNING id",
                    (user_id, name, description)
                )
                return cur.fetchone()[0]
        except Exception as e:
            print(f"Error creating project: {e}")
            return None

    def get_user_projects(self, user_id: int) -> List[Dict]:
        """Get all projects for a user"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM projects WHERE user_id = %s ORDER BY updated_at DESC",
                    (user_id,)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"Error getting projects: {e}")
            return []

    def add_file_to_project(self, project_id: int, file_info: Dict) -> Optional[int]:
        """Add a file to a project"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO files (project_id, name, path, relative_path, file_type, size, content)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (project_id, file_info['name'], file_info.get('path'),
                     file_info.get('relative_path'), file_info['type'],
                     file_info['size'], file_info['content'])
                )

                # Update project timestamp
                cur.execute(
                    "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (project_id,)
                )

                return cur.fetchone()[0]
        except Exception as e:
            print(f"Error adding file: {e}")
            return None

    def get_project_files(self, project_id: int) -> List[Dict]:
        """Get all files for a project"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM files WHERE project_id = %s ORDER BY uploaded_at DESC",
                    (project_id,)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"Error getting files: {e}")
            return []

    # Chat thread management
    def create_thread(self, user_id: int, title: str = "New chat", project_id: Optional[int] = None) -> Optional[int]:
        """Create a new chat thread"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_threads (user_id, title, project_id) VALUES (%s, %s, %s) RETURNING id",
                    (user_id, title, project_id)
                )
                return cur.fetchone()[0]
        except Exception as e:
            print(f"Error creating thread: {e}")
            return None

    def get_user_threads(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get chat threads for a user"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM chat_threads WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
                    (user_id, limit)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"Error getting threads: {e}")
            return []

    def add_message(self, thread_id: int, role: str, content: str) -> Optional[int]:
        """Add a message to a thread"""
        if not self.conn:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (thread_id, role, content) VALUES (%s, %s, %s) RETURNING id",
                    (thread_id, role, content)
                )

                # Update thread timestamp
                cur.execute(
                    "UPDATE chat_threads SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (thread_id,)
                )

                return cur.fetchone()[0]
        except Exception as e:
            print(f"Error adding message: {e}")
            return None

    def get_thread_messages(self, thread_id: int) -> List[Dict]:
        """Get all messages for a thread"""
        if not self.conn:
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM messages WHERE thread_id = %s ORDER BY created_at ASC",
                    (thread_id,)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []

    def update_thread_title(self, thread_id: int, title: str):
        """Update thread title"""
        if not self.conn:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE chat_threads SET title = %s WHERE id = %s",
                    (title, thread_id)
                )
        except Exception as e:
            print(f"Error updating thread title: {e}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
