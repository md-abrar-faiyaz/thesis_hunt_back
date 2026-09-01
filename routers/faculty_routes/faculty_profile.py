"""
Faculty Profile Router
Handles fetching and updating faculty profile info.
"""
from fastapi import APIRouter
from database import get_db_connection
from schemas import FacultyProfileUpdateRequest
from routers.auth import resolve_domain_id

router = APIRouter()


@router.get("/profile/{faculty_id}")
def get_faculty_profile(faculty_id: int):
    """
    Fetch all profile information for a faculty member from User and Faculty tables.
    Excludes pass_hash.
    """
    try:
        # Establish MySQL database connection
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Query User and Faculty details excluding pass_hash
        query = """
            SELECT 
                u.UID as faculty_id,
                u.name,
                u.email,
                u.gender,
                f.Fac_initial as fac_initial,
                f.`designation` as designation,
                f.UG_PG as ug_pg,
                f.sem_free_from,
                f.max_grp_per_sem,
                f.total_supervised,
                f.room_no,
                f.calendar_link,
                d.domain_name as research_domain
            FROM User u
            JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Domain d ON f.work_on_domain = d.domain_id
            WHERE u.UID = %s LIMIT 1;
        """
        cursor.execute(query, (faculty_id,))
        faculty = cursor.fetchone()

        if not faculty:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Faculty profile not found."}

        # Clean up database resources
        cursor.close()
        conn.close()

        return {"status": "ok", "faculty": faculty}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.put("/profile/{faculty_id}")
def update_faculty_profile(faculty_id: int, req: FacultyProfileUpdateRequest):
    """Update faculty profile information (designation, ug_pg, sem_free_from, max_grp_per_sem, room_no, calendar_link, domain)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name) if req.domain_name else None

        # Build dynamic SQL update statement
        update_fields = []
        params = []

        if req.designation is not None:
            update_fields.append("`designation` = %s")
            params.append(req.designation)
        if req.ug_pg is not None:
            update_fields.append("UG_PG = %s")
            params.append(req.ug_pg)
        if req.sem_free_from is not None:
            update_fields.append("sem_free_from = %s")
            params.append(req.sem_free_from)
        if req.max_grp_per_sem is not None:
            update_fields.append("max_grp_per_sem = %s")
            params.append(req.max_grp_per_sem)
        if req.room_no is not None:
            update_fields.append("room_no = %s")
            params.append(req.room_no)
        if req.calendar_link is not None:
            update_fields.append("calendar_link = %s")
            params.append(req.calendar_link)
        if domain_id is not None:
            update_fields.append("work_on_domain = %s")
            params.append(domain_id)

        if update_fields:
            params.append(faculty_id)
            sql = f"UPDATE Faculty SET {', '.join(update_fields)} WHERE faculty_id = %s;"
            cursor.execute(sql, tuple(params))
            conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Faculty profile updated successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
