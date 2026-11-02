from sqlalchemy import select
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User

def main():
    settings=get_settings()
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email==str(settings.admin_email).lower())):
            db.add(User(email=str(settings.admin_email).lower(),password_hash=hash_password(settings.admin_password),role="admin")); db.commit()
if __name__=="__main__": main()
