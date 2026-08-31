from typing import Optional, List
from fastapi import APIRouter, Query
from database import get_db_connection
from schemas import StudentProfileUpdateRequest
from routers.auth import resolve_domain_id, to_bool

router = APIRouter()


@router.get("/search")
def search_students(
    q: Optional[str] = None,
    has_completed_thesis: Optional[bool] = None,
    available_only: Optional[bool] = None,
    gender: Optional[str] = None,
    sort_by: Optional[List[str]] = Query(None)
):
    """Search, filter, and sort student records."""
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
    """Fetch profile information for a student."""
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

        student["has_done_thesis"] = to_bool(student.get("has_done_thesis"))
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


@router.put("/profile/{student_id}")
def update_student_profile(student_id: int, req: StudentProfileUpdateRequest):
    """Update student profile details."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """UPDATE Student 
               SET CGPA = %s, credits_completed = %s, sem_no = %s, preferred_domain = %s 
               WHERE student_id = %s;""",
            (req.cgpa, req.credits_completed, req.sem_no, domain_id, student_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Student profile updated successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/faculties")
def search_faculties(
    q: Optional[str] = None,
    ug_pg: Optional[List[str]] = Query(None),
    designations: Optional[List[str]] = Query(None),
    sort_by: Optional[List[str]] = Query(None)
):
    """Search, filter, and sort faculty supervisor records."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

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
                d.domain_name as research_domain,
                COUNT(DISTINCT ab.paper_id) as num_publications,
                COUNT(DISTINCT sup.group_id) as current_groups_supervised,
                GROUP_CONCAT(DISTINCT w.website_link SEPARATOR '||') as website_links
            FROM User u
            JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Domain d ON f.work_on_domain = d.domain_id
            LEFT JOIN AuthoredBy ab ON u.UID = ab.author_id
            LEFT JOIN Supervises sup ON f.faculty_id = sup.supervisor_id
            LEFT JOIN Websites w ON f.faculty_id = w.creator_id
            WHERE 1=1
        """
        params = []

        if q and q.strip():
            search_pattern = f"%{q.strip()}%"
            query += " AND (u.name LIKE %s OR f.Fac_initial LIKE %s OR d.domain_name LIKE %s OR f.sem_free_from LIKE %s)"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

        clean_ug_pg = []
        if ug_pg:
            for item in ug_pg:
                for val in item.split(","):
                    val_clean = val.strip()
                    if val_clean:
                        if val_clean.lower() in ["undergraduate", "ug"]:
                            clean_ug_pg.append("UG")
                        elif val_clean.lower() in ["postgraduate", "pg"]:
                            clean_ug_pg.append("PG")
                        elif val_clean.lower() in ["both"]:
                            clean_ug_pg.append("Both")
                        else:
                            clean_ug_pg.append(val_clean)

        if clean_ug_pg:
            ug_pg_conditions = []
            if "UG" in clean_ug_pg:
                ug_pg_conditions.append("(f.UG_PG = 'UG' OR f.UG_PG = 'Undergraduate' OR f.UG_PG = 'Both' OR f.UG_PG LIKE '%%UG%%')")
            if "PG" in clean_ug_pg:
                ug_pg_conditions.append("(f.UG_PG = 'PG' OR f.UG_PG = 'Postgraduate' OR f.UG_PG = 'Both' OR f.UG_PG LIKE '%%PG%%')")
            if "Both" in clean_ug_pg:
                ug_pg_conditions.append("(f.UG_PG = 'Both' OR f.UG_PG LIKE '%%Both%%')")

            other_vals = [v for v in clean_ug_pg if v not in ["UG", "PG", "Both"]]
            if other_vals:
                placeholders = ", ".join(["%s"] * len(other_vals))
                ug_pg_conditions.append(f"f.UG_PG IN ({placeholders})")
                params.extend(other_vals)

            if ug_pg_conditions:
                query += " AND (" + " OR ".join(ug_pg_conditions) + ")"

        clean_designations = []
        if designations:
            for item in designations:
                for val in item.split(","):
                    val_clean = val.strip()
                    if val_clean and val_clean not in clean_designations:
                        clean_designations.append(val_clean)

        if clean_designations:
            placeholders = ", ".join(["%s"] * len(clean_designations))
            query += f" AND f.designation IN ({placeholders})"
            params.extend(clean_designations)

        query += """
            GROUP BY 
                u.UID, u.name, u.email, u.gender, f.Fac_initial, f.designation,
                f.UG_PG, f.sem_free_from, f.max_grp_per_sem, f.total_supervised,
                f.room_no, f.calendar_link, d.domain_name
        """

        clean_sorts = []
        if sort_by:
            for item in sort_by:
                for s in item.split(","):
                    clean_s = s.strip().lower()
                    if clean_s and clean_s not in clean_sorts:
                        clean_sorts.append(clean_s)

        order_clauses = []
        sort_map = {
            "groups_supervised": "f.total_supervised DESC",
            "publications": "num_publications DESC"
        }

        for key in clean_sorts:
            if key in sort_map:
                order_clauses.append(sort_map[key])

        if order_clauses:
            query += " ORDER BY " + ", ".join(order_clauses) + ", u.UID ASC"
        else:
            query += " ORDER BY u.UID ASC"

        cursor.execute(query, tuple(params))
        faculties = cursor.fetchall()

        cursor.close()
        conn.close()

        for fac in faculties:
            fac["num_publications"] = int(fac.get("num_publications") or 0)
            total_sup = int(fac.get("total_supervised") or 0)
            curr_sup = int(fac.get("current_groups_supervised") or 0)
            fac["total_supervised"] = total_sup
            fac["current_groups_supervised"] = curr_sup
            fac["all_supervised_count"] = total_sup + curr_sup

            raw_websites = fac.get("website_links")
            if raw_websites:
                fac["websites"] = [w.strip() for w in raw_websites.split("||") if w.strip()]
            else:
                fac["websites"] = []

        return {"status": "ok", "count": len(faculties), "faculties": faculties}

    except Exception as e:
        return {"status": "error", "message": str(e)}
