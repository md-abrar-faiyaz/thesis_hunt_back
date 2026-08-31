from fastapi import APIRouter
from database import get_db_connection
from schemas import SendMessageRequest

router = APIRouter()


@router.get("/users-list")
def get_users_list():
    """Fetch registered users list for selection."""
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


@router.get("/inbox/conversations")
def get_inbox_conversations(user_id: int):
    """Fetch all conversation partner cards for the user."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 
                partner.UID AS partner_id,
                partner.name AS partner_name,
                partner.email AS partner_email,
                CASE 
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    WHEN s.student_id IS NOT NULL THEN 'Student'
                    ELSE 'User'
                END AS partner_role,
                MAX(c.timestamp) AS last_timestamp,
                DATE_FORMAT(CONVERT_TZ(MAX(c.timestamp), @@session.time_zone, '+06:00'), '%b %d, %Y %h:%i %p') AS formatted_last_timestamp,
                SUM(CASE WHEN c.receiver_id = %s AND c.status = 'Unread' THEN 1 ELSE 0 END) AS unread_count
            FROM Contact c
            JOIN User partner ON (
                (c.sender_id = %s AND c.receiver_id = partner.UID) OR 
                (c.receiver_id = %s AND c.sender_id = partner.UID)
            )
            LEFT JOIN Faculty f ON partner.UID = f.faculty_id
            LEFT JOIN Student s ON partner.UID = s.student_id
            WHERE c.sender_id = %s OR c.receiver_id = %s
            GROUP BY partner.UID, partner.name, partner.email, partner_role
            ORDER BY last_timestamp DESC;
            """,
            (user_id, user_id, user_id, user_id, user_id)
        )
        conversations = cursor.fetchall()
        total_unread = sum(c.get("unread_count", 0) for c in conversations)

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "total_unread": total_unread,
            "conversations": conversations
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/inbox/messages")
def get_inbox_messages(user_id: int, partner_id: int):
    """Fetch full message history between user_id and partner_id."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            UPDATE Contact 
            SET status = 'Read' 
            WHERE receiver_id = %s AND sender_id = %s AND status = 'Unread';
            """,
            (user_id, partner_id)
        )
        conn.commit()

        cursor.execute(
            """
            SELECT 
                c.sender_id,
                c.receiver_id,
                c.message_text,
                c.status,
                c.timestamp,
                DATE_FORMAT(CONVERT_TZ(c.timestamp, @@session.time_zone, '+06:00'), '%b %d, %Y %h:%i %p') AS formatted_time,
                u.name AS sender_name
            FROM Contact c
            JOIN User u ON c.sender_id = u.UID
            WHERE (c.sender_id = %s AND c.receiver_id = %s)
               OR (c.sender_id = %s AND c.receiver_id = %s)
            ORDER BY c.timestamp ASC;
            """,
            (user_id, partner_id, partner_id, user_id)
        )
        messages = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                u.UID AS partner_id,
                u.name AS partner_name,
                u.email AS partner_email,
                CASE 
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    WHEN s.student_id IS NOT NULL THEN 'Student'
                    ELSE 'User'
                END AS partner_role
            FROM User u
            LEFT JOIN Faculty f ON u.UID = f.faculty_id
            LEFT JOIN Student s ON u.UID = s.student_id
            WHERE u.UID = %s;
            """,
            (partner_id,)
        )
        partner_info = cursor.fetchone()

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "partner": partner_info,
            "messages": messages
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/inbox/send")
def send_inbox_message(req: SendMessageRequest):
    """Send a direct 1-on-1 message or notification to another user."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            INSERT INTO Contact (sender_id, receiver_id, message_text, status)
            VALUES (%s, %s, %s, 'Unread');
            """,
            (req.sender_id, req.receiver_id, req.message_text.strip())
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Message sent successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/inbox/message")
def delete_inbox_message(sender_id: int, receiver_id: int, timestamp: str):
    """Delete a specific message or notification from Contact table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            DELETE FROM Contact 
            WHERE sender_id = %s AND receiver_id = %s AND timestamp = %s;
            """,
            (sender_id, receiver_id, timestamp)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Message deleted successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/request-counts/{student_id}")
def get_student_request_counts(student_id: int):
    """
    Fetch counts of pending requests for student navigation badges:
    - unread_inbox: Unread contact messages
    - pending_tasks: Pending task requests assigned to student
    - incoming_meetings: Pending meeting requests where student is host
    - pending_group_requests: Pending join requests in group chat or pending group invitations
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM Contact WHERE receiver_id = %s AND status = 'Unread';",
            (student_id,)
        )
        row = cursor.fetchone()
        unread_inbox = row["cnt"] if row else 0

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM Task WHERE assigned_to = %s AND status = 'Pending';",
            (student_id,)
        )
        row = cursor.fetchone()
        pending_tasks = row["cnt"] if row else 0

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt FROM Meeting 
            WHERE host_id = %s AND (Approve_Stat IS NULL OR LOWER(Approve_Stat) = 'pending');
            """,
            (student_id,)
        )
        row = cursor.fetchone()
        incoming_meetings = row["cnt"] if row else 0

        pending_group_requests = 0

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt FROM Contact 
            WHERE receiver_id = %s AND status = 'Unread' AND message_text LIKE '[Group Invitation:%%';
            """,
            (student_id,)
        )
        inv_row = cursor.fetchone()
        if inv_row:
            pending_group_requests += inv_row["cnt"]

        cursor.execute("SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;", (student_id,))
        st = cursor.fetchone()
        if st and st.get("thesis_group"):
            group_id = st["thesis_group"]
            cursor.execute(
                """
                SELECT content FROM GroupMessage 
                WHERE posted_in = %s AND content LIKE '[Join Request:%%';
                """,
                (group_id,)
            )
            msg_rows = cursor.fetchall()
            import re
            for m in msg_rows:
                content = m.get("content", "")
                if ":ACCEPTED" in content or ":REJECTED" in content:
                    continue
                match = re.search(r"\[Join Request:\d+(?::VOTES:([\d,]*))?\]", content)
                if match:
                    votes_str = match.group(1) or ""
                    voted_uids = set(int(x) for x in votes_str.split(",") if x.strip().isdigit())
                    if student_id not in voted_uids:
                        pending_group_requests += 1
                else:
                    pending_group_requests += 1

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "unread_inbox": unread_inbox,
            "pending_tasks": pending_tasks,
            "incoming_meetings": incoming_meetings,
            "pending_group_requests": pending_group_requests
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "unread_inbox": 0,
            "pending_tasks": 0,
            "incoming_meetings": 0,
            "pending_group_requests": 0
        }

