from database import Base, engine
from models import User, Project, Branch, Task, Skill

def create_tables():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_tables() 