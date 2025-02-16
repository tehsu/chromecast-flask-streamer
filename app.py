from flask import Flask, render_template, request, jsonify, send_from_directory, url_for, Response
import pychromecast
from pychromecast.controllers.media import MediaController
from pychromecast.controllers.youtube import YouTubeController
from flask_cors import CORS
import logging
import re
from urllib.parse import urlparse, parse_qs
import os
import socket
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov', 'webm'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024 * 1024  # 16GB max file size

# Get local IP address
def get_local_ip():
    try:
        # Create a socket to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return '0.0.0.0'

# Server configuration
SERVER_IP = get_local_ip()
SERVER_PORT = 5000
BASE_URL = f'http://{SERVER_IP}:{SERVER_PORT}'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['SERVER_NAME'] = f'{SERVER_IP}:{SERVER_PORT}'

chromecasts = None
selected_chromecast = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def initialize_chromecasts():
    global chromecasts
    try:
        logger.info("Searching for Chromecast devices...")
        chromecasts, browser = pychromecast.get_chromecasts(timeout=10)
        logger.info(f"Found {len(chromecasts)} device(s)")
        return [{"name": cc.name, "uuid": str(cc.uuid)} for cc in chromecasts]
    except Exception as e:
        logger.error(f"Error discovering Chromecast devices: {str(e)}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/devices')
def get_devices():
    try:
        devices = initialize_chromecasts()
        logger.info(f"Returning devices: {devices}")
        return jsonify(devices)
    except Exception as e:
        logger.error(f"Error in get_devices: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/connect', methods=['POST'])
def connect_device():
    global selected_chromecast
    try:
        data = request.json
        device_uuid = data.get('uuid')
        
        for cc in chromecasts:
            if str(cc.uuid) == device_uuid:
                selected_chromecast = cc
                selected_chromecast.wait()
                return jsonify({"status": "success", "device": cc.name}), 200
        
        return jsonify({"status": "error", "message": "Device not found"}), 404
    except Exception as e:
        logger.error(f"Error in connect_device: {str(e)}")
        return jsonify({"error": str(e)}), 500

def get_youtube_video_id(url):
    """Extract YouTube video ID from URL."""
    # Full URLs
    parsed = urlparse(url)
    if 'youtube.com' in parsed.netloc:
        if 'watch' in parsed.path:
            return parse_qs(parsed.query).get('v', [None])[0]
        elif 'embed' in parsed.path:
            return parsed.path.split('/')[-1]
    # Shortened URLs
    elif 'youtu.be' in parsed.netloc:
        return parsed.path[1:]
    return None

def get_content_type(filename):
    """Get the content type based on file extension."""
    ext = filename.lower().split('.')[-1]
    content_types = {
        'mp4': 'video/mp4',
        'mkv': 'video/x-matroska',
        'avi': 'video/x-msvideo',
        'mov': 'video/quicktime',
        'webm': 'video/webm'
    }
    return content_types.get(ext, 'video/mp4')

@app.route('/stream', methods=['POST'])
def stream_media():
    global selected_chromecast
    if not selected_chromecast:
        return jsonify({"status": "error", "message": "No Chromecast selected"}), 400

    try:
        data = request.json
        media_url = data.get('url')
        
        if not media_url:
            return jsonify({"status": "error", "message": "No media URL provided"}), 400

        # Check if it's a YouTube URL
        youtube_id = get_youtube_video_id(media_url)
        
        if youtube_id:
            # Handle YouTube video
            selected_chromecast.wait()
            
            # Initialize YouTube controller
            yt = YouTubeController()
            selected_chromecast.register_handler(yt)
            
            try:
                yt.play_video(youtube_id)
                return jsonify({"status": "success", "message": "YouTube video streaming started"}), 200
            except Exception as e:
                logger.error(f"Error playing YouTube video: {str(e)}")
                return jsonify({"status": "error", "message": "Failed to play YouTube video"}), 500
        else:
            # Handle regular media URL
            try:
                # Make sure we're connected
                selected_chromecast.wait()
                
                # Stop any current app
                selected_chromecast.quit_app()
                selected_chromecast.wait()
                
                # Start the default media receiver
                selected_chromecast.start_app('CC1AD845')
                selected_chromecast.wait()
                
                # Get the media controller
                mc = selected_chromecast.media_controller
                
                # Check if it's a local uploaded file and ensure it uses the correct base URL
                if '/uploads/' in media_url:
                    filename = media_url.split('/')[-1]
                    media_url = f'{BASE_URL}/uploads/{filename}'
                    content_type = get_content_type(filename)
                else:
                    content_type = 'video/mp4'
                
                logger.info(f"Streaming URL: {media_url} with content type: {content_type}")
                
                # Play the media with specific metadata
                import time
                mc.play_media(
                    media_url,
                    content_type=content_type,
                    stream_type="BUFFERED",
                    autoplay=True,
                    metadata={
                        'metadataType': 0,  # GENERIC
                        'title': filename if '/uploads/' in media_url else "Streaming Media"
                    }
                )
                
                # Give it a moment to initialize
                time.sleep(2)
                
                # Ensure playback starts
                mc.play()
                    
                return jsonify({"status": "success", "message": "Media streaming started"}), 200
                
            except pychromecast.error.UnsupportedNamespace:
                return jsonify({"status": "error", "message": "Media receiver not available"}), 500
            except Exception as e:
                logger.error(f"Error in stream_media: {str(e)}")
                return jsonify({"status": "error", "message": str(e)}), 500
                
    except Exception as e:
        logger.error(f"Error in stream_media: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/control/<action>', methods=['POST'])
def media_control(action):
    global selected_chromecast
    if not selected_chromecast:
        return jsonify({"status": "error", "message": "No Chromecast selected"}), 400

    try:
        # Ensure connection
        selected_chromecast.wait()
        
        mc = selected_chromecast.media_controller
        
        # Force a status update
        mc.update_status()
        
        # Check if media controller is active
        if not mc.status or not mc.status.media_session_id:
            return jsonify({"status": "error", "message": "No active media session. Please start playing media first."}), 400
            
        if action == 'pause':
            mc.pause()
        elif action == 'play':
            mc.play()
        elif action == 'stop':
            mc.stop()
        else:
            return jsonify({"status": "error", "message": "Invalid action"}), 400
            
        # Wait for the action to take effect
        mc.block_until_active(timeout=5)
        return jsonify({"status": "success", "action": action}), 200
    except Exception as e:
        logger.error(f"Error in media_control: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file
        file.save(file_path)
        
        # Generate the absolute URL for the uploaded file
        file_url = f'{BASE_URL}/uploads/{filename}'
        
        return jsonify({
            "status": "success",
            "message": "File uploaded successfully",
            "filename": filename,
            "url": file_url
        }), 200
    
    return jsonify({"status": "error", "message": "File type not allowed"}), 400

@app.route('/files')
def list_files():
    try:
        files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                file_url = f'{BASE_URL}/uploads/{filename}'
                files.append({
                    "filename": filename,
                    "url": file_url
                })
        return jsonify({
            "status": "success",
            "files": files
        }), 200
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/uploads/<filename>')
def serve_file(filename):
    response = send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    response.headers['Accept-Ranges'] = 'bytes'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = get_content_type(filename)
    return response

@app.route('/status')
def get_status():
    global selected_chromecast
    if not selected_chromecast:
        return jsonify({"status": "error", "message": "No Chromecast selected"}), 400

    try:
        mc = selected_chromecast.media_controller
        mc.update_status()
        status = mc.status

        if status:
            return jsonify({
                "status": "success",
                "player_state": status.player_state,
                "current_time": status.current_time if status.current_time else 0,
                "duration": status.duration if status.duration else 0,
                "volume_level": selected_chromecast.status.volume_level,
                "volume_muted": selected_chromecast.status.volume_muted
            }), 200
        else:
            return jsonify({"status": "error", "message": "No media status available"}), 404
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/seek', methods=['POST'])
def seek():
    global selected_chromecast
    if not selected_chromecast:
        return jsonify({"status": "error", "message": "No Chromecast selected"}), 400

    try:
        data = request.json
        time_to_seek = data.get('time')
        
        if time_to_seek is None:
            return jsonify({"status": "error", "message": "No time specified"}), 400

        mc = selected_chromecast.media_controller
        mc.seek(time_to_seek)
        
        return jsonify({"status": "success", "message": "Seek successful"}), 200
    except Exception as e:
        logger.error(f"Error seeking: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # Run the app on all network interfaces
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True)
