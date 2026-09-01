"""
Faculty Groups & Group Channel Router
Handles fetching supervised thesis groups and managing group chat interactions for faculty.
"""
from typing import Optional
from fastapi import APIRouter
from database import get_db_connection
from schemas import GroupMessageCreateRequest

router = APIRouter()


@router.get("/groups/{faculty_id}")
def get_faculty_supervised_groups(faculty_id: int, role: Optional[str] = None):
    """
    Fetch all thesis groups where the faculty member is assigned as supervisor or co-supervisor.
    Returns group details, thesis title, description, research domain, and all member student details.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Query thesis groups supervised by faculty in Supervises junction table
        query = """
            SELECT 
                sup.group_id,
                sup.role as faculty_role,
                sup.semester,
                tg.formation_status,
                t.thesis_id,
                COALESCE(t.title, 'No Thesis Topic Selected Yet') as title,
                COALESCE(t.description, 'No description available.') as description,
                COALESCE(d.domain_name, 'Domain Not Specified') as domain
            FROM Supervises sup
            JOIN ThesisGroup tg ON sup.group_id = tg.group_id
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            LEFT JOIN Domain d ON t.research_domain = d.domain_id
            WHERE sup.supervisor_id = %s
        """
        params = [faculty_id]

        if role and role.strip().lower() != 'all':
            query += " AND LOWER(sup.role) = %s"
            params.append(role.strip().lower())

        query += " ORDER BY sup.group_id DESC;"

        cursor.execute(query, tuple(params))
        groups = cursor.fetchall()

        # For each group, fetch members (students) and supervisors list
        for g in groups:
            gid = g["group_id"]

            # Query group members from Student & User tables
            member_query = """
                SELECT 
                    s.student_id,
                    u.name,
                    u.email,
                    u.gender,
                    s.CGPA,
                    s.credits_completed,
                    s.sem_no,
                    CASE WHEN s.sem_no > 1 THEN (s.sem_no - 1) ELSE 0 END as semesters_completed,
                    ROUND(s.credits_completed / NULLIF(s.sem_no - 1, 0), 2) as credits_per_sem
                FROM Student s
                JOIN User u ON s.student_id = u.UID
                WHERE s.thesis_group = %s
                ORDER BY u.name ASC;
            """
            cursor.execute(member_query, (gid,))
            members = cursor.fetchall()
            for m in members:
                if m.get("CGPA") is not None:
                    m["CGPA"] = float(m["CGPA"])
                if m.get("credits_per_sem") is None:
                    m["credits_per_sem"] = float(m.get("credits_completed", 0))
                else:
                    m["credits_per_sem"] = float(m["credits_per_sem"])
            g["members"] = members

            # Query all supervisors/co-supervisors assigned to this group
            sup_query = """
                SELECT 
                    sup_all.supervisor_id,
                    sup_all.role,
                    sup_all.semester,
                    u_sup.name,
                    u_sup.email,
                    f_sup.Fac_initial as fac_initial,
                    f_sup.`designation` as designation
                FROM Supervises sup_all
                JOIN Faculty f_sup ON sup_all.supervisor_id = f_sup.faculty_id
                JOIN User u_sup ON f_sup.faculty_id = u_sup.UID
                WHERE sup_all.group_id = %s
                ORDER BY sup_all.role DESC, u_sup.name ASC;
            """
            cursor.execute(sup_query, (gid,))
            g["supervisors"] = cursor.fetchall()

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(groups), "groups": groups}

    except Exception as e:
        return {"status": "error", "message": str(e), "groups": []}


@router.get("/group-channel/{faculty_id}/{group_id}")
def get_faculty_group_channel(faculty_id: int, group_id: int):
    """
    Fetch group information, member roster, supervisor info, and message history for a specific thesis group.
    Ensures the faculty is a supervisor/co-supervisor of the group.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify faculty supervision permission
        cursor.execute(
            "SELECT role FROM Supervises WHERE supervisor_id = %s AND group_id = %s LIMIT 1;",
            (faculty_id, group_id)
        )
        sup_role = cursor.fetchone()
        if not sup_role:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You are not an assigned supervisor/co-supervisor of this thesis group."}

        # Fetch group metadata
        cursor.execute(
            """
            SELECT 
                tg.group_id,
                tg.formation_status,
                t.thesis_id,
                COALESCE(t.title, 'No Thesis Topic Selected Yet') AS title,
                COALESCE(t.description, '') AS description,
                COALESCE(d.domain_name, 'Domain Not Specified') AS domain
            FROM ThesisGroup tg
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            LEFT JOIN Domain d ON t.research_domain = d.domain_id
            WHERE tg.group_id = %s LIMIT 1;
            """,
            (group_id,)
        )
        group_info = cursor.fetchone()

        if not group_info:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Thesis group not found."}

        # Fetch group members
        cursor.execute(
            """
            SELECT s.student_id, u.name, u.email, u.gender, s.CGPA, s.credits_completed, s.sem_no
            FROM Student s
            JOIN User u ON s.student_id = u.UID
            WHERE s.thesis_group = %s
            ORDER BY u.name ASC;
            """,
            (group_id,)
        )
        members = cursor.fetchall()
        for m in members:
            if m.get("CGPA") is not None:
                m["CGPA"] = float(m["CGPA"])
        group_info["members"] = members

        # Fetch all supervisors
        cursor.execute(
            """
            SELECT sup.supervisor_id, sup.role, sup.semester, u.name, u.email, f.Fac_initial AS fac_initial
            FROM Supervises sup
            JOIN Faculty f ON sup.supervisor_id = f.faculty_id
            JOIN User u ON f.faculty_id = u.UID
            WHERE sup.group_id = %s
            ORDER BY sup.role DESC, u.name ASC;
            """,
            (group_id,)
        )
        group_info["supervisors"] = cursor.fetchall()

        # Fetch group messages
        cursor.execute(
            """
            SELECT 
                gm.message_id,
                gm.content,
                gm.sent_by,
                gm.posted_in,
                gm.timestamp,
                DATE_FORMAT(CONVERT_TZ(gm.timestamp, @@session.time_zone, '+06:00'), '%b %d, %Y %h:%i %p') AS formatted_time,
                u.name AS sender_name,
                CASE 
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    WHEN s.student_id IS NOT NULL THEN 'Student'
                    ELSE 'User'
                END AS sender_role
            FROM GroupMessage gm
            JOIN User u ON gm.sent_by = u.UID
            LEFT JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Student s ON u.UID = s.student_id
            WHERE gm.posted_in = %s
            ORDER BY gm.timestamp ASC;
            """,
            (group_id,)
        )
        group_info["messages"] = cursor.fetchall()

        cursor.close()
        conn.close()

        return {"status": "ok", "has_group": True, "group": group_info, "user_role": sup_role["role"]}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group-channel/message")
def send_faculty_group_message(req: GroupMessageCreateRequest):
    """Allow faculty to send a message into their thesis group channel."""
    try:
        if not req.content or not req.content.strip():
            return {"status": "error", "message": "Message content cannot be empty."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify permission
        cursor.execute(
            "SELECT 1 FROM Supervises WHERE supervisor_id = %s AND group_id = %s LIMIT 1;",
            (req.sent_by, req.posted_in)
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You are not a supervisor of this group."}

        cursor.execute(
            """
            INSERT INTO GroupMessage (content, sent_by, posted_in)
            VALUES (%s, %s, %s);
            """,
            (req.content.strip(), req.sent_by, req.posted_in)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Group message posted successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
