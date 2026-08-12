import sqlite3
import os
import json
import logging
from datetime import datetime
from app.config import DB_PATH

logger = logging.getLogger(__name__)

def get_db_connection():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database schema if it doesn't exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL
    )
    """)
    
    # Tool calls log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        arguments TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT
    )
    """)
    
    # Memory key-value store (for settings, favorite project paths, etc)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS key_value_store (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")

def add_message(role: str, content: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (timestamp, role, content) VALUES (?, ?, ?)",
        (datetime.now().isoformat(), role, content)
    )
    conn.commit()
    conn.close()

def get_recent_history(limit: int = 10) -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    # Return in chronological order
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def log_tool_call(tool_name: str, arguments: dict, status: str, result: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tool_calls (timestamp, tool_name, arguments, status, result) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), tool_name, json.dumps(arguments), status, str(result))
    )
    # If it was an open_folder command and successful, save it to projects memory
    if tool_name == "open_folder" and status == "success" and "path" in arguments:
        path = arguments["path"]
        folder_name = os.path.basename(path.rstrip("/"))
        if folder_name:
            cursor.execute(
                "INSERT OR REPLACE INTO key_value_store (key, value, updated_at) VALUES (?, ?, ?)",
                (f"project_path_{folder_name.lower()}", path, datetime.now().isoformat())
            )
            
    conn.commit()
    conn.close()

def set_value(key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO key_value_store (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_value(key: str, default: str = None) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM key_value_store WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def resolve_project_path(project_name: str) -> str:
    """
    Attempts to resolve project folders from name using past history or custom configs.
    Example: 'flutter' -> lookup 'project_path_flutter' -> returns '~/Projects/flutter'
    """
    key = f"project_path_{project_name.lower().strip()}"
    return get_value(key)

# Initialize database on module load
try:
    init_db()
except Exception as e:
    logger.exception(f"Could not initialize memory database: {e}")
