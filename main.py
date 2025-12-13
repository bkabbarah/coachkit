from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import engine, get_db
from models import Base, Client

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client))
    clients = result.scalars().all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "coach_name": "Bashar",
        "clients": clients
    })

@app.get("/client/{client_id}")
async def get_client(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/client_detail.html", {
        "request": request,
        "client": client
    })

@app.post("/client")
async def create_client(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    client = Client(name=name, email=email)
    db.add(client)
    await db.commit()
    await db.refresh(client)

    return templates.TemplateResponse("partials/client_card.html", {
        "request": request,
        "client": client
    })