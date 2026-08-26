from pydantic import BaseModel
from typing import Optional


class StudentRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    gender: Optional[str] = 'Other'
    cgpa: float
    credits_completed: int
    sem_no: Optional[int] = 1
    has_done_thesis: bool = False
    domain_name: Optional[str] = None


class FacultyRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    gender: Optional[str] = 'Other'
    fac_initial: str
    rank: str
    ug_pg: str
    sem_free_from: Optional[str] = ''
    max_grp_per_sem: int = 3
    total_supervised: int = 0
    room_no: Optional[str] = ''
    calendar_link: Optional[str] = ''
    domain_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str
