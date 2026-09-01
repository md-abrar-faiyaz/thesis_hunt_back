"""
Faculty Publications Router
Handles listing, searching, filtering, sorting, and adding research publications.
"""
from typing import Optional, List
from fastapi import APIRouter
from database import get_db_connection
from schemas import PublicationCreateRequest
from routers.auth import resolve_domain_id

router = APIRouter()


@router.get("/publications")
def get_faculty_publications(
    q: Optional[str] = None,
    journal_category: Optional[str] = None,
    domain: Optional[str] = None,
    sort_by_date: Optional[str] = 'desc'
):
    """
    Fetch all publications from MySQL.
    Supports searching by title, filtering by journal category and domain, and sorting by publication date.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                p.publication_id,
                p.title,
                p.journal_category,
                p.publication_date,
                DATE_FORMAT(p.publication_date, '%b %d, %Y') as formatted_date,
                p.link,
                COALESCE(d.domain_name, 'General Science') as domain_name
            FROM Publication p
            LEFT JOIN Domain d ON p.paper_domain = d.domain_id
            WHERE 1=1
        """
        params = []

        if q and q.strip():
            pattern = f"%{q.strip()}%"
            query += " AND p.title LIKE %s"
            params.append(pattern)

        if journal_category and journal_category.strip():
            cat_pattern = f"%{journal_category.strip()}%"
            query += " AND p.journal_category LIKE %s"
            params.append(cat_pattern)

        if domain and domain.strip():
            dom_pattern = f"%{domain.strip()}%"
            query += " AND d.domain_name LIKE %s"
            params.append(dom_pattern)

        if sort_by_date and sort_by_date.lower() == 'asc':
            query += " ORDER BY p.publication_date ASC, p.publication_id ASC;"
        else:
            query += " ORDER BY p.publication_date DESC, p.publication_id DESC;"

        cursor.execute(query, tuple(params))
        publications = cursor.fetchall()

        # For each publication, fetch authored authors from AuthoredBy & User
        for pub in publications:
            pid = pub["publication_id"]
            if pub.get("publication_date"):
                pub["publication_date"] = str(pub["publication_date"])

            author_query = """
                SELECT 
                    ab.author_id,
                    ab.author_order,
                    u.name as author_name,
                    u.email as author_email,
                    CASE 
                        WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                        WHEN s.student_id IS NOT NULL THEN 'Student'
                        ELSE 'User'
                    END as role
                FROM AuthoredBy ab
                JOIN User u ON ab.author_id = u.UID
                LEFT JOIN Faculty f ON u.UID = f.faculty_id
                LEFT JOIN Student s ON u.UID = s.student_id
                WHERE ab.paper_id = %s
                ORDER BY ab.author_order ASC;
            """
            cursor.execute(author_query, (pid,))
            pub["authors"] = cursor.fetchall()

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(publications), "publications": publications}

    except Exception as e:
        return {"status": "error", "message": str(e), "publications": []}


@router.post("/publications")
def create_faculty_publication(req: PublicationCreateRequest):
    """
    Allow faculty to add a new publication to the repository and attach authors.
    Inserts into Publication and AuthoredBy tables.
    """
    try:
        if not req.title or not req.title.strip():
            return {"status": "error", "message": "Publication title cannot be empty."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """
            INSERT INTO Publication (title, journal_category, publication_date, link, paper_domain)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (req.title.strip(), req.journal_category, req.publication_date or None, req.link, domain_id)
        )
        paper_id = cursor.lastrowid

        # Insert author relationships into AuthoredBy table
        if req.authors:
            for auth in req.authors:
                cursor.execute(
                    """
                    INSERT INTO AuthoredBy (author_id, paper_id, author_order)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE author_order = VALUES(author_order);
                    """,
                    (auth.author_id, paper_id, auth.author_order)
                )

        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Publication published successfully!", "publication_id": paper_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}
