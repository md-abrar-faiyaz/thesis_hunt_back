import os
import mysql.connector
from dotenv import load_dotenv

# Load environment variables (e.g., Aiven DB connection string)
load_dotenv()

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables.
    Returns a MySQL connection object.
    
    Make sure to provide DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, and DB_PORT 
    in your environment variables or .env file.
    """
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "thesis_hunt"),
        port=os.getenv("DB_PORT", "3306")
    )
    return connection
