import time
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from collections import defaultdict
from typing import List
from fastapi.middleware.cors import CORSMiddleware

from . import models, schemas, crud, database

# Create tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="VinnoDrive API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (simplest for testing)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

# --- Rate Limiting ---
RATE_LIMIT_CALLS = 2
RATE_LIMIT_WINDOW = 1.0 # Seconds
request_history = defaultdict(list)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    now = time.time()
    request_history[client_ip] = [t for t in request_history[client_ip] if now - t < RATE_LIMIT_WINDOW]
    
    if len(request_history[client_ip]) >= RATE_LIMIT_CALLS:
        return Response(content="Rate limit exceeded (2 req/sec).", status_code=429)
    
    request_history[client_ip].append(now)
    response = await call_next(request)
    return response

# --- Routes ---

@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    return crud.create_user(db=db, user=user)

@app.post("/upload/{user_id}", response_model=schemas.FileResponse)
def upload_file(user_id: int, file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    return crud.upload_file(db=db, user_id=user_id, file=file)

@app.get("/stats/{user_id}")
def get_stats(user_id: int, db: Session = Depends(database.get_db)):
    """Returns storage insights"""
    return crud.get_user_stats(db=db, user_id=user_id)

@app.get("/download/{file_id}")
def download_file(file_id: int, user_id: int = None, db: Session = Depends(database.get_db)):
    """Increments counter and serves file"""
    file_path, filename = crud.get_downloadable_file(db=db, file_id=file_id, user_id=user_id)
    return FileResponse(file_path, media_type='application/octet-stream', filename=filename)

@app.delete("/files/{file_id}")
def delete_file(file_id: int, user_id: int, db: Session = Depends(database.get_db)):
    success = crud.delete_file(db=db, file_id=file_id, user_id=user_id)
    return {"status": "deleted successfully"}

@app.get("/files/{user_id}", response_model=List[schemas.FileResponse])
def get_user_files(user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return []
    
    # helper list to store fixed data
    results = []
    
    for f in user.files:
        # We assume deduplication is active if more than 1 reference exists
        is_dedup = False
        if f.blob and f.blob.ref_count > 1:
            is_dedup = True

        results.append({
            "id": f.id,
            "filename": f.filename,
            # We grab the size from the 'blob' relationship
            "size_bytes": f.blob.size_bytes if f.blob else 0,
            "upload_date": f.upload_date,
            "is_deduplicated": is_dedup,
            "download_count": f.download_count
        })
        
    return results
