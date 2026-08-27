from typing import Optional, List
from fastapi import APIRouter, Query
from database import get_db_connection
from schemas import BlogPostCreateRequest, PublicationCreateRequest

from routers.auth import resolve_domain_id

router = APIRouter(prefix="/api/student", tags=["Student Interface"])



@router.get("/search")
def search_students(
    q: Optional[str] = None,
    has_completed_thesis: Optional[bool] = None,
    available_only: Optional[bool] = None,
    gender: Optional[str] = None,
    sort_by: Optional[List[str]] = Query(None)
):

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


@router.get("/blogposts")
def get_blogposts(q: Optional[str] = None):
    """Fetch blog posts with writer details, formatted timestamp, and topic domain."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                bp.post_id,
                bp.title,
                bp.content_guideline as content,
                bp.created_at,
                DATE_FORMAT(bp.created_at, '%d %M, %Y') as formatted_date,
                u.UID as posted_by_id,
                u.name as writer_name,
                CASE 
                    WHEN s.student_id IS NOT NULL THEN 'Student'
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    ELSE 'User'
                END as writer_role,
                d.domain_name as topic_domain
            FROM BlogPost bp
            LEFT JOIN User u ON bp.posted_by = u.UID
            LEFT JOIN Student s ON u.UID = s.student_id
            LEFT JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Domain d ON bp.topic_domain = d.domain_id
            WHERE 1=1
        """
        params = []

        if q and q.strip():
            search_pattern = f"%{q.strip()}%"
            query += " AND (bp.title LIKE %s OR u.name LIKE %s OR d.domain_name LIKE %s)"
            params.extend([search_pattern, search_pattern, search_pattern])

        query += " ORDER BY bp.created_at DESC, bp.post_id DESC"

        cursor.execute(query, tuple(params))
        posts = cursor.fetchall()

        cursor.close()
        conn.close()

        # Post-process formatted date fallback
        for post in posts:
            if not post.get("formatted_date") and post.get("created_at"):
                dt = post["created_at"]
                post["formatted_date"] = dt.strftime("%d %B, %Y") if hasattr(dt, 'strftime') else str(dt)
            elif not post.get("formatted_date"):
                post["formatted_date"] = "Unknown Date"

        return {"status": "ok", "count": len(posts), "posts": posts}

    except Exception as e:
        return {"status": "error", "message": str(e), "posts": []}


@router.post("/blogpost")
def create_blogpost(req: BlogPostCreateRequest):
    """Create a new blog post written by a student or faculty member."""
    try:
        if not req.title or not req.title.strip():
            return {"status": "error", "message": "Post title is required."}
        if not req.content or not req.content.strip():
            return {"status": "error", "message": "Post content is required."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """INSERT INTO BlogPost (title, content_guideline, posted_by, topic_domain)
               VALUES (%s, %s, %s, %s);""",
            (req.title.strip(), req.content.strip(), req.posted_by, domain_id)
        )

        post_id = cursor.lastrowid
        conn.commit()

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "message": "Blog post published successfully!",
            "post_id": post_id
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/publications")
def get_publications(q: Optional[str] = None, category: Optional[str] = None):
    """Fetch publications with author details, journal category, publication date, domain, and DOI/link."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                p.publication_id,
                p.title,
                p.journal_category,
                p.publication_date,
                DATE_FORMAT(p.publication_date, '%d %M, %Y') as formatted_date,
                p.link,
                d.domain_name
            FROM Publication p
            LEFT JOIN Domain d ON p.paper_domain = d.domain_id
            WHERE 1=1
        """
        params = []

        if q and q.strip():
            search_pattern = f"%{q.strip()}%"
            query += " AND (p.title LIKE %s OR d.domain_name LIKE %s)"
            params.extend([search_pattern, search_pattern])

        if category and category.strip() and category.strip() != 'All':
            query += " AND p.journal_category = %s"
            params.append(category.strip())

        query += " ORDER BY p.publication_date DESC, p.publication_id DESC"

        cursor.execute(query, tuple(params))
        publications = cursor.fetchall()

        for pub in publications:
            cursor.execute(
                """
                SELECT 
                    ab.author_id,
                    ab.author_order,
                    u.name as name,
                    CASE 
                        WHEN s.student_id IS NOT NULL THEN 'Student'
                        WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                        ELSE 'User'
                    END as role
                FROM AuthoredBy ab
                JOIN User u ON ab.author_id = u.UID
                LEFT JOIN Student s ON u.UID = s.student_id
                LEFT JOIN Faculty f ON u.UID = f.faculty_id
                WHERE ab.paper_id = %s
                ORDER BY ab.author_order ASC
                """,
                (pub["publication_id"],)
            )
            pub["authors"] = cursor.fetchall()

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(publications), "publications": publications}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/publication")
def create_publication(req: PublicationCreateRequest):
    """Create a new publication and link authors in AuthoredBy table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """INSERT INTO Publication (title, journal_category, publication_date, link, paper_domain)
               VALUES (%s, %s, %s, %s, %s);""",
            (
                req.title.strip(),
                req.journal_category.strip() if req.journal_category else None,
                req.publication_date if req.publication_date else None,
                req.link.strip() if req.link else None,
                domain_id
            )
        )
        publication_id = cursor.lastrowid

        if req.authors:
            for author in req.authors:
                cursor.execute(
                    """INSERT INTO AuthoredBy (author_id, paper_id, author_order)
                       VALUES (%s, %s, %s);""",
                    (author.author_id, publication_id, author.author_order)
                )

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "message": "Publication added successfully!",
            "publication_id": publication_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/users-list")
def get_users_list():
    """Fetch registered users list for co-author selection."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 
                u.UID as uid,
                u.name,
                u.email,
                CASE 
                    WHEN s.student_id IS NOT NULL THEN 'Student'
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    ELSE 'User'
                END as role
            FROM User u
            LEFT JOIN Student s ON u.UID = s.student_id
            LEFT JOIN Faculty f ON u.UID = f.faculty_id
            ORDER BY u.name ASC
            """
        )
        users = cursor.fetchall()
        cursor.close()
        conn.close()

        return {"status": "ok", "users": users}
    except Exception as e:
        return {"status": "error", "message": str(e)}




