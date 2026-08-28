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
    designation: str  # renamed from 'rank' to avoid MySQL 8+ reserved keyword conflict
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


class BlogPostCreateRequest(BaseModel):
    title: str
    content: str
    posted_by: int
    domain_name: Optional[str] = None


class AuthorInput(BaseModel):
    author_id: int
    author_order: int


class PublicationCreateRequest(BaseModel):
    title: str
    journal_category: Optional[str] = None
    publication_date: Optional[str] = None
    link: Optional[str] = None
    domain_name: Optional[str] = None
    authors: list[AuthorInput] = []


class StudentProfileUpdateRequest(BaseModel):
    cgpa: float
    credits_completed: int
    sem_no: int
    domain_name: Optional[str] = None


class BlogPostUpdateRequest(BaseModel):
    posted_by: int
    title: str
    content: str
    domain_name: Optional[str] = None


class SendMessageRequest(BaseModel):
    sender_id: int
    receiver_id: int
    message_text: str


class TaskCreateRequest(BaseModel):
    task_description: str
    deadline: Optional[str] = None
    assigned_to: int
    assigned_by: int


class TaskActionRequest(BaseModel):
    action: str  # 'accept' | 'reject' | 'complete'
    user_id: int




