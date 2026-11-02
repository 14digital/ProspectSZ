from pathlib import Path

def test_authentication_required(client): assert client.get("/api/v1/companies").status_code==401
def test_login_rejects_bad_password(client): assert client.post("/api/v1/auth/token",data={"username":"admin@example.com","password":"wrong"}).status_code==401
def test_migration_exists(): assert Path("migrations/versions/0001_initial.py").exists()
def test_health(client): assert client.get("/health").json()=={"status":"ok"}
