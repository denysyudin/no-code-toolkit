from flask import Blueprint
from app_utils import *
import logging
from services.audio_mixing import process_audio_mixing
from services.authentication import authenticate
from services.cloud_storage import upload_file

audio_mixing_bp = Blueprint('audio_mixing', __name__)
logger = logging.getLogger(__name__)

@audio_mixing_bp.route('/audio-mixing', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "audio_url": {"type": "string", "format": "uri"},
        "video_vol": {"type": "number", "minimum": 0, "maximum": 100},
        "audio_vol": {"type": "number", "minimum": 0, "maximum": 100},
        "output_length": {"type": "string", "enum": ["video", "audio"]},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url", "audio_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def audio_mixing(job_id, data):
    video_url = data.get('video_url')
    audio_url = data.get('audio_url')
    video_vol = data.get('video_vol', 100)
    audio_vol = data.get('audio_vol', 100)
    output_length = data.get('output_length', 'video')
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    logger.info(f"Job {job_id}: Received audio mixing request for {video_url} and {audio_url}")

    try:
        # Process audio and video mixing
        output_filename = process_audio_mixing(
            video_url, audio_url, video_vol, audio_vol, output_length, job_id, webhook_url
        )

        # Upload the mixed file using the unified upload_file() method
        cloud_url = upload_file(output_filename)

        logger.info(f"Job {job_id}: Mixed media uploaded to cloud storage: {cloud_url}")

        # Return the cloud URL for the uploaded file
        return cloud_url, "/audio-mixing", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error during audio mixing process - {str(e)}")
        return str(e), "/audio-mixing", 500
