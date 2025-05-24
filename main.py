from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import os
from datetime import datetime
import re

from database import get_db, logger
from models import User, Project, Branch, Task, Skill
from utils import (
    verify_password, get_password_hash, create_access_token,
    verify_token, PasswordValidator, UserValidator, handle_exception,
    AppException
)

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройка статических файлов
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Вспомогательные функции
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = verify_token(token)
        user = db.query(User).filter(User.login == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except Exception as e:
        handle_exception(e)

# Эндпоинты аутентификации
@app.post("/auth/login")
async def login(form_data: dict, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.login == form_data["login"]).first()
        if not user or not verify_password(form_data["password"], user.hashed_password):
            raise AppException("Invalid login or password", status.HTTP_401_UNAUTHORIZED)
        
        token = create_access_token({"sub": user.login})
        logger.info(f"User {user.login} logged in successfully")
        return token
    except Exception as e:
        handle_exception(e)

@app.post("/auth/register")
async def register(user_data: dict, db: Session = Depends(get_db)):
    try:
        # Валидация данных
        if not UserValidator.validate_login(user_data["login"]):
            raise AppException("Invalid login format")
        if not UserValidator.validate_email(user_data["email"]):
            raise AppException("Invalid email format")
        if not PasswordValidator.validate(user_data["password"]):
            raise AppException("Password does not meet requirements")
        print(user_data)
        # Проверка существования пользователя
        if db.query(User).filter(User.login == user_data["login"]).first():
            raise AppException("Login already exists")
        if db.query(User).filter(User.email == user_data["email"]).first():
            raise AppException("Email already exists")

        # Создание пользователя
        hashed_password = get_password_hash(user_data["password"])
        new_user = User(
            login=user_data["login"],
            email=user_data["email"],
            hashed_password=hashed_password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        token = create_access_token({"sub": new_user.login})
        logger.info(f"New user registered: {new_user.login}")
        return token
    except Exception as e:
        handle_exception(e)

# Эндпоинты для работы с проектами
@app.get("/projects/list")
async def get_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        projects = current_user.projects
        return projects
    except Exception as e:
        handle_exception(e)

@app.post("/projects")
async def add_project(project_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        new_project = Project(
            name=project_data["name"],
            description=project_data["description"],
            avatar_url=project_data.get("avatarUrl"),
            created_by=current_user.id
        )
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        
        # Добавляем создателя в участники проекта
        new_project.members.append(current_user)
        db.commit()
        
        logger.info(f"New project created: {new_project.name} by {current_user.login}")
        return new_project
    except Exception as e:
        handle_exception(e)

@app.post("/projects/{project_id}/edit")
async def edit_project(
    project_id: int,
    project_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to edit this project", status.HTTP_403_FORBIDDEN)

        project.name = project_data["name"]
        project.description = project_data["description"]
        project.avatar_url = project_data.get("avatarUrl")
        
        db.commit()
        db.refresh(project)
        
        logger.info(f"Project {project.name} edited by {current_user.login}")
        return project
    except Exception as e:
        handle_exception(e)

# Эндпоинты для работы с ветками
@app.post("/project/{project_id}/branch")
async def add_branch(
    project_id: int,
    branch_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to add branches", status.HTTP_403_FORBIDDEN)

        new_branch = Branch(
            id=str(uuid.uuid4()),
            name=branch_data["name"],
            description=None,
            project_id=project_id
        )
        db.add(new_branch)
        db.commit()
        db.refresh(new_branch)
        
        logger.info(f"New branch {new_branch.name} added to project {project.name}")
        return new_branch
    except Exception as e:
        handle_exception(e)

@app.post("/project/{project_id}/branch/edit")
async def edit_project_branch(
    project_id: int,
    branch_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        branch = db.query(Branch).filter(Branch.id == branch_data["id"]).first()
        if not branch or branch.project_id != project_id:
            raise AppException("Branch not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in branch.project.members:
            raise AppException("Not authorized to edit branches", status.HTTP_403_FORBIDDEN)

        branch.name = branch_data["name"]
        branch.description = branch_data.get("description")
        
        db.commit()
        db.refresh(branch)
        
        logger.info(f"Branch {branch.name} edited in project {branch.project.name}")
        return True
    except Exception as e:
        handle_exception(e)

@app.post("/project/{project_id}/branch/delete")
async def delete_project_branch(
    project_id: int,
    branch_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        branch = db.query(Branch).filter(Branch.id == branch_data["branchId"]).first()
        if not branch or branch.project_id != project_id:
            raise AppException("Branch not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in branch.project.members:
            raise AppException("Not authorized to delete branches", status.HTTP_403_FORBIDDEN)

        db.delete(branch)
        db.commit()
        
        logger.info(f"Branch {branch.name} deleted from project {branch.project.name}")
        return True
    except Exception as e:
        handle_exception(e)

# Эндпоинты для работы с задачами
@app.post("/project/{project_id}/branch/{branch_id}")
async def add_task(
    project_id: int,
    branch_id: str,
    task_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if not branch or branch.project_id != project_id:
            raise AppException("Branch not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in branch.project.members:
            raise AppException("Not authorized to add tasks", status.HTTP_403_FORBIDDEN)

        # Преобразование дат из формата DD.MM.YYYY
        start_date = None
        end_date = None
        if task_data.get("startDate"):
            start_date = parse_date(task_data["startDate"])
        if task_data.get("endDate"):
            end_date = parse_date(task_data["startDate"])

        new_task = Task(
            id=str(uuid.uuid4()),
            name=task_data["title"],
            description=task_data["description"],
            branch_id=branch_id,
            assigned_to_id=task_data.get("assignedTo"),
            done=task_data.get("done", False),
            has_problem=task_data.get("hasProblem", False),
            problem_message=task_data.get("problemMessage"),
            start_date=start_date,
            end_date=end_date,
            skill_id=task_data.get("skillId"),
            file=task_data.get("file")
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        
        logger.info(f"New task {new_task.name} added to branch {branch.name}")
        return new_task
    except Exception as e:
        handle_exception(e)

@app.post("/project/{project_id}/branch/{branch_id}/task/{task_id}")
async def edit_task_in_branch(
    project_id: int,
    branch_id: str,
    task_id: str,
    task_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.branch_id != branch_id:
            raise AppException("Task not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in task.branch.project.members:
            raise AppException("Not authorized to edit tasks", status.HTTP_403_FORBIDDEN)

        # Преобразование дат из формата DD.MM.YYYY
        if task_data.get("startDate"):
            task.start_date = parse_date(task_data["startDate"])
        if task_data.get("endDate"):
            task.end_date = parse_date(task_data["endDate"])

        task.name = task_data["title"]
        task.description = task_data["description"]
        task.assigned_to_id = task_data.get("assignedTo")
        task.skill_id = task_data.get("skillId")
        task.file = task_data.get("file")
        task.problem_message = task_data.get("problemMessage")
        
        db.commit()
        db.refresh(task)
        
        logger.info(f"Task {task.name} edited in branch {task.branch.name}")
        return True
    except Exception as e:
        handle_exception(e)

@app.post("/project/{project_id}/branch/{branch_id}/task/{task_id}/delete")
async def delete_task_in_branch(
    project_id: int,
    branch_id: str,
    task_id: str,
    task_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.branch_id != branch_id:
            raise AppException("Task not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in task.branch.project.members:
            raise AppException("Not authorized to delete tasks", status.HTTP_403_FORBIDDEN)

        db.delete(task)
        db.commit()
        
        logger.info(f"Task {task.name} deleted from branch {task.branch.name}")
        return True
    except Exception as e:
        handle_exception(e)

@app.post("/project/{project_id}/branch/{branch_id}/task/{task_id}/done")
async def done_task_in_branch(
    project_id: int,
    branch_id: str,
    task_id: str,
    problemMessage: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.branch_id != branch_id:
            raise AppException("Task not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in task.branch.project.members:
            raise AppException("Not authorized to modify tasks", status.HTTP_403_FORBIDDEN)

        task.done = True
        task.has_problem = False
        task.problem_message = problemMessage
        
        db.commit()
        db.refresh(task)
        
        logger.info(f"Task {task.name} marked as done in branch {task.branch.name}")
        return True
    except Exception as e:
        handle_exception(e)

@app.post("/project/{project_id}/branch/{branch_id}/task/{task_id}/problem")
async def problem_task_in_branch(
    project_id: int,
    branch_id: str,
    task_id: str,
    problemMessage: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.branch_id != branch_id:
            raise AppException("Task not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in task.branch.project.members:
            raise AppException("Not authorized to modify tasks", status.HTTP_403_FORBIDDEN)

        task.has_problem = True
        task.done = False
        task.problem_message = problemMessage
        db.commit()
        db.refresh(task)
        
        logger.info(f"Task {task.name} marked as problematic in branch {task.branch.name}")
        return True
    except Exception as e:
        handle_exception(e)

# Эндпоинты для работы с пользователями
@app.get("/user")
async def get_user(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return {
            "id": current_user.id,
            "login": current_user.login,
            "email": current_user.email,
            "fullName": current_user.full_name,
            "globalRole": current_user.role,
            "skillIds": [skill.id for skill in current_user.skills],
            "createdAt": current_user.created_at.isoformat() if current_user.created_at else None,
            "avatarUrl": current_user.avatar_url
        }
    except Exception as e:
        handle_exception(e)

@app.get("/user/tasks")
async def get_user_tasks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        tasks = db.query(Task).filter(Task.assigned_to_id == current_user.id).all()
        result = []
        for task in tasks:
            task_dto = {
                    "taskId": task.id,
                    "title": task.name,
                    "description": task.description,
                    "startDate": task.start_date.isoformat() if task.start_date else None,
                    "endDate": task.end_date.isoformat() if task.end_date else None,
                    "done": task.done,
                    "hasProblem": task.has_problem,
                    "problemMessage": task.problem_message,
                    "skillId": task.skill_id,
                    "assignedTo": task.assigned_to_id,
                    "file": task.file
                }
            result.append(task_dto)
        return result
    except Exception as e:
        handle_exception(e)

# Эндпоинты для работы с изображениями
@app.post("/images")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        # Создаем директорию для изображений, если её нет
        os.makedirs("uploads", exist_ok=True)
        
        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join("uploads", unique_filename)
        
        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"Image uploaded by {current_user.login}: {unique_filename}")
        return f"/uploads/{unique_filename}"
    except Exception as e:
        handle_exception(e)

@app.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        # Создаем директорию для изображений, если её нет
        os.makedirs("uploads", exist_ok=True)
        
        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join("uploads", unique_filename)
        
        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"File uploaded by {current_user.login}: {unique_filename}")
        return f"/media/{unique_filename}"
    except Exception as e:
        handle_exception(e)

# Административные эндпоинты
@app.get("/admin/skills")
async def get_skills(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # if current_user.role != "ADMIN":
        #     raise AppException("Not authorized", status.HTTP_403_FORBIDDEN)
        
        skills = db.query(Skill).all()
        return skills
    except Exception as e:
        handle_exception(e)

@app.get("/admin/user")
async def get_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # if current_user.role != "ADMIN":
        #     raise AppException("Not authorized", status.HTTP_403_FORBIDDEN)
        
        users = db.query(User).all()
        return [
            {
                "id": user.id,
                "login": user.login,
                "email": user.email,
                "fullName": user.full_name,
                "globalRole": user.role,
                "skillIds": [skill.id for skill in user.skills],
                "createdAt": user.created_at.isoformat() if user.created_at else None,
                "avatarUrl": user.avatar_url
            } for user in users
        ]
    except Exception as e:
        handle_exception(e)

@app.post("/admin/skills")
async def add_skill(
    skill_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if current_user.role != "ADMIN":
            raise AppException("Not authorized", status.HTTP_403_FORBIDDEN)
        
        new_skill = Skill(name=skill_data["name"])
        db.add(new_skill)
        db.commit()
        db.refresh(new_skill)
        
        logger.info(f"New skill added by admin {current_user.login}: {new_skill.name}")
        return new_skill
    except Exception as e:
        handle_exception(e)

@app.get("/project/{project_id}")
async def get_project_info(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to view this project", status.HTTP_403_FORBIDDEN)

        # Получаем все ветки проекта
        branches = db.query(Branch).filter(Branch.project_id == project_id).all()
        
        # Формируем статистику по задачам
        total_tasks = 0
        completed_tasks = 0
        delayed_tasks = 0
        problem_tasks = 0
        
        branch_dtos = []
        for branch in branches:
            tasks = db.query(Task).filter(Task.branch_id == branch.id).all()
            branch_tasks = []
            
            for task in tasks:
                total_tasks += 1
                if task.done:
                    completed_tasks += 1
                if task.has_problem:
                    problem_tasks += 1
                if task.end_date and task.end_date < datetime.now() and not task.done:
                    delayed_tasks += 1
                
                task_dto = {
                    "taskId": task.id,
                    "title": task.name,
                    "description": task.description,
                    "startDate": task.start_date.isoformat() if task.start_date else None,
                    "endDate": task.end_date.isoformat() if task.end_date else None,
                    "done": task.done,
                    "hasProblem": task.has_problem,
                    "problemMessage": task.problem_message,
                    "skillId": task.skill_id,
                    "assignedTo": task.assigned_to_id,
                    "file": task.file
                }
                branch_tasks.append(task_dto)
            
            branch_dto = {
                "branchId": branch.id,
                "name": branch.name,
                "tasks": branch_tasks,
                "statistics": {
                    "taskCount": len(branch_tasks),
                    "completedTasksCount": sum(1 for t in branch_tasks if t["done"]),
                    "delayedTasksCount": sum(1 for t in branch_tasks if t["endDate"] and datetime.fromisoformat(t["endDate"]) < datetime.now() and not t["done"]),
                    "problemTasksCount": sum(1 for t in branch_tasks if t["hasProblem"])
                }
            }
            branch_dtos.append(branch_dto)

        project_dto = {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "createdAt": project.created_at.isoformat() if project.created_at else None,
            "avatarUrl": project.avatar_url,
            "projectMembers": [
                {
                    "userId": member.id,
                    "login": member.login,
                    "email": member.email,
                    "role": member.role,
                    "avatarUrl": member.avatar_url
                } for member in project.members
            ]
        }

        task_statistics = {
            "taskCount": total_tasks,
            "completedTasksCount": completed_tasks,
            "delayedTasksCount": delayed_tasks,
            "problemTasksCount": problem_tasks
        }

        return {
            "projectId": project.id,
            "projectDTO": project_dto,
            "project": {
                "projectId": project.id,
                "branches": branch_dtos,
                "statistics": task_statistics
            }
        }
    except Exception as e:
        handle_exception(e)

@app.post("/user/edit")
async def edit_user(
    user_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Проверяем, что пользователь редактирует свой профиль или имеет права администратора
        if current_user.id != user_data["id"] and current_user.role != "ADMIN":
            raise AppException("Not authorized to edit this user", status.HTTP_403_FORBIDDEN)

        user = db.query(User).filter(User.id == user_data["id"]).first()
        if not user:
            raise AppException("User not found", status.HTTP_404_NOT_FOUND)

        # Обновляем основные данные пользователя
        user.login = user_data["login"]
        user.email = user_data["email"]
        user.full_name = user_data.get("fullName")
        user.role = user_data["globalRole"]
        user.avatar_url = user_data.get("avatarUrl")

        # Обновляем навыки пользователя
        if "skillIds" in user_data:
            # Получаем все навыки
            skills = db.query(Skill).filter(Skill.id.in_(user_data["skillIds"])).all()
            # Очищаем текущие навыки и добавляем новые
            user.skills = []
            user.skills.extend(skills)

        db.commit()
        db.refresh(user)

        # Формируем ответ в соответствии с интерфейсом UserDTO
        return {
            "id": user.id,
            "login": user.login,
            "email": user.email,
            "fullName": user.full_name,
            "globalRole": user.role,
            "skillIds": [skill.id for skill in user.skills],
            "createdAt": user.created_at.isoformat() if user.created_at else None,
            "avatarUrl": user.avatar_url
        }
    except Exception as e:
        handle_exception(e)

@app.post("/projects/{project_id}/users")
async def add_user_to_project(
    project_id: int,
    user_project_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to add users", status.HTTP_403_FORBIDDEN)

        user = db.query(User).filter(User.id == user_project_data["userId"]).first()
        if not user:
            raise AppException("User not found", status.HTTP_404_NOT_FOUND)

        if user in project.members:
            raise AppException("User is already a member of this project", status.HTTP_400_BAD_REQUEST)

        project.members.append(user)
        db.commit()
        
        logger.info(f"User {user.login} added to project {project.name}")
        return project
    except Exception as e:
        handle_exception(e)

@app.post("/projects/{project_id}/users/{user_id}")
async def remove_user_from_project(
    project_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to remove users", status.HTTP_403_FORBIDDEN)

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise AppException("User not found", status.HTTP_404_NOT_FOUND)

        if user not in project.members:
            raise AppException("User is not a member of this project", status.HTTP_400_BAD_REQUEST)

        project.members.remove(user)
        db.commit()
        
        logger.info(f"User {user.login} removed from project {project.name}")
        return project
    except Exception as e:
        handle_exception(e)

@app.post("/projects/{project_id}/users/{user_id}/edit")
async def modify_user_in_project(
    project_id: int,
    user_id: int,
    user_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to modify users", status.HTTP_403_FORBIDDEN)

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise AppException("User not found", status.HTTP_404_NOT_FOUND)

        if user not in project.members:
            raise AppException("User is not a member of this project", status.HTTP_400_BAD_REQUEST)

        # Здесь можно добавить логику изменения роли пользователя в проекте
        # Например, если у вас есть таблица ProjectMember с дополнительными полями
        
        db.commit()
        
        logger.info(f"User {user.login} modified in project {project.name}")
        return project
    except Exception as e:
        handle_exception(e)

@app.post("/projects/{project_id}/delete")
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise AppException("Project not found", status.HTTP_404_NOT_FOUND)
        
        if current_user not in project.members:
            raise AppException("Not authorized to delete project", status.HTTP_403_FORBIDDEN)

        db.delete(project)
        db.commit()
        
        logger.info(f"Project {project.name} deleted by {current_user.login}")
        return project
    except Exception as e:
        handle_exception(e)

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        # Пробуем сначала ISO формат
        return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            # Пробуем формат DD.MM.YYYY
            return datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)