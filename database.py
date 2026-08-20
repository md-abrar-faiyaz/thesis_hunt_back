import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables.
    Returns a MySQL connection object.
    """
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "thesis_hunt"),
        port=os.getenv("DB_PORT", "3306")
    )
    return connection
