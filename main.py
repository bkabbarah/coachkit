from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from models import Base, Client, CheckIn

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

@app.get("/client/new")
async def new_client_form(request: Request):
    return templates.TemplateResponse("partials/client_form.html", {
        "request": request
    })

@app.get("/client/{client_id}")
async def get_client(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id).options(selectinload(Client.checkins)))
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

    result = await db.execute(
        select(Client).where(Client.id == client.id).options(selectinload(Client.checkins))
    )

    client = result.scalar_one()

    response = templates.TemplateResponse("partials/client_detail.html", {
        "request": request,
        "client": client
    })
    response.headers["HX-Trigger"] = "clientListChanged"
    return response

@app.post("/client/{client_id}/checkin")
async def create_checkin(
    request: Request,
    client_id = int,
    note: str = Form(""),
    weight: int = Form(None),
    db: AsyncSession = Depends(get_db)
):
    checkin = CheckIn(client_id=client_id, note=note, weight=weight)
    db.add(checkin)

    # update client's last_checkin time
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one()
    client.last_checkin = checkin.created_at

    await db.commit()
    await db.refresh(checkin)

    return templates.TemplateResponse("partials/checkin_item.html", {
        "request": request,
        "checkin": checkin
    })

@app.get("/clients/search")
async def search_clients(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(Client.name.ilike(f"%{q}%"))
    )
    clients = result.scalars().all()

    return templates.TemplateResponse("partials/client_list.html", {
        "request": request,
        "clients": clients
    })

@app.delete("/client/{client_id}")
async def delete_client(
    request: Request,
    client_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if client:
        await db.delete(client)
        await db.commit()
    
    response = templates.TemplateResponse("partials/client_placeholder.html", {
        "request": request
    })
    response.headers["HX-Trigger"] = "clientListChanged"
    return response
    
@app.get("/client/{client_id}/delete-modal")
async def delete_modal(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/delete_modal.html", {
        "request": request,
        "client": client
    })

@app.get("/modal/close")
async def close_modal():
    return HTMLResponse("")
