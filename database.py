import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """
    Establishes a connection to the Aiven Cloud MySQL database using environment variables.
    Converts DB_PORT safely to int and sets a connection timeout.
    """
    raw_port = os.getenv("DB_PORT", "3306")
    try:
        port_int = int(raw_port)
    except (ValueError, TypeError):
        port_int = 3306

    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "thesis_hunt"),
        port=port_int,
        connect_timeout=10
    )
    return connection
