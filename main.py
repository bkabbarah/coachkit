from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

clients = [
    {"name": "Alex", "last_checkin": "2 days ago", "status": "on_track"},
    {"name": "Jordan", "last_checkin": "5 days ago", "status": "at_risk"},
    {"name": "Sam", "last_checkin": "Today", "status": "on_track"},
    {"name": "Riley", "last_checkin": "8 days ago", "status": "at_risk"},
]

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "coach_name": "Bashar",
        "clients": clients
    })

@app.get("/client/{client_id}")
def get_client(request: Request, client_id: int):
    client = clients[client_id]
    return templates.TemplateResponse("partials/client_detail.html", {
        "request": request,
        "client": client
    })