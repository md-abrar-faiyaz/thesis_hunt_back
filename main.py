from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from database import get_db_connection
import uvicorn
import hashlib
import os

# Password Hashing Helper
try:
    import bcrypt
    USE_BCRYPT = True
except ImportError:
    USE_BCRYPT = False

def hash_password(password: str) -> str:
    if USE_BCRYPT:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    else:
        salt = os.urandom(16)
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return salt.hex() + ':' + hashed.hex()

def verify_password(password: str, pass_hash: str) -> bool:
    if USE_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), pass_hash.encode('utf-8'))
        except Exception:
            return False
    else:
        try:
            salt_hex, hash_hex = pass_hash.split(':')
            salt = bytes.fromhex(salt_hex)
            hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            return hashed.hex() == hash_hex
        except Exception:
            return False


class StudentRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    gender: Optional[str] = 'Other'
    cgpa: float
    credits_completed: int
    has_done_thesis: bool = False
    domain_name: Optional[str] = None

class FacultyRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    gender: Optional[str] = 'Other'
    fac_initial: str
    rank: str
    ug_pg: str
    sem_free_from: Optional[str] = ''
    max_grp_per_sem: int = 3
    total_supervised: int = 0
    room_no: Optional[str] = ''
    calendar_link: Optional[str] = ''
    domain_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str


app = FastAPI(title="Thesis Hunt API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://thesis-hunt.web.app",
        "https://thesis-hunt.firebaseapp.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Thesis Hunt API!"}

@app.get("/health")
def health_check():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "db_connection": "successful"}
    except Exception as e:
        return {"status": "error", "db_connection": str(e)}

# Helper to get or insert a domain name into MySQL Domain table
def resolve_domain_id(cursor, domain_name: Optional[str]) -> Optional[int]:
    if not domain_name or not domain_name.strip():
        return None
    
    clean_domain = domain_name.strip()
    cursor.execute("SELECT domain_id FROM Domain WHERE domain_name = %s LIMIT 1;", (clean_domain,))
    row = cursor.fetchone()
    if row:
        return row['domain_id']
    
    cursor.execute("INSERT INTO Domain (domain_name, description) VALUES (%s, %s);", (clean_domain, "Added during registration"))
    return cursor.lastrowid

@app.get("/api/domains")
def get_domains():
    """
    Fetches all available research domains from MySQL Domain table.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT domain_id, domain_name, description FROM Domain ORDER BY domain_name ASC;")
        domains = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "ok", "domains": domains}
    except Exception as e:
        return {"status": "error", "message": str(e), "domains": []}

@app.post("/api/register/student")
def register_student(req: StudentRegisterRequest):
    """
    Registers a new Student by creating records in User and Student tables.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check existing email
        cursor.execute("SELECT UID FROM User WHERE email = %s LIMIT 1;", (req.email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Email is already registered."}

        # Resolve Domain ID
        domain_id = resolve_domain_id(cursor, req.domain_name)

        # Hash Password
        hashed_pass = hash_password(req.password)

        # Insert User
        cursor.execute(
            "INSERT INTO User (name, email, pass_hash, gender) VALUES (%s, %s, %s, %s);",
            (req.name, req.email, hashed_pass, req.gender)
        )
        uid = cursor.lastrowid

        # Insert Student
        cursor.execute(
            "INSERT INTO Student (student_id, CGPA, credits_completed, has_done_thesis, preferred_domain) VALUES (%s, %s, %s, %s, %s);",
            (uid, req.cgpa, req.credits_completed, req.has_done_thesis, domain_id)
        )

        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "ok", "message": "Student account registered successfully!", "uid": uid}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/register/faculty")
def register_faculty(req: FacultyRegisterRequest):
    """
    Registers a new Faculty member by creating records in User and Faculty tables.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check existing email
        cursor.execute("SELECT UID FROM User WHERE email = %s LIMIT 1;", (req.email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Email is already registered."}

        # Resolve Domain ID
        domain_id = resolve_domain_id(cursor, req.domain_name)

        # Hash Password
        hashed_pass = hash_password(req.password)

        # Insert User
        cursor.execute(
            "INSERT INTO User (name, email, pass_hash, gender) VALUES (%s, %s, %s, %s);",
            (req.name, req.email, hashed_pass, req.gender)
        )
        uid = cursor.lastrowid

        # Insert Faculty
        cursor.execute(
            """INSERT INTO Faculty (faculty_id, Fac_initial, rank, UG_PG, sem_free_from, max_grp_per_sem, total_supervised, room_no, calendar_link, work_on_domain) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
            (uid, req.fac_initial, req.rank, req.ug_pg, req.sem_free_from, req.max_grp_per_sem, req.total_supervised, req.room_no, req.calendar_link, domain_id)
        )

        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "ok", "message": "Faculty account registered successfully!", "uid": uid}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/login")
def login_user(req: LoginRequest):
    """
    Authenticates user with email and password and returns user details and role.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT UID, name, email, pass_hash, gender FROM User WHERE email = %s LIMIT 1;", (req.email,))
        user = cursor.fetchone()

        if not user or not verify_password(req.password, user['pass_hash']):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Invalid email or password."}

        uid = user['UID']
        role = "User"

        # Check if Student
        cursor.execute("SELECT student_id FROM Student WHERE student_id = %s LIMIT 1;", (uid,))
        if cursor.fetchone():
            role = "Student"
        else:
            # Check if Faculty
            cursor.execute("SELECT faculty_id FROM Faculty WHERE faculty_id = %s LIMIT 1;", (uid,))
            if cursor.fetchone():
                role = "Faculty"

        cursor.close()
        conn.close()
        return {
            "status": "ok",
            "message": "Login successful!",
            "user": {
                "uid": uid,
                "name": user['name'],
                "email": user['email'],
                "role": role
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/tables")
def get_all_tables():
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

