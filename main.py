from fastapi import FastAPI, Request, Depends, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from models import Base, Coach, Client, CheckIn
import uuid
import os
import tempfile
import json
from ai_service import generate_reengagement_message
from import_service import read_spreadsheet, analyze_columns, preview_import, parse_spreadsheet_for_import
from auth_service import hash_password, verify_password, create_token, get_current_coach_id

from database import engine, get_db

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Auth dependency
async def require_auth(request: Request, db: AsyncSession = Depends(get_db)):
    coach_id = get_current_coach_id(request)
    if not coach_id:
        return None
    result = await db.execute(select(Coach).where(Coach.id == coach_id))
    return result.scalar_one_or_none()

# Auth routes
@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Coach).where(Coach.email == email))
    coach = result.scalar_one_or_none()
    
    if not coach or not verify_password(password, coach.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })
    
    token = create_token(coach.id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=7*24*60*60)
    return response

@app.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Check if email exists
    result = await db.execute(select(Coach).where(Coach.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse("signup.html", {
            "request": request,
            "error": "Email already registered"
        })
    
    # Create coach
    coach = Coach(
        name=name,
        email=email,
        password_hash=hash_password(password)
    )
    db.add(coach)
    await db.commit()
    
    token = create_token(coach.id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=7*24*60*60)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response

# Main app routes (now protected)
@app.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return RedirectResponse(url="/login", status_code=303)
    
    result = await db.execute(
        select(Client).where(Client.coach_id == coach.id)
    )
    clients = result.scalars().all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "coach_name": coach.name,
        "clients": clients
    })

@app.get("/client/new")
async def new_client_form(request: Request, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse("partials/client_form.html", {
        "request": request
    })

@app.get("/client/{client_id}")
async def get_client(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return RedirectResponse(url="/login", status_code=303)
    
    result = await db.execute(
        select(Client)
        .where(Client.id == client_id, Client.coach_id == coach.id)
        .options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    if not client:
        return HTMLResponse("Client not found", status_code=404)
    
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    client = Client(name=name, email=email, coach_id=coach.id)
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    # Verify client belongs to coach
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id)
    )
    client = result.scalar_one_or_none()
    if not client:
        return HTMLResponse("Client not found", status_code=404)
    
    photo_filename = None
    if photo and photo.filename:
        ext = os.path.splitext(photo.filename)[1]
        photo_filename = f"{uuid.uuid4()}{ext}"
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(
            Client.coach_id == coach.id,
            Client.name.ilike(f"%{q}%")
        )
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id)
    )
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id)
    )
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id)
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/edit_goal.html", {
        "request": request,
        "client": client
    })

@app.get("/client/{client_id}/goal")
async def get_goal(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id).options(selectinload(Client.checkins))
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
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    if not client:
        return HTMLResponse("Client not found", status_code=404)
    
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

@app.get("/analytics/empty")
async def analytics_empty(request: Request):
    return templates.TemplateResponse("partials/analytics_empty.html", {
        "request": request
    })

@app.get("/client/{client_id}/analytics")
async def client_analytics(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/analytics_tray.html", {
        "request": request,
        "client": client
    })

@app.get("/client/{client_id}/chart-modal")
async def chart_modal(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/chart_modal.html", {
        "request": request,
        "client": client
    })

@app.get("/checkin/{checkin_id}/photo-view")
async def photo_view(request: Request, checkin_id: int, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(CheckIn).where(CheckIn.id == checkin_id).options(selectinload(CheckIn.client))
    )
    checkin = result.scalar_one_or_none()
    
    # Verify the checkin's client belongs to coach
    if not checkin or checkin.client.coach_id != coach.id:
        return HTMLResponse("Not found", status_code=404)
    
    return templates.TemplateResponse("partials/photo_view.html", {
        "request": request,
        "checkin": checkin
    })

@app.post("/client/{client_id}/generate-message")
async def generate_message(
    request: Request,
    client_id: int,
    db: AsyncSession = Depends(get_db)
):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    if not client:
        return HTMLResponse("Client not found", status_code=404)
    
    message = generate_reengagement_message(
        client_name=client.name,
        days_inactive=client.days_since_checkin(),
        notes=client.notes,
        recent_checkins=list(client.checkins)
    )
    
    return templates.TemplateResponse("partials/generated_message.html", {
        "request": request,
        "client": client,
        "message": message
    })

@app.get("/client/{client_id}/at-risk-status")
async def at_risk_status(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.coach_id == coach.id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/at_risk_status.html", {
        "request": request,
        "client": client
    })

@app.get("/import")
async def import_page(request: Request, db: AsyncSession = Depends(get_db)):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    return templates.TemplateResponse("partials/import_modal.html", {
        "request": request
    })

@app.post("/import/analyze")
async def analyze_import(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    ext = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        df = read_spreadsheet(tmp_path)
        mapping = analyze_columns(df)
        preview = preview_import(df, mapping)
        
        return templates.TemplateResponse("partials/import_preview.html", {
            "request": request,
            "mapping": mapping,
            "preview": preview,
            "total_rows": len(df),
            "tmp_path": tmp_path,
            "filename": file.filename
        })
    except Exception as e:
        os.unlink(tmp_path)
        return templates.TemplateResponse("partials/import_error.html", {
            "request": request,
            "error": str(e)
        })

@app.post("/import/confirm")
async def confirm_import(
    request: Request,
    tmp_path: str = Form(...),
    mapping: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    coach = await require_auth(request, db)
    if not coach:
        return HTMLResponse("Unauthorized", status_code=401)
    
    try:
        mapping_dict = json.loads(mapping)
        df = read_spreadsheet(tmp_path)
        records = parse_spreadsheet_for_import(df, mapping_dict)
        
        imported_count = 0
        for record in records:
            client = Client(
                name=record["name"],
                email=record.get("email"),
                goal_weight=record.get("goal_weight"),
                notes=record.get("notes"),
                coach_id=coach.id
            )
            db.add(client)
            imported_count += 1
            
            if record.get("weight"):
                await db.flush()
                checkin = CheckIn(
                    client_id=client.id,
                    weight=record["weight"],
                    note="Imported from spreadsheet"
                )
                db.add(checkin)
        
        await db.commit()
        os.unlink(tmp_path)
        
        response = templates.TemplateResponse("partials/import_success.html", {
            "request": request,
            "count": imported_count
        })
        response.headers["HX-Trigger"] = "clientListChanged"
        return response
        
    except Exception as e:
        return templates.TemplateResponse("partials/import_error.html", {
            "request": request,
            "error": str(e)
        })