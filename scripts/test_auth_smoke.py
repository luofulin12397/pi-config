"""快速验证鉴权接口。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.api.http.query_server import app

client = TestClient(app)
r = client.post("/auth/login", json={"username": "admin", "password": "admin123", "remember_me": False})
assert r.status_code == 200, r.text
data = r.json()["data"]
token = data["access_token"]
headers = {"Authorization": f"Bearer {token}"}

r2 = client.get("/auth/me", headers=headers)
assert r2.status_code == 200
assert r2.json()["data"]["username"] == "admin"

r3 = client.get("/auth/roles", headers=headers)
assert r3.status_code == 200
assert len(r3.json()["data"]) >= 4

r4 = client.post("/auth/logout", headers=headers, json={"refresh_token": data["refresh_token"]})
assert r4.status_code == 200

print("auth smoke test passed")
