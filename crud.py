from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse
import shutil
import os
from . import models, schemas, utils

UPLOAD_DIR = "uploads"
MAX_STORAGE_QUOTA = 10 * 1024 * 1024  # 10 MB

os.makedirs(UPLOAD_DIR, exist_ok=True)

def create_user(db: Session, user: schemas.UserCreate):
    fake_hashed_password = user.password + "notreallyhashed"
    db_user = models.User(email=user.email, hashed_password=fake_hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def upload_file(db: Session, user_id: int, file: UploadFile):
    # 1. Calculate Hash
    file_hash = utils.calculate_hash(file.file)
    
    # 2. Check Deduplication Status
    existing_blob = db.query(models.FileBlob).filter(models.FileBlob.content_hash == file_hash).first()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_dedup = False
    bytes_to_charge = 0
    file_size = 0

    if existing_blob:
        # Store only a reference
        is_dedup = True
        file_size = existing_blob.size_bytes
        # Cost to quota is 0 because we aren't using new disk space!
        bytes_to_charge = 0 
    else:
        # Calculate size before saving to check quota
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
        
        bytes_to_charge = file_size
    
    # 3. QUOTA CHECK
    # We check if (Actual Used + New Bytes) > 10MB
    if user.storage_used_actual + bytes_to_charge > MAX_STORAGE_QUOTA:
        raise HTTPException(status_code=413, detail="Storage quota of 10MB exceeded.")

    # 4. Save Logic
    if existing_blob:
        existing_blob.ref_count += 1
    else:
        file_path = os.path.join(UPLOAD_DIR, f"{file_hash}_{file.filename}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        new_blob = models.FileBlob(
            content_hash=file_hash,
            file_path=file_path,
            size_bytes=file_size,
            ref_count=1
        )
        db.add(new_blob)

    # 5. Create Virtual File & Update Stats
    user_file = models.UserFile(
        filename=file.filename,
        user_id=user_id,
        blob_hash=file_hash,
        is_public=False # Private by default
    )
    
    # Update User Stats
    user.storage_used_actual += bytes_to_charge
    user.storage_used_original += file_size # This always goes up
    
    db.add(user_file)
    db.commit()
    db.refresh(user_file)
    
    return {
        "id": user_file.id,
        "filename": user_file.filename,
        "size_bytes": file_size,
        "upload_date": user_file.upload_date,
        "is_deduplicated": is_dedup,
        "download_count": 0
    }

def get_downloadable_file(db: Session, file_id: int, user_id: int = None):
    """
    Handles sharing rules and download counters.
    """
    user_file = db.query(models.UserFile).filter(models.UserFile.id == file_id).first()
    if not user_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Access Control: Owner OR Public
    if not user_file.is_public and (user_id != user_file.user_id):
        raise HTTPException(status_code=403, detail="Access denied. This file is private.")

    # Increment download count
    user_file.download_count += 1
    db.commit()

    return user_file.blob.file_path, user_file.filename

def get_user_stats(db: Session, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    saved_bytes = user.storage_used_original - user.storage_used_actual
    saved_pct = 0
    if user.storage_used_original > 0:
        saved_pct = (saved_bytes / user.storage_used_original) * 100
        
    return {
        "actual_used_bytes": user.storage_used_actual,
        "original_size_bytes": user.storage_used_original,
        "savings_bytes": saved_bytes,
        "savings_percentage": round(saved_pct, 2)
    }

def delete_file(db: Session, file_id: int, user_id: int):
    # Only the uploader can delete
    user_file = db.query(models.UserFile).filter(models.UserFile.id == file_id).first()
    if not user_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    if user_file.user_id != user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own files.")

    blob_hash = user_file.blob_hash
    file_size = user_file.blob.size_bytes
    blob = user_file.blob
    user = user_file.owner
    
    # Update Stats
    # Note: If it was deduped, we didn't charge actual, so we don't refund actual unless ref_count==1
    # But for simplicity in this logic, we track strictly what we added.
    # Refined Logic: We reduce original size always. We reduce actual ONLY if we delete the BLOB.
    # Wait, that's complex. Better approach:
    # If ref_count > 1: It was "free" or shared.
    # Let's stick to the prompt's requirement: "Actual storage used".
    
    # We remove the virtual file
    db.delete(user_file)
    user.storage_used_original -= file_size
    
    blob.ref_count -= 1
    
    # Delete only when all references are gone
    if blob.ref_count <= 0:
        if os.path.exists(blob.file_path):
            os.remove(blob.file_path)
        db.delete(blob)
        # Refund the actual storage cost since the physical file is gone
        user.storage_used_actual -= file_size 
            
    db.commit()
    return True