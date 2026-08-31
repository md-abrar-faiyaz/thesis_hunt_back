from fastapi import APIRouter
from database import get_db_connection
from schemas import MeetingCreateRequest, MeetingRespondRequest

router = APIRouter()


@router.get("/meetings/{student_id}")
def get_student_meetings(student_id: int):
    """Get all meetings for the student's thesis group and available hosts."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;", (student_id,))
        st = cursor.fetchone()

        cursor.execute(
            """
            SELECT 
                m.meeting_id,
                m.date,
                m.slot,
                m.link_or_room,
                m.Approve_Stat AS approve_stat,
                m.group_id,
                m.host_id,
                COALESCE(t.title, CONCAT('Group #', m.group_id)) AS group_title,
                COALESCE(d.domain_name, '') AS group_domain
            FROM Meeting m
            LEFT JOIN ThesisGroup tg ON m.group_id = tg.group_id
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            LEFT JOIN Domain d ON t.research_domain = d.domain_id
            WHERE m.host_id = %s
            ORDER BY m.date DESC, m.meeting_id DESC;
            """,
            (student_id,)
        )
        inc_raw = cursor.fetchall()
        incoming_meetings = []
        for inc in inc_raw:
            inc["date_str"] = str(inc["date"]) if inc.get("date") else ""
            incoming_meetings.append(inc)

        if not st or not st.get("thesis_group"):
            cursor.close()
            conn.close()
            return {
                "status": "ok",
                "has_group": False,
                "approved_meetings": [],
                "pending_meetings": [],
                "rejected_meetings": [],
                "incoming_meetings": incoming_meetings,
                "hosts": [],
                "supervisors": []
            }

        group_id = st["thesis_group"]

        cursor.execute(
            """
            SELECT 
                m.meeting_id,
                m.date,
                m.slot,
                m.link_or_room,
                m.Approve_Stat AS approve_stat,
                m.host_id,
                m.group_id,
                u.name AS host_name,
                u.email AS host_email,
                CASE WHEN f.faculty_id IS NOT NULL THEN 'Faculty' ELSE 'Student' END AS host_role,
                f.Fac_initial AS host_initial
            FROM Meeting m
            LEFT JOIN User u ON m.host_id = u.UID
            LEFT JOIN Faculty f ON m.host_id = f.faculty_id
            WHERE m.group_id = %s
            ORDER BY m.date ASC, m.meeting_id DESC;
            """,
            (group_id,)
        )
        all_meetings = cursor.fetchall()

        approved = []
        pending = []
        rejected = []

        for m in all_meetings:
            m["date_str"] = str(m["date"]) if m.get("date") else ""
            stat = (m.get("approve_stat") or "").lower()
            if stat == "approved":
                approved.append(m)
            elif stat == "rejected":
                rejected.append(m)
            else:
                pending.append(m)

        cursor.execute(
            """
            SELECT 
                u.UID AS host_id,
                u.name,
                u.email,
                CASE WHEN f.faculty_id IS NOT NULL THEN 'Faculty' ELSE 'Student' END AS role,
                f.Fac_initial AS initial,
                s.student_id
            FROM User u
            LEFT JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Student s ON u.UID = s.student_id
            WHERE u.UID != %s
            ORDER BY u.name ASC;
            """,
            (student_id,)
        )
        all_hosts = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                sup.supervisor_id AS host_id,
                u.name,
                u.email,
                sup.role AS sup_role,
                f.Fac_initial AS initial
            FROM Supervises sup
            JOIN Faculty f ON sup.supervisor_id = f.faculty_id
            JOIN User u ON f.faculty_id = u.UID
            WHERE sup.group_id = %s;
            """,
            (group_id,)
        )
        supervisors = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "has_group": True,
            "group_id": group_id,
            "approved_meetings": approved,
            "pending_meetings": pending,
            "rejected_meetings": rejected,
            "incoming_meetings": incoming_meetings,
            "hosts": all_hosts,
            "supervisors": supervisors
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "approved_meetings": [],
            "pending_meetings": [],
            "rejected_meetings": [],
            "incoming_meetings": [],
            "hosts": [],
            "supervisors": []
        }


@router.post("/meeting/request")
def request_meeting(req: MeetingCreateRequest):
    """Request a meeting for a thesis group with schedule conflict checking."""
    try:
        if req.host_id == req.student_id:
            return {"status": "error", "message": "You cannot schedule a meeting with yourself."}

        if not req.date or not req.slot:
            return {"status": "error", "message": "Date and time slot are required."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT meeting_id FROM Meeting 
            WHERE host_id = %s 
              AND date = %s 
              AND slot = %s 
              AND (Approve_Stat = 'Approved' OR Approve_Stat = 'Pending')
            LIMIT 1;
            """,
            (req.host_id, req.date, req.slot.strip())
        )
        conflict = cursor.fetchone()
        if conflict:
            cursor.close()
            conn.close()
            return {
                "status": "error",
                "message": "Schedule Conflict: The selected host already has a meeting scheduled at this date and time slot."
            }

        cursor.execute(
            """
            INSERT INTO Meeting (date, slot, link_or_room, Approve_Stat, host_id, group_id)
            VALUES (%s, %s, %s, 'Pending', %s, %s);
            """,
            (req.date, req.slot.strip(), req.link_or_room.strip() if req.link_or_room else None, req.host_id, req.group_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Meeting requested successfully! Awaiting host approval."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/meeting/{meeting_id}")
def delete_meeting(meeting_id: int, student_id: int):
    """Remove/delete a meeting record."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;", (student_id,))
        st = cursor.fetchone()
        if not st or not st.get("thesis_group"):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Student has no thesis group."}

        group_id = st["thesis_group"]

        cursor.execute(
            "DELETE FROM Meeting WHERE meeting_id = %s AND group_id = %s;",
            (meeting_id, group_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Meeting removed successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/meeting/respond")
def respond_meeting(req: MeetingRespondRequest):
    """Host accepts or rejects a meeting request."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT meeting_id, host_id FROM Meeting WHERE meeting_id = %s AND host_id = %s;",
            (req.meeting_id, req.host_id)
        )
        meeting = cursor.fetchone()
        if not meeting:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Meeting request not found or unauthorized."}

        action = (req.action or "").lower()

        if action == "accept":
            if not req.link_or_room or not req.link_or_room.strip():
                cursor.close()
                conn.close()
                return {"status": "error", "message": "Please provide a room number or meeting link to accept."}

            cursor.execute(
                """
                UPDATE Meeting 
                SET Approve_Stat = 'Approved', link_or_room = %s 
                WHERE meeting_id = %s AND host_id = %s;
                """,
                (req.link_or_room.strip(), req.meeting_id, req.host_id)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return {"status": "ok", "message": "Meeting request approved successfully!"}

        elif action == "reject":
            cursor.execute(
                """
                UPDATE Meeting 
                SET Approve_Stat = 'Rejected' 
                WHERE meeting_id = %s AND host_id = %s;
                """,
                (req.meeting_id, req.host_id)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return {"status": "ok", "message": "Meeting request rejected."}

        else:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Invalid action."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
