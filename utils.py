import hashlib

def calculate_hash(file_file) -> str:
    """Reads file stream and returns SHA-256 hash"""
    sha256 = hashlib.sha256()
    # Read in 8kb chunks to prevent memory crash on large files
    while chunk := file_file.read(8192):
        sha256.update(chunk)
    file_file.seek(0) # Reset cursor to start so we can save it later!
    return sha256.hexdigest()