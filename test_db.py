import os
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

load_dotenv()

try:
    conn = psycopg.connect(
        os.environ.get('DATABASE_URL'),
        row_factory=dict_row
    )
    print("✅ Database connection successful!")
    
    cur = conn.cursor()
    cur.execute("SELECT version()")
    version = cur.fetchone()
    print(f"PostgreSQL version: {version['version']}")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Connection failed: {e}")