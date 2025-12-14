from fastapi import FastAPI, Request, Depends, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from models import Base, Client, CheckIn
import uuid
import os

from database import engine, get_db
from models import Base, Client

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
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
    client_id: int,
    note: str = Form(""),
    weight: float = Form(None),
    photo: UploadFile = File(None),
    db: AsyncSession = Depends(get_db)
    ):
    photo_filename = None
    
    if photo and photo.filename:
        # Generate unique filename
        ext = os.path.splitext(photo.filename)[1]
        photo_filename = f"{uuid.uuid4()}{ext}"
        
        # Save file
        file_path = f"static/uploads/{photo_filename}"
        with open(file_path, "wb") as f:
            content = await photo.read()
            f.write(content)
    
    checkin = CheckIn(
        client_id=client_id, 
        note=note, 
        weight=weight,
        photo=photo_filename
    )
    db.add(checkin)

    # update client's last_checkin time
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one()
    client.last_checkin = checkin.created_at

    await db.commit()
    await db.refresh(checkin)

    response = templates.TemplateResponse("partials/checkin_item.html", {
        "request": request,
        "checkin": checkin
    })

    response.headers["HX-Trigger"] = "checkinAdded"
    return response


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

@app.get("/client/{client_id}/edit-goal")
async def edit_goal_form(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/edit_goal.html", {
        "request": request,
        "client": client
    })

@app.get("/client/{client_id}/goal")
async def get_goal(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(Client.id == client_id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/goal_display.html", {
        "request": request,
        "client": client
    })

@app.put("/client/{client_id}/goal")
async def update_goal(
    request: Request,
    client_id: int,
    goal_weight: float = Form(None),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Client).where(Client.id == client_id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    client.goal_weight = goal_weight
    client.notes = notes
    await db.commit()
    await db.refresh(client)
    
    return templates.TemplateResponse("partials/goal_display.html", {
        "request": request,
        "client": client
    })

@app.get("/photo/{filename}")
async def view_photo(request: Request, filename: str):
    return templates.TemplateResponse("partials/photo_modal.html", {
        "request": request,
        "filename": filename
    })