"""
Faculty Meetings Router
Handles fetching and booking meetings for thesis groups supervised by the faculty.
"""
from fastapi import APIRouter
from database import get_db_connection
from schemas import FacultyMeetingBookRequest

router = APIRouter()


@router.get("/meetings/{faculty_id}")
def get_faculty_meetings(faculty_id: int):
    """
    Fetch all meetings requested by the thesis groups the faculty is a supervisor/co-supervisor of,
    or requested by the faculty member themselves.
    Returns meeting date, slot, link_or_room, Approve_Stat, host information (name, profile ID), and group title.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT DISTINCT
                m.meeting_id,
                m.date,
                m.slot,
                m.link_or_room,
                m.Approve_Stat as approve_stat,
                m.host_id,
                m.group_id,
                u_host.name as host_name,
                u_host.email as host_email,
                f_host.Fac_initial as host_fac_initial,
                s_host.student_id as host_student_id,
                CASE 
                    WHEN f_host.faculty_id IS NOT NULL THEN 'Faculty'
                    WHEN s_host.student_id IS NOT NULL THEN 'Student'
                    ELSE 'User'
                END as host_role,
                COALESCE(t.title, 'No Thesis Title') as thesis_title,
                COALESCE(d.domain_name, 'Domain Not Specified') as domain
            FROM Meeting m
            JOIN User u_host ON m.host_id = u_host.UID
            LEFT JOIN Faculty f_host ON u_host.UID = f_host.faculty_id
            LEFT JOIN Student s_host ON u_host.UID = s_host.student_id
            LEFT JOIN ThesisGroup tg ON m.group_id = tg.group_id
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            LEFT JOIN Domain d ON t.research_domain = d.domain_id
            LEFT JOIN Supervises sup ON tg.group_id = sup.group_id
            WHERE m.host_id = %s OR sup.supervisor_id = %s
            ORDER BY m.date DESC, m.meeting_id DESC;
        """
        cursor.execute(query, (faculty_id, faculty_id))
        meetings = cursor.fetchall()

        for m in meetings:
            if m.get("date"):
                m["date"] = str(m["date"])

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(meetings), "meetings": meetings}

    except Exception as e:
        return {"status": "error", "message": str(e), "meetings": []}


@router.post("/meetings/book")
def book_faculty_meeting(req: FacultyMeetingBookRequest):
    """
    Allow a faculty member to book a meeting with a thesis group they supervise.
    Creates a Meeting record with host_id = faculty_id and Approve_Stat = 'Approved'.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify faculty is a supervisor of the target group
        cursor.execute(
            "SELECT 1 FROM Supervises WHERE supervisor_id = %s AND group_id = %s LIMIT 1;",
            (req.faculty_id, req.group_id)
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You can only book meetings with thesis groups you supervise."}

        cursor.execute(
            """
            INSERT INTO Meeting (date, slot, link_or_room, Approve_Stat, host_id, group_id)
            VALUES (%s, %s, %s, 'Approved', %s, %s);
            """,
            (req.date, req.slot, req.link_or_room or "To be shared", req.faculty_id, req.group_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Meeting scheduled successfully!"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
