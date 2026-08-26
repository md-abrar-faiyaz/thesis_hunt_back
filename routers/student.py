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


@router.get("/faculties")
def search_faculties(
    q: Optional[str] = None,
    ug_pg: Optional[List[str]] = Query(None),
    designations: Optional[List[str]] = Query(None),
    sort_by: Optional[List[str]] = Query(None)
):
    """
    Search faculties based on specification #7 in INTERFACES.md:
    - Search using faculty name, initial (f.Fac_initial), research domain (d.domain_name), and semester free from (f.sem_free_from).
    - Filter by UG, PG or both (f.UG_PG) and designations (f.designation) using checkboxes.
    - Sort by number of groups supervised and number of publications in DESCENDING order via checkboxes.
    - Default sort if no checkbox checked: u.UID ASC.
    """
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
                    if val_clean and val_clean not in clean_ug_pg:
                        clean_ug_pg.append(val_clean)

        if clean_ug_pg:
            placeholders = ", ".join(["%s"] * len(clean_ug_pg))
            query += f" AND f.UG_PG IN ({placeholders})"
            params.extend(clean_ug_pg)

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


