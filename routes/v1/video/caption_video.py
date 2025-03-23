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
import glob

v1_video_caption_bp = Blueprint('v1_video/caption', __name__)
logger = logging.getLogger(__name__)

@v1_video_caption_bp.route('/v1/video/caption', methods=['POST'])
# @authenticate
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

    # Get the maximum words per line from settings
    max_words_per_line = settings.get('max_words_per_line', 1)
    logger.info(f"Job {job_id}: Using max_words_per_line={max_words_per_line}")
    
    # Process transcription in batches according to max_words_per_line
    i = 0
    previous_end_time = 0
    
    while i < len(transcribe):
        # Determine the batch size (not exceeding the end of the transcription)
        batch_size = min(max_words_per_line, len(transcribe) - i)
        batch = transcribe[i:i+batch_size]
        
        # Get the start time from the first word and end time from the last word in the batch
        start_time = batch[0]['start']
        end_time = batch[-1]['end']
        
        logger.debug(f"Job {job_id}: Processing batch of {batch_size} words from index {i}")
        
        # Skip invalid time ranges
        if end_time < start_time or start_time < 0 or end_time > video.duration:
            i += batch_size
            continue
        
        # Check if there's a gap between previous word and current word
        if previous_end_time > 0 and start_time > previous_end_time and start_time != 0:
            # Create a silent clip for the gap
            gap_clip = video.subclipped(previous_end_time, start_time)
            clips.append(gap_clip)
            logger.debug(f"Job {job_id}: Added silent gap clip from {previous_end_time} to {start_time}")

        # Update previous_end_time for the next iteration
        previous_end_time = end_time
        
        # Process all words in the batch
        display_text = ""
        for word_data in batch:
            # Get word, applying replacements if needed
            display_word = word_data['word']
            
            for find, replace in replacements.items():
                if find.lower() in display_word.lower():
                    display_word = replace
            
            # Add space between words
            if display_text:
                display_text += " "
            display_text += display_word
        
        # Apply text formatting from settings
        if settings.get('all_caps', False):
            display_text = display_text.upper()
        
        word_clip = video.subclipped(start_time, end_time)
        
        # Default font path in the project
        font_family = settings.get('font_family', 'Arial')
        font_path = find_font_file(font_family)
        
        # Create text clip with styling based on settings
        position = settings.get('position', 'middle_center')
        if 'bottom' in position:
            if 'left' in position:
                vertical_position = 'bottom'
                horizontal_position = 'left'
            elif 'right' in position:
                vertical_position = 'bottom'
                horizontal_position = 'right'
            else:
                vertical_position = 'bottom'
                horizontal_position = 'center'
        elif 'top' in position:
            if 'left' in position:
                vertical_position = 'top'
                horizontal_position = 'left'
            elif 'right' in position:
                vertical_position = 'top'
                horizontal_position = 'right'
            else:
                vertical_position = 'top'
                horizontal_position = 'center'
        elif 'middle' in position:
            if 'left' in position:
                vertical_position = 'center'
                horizontal_position = 'left'
            elif 'right' in position:
                vertical_position = 'center'
                horizontal_position = 'right'
            else:
                vertical_position = 'center'
                horizontal_position = 'center'
        else:
            vertical_position = 'center'
            horizontal_position = 'center'

        txt_clip = TextClip(
            text=display_text,
            font=font_path,
            font_size=settings.get('font_size', 24),
            color=settings.get('word_color', 'white'),
            stroke_color=settings.get('line_color', 'black'),
            stroke_width=settings.get('outline_width', 2),
            duration=end_time - start_time,
            vertical_align=vertical_position,
            horizontal_align=horizontal_position,
            text_align=settings.get('alignment', 'center'),
            method='caption',
            size=(video.w, video.h)
        )
            
        # Combine video and text
        composite = CompositeVideoClip([word_clip, txt_clip])
        clips.append(composite)
        
        # Move to the next batch
        i += batch_size
    
    # Add remaining video after the last transcription entry if it exists
    if previous_end_time < video.duration:
        remaining_clip = video.subclipped(previous_end_time, video.duration)
        clips.append(remaining_clip)
        logger.info(f"Job {job_id}: Added remaining video from {previous_end_time} to {video.duration}")
    
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

def find_font_file(font_name: str) -> str:
    """
    Find a font file in the fonts directory that matches the requested font name.
    If no matching font is found, returns the default 'Arial.ttf' font path.
    
    Args:
        font_name: Name of the font to search for
    
    Returns:
        Path to the matching font file or default font
    """
    font_dir = os.path.abspath("fonts")
    default_font = os.path.join(font_dir, "Arial.ttf")
    
    if not os.path.exists(font_dir):
        logger.warning(f"Fonts directory not found at {font_dir}")
        return default_font
    
    # Normalize the requested font name for comparison
    font_name_lower = font_name.lower().replace(" ", "").replace("-", "")
    
    # Get all font files
    font_files = glob.glob(os.path.join(font_dir, "*.ttf")) + glob.glob(os.path.join(font_dir, "*.TTF"))
    
    for font_file in font_files:
        # Extract basename without extension and normalize
        basename = os.path.splitext(os.path.basename(font_file))[0].lower().replace(" ", "").replace("-", "")
        
        # Check if the requested font name is in the font file name
        if font_name_lower in basename:
            logger.info(f"Found matching font: {font_file} for requested font: {font_name}")
            return font_file
    
    # If exact match not found, try partial match
    for font_file in font_files:
        basename = os.path.splitext(os.path.basename(font_file))[0].lower()
        
        # Check for partial matches
        if any(part in basename for part in font_name_lower.split()):
            logger.info(f"Found partial matching font: {font_file} for requested font: {font_name}")
            return font_file
    
    logger.warning(f"Font '{font_name}' not found in fonts directory, using default Arial")
    return default_font