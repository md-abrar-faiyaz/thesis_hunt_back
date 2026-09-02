"""
Faculty Tasks Router
Handles listing tasks and assigning tasks to students in faculty-supervised thesis groups.
"""
from fastapi import APIRouter
from database import get_db_connection
from schemas import FacultyTaskAssignRequest

router = APIRouter()


@router.get("/tasks/{faculty_id}")
def get_faculty_supervised_tasks(faculty_id: int):
    """
    Fetch all tasks associated with thesis groups supervised by the faculty member.
    Returns task description, deadline, status, assigned student details, and thesis group info.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT DISTINCT
                tk.task_id,
                tk.task_description,
                tk.status,
                tk.deadline,
                DATE_FORMAT(CONVERT_TZ(tk.deadline, @@session.time_zone, '+06:00'), '%b %d, %Y %h:%i %p') AS formatted_deadline,
                tk.assigned_to,
                u_st.name AS student_name,
                u_st.email AS student_email,
                s.thesis_group AS group_id,
                t.title AS thesis_title
            FROM Task tk
            JOIN Student s ON tk.assigned_to = s.student_id
            JOIN User u_st ON s.student_id = u_st.UID
            JOIN ThesisGroup tg ON s.thesis_group = tg.group_id
            JOIN Supervises sup ON tg.group_id = sup.group_id
            LEFT JOIN Thesis t ON tg.thesis_id = t.thesis_id
            WHERE sup.supervisor_id = %s
            -- Sorted by thesis group (s.thesis_group ASC) and then by assignment time (tk.task_id DESC, latest on top)
            ORDER BY s.thesis_group ASC, tk.task_id DESC;
        """
        cursor.execute(query, (faculty_id,))
        tasks = cursor.fetchall()

        for tk in tasks:
            if tk.get("deadline"):
                tk["deadline"] = str(tk["deadline"])

        cursor.close()
        conn.close()

        return {"status": "ok", "count": len(tasks), "tasks": tasks}

    except Exception as e:
        return {"status": "error", "message": str(e), "tasks": []}


@router.post("/tasks")
def assign_faculty_task(req: FacultyTaskAssignRequest):
    """
    Faculty assigns a task to a student member of their supervised thesis group.
    Sets plain text description and date deadline. Inserts into Task table with status = 'Pending'.
    """
    try:
        if not req.task_description or not req.task_description.strip():
            return {"status": "error", "message": "Task description cannot be empty."}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify faculty supervises this group
        cursor.execute(
            "SELECT 1 FROM Supervises WHERE supervisor_id = %s AND group_id = %s LIMIT 1;",
            (req.faculty_id, req.group_id)
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "You can only assign tasks to students in groups you supervise."}

        # Verify student belongs to this group
        cursor.execute(
            "SELECT 1 FROM Student WHERE student_id = %s AND thesis_group = %s LIMIT 1;",
            (req.assigned_to, req.group_id)
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Selected student is not a member of this thesis group."}

        cursor.execute(
            """
            INSERT INTO Task (task_description, status, deadline, assigned_to, assigned_by)
            VALUES (%s, 'Pending', %s, %s, %s);
            """,
            (req.task_description.strip(), req.deadline or None, req.assigned_to, req.faculty_id)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "ok", "message": "Task assigned to student successfully!"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
