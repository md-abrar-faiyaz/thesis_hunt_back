import re
from typing import Optional
from fastapi import APIRouter
from database import get_db_connection
from schemas import (
    ThesisGroupCreateRequest,
    GroupToggleStatusRequest,
    GroupInviteRequest,
    GroupInviteResponseRequest,
    GroupMessageCreateRequest,
    GroupJoinRequest,
    JoinRequestResponseRequest,
    GroupLeaveRequest,
    ThesisEditRequest
)
from routers.auth import resolve_domain_id

router = APIRouter()


@router.get("/group-channel/{student_id}")
def get_group_channel(student_id: int):
    """Fetch student's thesis group information, members, supervisors, and chat history."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;",
            (student_id,)
        )
        student = cursor.fetchone()
        if not student or not student.get("thesis_group"):
            cursor.close()
            conn.close()
            return {
                "status": "ok",
                "has_group": False,
                "message": "You are not currently part of any thesis group."
            }

        group_id = student["thesis_group"]

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
            return {
                "status": "ok",
                "has_group": False,
                "message": "Thesis group record not found."
            }

        cursor.execute(
            """
            SELECT 
                s.student_id,
                u.name,
                u.email,
                u.gender,
                s.CGPA,
                s.credits_completed,
                s.sem_no
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

        cursor.execute(
            """
            SELECT 
                sup.supervisor_id,
                sup.role,
                sup.semester,
                u.name,
                u.email,
                f.Fac_initial AS fac_initial,
                f.`designation` AS designation
            FROM Supervises sup
            JOIN Faculty f ON sup.supervisor_id = f.faculty_id
            JOIN User u ON f.faculty_id = u.UID
            WHERE sup.group_id = %s
            ORDER BY sup.role DESC, u.name ASC;
            """,
            (group_id,)
        )
        supervisors = cursor.fetchall()

        group_info["members"] = members
        group_info["supervisors"] = supervisors

        cursor.execute(
            """
            SELECT 
                gm.message_id,
                gm.content,
                gm.timestamp,
                DATE_FORMAT(CONVERT_TZ(gm.timestamp, @@session.time_zone, '+06:00'), '%b %d, %Y %h:%i %p') AS formatted_time,
                gm.sent_by,
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
            ORDER BY gm.timestamp ASC, gm.message_id ASC;
            """,
            (group_id,)
        )
        messages = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "has_group": True,
            "group_info": group_info,
            "messages": messages
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group-channel/create")
def create_thesis_group(req: ThesisGroupCreateRequest):
    """Create a new thesis group, insert thesis details, assign student to group."""
    try:
        if not req.title or not req.title.strip():
            return {"status": "error", "message": "Thesis title is required."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;",
            (req.student_id,)
        )
        student = cursor.fetchone()
        if student and student.get("thesis_group"):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You are already a member of a thesis group."}

        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """
            INSERT INTO Thesis (title, description, research_domain)
            VALUES (%s, %s, %s);
            """,
            (req.title.strip(), req.description.strip() if req.description else None, domain_id)
        )
        thesis_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO ThesisGroup (formation_status, thesis_id)
            VALUES ('Forming', %s);
            """,
            (thesis_id,)
        )
        group_id = cursor.lastrowid

        cursor.execute(
            "UPDATE Student SET thesis_group = %s WHERE student_id = %s;",
            (group_id, req.student_id)
        )

        cursor.execute(
            """
            INSERT INTO GroupMessage (content, sent_by, posted_in)
            VALUES ('Thesis group created successfully. Welcome to the group channel!', %s, %s);
            """,
            (req.student_id, group_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "message": "Thesis group created successfully!",
            "group_id": group_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.put("/group-channel/{group_id}/toggle-status")
def toggle_group_status(group_id: int, req: GroupToggleStatusRequest):
    """Toggle formation status between 'Forming' (accepting requests) and 'Pending'."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        action = req.action.lower()
        if action == "stop_requests":
            new_status = "Pending"
        elif action == "allow_requests":
            new_status = "Forming"
        else:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Invalid toggle action."}

        cursor.execute(
            "UPDATE ThesisGroup SET formation_status = %s WHERE group_id = %s;",
            (new_status, group_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "message": f"Group formation status changed to '{new_status}'.",
            "new_status": new_status
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group-channel/invite")
def send_group_invitation(req: GroupInviteRequest):
    """Send an invitation to join the student's thesis group into recipient's Inbox."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;",
            (req.receiver_id,)
        )
        receiver = cursor.fetchone()
        if not receiver:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Recipient student profile not found."}
        if receiver.get("thesis_group"):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "This student is already a member of a thesis group."}

        cursor.execute(
            """
            SELECT u.name, t.title
            FROM User u
            JOIN Student s ON u.UID = s.student_id
            JOIN ThesisGroup tg ON s.thesis_group = tg.group_id
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            WHERE u.UID = %s LIMIT 1;
            """,
            (req.sender_id,)
        )
        sender_info = cursor.fetchone()
        if not sender_info:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You must be in a thesis group to invite students."}

        sender_name = sender_info["name"]
        thesis_title = sender_info.get("title") or "Thesis Group"

        invite_msg = f"[Group Invitation:{req.group_id}] {sender_name} invited to join their thesis group: '{thesis_title}'."

        cursor.execute(
            """
            INSERT INTO Contact (sender_id, receiver_id, message_text, status)
            VALUES (%s, %s, %s, 'Unread');
            """,
            (req.sender_id, req.receiver_id, invite_msg)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Group invitation sent to student's inbox!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group-channel/invitation-response")
def respond_group_invitation(req: GroupInviteResponseRequest):
    """Handle user acceptance or rejection of a thesis group invitation."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        action = req.action.lower()

        cursor.execute("SELECT name FROM User WHERE UID = %s LIMIT 1;", (req.user_id,))
        user_row = cursor.fetchone()
        user_name = user_row["name"] if user_row else "A student"

        if action == "accept":
            cursor.execute("SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;", (req.user_id,))
            st = cursor.fetchone()
            if st and st.get("thesis_group"):
                cursor.close()
                conn.close()
                return {"status": "error", "message": "You are already a member of another thesis group."}

            cursor.execute(
                "UPDATE Student SET thesis_group = %s WHERE student_id = %s;",
                (req.group_id, req.user_id)
            )

            cursor.execute(
                """
                INSERT INTO GroupMessage (content, sent_by, posted_in)
                VALUES (%s, %s, %s);
                """,
                (f"{user_name} accepted the invitation and joined the thesis group!", req.user_id, req.group_id)
            )

            cursor.execute(
                """
                INSERT INTO Contact (sender_id, receiver_id, message_text, status)
                VALUES (%s, %s, %s, 'Unread');
                """,
                (req.user_id, req.sender_id, f"[Notification] {user_name} accepted thesis group invitation!")
            )

            cursor.execute(
                """
                UPDATE Contact
                SET message_text = CONCAT(message_text, ' [ACCEPTED]')
                WHERE sender_id = %s AND receiver_id = %s AND timestamp = %s;
                """,
                (req.sender_id, req.user_id, req.timestamp)
            )

        elif action == "reject":
            cursor.execute(
                """
                INSERT INTO Contact (sender_id, receiver_id, message_text, status)
                VALUES (%s, %s, %s, 'Unread');
                """,
                (req.user_id, req.sender_id, f"[Notification] {user_name} rejected thesis group invitation.")
            )

            cursor.execute(
                """
                UPDATE Contact
                SET message_text = CONCAT(message_text, ' [REJECTED]')
                WHERE sender_id = %s AND receiver_id = %s AND timestamp = %s;
                """,
                (req.sender_id, req.user_id, req.timestamp)
            )
        else:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Invalid response action."}

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "ok", "message": f"Invitation {action}ed successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group-channel/send")
def send_group_message(req: GroupMessageCreateRequest):
    """Send a message into the thesis group chat."""
    try:
        if not req.content or not req.content.strip():
            return {"status": "error", "message": "Message content cannot be empty."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

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

        return {"status": "ok", "message": "Group message sent successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/group-channel/message/{message_id}")
def delete_group_message(message_id: int, sent_by: int):
    """Delete a message from GroupMessage table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "DELETE FROM GroupMessage WHERE message_id = %s AND sent_by = %s;",
            (message_id, sent_by)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Message deleted successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/forming-groups")
def get_forming_thesis_groups(
    domain: Optional[str] = None,
    supervisor_name: Optional[str] = None,
    semester: Optional[str] = None
):
    """List all thesis groups that currently have formation_status = 'Forming'."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT 
                tg.group_id,
                tg.formation_status,
                t.thesis_id,
                COALESCE(t.title, 'No Thesis Topic Selected Yet') AS title,
                COALESCE(t.description, 'No thesis description provided yet.') AS description,
                COALESCE(d.domain_name, 'Domain Not Specified') AS domain
            FROM ThesisGroup tg
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            LEFT JOIN Domain d ON t.research_domain = d.domain_id
            WHERE tg.formation_status = 'Forming'
        """
        params = []

        if domain and domain.strip():
            query += " AND d.domain_name LIKE %s"
            params.append(f"%{domain.strip()}%")

        if supervisor_name and supervisor_name.strip():
            sup_pattern = f"%{supervisor_name.strip()}%"
            query += """
                AND EXISTS (
                    SELECT 1 
                    FROM Supervises sup_sub
                    JOIN Faculty f_sup ON sup_sub.supervisor_id = f_sup.faculty_id
                    JOIN User u_sup ON f_sup.faculty_id = u_sup.UID
                    WHERE sup_sub.group_id = tg.group_id 
                    AND (u_sup.name LIKE %s OR f_sup.Fac_initial LIKE %s)
                )
            """
            params.extend([sup_pattern, sup_pattern])

        if semester and semester.strip():
            sem_pattern = f"%{semester.strip()}%"
            query += """
                AND EXISTS (
                    SELECT 1 
                    FROM Supervises sup_sem
                    WHERE sup_sem.group_id = tg.group_id 
                    AND sup_sem.semester LIKE %s
                )
            """
            params.append(sem_pattern)

        query += " ORDER BY tg.group_id DESC;"

        cursor.execute(query, tuple(params))
        groups = cursor.fetchall()

        for g in groups:
            gid = g["group_id"]

            cursor.execute(
                """
                SELECT 
                    s.student_id,
                    u.name,
                    u.email,
                    u.gender,
                    s.CGPA,
                    s.credits_completed,
                    s.sem_no
                FROM Student s
                JOIN User u ON s.student_id = u.UID
                WHERE s.thesis_group = %s;
                """,
                (gid,)
            )
            g["members"] = cursor.fetchall()

            cursor.execute(
                """
                SELECT 
                    sup.supervisor_id,
                    sup.role,
                    sup.semester,
                    u.name,
                    u.email,
                    f.Fac_initial,
                    f.designation
                FROM Supervises sup
                JOIN Faculty f ON sup.supervisor_id = f.faculty_id
                JOIN User u ON f.faculty_id = u.UID
                WHERE sup.group_id = %s;
                """,
                (gid,)
            )
            g["supervisors"] = cursor.fetchall()

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(groups), "groups": groups}
    except Exception as e:
        return {"status": "error", "message": str(e), "groups": []}


@router.post("/group/join-request")
def request_to_join_group(req: GroupJoinRequest):
    """Send a join request message into target thesis group's channel."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;", (req.student_id,))
        st = cursor.fetchone()
        if not st:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Student profile not found."}
        if st.get("thesis_group"):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You are already a member of a thesis group."}

        cursor.execute("SELECT formation_status FROM ThesisGroup WHERE group_id = %s LIMIT 1;", (req.group_id,))
        tg = cursor.fetchone()
        if not tg or tg.get("formation_status") != "Forming":
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Target thesis group is not accepting join requests."}

        cursor.execute("SELECT name FROM User WHERE UID = %s LIMIT 1;", (req.student_id,))
        user_row = cursor.fetchone()
        student_name = user_row["name"] if user_row else "A student"

        cursor.execute(
            """
            SELECT message_id FROM GroupMessage 
            WHERE posted_in = %s AND content LIKE %s;
            """,
            (req.group_id, f"[Join Request:{req.student_id}]%")
        )
        existing_msg = cursor.fetchone()
        if existing_msg:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You have already submitted a join request to this group."}

        content = f"[Join Request:{req.student_id}] {student_name} requested to join this thesis group."
        cursor.execute(
            """
            INSERT INTO GroupMessage (content, sent_by, posted_in)
            VALUES (%s, %s, %s);
            """,
            (content, req.student_id, req.group_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Join request submitted to group channel!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group/join-request-response")
def respond_join_request(req: JoinRequestResponseRequest):
    """Handle group member voting on a student's join request in group channel."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        action = req.action.lower()

        cursor.execute(
            "SELECT message_id, content, posted_in FROM GroupMessage WHERE message_id = %s LIMIT 1;",
            (req.message_id,)
        )
        msg = cursor.fetchone()
        if not msg:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Join request message not found."}

        content = msg["content"]
        group_id = msg["posted_in"]

        match = re.search(r"\[Join Request:(\d+)(?::VOTES:([\d,]*))?(?::ACCEPTED|:REJECTED)?\]", content)
        if not match:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Invalid join request message format."}

        applicant_id = int(match.group(1))
        existing_votes_str = match.group(2) or ""
        voted_uids = set(int(x) for x in existing_votes_str.split(",") if x.strip().isdigit())

        cursor.execute("SELECT student_id FROM Student WHERE thesis_group = %s;", (group_id,))
        members_rows = cursor.fetchall()
        group_member_uids = set(r["student_id"] for r in members_rows)

        if req.user_id not in group_member_uids:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Only current group members can vote on join requests."}

        cursor.execute("SELECT name FROM User WHERE UID = %s LIMIT 1;", (applicant_id,))
        applicant_row = cursor.fetchone()
        applicant_name = applicant_row["name"] if applicant_row else "Applicant"

        if action == "accept":
            voted_uids.add(req.user_id)

            if group_member_uids.issubset(voted_uids):
                cursor.execute("UPDATE Student SET thesis_group = %s WHERE student_id = %s;", (group_id, applicant_id))

                cursor.execute(
                    """
                    INSERT INTO GroupMessage (content, sent_by, posted_in)
                    VALUES (%s, %s, %s);
                    """,
                    (f"{applicant_name} has joined the thesis group! Welcome to the channel.", applicant_id, group_id)
                )

                new_tag = f"[Join Request:{applicant_id}:ACCEPTED]"
                new_content = re.sub(r"\[Join Request:\d+(?::VOTES:[\d,]*)?(?::ACCEPTED|:REJECTED)?\]", new_tag, content)
                cursor.execute("UPDATE GroupMessage SET content = %s WHERE message_id = %s;", (new_content, req.message_id))
                res_msg = "All group members accepted! Applicant joined the thesis group."
            else:
                votes_csv = ",".join(str(x) for x in sorted(voted_uids))
                new_tag = f"[Join Request:{applicant_id}:VOTES:{votes_csv}]"
                new_content = re.sub(r"\[Join Request:\d+(?::VOTES:[\d,]*)?(?::ACCEPTED|:REJECTED)?\]", new_tag, content)
                cursor.execute("UPDATE GroupMessage SET content = %s WHERE message_id = %s;", (new_content, req.message_id))
                res_msg = f"Vote recorded! ({len(voted_uids)}/{len(group_member_uids)} members accepted)."

        else:
            new_tag = f"[Join Request:{applicant_id}:REJECTED]"
            new_content = re.sub(r"\[Join Request:\d+(?::VOTES:[\d,]*)?(?::ACCEPTED|:REJECTED)?\]", new_tag, content)
            cursor.execute("UPDATE GroupMessage SET content = %s WHERE message_id = %s;", (new_content, req.message_id))
            res_msg = "Join request rejected."

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "ok", "message": res_msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/group/leave")
def leave_thesis_group(req: GroupLeaveRequest):
    """Allow a student to leave their thesis group if formation_status is NOT 'Approved'."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT s.thesis_group, u.name, tg.formation_status 
            FROM Student s
            JOIN User u ON s.student_id = u.UID
            LEFT JOIN ThesisGroup tg ON s.thesis_group = tg.group_id
            WHERE s.student_id = %s LIMIT 1;
            """,
            (req.student_id,)
        )
        st = cursor.fetchone()
        if not st or not st.get("thesis_group"):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You are not currently in a thesis group."}

        group_id = st["thesis_group"]
        student_name = st["name"]
        formation_status = st.get("formation_status")

        if formation_status == "Approved":
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You cannot leave an approved thesis group."}

        cursor.execute("UPDATE Student SET thesis_group = NULL WHERE student_id = %s;", (req.student_id,))

        cursor.execute(
            """
            INSERT INTO GroupMessage (content, sent_by, posted_in)
            VALUES (%s, %s, %s);
            """,
            (f"{student_name} has left the thesis group.", req.student_id, group_id)
        )

        cursor.execute("SELECT COUNT(*) AS remaining FROM Student WHERE thesis_group = %s;", (group_id,))
        count_row = cursor.fetchone()
        remaining_count = count_row["remaining"] if count_row else 0

        if remaining_count == 0:
            cursor.execute("DELETE FROM ThesisGroup WHERE group_id = %s;", (group_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "ok", "message": "You have left the thesis group."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.put("/group-channel/{group_id}/thesis")
def update_thesis_info(group_id: int, req: ThesisEditRequest):
    """Update thesis title, description, and research domain for the group."""
    try:
        if not req.title or not req.title.strip():
            return {"status": "error", "message": "Thesis title is required."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify student belongs to this thesis group
        cursor.execute(
            "SELECT thesis_group FROM Student WHERE student_id = %s LIMIT 1;",
            (req.student_id,)
        )
        student = cursor.fetchone()
        if not student or student.get("thesis_group") != group_id:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You are not a member of this thesis group."}

        # Find thesis_id for the group
        cursor.execute(
            "SELECT thesis_id FROM ThesisGroup WHERE group_id = %s LIMIT 1;",
            (group_id,)
        )
        group_row = cursor.fetchone()
        if not group_row or not group_row.get("thesis_id"):
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Thesis group record not found."}

        thesis_id = group_row["thesis_id"]
        domain_id = resolve_domain_id(cursor, req.domain_name)

        cursor.execute(
            """
            UPDATE Thesis 
            SET title = %s, description = %s, research_domain = %s
            WHERE thesis_id = %s;
            """,
            (req.title.strip(), req.description.strip() if req.description else None, domain_id, thesis_id)
        )

        cursor.execute(
            """
            INSERT INTO GroupMessage (content, sent_by, posted_in)
            VALUES (%s, %s, %s);
            """,
            (f"Thesis info updated: '{req.title.strip()}'", req.student_id, group_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Thesis details updated successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

