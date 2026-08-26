from typing import Optional
from fastapi import APIRouter
from database import get_db_connection
from security import hash_password, verify_password
from schemas import StudentRegisterRequest, FacultyRegisterRequest, LoginRequest

router = APIRouter(prefix="/api", tags=["Auth & Registration"])


def resolve_domain_id(cursor, domain_name: Optional[str]) -> Optional[int]:
    """Look up an existing domain by name or insert a new record into the Domain table."""
    if not domain_name or not domain_name.strip():
        return None

    clean_domain = domain_name.strip()
    cursor.execute("SELECT domain_id FROM Domain WHERE domain_name = %s LIMIT 1;", (clean_domain,))
    row = cursor.fetchone()
    if row:
        return row['domain_id']

    cursor.execute(
        "INSERT INTO Domain (domain_name, description) VALUES (%s, %s);",
        (clean_domain, "Added during registration")
    )
    return cursor.lastrowid


@router.get("/domains")
def get_domains():
    """Fetch available research domains from MySQL."""
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


@router.post("/register/student")
def register_student(req: StudentRegisterRequest):
    """Register a student user (creates User and Student records)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT UID FROM User WHERE email = %s LIMIT 1;", (req.email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Email is already registered."}

        domain_id = resolve_domain_id(cursor, req.domain_name)
        hashed_pass = hash_password(req.password)

        cursor.execute(
            "INSERT INTO User (name, email, pass_hash, gender) VALUES (%s, %s, %s, %s);",
            (req.name, req.email, hashed_pass, req.gender)
        )
        uid = cursor.lastrowid

        cursor.execute(
            """INSERT INTO Student 
               (student_id, CGPA, credits_completed, has_done_thesis, preferred_domain, sem_no) 
               VALUES (%s, %s, %s, %s, %s, %s);""",
            (uid, req.cgpa, req.credits_completed, req.has_done_thesis, domain_id, req.sem_no)
        )

        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "ok", "message": "Student account registered successfully!", "uid": uid}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/register/faculty")
def register_faculty(req: FacultyRegisterRequest):
    """Register a faculty user (creates User and Faculty records)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT UID FROM User WHERE email = %s LIMIT 1;", (req.email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Email is already registered."}

        domain_id = resolve_domain_id(cursor, req.domain_name)
        hashed_pass = hash_password(req.password)

        cursor.execute(
            "INSERT INTO User (name, email, pass_hash, gender) VALUES (%s, %s, %s, %s);",
            (req.name, req.email, hashed_pass, req.gender)
        )
        uid = cursor.lastrowid

        cursor.execute(
            """INSERT INTO Faculty 
               (faculty_id, Fac_initial, `rank`, UG_PG, sem_free_from, max_grp_per_sem, total_supervised, room_no, calendar_link, work_on_domain) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
            (uid, req.fac_initial, req.designation, req.ug_pg, req.sem_free_from, req.max_grp_per_sem, req.total_supervised, req.room_no, req.calendar_link, domain_id)
        )

        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "ok", "message": "Faculty account registered successfully!", "uid": uid}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/login")
def login_user(req: LoginRequest):
    """Authenticate user with email and password, returning role and basic info."""
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

        cursor.execute("SELECT student_id FROM Student WHERE student_id = %s LIMIT 1;", (uid,))
        if cursor.fetchone():
            role = "Student"
        else:
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
