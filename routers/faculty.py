"""
Master Faculty Router
Aggregates all faculty-specific sub-routers under /api/faculty.
"""
from fastapi import APIRouter
from routers.faculty_routes import (
    faculty_profile,
    faculty_groups,
    faculty_inbox,
    faculty_meetings,
    faculty_blogposts,
    faculty_tasks,
    faculty_publications
)

router = APIRouter(prefix="/api/faculty", tags=["Faculty Features"])

# Include modular faculty routers
router.include_router(faculty_profile.router)
router.include_router(faculty_groups.router)
router.include_router(faculty_inbox.router)
router.include_router(faculty_meetings.router)
router.include_router(faculty_blogposts.router)
router.include_router(faculty_tasks.router)
router.include_router(faculty_publications.router)
