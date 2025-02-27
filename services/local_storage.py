import os
import shutil
import logging
from datetime import datetime
from urllib.parse import urljoin
from flask import current_app

logger = logging.getLogger(__name__)

class LocalStorageProvider:
    def __init__(self):
        self.storage_dir = os.getenv('LOCAL_STORAGE_PATH', '/var/www/storage')
        self.base_url = os.getenv('BASE_URL', 'http://localhost:5000')
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """Ensure the storage directory exists"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)

    def _generate_unique_filename(self, original_filename):
        """Generate a unique filename to avoid conflicts"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        name, ext = os.path.splitext(original_filename)
        return f"{name}_{timestamp}{ext}"

    def upload_file(self, file_path: str) -> str:
        """
        Upload a file to local storage and return its public URL
        
        Args:
            file_path: Path to the file to upload
            
        Returns:
            str: Public URL of the uploaded file
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # Generate unique filename
            filename = self._generate_unique_filename(os.path.basename(file_path))
            destination = os.path.join(self.storage_dir, filename)

            # Copy file to storage directory
            shutil.copy2(file_path, destination)
            
            # Generate public URL
            relative_url = f'/storage/{filename}'
            public_url = urljoin(self.base_url, relative_url)
            
            logger.info(f"File uploaded successfully to local storage: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"Error uploading file to local storage: {e}")
            raise
