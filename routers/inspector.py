from fastapi import APIRouter
from database import get_db_connection

router = APIRouter(tags=["Inspector & System"])


@router.get("/")
def read_root():
    return {"message": "Welcome to the Thesis Hunt API!"}


@router.get("/health")
def health_check():
    """Verify database connection health."""
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "db_connection": "successful"}
    except Exception as e:
        return {"status": "error", "db_connection": str(e)}


@router.get("/api/tables")
def get_all_tables():
    """Dump database tables and records for developer inspection portal."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SHOW TABLES;")
        tables_raw = cursor.fetchall()
        
        db_data = {}
        for table_dict in tables_raw:
            table_name = list(table_dict.values())[0]
            cursor.execute(f"SELECT * FROM `{table_name}`;")
            rows = cursor.fetchall()
            
            serializable_rows = []
            for row in rows:
                clean_row = {}
                for key, val in row.items():
                    if hasattr(val, 'isoformat'):
                        clean_row[key] = val.isoformat()
                    elif isinstance(val, (bytes, bytearray)):
                        clean_row[key] = val.decode('utf-8', errors='ignore')
                    else:
                        clean_row[key] = val
                serializable_rows.append(clean_row)
                
            db_data[table_name] = serializable_rows
            
        cursor.close()
        conn.close()
        return {"status": "ok", "tables": db_data}
    except Exception as e:
        return {"status": "error", "message": str(e), "tables": {}}
