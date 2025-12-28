from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    class Config:
        from_attributes = True

class FileResponse(BaseModel):
    id: int
    filename: str
    size_bytes: int
    upload_date: datetime
    is_deduplicated: bool
    download_count: int
    
    class Config:
        from_attributes = True

class FileListResponse(FileResponse):
    pass