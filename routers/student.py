from fastapi import APIRouter
from routers.student_routes import (
    student_search,
    student_social,
    student_inbox,
    student_tasks,
    student_group,
    student_meetings
)

router = APIRouter(prefix="/api/student", tags=["Student Interface"])

# Aggregate modular sub-routers
router.include_router(student_search.router)
router.include_router(student_social.router)
router.include_router(student_inbox.router)
router.include_router(student_tasks.router)
router.include_router(student_group.router)
router.include_router(student_meetings.router)
