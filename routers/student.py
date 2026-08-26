from typing import Optional, List
from fastapi import APIRouter, Query
from database import get_db_connection

router = APIRouter(prefix="/api/student", tags=["Student Interface"])


@router.get("/search")
def search_students(
    q: Optional[str] = None,
    has_completed_thesis: Optional[bool] = None,
    available_only: Optional[bool] = None,
    gender: Optional[str] = None,
    sort_by: Optional[List[str]] = Query(None)
):
    """
    Search students based on specification #6 in INTERFACES.md:
    - Search by name, student id (u.UID), or preferred domain name.
    - Filter by has_completed_thesis (s.has_done_thesis), available_only (s.thesis_group IS NULL), and gender.
    - Sort by CGPA, completed credits, number of publications, semesters completed (sem_no - 1) in DESCENDING order via checkboxes.
    - Default sort if no checkbox checked: u.UID ASC.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                u.UID as student_id,
                u.name,
                u.email,
                u.gender,
                s.CGPA,
                s.credits_completed,
                s.has_done_thesis,
                s.thesis_group,
                tg.formation_status,
                s.sem_no,
                CASE WHEN s.sem_no > 1 THEN (s.sem_no - 1) ELSE 0 END as semesters_completed,
                d.domain_name as preferred_domain,
                COUNT(ab.paper_id) as num_publications
            FROM User u
            JOIN Student s ON u.UID = s.student_id
            LEFT JOIN ThesisGroup tg ON s.thesis_group = tg.group_id
            LEFT JOIN Domain d ON s.preferred_domain = d.domain_id
            LEFT JOIN AuthoredBy ab ON u.UID = ab.author_id
            WHERE 1=1
        """
        params = []

        if q and q.strip():
            search_pattern = f"%{q.strip()}%"
            query += " AND (u.name LIKE %s OR CAST(u.UID AS CHAR) LIKE %s OR d.domain_name LIKE %s)"
            params.extend([search_pattern, search_pattern, search_pattern])

        if has_completed_thesis is True:
            query += " AND s.has_done_thesis = TRUE"

        if available_only is True:
            query += " AND s.thesis_group IS NULL"

        if gender and gender.strip() and gender.strip().lower() != "all":
            query += " AND u.gender = %s"
            params.append(gender.strip())

        query += " GROUP BY u.UID, u.name, u.email, u.gender, s.CGPA, s.credits_completed, s.has_done_thesis, s.thesis_group, tg.formation_status, s.sem_no, d.domain_name"

        # Dynamic sorting logic
        order_clauses = []
        normalized_sort_by = []
        if sort_by:
            for item in sort_by:
                for s in item.split(","):
                    clean_s = s.strip().lower()
                    if clean_s and clean_s not in normalized_sort_by:
                        normalized_sort_by.append(clean_s)

        sort_map = {
            "cgpa": "s.CGPA DESC",
            "credits": "s.credits_completed DESC",
            "publications": "num_publications DESC",
            "semesters": "s.sem_no DESC"
        }

        for key in normalized_sort_by:
            if key in sort_map:
                order_clauses.append(sort_map[key])

        if order_clauses:
            query += " ORDER BY " + ", ".join(order_clauses) + ", u.UID ASC"
        else:
            query += " ORDER BY u.UID ASC"

        cursor.execute(query, tuple(params))
        students = cursor.fetchall()

        cursor.close()
        conn.close()

        # Post-processing numeric and boolean fields
        for student in students:
            if student.get("CGPA") is not None:
                student["CGPA"] = float(student["CGPA"])
            student["has_done_thesis"] = bool(student.get("has_done_thesis"))
            student["num_publications"] = int(student.get("num_publications") or 0)
            student["credits_completed"] = int(student.get("credits_completed") or 0)
            student["sem_no"] = int(student.get("sem_no") or 1)
            student["semesters_completed"] = int(student.get("semesters_completed") or 0)

        return {"status": "ok", "count": len(students), "students": students}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/profile/{student_id}")
def get_student_profile(student_id: int):
    """Fetch profile information for a student from User, Student, and Domain tables."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                u.UID as student_id,
                u.name,
                u.email,
                u.gender,
                s.CGPA,
                s.credits_completed,
                s.sem_no,
                d.domain_name as preferred_domain
            FROM User u
            JOIN Student s ON u.UID = s.student_id
            LEFT JOIN Domain d ON s.preferred_domain = d.domain_id
            WHERE u.UID = %s LIMIT 1;
        """
        cursor.execute(query, (student_id,))
        student = cursor.fetchone()

        cursor.close()
        conn.close()

        if not student:
            return {"status": "error", "message": "Student profile not found."}

        # Calculate derived attribute: credits_completed / (sem_no - 1)
        sem_no = student.get("sem_no")
        credits_completed = student.get("credits_completed") or 0

        if sem_no and sem_no > 1:
            credits_per_sem = round(credits_completed / (sem_no - 1), 2)
        else:
            credits_per_sem = float(credits_completed)

        student["credits_completed_per_semester"] = credits_per_sem

        if student.get("CGPA") is not None:
            student["CGPA"] = float(student["CGPA"])

        return {"status": "ok", "student": student}

    except Exception as e:
        return {"status": "error", "message": str(e)}

