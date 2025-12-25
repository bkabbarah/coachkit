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
from ai_service import generate_reengagement_message
from import_service import read_spreadsheet, analyze_columns, preview_import, parse_spreadsheet_for_import
import tempfile
import os as os_module

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

@app.get("/analytics/empty")
async def analytics_empty(request: Request):
    return templates.TemplateResponse("partials/analytics_empty.html", {
        "request": request
    })

@app.get("/client/{client_id}/analytics")
async def client_analytics(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(Client.id == client_id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/analytics_tray.html", {
        "request": request,
        "client": client
    })

@app.get("/client/{client_id}/chart-modal")
async def chart_modal(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(Client.id == client_id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/chart_modal.html", {
        "request": request,
        "client": client
    })

@app.get("/checkin/{checkin_id}/photo-view")
async def photo_view(request: Request, checkin_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CheckIn).where(CheckIn.id == checkin_id).options(selectinload(CheckIn.client))
    )
    checkin = result.scalar_one_or_none()
    
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
    result = await db.execute(
        select(Client).where(Client.id == client_id).options(selectinload(Client.checkins))
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

@app.get("/import")
async def import_page(request: Request):
    return templates.TemplateResponse("partials/import_modal.html", {
        "request": request
    })

@app.post("/import/analyze")
async def analyze_import(
    request: Request,
    file: UploadFile = File(...)
):
    # Save uploaded file temporarily
    ext = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Read and analyze
        df = read_spreadsheet(tmp_path)
        mapping = analyze_columns(df)
        preview = preview_import(df, mapping)
        
        # Store temp file path and mapping in session (we'll use a hidden field)
        return templates.TemplateResponse("partials/import_preview.html", {
            "request": request,
            "mapping": mapping,
            "preview": preview,
            "total_rows": len(df),
            "tmp_path": tmp_path,
            "filename": file.filename
        })
    except Exception as e:
        os_module.unlink(tmp_path)
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
    import json
    
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
                notes=record.get("notes")
            )
            db.add(client)
            imported_count += 1
            
            # If there's a weight, create an initial check-in
            if record.get("weight"):
                await db.flush()  # Get the client ID
                checkin = CheckIn(
                    client_id=client.id,
                    weight=record["weight"],
                    note="Imported from spreadsheet"
                )
                db.add(checkin)
        
        await db.commit()
        
        # Clean up temp file
        os_module.unlink(tmp_path)
        
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

@app.get("/client/{client_id}/at-risk-status")
async def at_risk_status(request: Request, client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(Client.id == client_id).options(selectinload(Client.checkins))
    )
    client = result.scalar_one_or_none()
    
    return templates.TemplateResponse("partials/at_risk_status.html", {
        "request": request,
        "client": client
    })