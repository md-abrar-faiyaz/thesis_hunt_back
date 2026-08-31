from fastapi import APIRouter
from database import get_db_connection
from schemas import TaskCreateRequest, TaskActionRequest

router = APIRouter()


@router.get("/tasks")
def get_student_tasks(student_id: int):
    """Fetch all tasks associated with the student (assigned to or created by student)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 
                s.student_id,
                u.name,
                u.email
            FROM Student s
            JOIN User u ON s.student_id = u.UID
            WHERE s.thesis_group IS NOT NULL
              AND s.thesis_group = (SELECT thesis_group FROM Student WHERE student_id = %s)
              AND s.student_id != %s
            ORDER BY u.name ASC;
            """,
            (student_id, student_id)
        )
        group_members = cursor.fetchall()

        cursor.execute(
            """
            SELECT 
                t.task_id,
                t.task_description,
                t.status,
                t.deadline,
                DATE_FORMAT(t.deadline, '%b %d, %Y') AS formatted_deadline,
                t.assigned_to,
                t.assigned_by,
                assigner.name AS assigner_name,
                CASE 
                    WHEN f.faculty_id IS NOT NULL THEN 'Faculty'
                    ELSE 'Student'
                END AS assigner_role
            FROM Task t
            LEFT JOIN User assigner ON t.assigned_by = assigner.UID
            LEFT JOIN Faculty f ON assigner.UID = f.faculty_id
            WHERE t.assigned_to = %s
            ORDER BY t.task_id DESC;
            """,
            (student_id,)
        )
        all_tasks = cursor.fetchall()

        requests = [t for t in all_tasks if t['status'] == 'Pending']
        in_progress_supervisor = [
            t for t in all_tasks 
            if t['status'] == 'In Progress' and t['assigner_role'] == 'Faculty'
        ]
        in_progress_members = [
            t for t in all_tasks 
            if t['status'] == 'In Progress' and t['assigner_role'] == 'Student'
        ]
        completed_supervisor = [
            t for t in all_tasks 
            if t['status'] == 'Completed' and t['assigner_role'] == 'Faculty'
        ]
        completed_members = [
            t for t in all_tasks 
            if t['status'] == 'Completed' and t['assigner_role'] == 'Student'
        ]

        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "group_members": group_members,
            "requests": requests,
            "in_progress_supervisor": in_progress_supervisor,
            "in_progress_members": in_progress_members,
            "completed_supervisor": completed_supervisor,
            "completed_members": completed_members
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/task")
def create_student_task(req: TaskCreateRequest):
    """Create a new task assigned to a thesis group member."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            INSERT INTO Task (task_description, status, deadline, assigned_to, assigned_by)
            VALUES (%s, 'Pending', %s, %s, %s);
            """,
            (
                req.task_description.strip(),
                req.deadline if req.deadline else None,
                req.assigned_to,
                req.assigned_by
            )
        )
        task_id = cursor.lastrowid

        cursor.execute("SELECT name FROM User WHERE UID = %s;", (req.assigned_by,))
        assigner = cursor.fetchone()
        assigner_name = assigner['name'] if assigner else 'A group member'

        notification_text = f"[Notification] You have a new task request from {assigner_name}: '{req.task_description.strip()}'"
        cursor.execute(
            """
            INSERT INTO Contact (sender_id, receiver_id, message_text, status)
            VALUES (%s, %s, %s, 'Unread');
            """,
            (req.assigned_by, req.assigned_to, notification_text)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "message": "Task created successfully!",
            "task_id": task_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.put("/task/{task_id}/action")
def update_task_action(task_id: int, req: TaskActionRequest):
    """Handle task action: 'accept', 'reject', or 'complete'."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 
                t.task_description, 
                t.assigned_to, 
                t.assigned_by, 
                u.name AS assignee_name
            FROM Task t
            LEFT JOIN User u ON t.assigned_to = u.UID
            WHERE t.task_id = %s;
            """,
            (task_id,)
        )
        task = cursor.fetchone()
        if not task:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Task not found."}

        action = req.action.lower()
        new_status = ""
        notification_text = ""

        if action == "accept":
            new_status = "In Progress"
            notification_text = f"[Notification] Task '{task['task_description']}' request is ACCEPTED by {task['assignee_name']}."
        elif action == "reject":
            new_status = "Rejected"
            notification_text = f"[Notification] Task '{task['task_description']}' request is REJECTED by {task['assignee_name']}."
        elif action == "complete":
            new_status = "Completed"
            notification_text = f"[Notification] Task '{task['task_description']}' assigned to {task['assignee_name']} is completed."
        else:
            cursor.close()
            conn.close()
            return {"status": "error", "message": "Invalid action parameter."}

        cursor.execute(
            "UPDATE Task SET status = %s WHERE task_id = %s;",
            (new_status, task_id)
        )

        if task['assigned_by']:
            cursor.execute(
                """
                INSERT INTO Contact (sender_id, receiver_id, message_text, status)
                VALUES (%s, %s, %s, 'Unread');
                """,
                (task['assigned_to'], task['assigned_by'], notification_text)
            )

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "ok",
            "message": f"Task status updated to {new_status}!"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
