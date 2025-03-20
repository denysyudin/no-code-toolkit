import os

# Retrieve the API key from environment variables
API_KEY = os.environ.get('API_KEY')
# if not API_KEY:
#     raise ValueError("API_KEY environment variable is not set")

# Local storage configuration
LOCAL_STORAGE_PATH = os.environ.get('LOCAL_STORAGE_PATH', '/var/www/storage')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

# Temporary storage path for processing
TEMP_STORAGE_PATH = os.environ.get('TEMP_STORAGE_PATH', '/tmp')

def validate_storage_config():
    """Validate the storage configuration"""
    if not os.path.exists(LOCAL_STORAGE_PATH):
        try:
            os.makedirs(LOCAL_STORAGE_PATH, exist_ok=True)
        except Exception as e:
            raise ValueError(f"Could not create storage directory at {LOCAL_STORAGE_PATH}: {e}")
    
    if not os.access(LOCAL_STORAGE_PATH, os.W_OK):
        raise ValueError(f"Storage directory {LOCAL_STORAGE_PATH} is not writable")

# Validate storage configuration on import
validate_storage_config()

# Storage provider interface
class CloudStorageProvider:
    """ Abstract CloudStorageProvider class to define the upload_file method """
    def upload_file(self, file_path: str) -> str:
        raise NotImplementedError("upload_file must be implemented by subclasses")

def get_storage_provider() -> CloudStorageProvider:
    """ Get the appropriate storage provider based on the available environment variables """
    from services.local_storage import LocalStorageProvider
    return LocalStorageProvider()
