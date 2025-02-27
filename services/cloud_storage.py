import os
import logging
from abc import ABC, abstractmethod
from services.local_storage import LocalStorageProvider

logger = logging.getLogger(__name__)

class CloudStorageProvider(ABC):
    @abstractmethod
    def upload_file(self, file_path: str) -> str:
        pass

def get_storage_provider() -> CloudStorageProvider:
    """Get the appropriate storage provider based on configuration"""
    return LocalStorageProvider()

def upload_file(file_path: str) -> str:
    provider = get_storage_provider()
    try:
        logger.info(f"Uploading file to storage: {file_path}")
        url = provider.upload_file(file_path)
        logger.info(f"File uploaded successfully: {url}")
        return url
    except Exception as e:
        logger.error(f"Error uploading file to storage: {e}")
        raise
    