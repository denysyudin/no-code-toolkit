from flask import Blueprint, jsonify, request, abort
from app_utils import validate_payload, queue_task_wrapper
import logging
import os
import uuid
import requests
from services.authentication import authenticate
from services.cloud_storage import upload_file
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
from typing import List, Dict, Any

v1_video_caption_bp = Blueprint('v1_video/caption', __name__)
logger = logging.getLogger(__name__)

@v1_video_caption_bp.route('/v1/video/caption', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "transcribe": {"type": "array"},
        "settings": {
            "type": "object",
            "properties": {
                "line_color": {"type": "string"},
                "word_color": {"type": "string"},
                "outline_color": {"type": "string"},
                "all_caps": {"type": "boolean"},
                "max_words_per_line": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "position": {
                    "type": "string",
                    "enum": [
                        "bottom_left", "bottom_center", "bottom_right",
                        "middle_left", "middle_center", "middle_right",
                        "top_left", "top_center", "top_right"
                    ]
                },
                "alignment": {
                    "type": "string",
                    "enum": ["left", "center", "right"]
                },
                "font_family": {"type": "string"},
                "font_size": {"type": "integer"},
                "position": {"type": "string"}
            }
        },
        "replace": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "find": {"type": "string"},
                    "replace": {"type": "string"}
                },
                "required": ["find", "replace"]
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url", "transcribe", "settings"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def caption_video_v1(job_id, data):
    video_url = data['video_url']
    transcribe = data['transcribe']
    settings = data.get('settings', {})
    replace = data.get('replace', [])
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    logger.info(f"Job {job_id}: Received v1 captioning request for {video_url}")
    logger.info(f"Job {job_id}: Settings received: {settings}")
    logger.info(f"Job {job_id}: Replace rules received: {replace}")

    try:
        # Create directories if they don't exist
        os.makedirs("downloads", exist_ok=True)
        os.makedirs("output", exist_ok=True)
        
        # Download the video file
        local_video_path = download_video(video_url, job_id)
        
        try:
            # Process the video with MoviePy
            output_filename = process_transcription(
                local_video_path, 
                transcribe, 
                replace, 
                settings,
                job_id
            )
            
            # Full path to the output file
            output_path = f"output/{output_filename}"
            logger.info(f"Job {job_id}: Captioning process completed successfully")

            # Upload the captioned video
            cloud_url = upload_file(output_path)
            logger.info(f"Job {job_id}: Captioned video uploaded to cloud storage: {cloud_url}")

            # Clean up the files after upload
            try:
                if os.path.exists(local_video_path):
                    os.remove(local_video_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                logger.info(f"Job {job_id}: Cleaned up local files")
            except Exception as e:
                logger.warning(f"Job {job_id}: Error cleaning up files: {str(e)}")
            
            return cloud_url, "/v1/video/caption", 200
            
        except Exception as e:
            logger.error(f"Job {job_id}: Error processing video: {str(e)}", exc_info=True)
            return {"error": str(e)}, "/v1/video/caption", 500
        finally:
            # Clean up the downloaded file
            try:
                if os.path.exists(local_video_path):
                    os.remove(local_video_path)
            except:
                pass
    except Exception as e:
        logger.error(f"Job {job_id}: Error during captioning process - {str(e)}", exc_info=True)
        return {"error": str(e)}, "/v1/video/caption", 500

def download_video(url: str, job_id: str) -> str:
    """
    Download video from URL and return the local file path.
    """
    try:
        # Generate unique filename
        filename = f"downloads/{uuid.uuid4()}.mp4"
        
        logger.info(f"Job {job_id}: Downloading video from {url}")
        
        # Stream download to avoid loading large files into memory
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        logger.info(f"Job {job_id}: Video downloaded to {filename}")
        return filename
    except Exception as e:
        logger.error(f"Job {job_id}: Failed to download video: {str(e)}", exc_info=True)
        raise Exception(f"Failed to download video: {str(e)}")

def process_transcription(video_path: str, transcribe: List[Dict[str, Any]], 
                         replace_words: List[Dict[str, str]], settings: Dict[str, Any],
                         job_id: str) -> str:
    """
    Process video by dividing it according to transcription timestamps and adding text overlays.
    """
    logger.info(f"Job {job_id}: Processing video with {len(transcribe)} transcription entries")
    
    # Load video
    video = VideoFileClip(video_path)
    # Track all created clips
    clips = []
    
    # Word replacements dictionary for censoring
    replacements = {item['find']: item['replace'] for item in replace_words}

    # Process each transcription item
    previous_end_time = 0
    
    for i, word_data in enumerate(transcribe):
        logger.debug(f"Job {job_id}: Processing word {i+1}/{len(transcribe)}")
        start_time = word_data['start']
        end_time = word_data['end']
        
        # Skip invalid time ranges
        if end_time < start_time or start_time < 0 or end_time > video.duration:
            continue
        
        # Check if there's a gap between previous word and current word
        if previous_end_time > 0 and start_time > previous_end_time and start_time != 0:
            # Create a silent clip for the gap
            gap_clip = video.subclip(previous_end_time, start_time)
            clips.append(gap_clip)
            logger.debug(f"Job {job_id}: Added silent gap clip from {previous_end_time} to {start_time}")

        # Update previous_end_time for the next iteration
        previous_end_time = end_time
            
        # Get word, applying replacements if needed
        display_word = word_data['word']
        
        for find, replace in replacements.items():
            if find.lower() in display_word.lower():
                display_word = replace
                
        # Apply text formatting from settings
        if settings.get('all_caps', False):
            display_word = display_word.upper()
        
        word_clip = video.subclip(start_time, end_time)
        
        # Default font path in the project
        font_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
                                 "fonts", "arial.ttf")
        
        # Create text clip
        txt_clip = TextClip(
            txt=display_word,
            fontsize=settings.get('font_size', 24),
            color=settings.get('word_color', 'white'),
            font=font_path if os.path.exists(font_path) else None
        ).set_duration(end_time - start_time)
        
        # Position text based on settings
        position = settings.get('position', 'bottom_center')
        if position == "middle_center":
            txt_clip = txt_clip.set_position('center')
        elif position == "bottom_center":
            txt_clip = txt_clip.set_position(('center', 'bottom'))
        elif position == "top_center":
            txt_clip = txt_clip.set_position(('center', 'top'))
        else:
            txt_clip = txt_clip.set_position('center')
            
        # Combine video and text
        composite = CompositeVideoClip([word_clip, txt_clip])
        clips.append(composite)
    
    # Concatenate all clips
    if clips:
        logger.info(f"Job {job_id}: Concatenating {len(clips)} clips")
        final_clip = concatenate_videoclips(clips)
        
        # Generate output filename with UUID
        output_filename = f"{uuid.uuid4()}.mp4"
        output_path = f"output/{output_filename}"
        
        # Write final video
        logger.info(f"Job {job_id}: Writing output video to {output_path}")
        final_clip.write_videofile(output_path, codec="libx264", logger=None)
        
        # Close clips to release resources
        final_clip.close()
        for clip in clips:
            clip.close()
        video.close()
        
        logger.info(f"Job {job_id}: Video processing complete")
        return output_filename
    else:
        video.close()
        logger.error(f"Job {job_id}: No valid word segments found in transcription")
        raise Exception("No valid word segments found in transcription")
