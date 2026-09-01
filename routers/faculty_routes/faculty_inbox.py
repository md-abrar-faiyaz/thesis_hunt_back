"""
Faculty Inbox Router
Handles supervisor/co-supervisor requests and meeting requests for faculty.
Enforces Max Group Per Semester logic (Rule 10).
"""
import re
from fastapi import APIRouter
from database import get_db_connection
from schemas import FacultySupervisorResponseRequest, MeetingRespondRequest

router = APIRouter()


def increment_semester_year(sem_str: str) -> str:
    """Helper to increment year in semester string e.g., 'Summer 2026' -> 'Summer 2027'."""
    if not sem_str:
        return "Summer 2027"
    match = re.search(r"^(.*?)\s*(\d{4})$", sem_str.strip())
    if match:
        term, year_str = match.group(1), match.group(2)
        next_year = int(year_str) + 1
        return f"{term} {next_year}"
    return f"{sem_str} 2027"


@router.get("/inbox/{faculty_id}")
def get_faculty_inbox(faculty_id: int):
    """
    Fetch pending requests for a faculty inbox:
    1. Supervisor / Co-Supervisor requests received from thesis groups via Contact table.
    2. Pending Meeting requests received where faculty is host.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Fetch Supervisor / Co-Supervisor requests from Contact table
        cursor.execute(
            """
            SELECT 
                c.sender_id,
                c.receiver_id,
                c.message_text,
                c.status,
                c.timestamp,
                DATE_FORMAT(CONVERT_TZ(c.timestamp, @@session.time_zone, '+06:00'), '%b %d, %Y %h:%i %p') AS formatted_time,
                u.name AS sender_name,
                u.email AS sender_email
            FROM Contact c
            JOIN User u ON c.sender_id = u.UID
            WHERE c.receiver_id = %s AND c.message_text LIKE '[Supervisor Request:%%'
            ORDER BY c.timestamp DESC;
            """,
            (faculty_id,)
        )
        sup_rows = cursor.fetchall()

        supervisor_requests = []
        for r in sup_rows:
            msg_text = r["message_text"]
            # Parse tag: [Supervisor Request:GROUP_ID:ROLE:SEMESTER:STATUS]
            match = re.search(r"\[Supervisor Request:(\d+):([^:\]]+)(?::([^:\]]+))?(?::([^\]]+))?\]\s*(.*)", msg_text, re.DOTALL)
            if match:
                gid = int(match.group(1))
                req_role = match.group(2)
                sem = match.group(3) or "Summer 2026"
                req_status = match.group(4) or "Pending"
                custom_note = match.group(5) or ""

                # Fetch full group details (members & member CGPA, sem_no, credits, thesis info)
                cursor.execute(
                    """
                    SELECT 
                        tg.group_id,
                        tg.formation_status,
                        t.thesis_id,
                        COALESCE(t.title, 'No Thesis Title') as title,
                        COALESCE(t.description, 'No description provided') as description,
                        COALESCE(d.domain_name, 'Domain Not Specified') as domain
                    FROM ThesisGroup tg
                    LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
                    LEFT JOIN Domain d ON t.research_domain = d.domain_id
                    WHERE tg.group_id = %s LIMIT 1;
                    """,
                    (gid,)
                )
                group_info = cursor.fetchone()

                if group_info:
                    # Query members and details
                    cursor.execute(
                        """
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
                        """,
                        (gid,)
                    )
                    members = cursor.fetchall()
                    for m in members:
                        if m.get("CGPA") is not None:
                            m["CGPA"] = float(m["CGPA"])
                        if m.get("credits_per_sem") is None:
                            m["credits_per_sem"] = float(m.get("credits_completed", 0))
                        else:
                            m["credits_per_sem"] = float(m["credits_per_sem"])
                    group_info["members"] = members

                    # Query supervisors
                    cursor.execute(
                        """
                        SELECT sup.supervisor_id, sup.role, sup.semester, u.name, u.email, f.Fac_initial
                        FROM Supervises sup
                        JOIN Faculty f ON sup.supervisor_id = f.faculty_id
                        JOIN User u ON f.faculty_id = u.UID
                        WHERE sup.group_id = %s;
                        """,
                        (gid,)
                    )
                    group_info["supervisors"] = cursor.fetchall()

                supervisor_requests.append({
                    "sender_id": r["sender_id"],
                    "sender_name": r["sender_name"],
                    "sender_email": r["sender_email"],
                    "timestamp": str(r["timestamp"]),
                    "formatted_time": r["formatted_time"],
                    "group_id": gid,
                    "role": req_role,
                    "semester": sem,
                    "status": req_status,
                    "custom_note": custom_note,
                    "group_info": group_info
                })

        # 2. Fetch Meeting requests where faculty is host
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
                u_host.name AS host_name,
                u_host.email AS host_email,
                t.title AS thesis_title,
                d.domain_name AS domain
            FROM Meeting m
            JOIN User u_host ON m.host_id = u_host.UID
            LEFT JOIN ThesisGroup tg ON m.group_id = tg.group_id
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            LEFT JOIN Domain d ON t.research_domain = d.domain_id
            WHERE m.host_id = %s
            ORDER BY m.meeting_id DESC;
            """,
            (faculty_id,)
        )
        meetings = cursor.fetchall()
        for m in meetings:
            if m.get("date"):
                m["date"] = str(m["date"])

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "supervisor_requests": supervisor_requests,
            "meeting_requests": meetings
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/inbox/supervisor-request/respond")
def respond_supervisor_request(req: FacultySupervisorResponseRequest):
    """
    Faculty accepts or rejects a supervisor/co-supervisor request.
    - If accept: Adds record to Supervises table and evaluates Rule 10 (Max Group Per Semester).
      If active supervisions count > max_grp_per_sem, updates sem_free_from to next year.
      Optionally sends faculty calendar link meeting offer into group channel.
    - If reject: Sends plain text feedback to requesting group.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        action = req.action.lower()

        # Update contact notification message status tag if sender_id & timestamp supplied
        if req.sender_id and req.timestamp:
            cursor.execute(
                "SELECT message_text FROM Contact WHERE sender_id = %s AND receiver_id = %s AND timestamp = %s LIMIT 1;",
                (req.sender_id, req.faculty_id, req.timestamp)
            )
            c_row = cursor.fetchone()
            if c_row:
                old_text = c_row["message_text"]
                status_str = "ACCEPTED" if action == "accept" else "REJECTED"
                new_text = re.sub(
                    r"\[Supervisor Request:\d+:[^:\]]+(?::[^:\]]+)?(?::[^\]]+)?\]",
                    f"[Supervisor Request:{req.group_id}:{req.role}:{req.semester}:{status_str}]",
                    old_text
                )
                cursor.execute(
                    "UPDATE Contact SET message_text = %s, status = 'Read' WHERE sender_id = %s AND receiver_id = %s AND timestamp = %s;",
                    (new_text, req.sender_id, req.faculty_id, req.timestamp)
                )

        # Get faculty details for calendar link and max grp settings
        cursor.execute(
            "SELECT calendar_link, max_grp_per_sem, sem_free_from FROM Faculty WHERE faculty_id = %s LIMIT 1;",
            (req.faculty_id,)
        )
        fac_row = cursor.fetchone()
        cal_link = fac_row["calendar_link"] if fac_row else ""
        max_grp = fac_row["max_grp_per_sem"] if fac_row and fac_row["max_grp_per_sem"] else 3
        current_sem_free = fac_row["sem_free_from"] if fac_row and fac_row["sem_free_from"] else "Summer 2026"

        cursor.execute("SELECT name FROM User WHERE UID = %s LIMIT 1;", (req.faculty_id,))
        fac_user = cursor.fetchone()
        fac_name = fac_user["name"] if fac_user else "Faculty"

        if action == "accept":
            # Insert record into Supervises table (or update if exists)
            cursor.execute(
                """
                INSERT INTO Supervises (supervisor_id, group_id, role, semester)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE role = VALUES(role), semester = VALUES(semester);
                """,
                (req.faculty_id, req.group_id, req.role, req.semester)
            )

            # Update ThesisGroup formation_status to 'Approved'
            cursor.execute(
                "UPDATE ThesisGroup SET formation_status = 'Approved' WHERE group_id = %s;",
                (req.group_id,)
            )

            # Check Rule 10: Count active groups supervised by faculty in this semester
            cursor.execute(
                "SELECT COUNT(*) AS active_cnt FROM Supervises WHERE supervisor_id = %s AND semester = %s;",
                (req.faculty_id, req.semester)
            )
            cnt_row = cursor.fetchone()
            active_cnt = cnt_row["active_cnt"] if cnt_row else 0

            # Increment total_supervised counter
            cursor.execute(
                "UPDATE Faculty SET total_supervised = total_supervised + 1 WHERE faculty_id = %s;",
                (req.faculty_id,)
            )

            # Enforce Rule 10: If active groups exceed max_grp_per_sem, increase sem_free_from by 1 year
            sem_message = ""
            if active_cnt > max_grp:
                next_sem_free = increment_semester_year(current_sem_free or req.semester)
                cursor.execute(
                    "UPDATE Faculty SET sem_free_from = %s WHERE faculty_id = %s;",
                    (next_sem_free, req.faculty_id)
                )
                sem_message = f" Supervised groups count ({active_cnt}) exceeded max capacity ({max_grp}). Your sem_free_from updated to {next_sem_free}."

            # Post acceptance notification message to group channel
            note_str = f"\nNote: {req.response_message}" if req.response_message else ""
            meeting_str = f"\nBook a meeting with me using my calendar link: {cal_link}" if req.offer_meeting and cal_link else ""
            
            group_msg_content = f"{fac_name} accepted the request to serve as {req.role} for semester {req.semester}!{note_str}{meeting_str}"
            cursor.execute(
                "INSERT INTO GroupMessage (content, sent_by, posted_in) VALUES (%s, %s, %s);",
                (group_msg_content, req.faculty_id, req.group_id)
            )

            conn.commit()
            cursor.close()
            conn.close()

            return {
                "status": "ok",
                "message": f"Successfully accepted request to be {req.role}!{sem_message}"
            }

        else:
            # Rejection branch: Send plain text rejection message to group channel
            note_str = req.response_message if req.response_message else "No specific preference detailed."
            group_msg_content = f"{fac_name} declined the request for {req.role}. Preference / Feedback: {note_str}"
            
            cursor.execute(
                "INSERT INTO GroupMessage (content, sent_by, posted_in) VALUES (%s, %s, %s);",
                (group_msg_content, req.faculty_id, req.group_id)
            )

            conn.commit()
            cursor.close()
            conn.close()

            return {"status": "ok", "message": "Supervisor request declined with feedback message."}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/inbox/meeting-request/respond")
def respond_meeting_request(req: MeetingRespondRequest):
    """
    Faculty accepts or rejects a meeting request.
    If accept: updates meeting status to 'Approved'.
    If reject: updates meeting status to 'Rejected'.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        action = req.action.lower()
        new_stat = 'Approved' if action == 'accept' else 'Rejected'

        if req.link_or_room and req.link_or_room.strip():
            cursor.execute(
                """
                UPDATE Meeting 
                SET Approve_Stat = %s, link_or_room = %s 
                WHERE meeting_id = %s AND host_id = %s;
                """,
                (new_stat, req.link_or_room.strip(), req.meeting_id, req.host_id)
            )
        else:
            cursor.execute(
                """
                UPDATE Meeting 
                SET Approve_Stat = %s 
                WHERE meeting_id = %s AND host_id = %s;
                """,
                (new_stat, req.meeting_id, req.host_id)
            )

        conn.commit()

        cursor.close()
        conn.close()

        msg = "Meeting request accepted and scheduled!" if action == 'accept' else "Meeting request cancelled."
        return {"status": "ok", "message": msg}

    except Exception as e:
        return {"status": "error", "message": str(e)}
