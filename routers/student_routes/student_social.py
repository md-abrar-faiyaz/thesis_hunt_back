from typing import Optional
from fastapi import APIRouter
from database import get_db_connection
from schemas import (
    BlogPostCreateRequest,
    BlogPostUpdateRequest,
    PublicationCreateRequest
)
from routers.auth import resolve_domain_id

router = APIRouter()


@router.get("/blogposts")
def get_blogposts(q: Optional[str] = None, author_id: Optional[int] = None, weeks: Optional[int] = 2):
    """Fetch blog posts with writer details, formatted timestamp, and topic domain."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if weeks is None or weeks <= 0:
            weeks = 2

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

        if author_id is not None:
            query += " AND bp.posted_by = %s"
            params.append(author_id)

        days_limit = weeks * 7
        query += " AND (bp.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY) OR bp.created_at IS NULL)"
        params.append(days_limit)

        query += " ORDER BY bp.created_at DESC, bp.post_id DESC"

        cursor.execute(query, tuple(params))
        posts = cursor.fetchall()

        check_query = """
            SELECT COUNT(*) as older_count
            FROM BlogPost bp
            LEFT JOIN User u ON bp.posted_by = u.UID
            LEFT JOIN Domain d ON bp.topic_domain = d.domain_id
            WHERE 1=1
        """
        check_params = []
        if q and q.strip():
            search_pattern = f"%{q.strip()}%"
            check_query += " AND (bp.title LIKE %s OR u.name LIKE %s OR d.domain_name LIKE %s)"
            check_params.extend([search_pattern, search_pattern, search_pattern])

        if author_id is not None:
            check_query += " AND bp.posted_by = %s"
            check_params.append(author_id)

        check_query += " AND bp.created_at < DATE_SUB(NOW(), INTERVAL %s DAY)"
        check_params.append(days_limit)

        cursor.execute(check_query, tuple(check_params))
        check_res = cursor.fetchone()
        has_more = bool(check_res and check_res.get("older_count", 0) > 0)

        cursor.close()
        conn.close()

        for post in posts:
            if not post.get("formatted_date") and post.get("created_at"):
                dt = post["created_at"]
                post["formatted_date"] = dt.strftime("%d %B, %Y") if hasattr(dt, 'strftime') else str(dt)
            elif not post.get("formatted_date"):
                post["formatted_date"] = "Unknown Date"

        return {"status": "ok", "count": len(posts), "posts": posts, "has_more": has_more}

    except Exception as e:
        return {"status": "error", "message": str(e), "posts": [], "has_more": False}


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


@router.put("/blogpost/{post_id}")
def update_blogpost(post_id: int, req: BlogPostUpdateRequest):
    """Update a blog post title, topic domain, and content."""
    try:
        if not req.title or not req.title.strip():
            return {"status": "error", "message": "Post title is required."}
        if not req.content or not req.content.strip():
            return {"status": "error", "message": "Post content is required."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """UPDATE BlogPost 
               SET title = %s, content_guideline = %s, topic_domain = %s 
               WHERE post_id = %s AND posted_by = %s;""",
            (req.title.strip(), req.content.strip(), domain_id, post_id, req.posted_by)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Blog post updated successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/publications")
def get_publications(q: Optional[str] = None, category: Optional[str] = None, author_id: Optional[int] = None):
    """Fetch publications with author details, journal category, publication date, domain, and link."""
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

        if author_id is not None:
            query += " AND EXISTS (SELECT 1 FROM AuthoredBy ab_sub WHERE ab_sub.paper_id = p.publication_id AND ab_sub.author_id = %s)"
            params.append(author_id)

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
