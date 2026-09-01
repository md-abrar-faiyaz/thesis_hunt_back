"""
Faculty Blogposts Router
Handles research blog post creation, listing, searching, editing, and deleting for faculties.
"""
from typing import Optional
from fastapi import APIRouter
from database import get_db_connection
from schemas import BlogPostCreateRequest, BlogPostUpdateRequest
from routers.auth import resolve_domain_id

router = APIRouter()


@router.get("/blogposts")
def search_blogposts(
    q: Optional[str] = None,
    writer_name: Optional[str] = None,
    domain: Optional[str] = None
):
    """
    Fetch all research blog posts with writer name, formatted timestamp, topic domain, title, and content.
    Supports searching by title, writer name, and topic domain. Results naturally sorted by timestamp DESC.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                b.post_id,
                b.title,
                b.content_guideline as content,
                b.created_at,
                DATE_FORMAT(CONVERT_TZ(b.created_at, @@session.time_zone, '+06:00'), '%b %d, %Y') as formatted_date,
                DATEDIFF(CURRENT_TIMESTAMP, b.created_at) as days_ago,
                b.posted_by,
                u.name as writer_name,
                f.Fac_initial as writer_initial,
                CASE 
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    WHEN s.student_id IS NOT NULL THEN 'Student'
                    ELSE 'User'
                END as writer_role,
                COALESCE(d.domain_name, 'General Research') as domain_name
            FROM BlogPost b
            JOIN User u ON b.posted_by = u.UID
            LEFT JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Student s ON u.UID = s.student_id
            LEFT JOIN Domain d ON b.topic_domain = d.domain_id
            WHERE 1=1
        """
        params = []

        if q and q.strip():
            pattern = f"%{q.strip()}%"
            query += " AND (b.title LIKE %s OR b.content_guideline LIKE %s)"
            params.extend([pattern, pattern])

        if writer_name and writer_name.strip():
            w_pattern = f"%{writer_name.strip()}%"
            query += " AND u.name LIKE %s"
            params.append(w_pattern)

        if domain and domain.strip():
            d_pattern = f"%{domain.strip()}%"
            query += " AND d.domain_name LIKE %s"
            params.append(d_pattern)

        query += " ORDER BY b.created_at DESC, b.post_id DESC;"

        cursor.execute(query, tuple(params))
        posts = cursor.fetchall()

        for p in posts:
            days = p.get("days_ago")
            if days == 0 or days is None:
                p["timestamp_display"] = "Today"
            elif days == 1:
                p["timestamp_display"] = "1 day ago"
            else:
                p["timestamp_display"] = f"{days} days ago"

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(posts), "posts": posts}

    except Exception as e:
        return {"status": "error", "message": str(e), "posts": []}


@router.post("/blogposts")
def create_blogpost(req: BlogPostCreateRequest):
    """Publish a new research blog post."""
    try:
        if not req.title or not req.title.strip():
            return {"status": "error", "message": "Blog title cannot be empty."}
        if not req.content or not req.content.strip():
            return {"status": "error", "message": "Blog content cannot be empty."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """
            INSERT INTO BlogPost (title, content_guideline, posted_by, topic_domain)
            VALUES (%s, %s, %s, %s);
            """,
            (req.title.strip(), req.content.strip(), req.posted_by, domain_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Blog post published successfully!"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.put("/blogposts/{post_id}")
def update_blogpost(post_id: int, req: BlogPostUpdateRequest):
    """Edit an existing blog post (only allowed by author)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT posted_by FROM BlogPost WHERE post_id = %s LIMIT 1;", (post_id,))
        post = cursor.fetchone()
        if not post or post["posted_by"] != req.posted_by:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Unauthorized to edit this post."}

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """
            UPDATE BlogPost 
            SET title = %s, content_guideline = %s, topic_domain = %s 
            WHERE post_id = %s;
            """,
            (req.title.strip(), req.content.strip(), domain_id, post_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Blog post updated successfully!"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/blogposts/{post_id}")
def delete_blogpost(post_id: int, user_id: int):
    """Delete a blog post (only allowed by author)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "DELETE FROM BlogPost WHERE post_id = %s AND posted_by = %s;",
            (post_id, user_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Blog post deleted successfully!"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
