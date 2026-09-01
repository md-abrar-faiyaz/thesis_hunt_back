from typing import Optional
from fastapi import APIRouter
from database import get_db_connection
from security import hash_password, verify_password
from schemas import StudentRegisterRequest, FacultyRegisterRequest, LoginRequest

router = APIRouter(prefix="/api", tags=["Auth & Registration"])


def to_bool(val) -> bool:
    """Helper to convert MySQL bit/tinyint/bytes/str/bool values to standard python bool."""
    if val is None:
        return False
    if isinstance(val, bytes):
        return int.from_bytes(val, byteorder='little') != 0
    if isinstance(val, str):
        return val.lower() in ('true', '1', 'yes')
    return bool(val)


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

        clean_initial = (req.fac_initial or "").strip().upper()
        if clean_initial:
            cursor.execute("SELECT faculty_id FROM Faculty WHERE Fac_initial = %s LIMIT 1;", (clean_initial,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return {"status": "error", "message": f"Faculty initial '{clean_initial}' is already registered."}

        domain_id = resolve_domain_id(cursor, req.domain_name)
        hashed_pass = hash_password(req.password)
        fac_rank = req.designation or req.rank or "Assistant Professor"

        cursor.execute(
            "INSERT INTO User (name, email, pass_hash, gender) VALUES (%s, %s, %s, %s);",
            (req.name, req.email, hashed_pass, req.gender)
        )
        uid = cursor.lastrowid

        cursor.execute(
            """INSERT INTO Faculty 
               (faculty_id, Fac_initial, designation, UG_PG, sem_free_from, max_grp_per_sem, total_supervised, room_no, calendar_link, work_on_domain) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
            (uid, clean_initial, fac_rank, req.ug_pg, req.sem_free_from, req.max_grp_per_sem, req.total_supervised, req.room_no, req.calendar_link, domain_id)
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

        cursor.execute("SELECT student_id, has_done_thesis FROM Student WHERE student_id = %s LIMIT 1;", (uid,))
        student_info = cursor.fetchone()
        has_done_thesis = False
        if student_info:
            role = "Student"
            has_done_thesis = to_bool(student_info.get('has_done_thesis'))
        else:
            cursor.execute("SELECT faculty_id FROM Faculty WHERE faculty_id = %s LIMIT 1;", (uid,))
            if cursor.fetchone():
                role = "Faculty"

        cursor.close()
        conn.close()
        
        user_payload = {
            "uid": uid,
            "name": user['name'],
            "email": user['email'],
            "role": role
        }
        if role == "Student":
            user_payload["has_done_thesis"] = has_done_thesis

        return {
            "status": "ok",
            "message": "Login successful!",
            "user": user_payload
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
