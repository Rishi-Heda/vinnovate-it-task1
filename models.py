from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    
    # STATISTICS & QUOTA
    # Actual bytes taking up space on disk for this user (deduplicated)
    storage_used_actual = Column(BigInteger, default=0)
    # The size of files the user *thinks* they have (before deduplication)
    storage_used_original = Column(BigInteger, default=0)
    
    files = relationship("UserFile", back_populates="owner")

class FileBlob(Base):
    """
    Physical File Storage.
    Unique by content_hash (SHA-256).
    """
    __tablename__ = "file_blobs"
    
    content_hash = Column(String, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    ref_count = Column(Integer, default=1) 

class UserFile(Base):
    """
    Virtual File.
    """
    __tablename__ = "user_files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    
    # SHARING & METADATA
    is_public = Column(Boolean, default=False)
    download_count = Column(Integer, default=0) #
    
    user_id = Column(Integer, ForeignKey("users.id"))
    blob_hash = Column(String, ForeignKey("file_blobs.content_hash"))
    
    owner = relationship("User", back_populates="files")
    blob = relationship("FileBlob")