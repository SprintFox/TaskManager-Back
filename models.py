from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Table, Enum
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import enum

class ProjectRole(str, enum.Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"
    MANAGER = "MANAGER"

# Таблица связи пользователей и проектов
user_project = Table(
    'user_project',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('project_id', Integer, ForeignKey('projects.id')),
    Column('role', Enum(ProjectRole), default=ProjectRole.MEMBER)
)

# Таблица связи пользователей и навыков
user_skill = Table(
    'user_skill',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('skill_id', Integer, ForeignKey('skills.id'))
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="USER")
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", secondary=user_project, back_populates="members")
    skills = relationship("Skill", secondary=user_skill, back_populates="users")
    tasks = relationship("Task", back_populates="assigned_to")

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))

    members = relationship("User", secondary=user_project, back_populates="projects")
    branches = relationship("Branch", back_populates="project")

class Branch(Base):
    __tablename__ = "branches"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    description = Column(String, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)

    project = relationship("Project", back_populates="branches")
    tasks = relationship("Task", back_populates="branch")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)  # title в DTO
    description = Column(String, nullable=True)
    parent_id = Column(String, ForeignKey("tasks.id"), nullable=True)
    branch_id = Column(String, ForeignKey("branches.id"))
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    done = Column(Boolean, default=False)
    has_problem = Column(Boolean, default=False)
    problem_message = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=True)
    file = Column(String, nullable=True)

    branch = relationship("Branch", back_populates="tasks")
    assigned_to = relationship("User", back_populates="tasks")
    skill = relationship("Skill")
    parent = relationship("Task", remote_side=[id], backref="subtasks")

class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String, default="GENERAL")
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", secondary=user_skill, back_populates="skills") 