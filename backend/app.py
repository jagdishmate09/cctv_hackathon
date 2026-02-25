from flask import Flask, request, jsonify, Response, stream_with_context, redirect
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer
import base64
import json
import numpy as np
import cv2
import os
import sys
import tempfile
import subprocess
import shutil
import urllib.parse
import requests
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

try:
    from oracle_occupancy import parse_dav_filename, insert_occupancy_buckets
except ImportError as e:
    parse_dav_filename = None
    insert_occupancy_buckets = None
    print(f"[DB] Oracle occupancy not loaded (oracledb?): {e}", flush=True)

# Microsoft SSO (OAuth 2.0) config from env
MICROSOFT_CLIENT_ID = os.environ.get('MICROSOFT_CLIENT_ID', '')
MICROSOFT_CLIENT_SECRET = os.environ.get('MICROSOFT_CLIENT_SECRET', '')
MICROSOFT_TENANT_ID = os.environ.get('MICROSOFT_TENANT_ID', 'common')
REDIRECT_URI = os.environ.get('REDIRECT_URI', 'http://localhost:5000/auth/microsoft/callback')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173')
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')

# Use agentic pipeline (multi-model YOLO, motion, presence, policy, alerts)
try:
    from agentic_detection_service import (
        AgenticPeopleDetector,
        AgenticVideoProcessor,
        extract_video_datetime,
    )
    DETECTOR_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not import agentic detector: {e}")
    print("Falling back to original detection_service.")
    try:
        from detection_service import PeopleDetector as AgenticPeopleDetector, extract_video_datetime
        AgenticVideoProcessor = None  # video endpoints will use single-frame detector per frame
        DETECTOR_AVAILABLE = True
    except Exception as e2:
        print(f"Warning: Could not import PeopleDetector: {e2}")
        AgenticPeopleDetector = None
        AgenticVideoProcessor = None
        extract_video_datetime = lambda frame: None
        DETECTOR_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
CORS(app, supports_credentials=True)  # Allow credentials for same-origin frontend

# Only push to Oracle when module is loaded AND credentials are set (avoids "Push failed" when not configured)
_has_oracle_creds = all([
    os.environ.get('ORACLE_URL'),
    os.environ.get('ORACLE_USERNAME'),
    os.environ.get('ORACLE_PASSWORD'),
])
OCCUPANCY_PUSH_CONFIGURED = bool(insert_occupancy_buckets and _has_oracle_creds)
if insert_occupancy_buckets and _has_oracle_creds:
    print("[DB] Oracle occupancy ready: data will be pushed to OCCUPANCY_DATA when video is processed.", flush=True)
elif insert_occupancy_buckets:
    print("[DB] Oracle module loaded but ORACLE_URL/USERNAME/PASSWORD not set in .env — push to DB disabled.", flush=True)
else:
    print("[DB] Oracle occupancy NOT available. Install oracledb and set ORACLE_* in .env to push to DB.", flush=True)


# Session token signer for SSO (signed payload, max 24h)
def _get_signer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='sso-session')

# -----------------------------------------------------------------------------
# Microsoft SSO (OAuth 2.0 authorization code flow)
# -----------------------------------------------------------------------------
AUTH_SCOPES = 'openid profile email'
AUTH_BASE = f'https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0'
AUTH_URL = f'{AUTH_BASE}/authorize'
TOKEN_URL = f'{AUTH_BASE}/token'
GRAPH_ME = 'https://graph.microsoft.com/v1.0/me'


@app.route('/auth/microsoft')
def auth_microsoft():
    """Redirect user to Microsoft sign-in."""
    if not MICROSOFT_CLIENT_ID:
        return jsonify({'error': 'Microsoft SSO not configured (MICROSOFT_CLIENT_ID missing)'}), 500
    params = {
        'client_id': MICROSOFT_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': AUTH_SCOPES,
        'response_mode': 'query',
    }
    url = AUTH_URL + '?' + urllib.parse.urlencode(params)
    return redirect(url)


@app.route('/auth/microsoft/callback')
def auth_microsoft_callback():
    """Handle redirect from Microsoft: exchange code for tokens, create session, redirect to frontend."""
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        return redirect(f"{FRONTEND_URL}/login?error=" + urllib.parse.quote(error))
    if not code:
        return redirect(f"{FRONTEND_URL}/login?error=no_code")
    if not MICROSOFT_CLIENT_ID or not MICROSOFT_CLIENT_SECRET:
        return redirect(f"{FRONTEND_URL}/login?error=server_config")

    data = {
        'client_id': MICROSOFT_CLIENT_ID,
        'client_secret': MICROSOFT_CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    try:
        r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=15)
        r.raise_for_status()
        token_json = r.json()
    except Exception as e:
        print(f"[Auth] Token exchange failed: {e}")
        return redirect(f"{FRONTEND_URL}/login?error=token_exchange")

    access_token = token_json.get('access_token')
    if not access_token:
        return redirect(f"{FRONTEND_URL}/login?error=no_token")

    try:
        me = requests.get(GRAPH_ME, headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
        me.raise_for_status()
        user = me.json()
    except Exception as e:
        print(f"[Auth] Graph me failed: {e}")
        user = {}

    payload = {
        'sub': user.get('id') or token_json.get('oid'),
        'email': user.get('mail') or user.get('userPrincipalName') or '',
        'name': user.get('displayName') or '',
    }
    signer = _get_signer()
    session_token = signer.dumps(payload)
    return redirect(f"{FRONTEND_URL}/dashboard?token=" + urllib.parse.quote(session_token))


@app.route('/auth/verify', methods=['GET'])
def auth_verify():
    """Verify a session token (e.g. from frontend). Returns user info if valid."""
    token = request.args.get('token') or (request.get_json() or {}).get('token')
    if not token:
        return jsonify({'valid': False, 'error': 'missing token'}), 401
    signer = _get_signer()
    try:
        payload = signer.loads(token, max_age=86400)  # 24 hours
        return jsonify({'valid': True, 'user': payload})
    except Exception:
        return jsonify({'valid': False, 'error': 'invalid or expired token'}), 401


# Initialize people detector
detector = None

def init_detector():
    """Initialize the agentic people detector (multi-model YOLO, policy, motion)."""
    global detector
    if not DETECTOR_AVAILABLE:
        print("Detector not available - detection features disabled")
        detector = None
        return
    try:
        detector = AgenticPeopleDetector(
            model_low='yolov10n.pt',
            model_med='yolov10s.pt',
            model_high='yolov10m.pt',
            default_mode='MED',
        )
        print("Agentic people detector initialized successfully")
    except Exception as e:
        print(f"Error initializing detector: {e}")
        print("Server will continue without detection features")
        detector = None

@app.route('/')
def home():
    return jsonify({
        'message': 'CCTV Hackathon Backend API',
        'status': 'running',
        'detector': 'ready' if detector else 'not initialized'
    })

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'backend',
        'detector_ready': detector is not None
    })

@app.route('/api/detect', methods=['POST'])
def detect_people():
    """
    Detect people in a video frame
    
    Expected request:
    - Content-Type: application/json
    - Body: {
        "frame": "base64_encoded_image",
        "conf_threshold": 0.5 (optional)
    }
    """
    if detector is None:
        return jsonify({
            'error': 'Detector not initialized'
        }), 500
    
    try:
        data = request.get_json()
        print(f"[API] Received detection request - data keys: {list(data.keys()) if data else 'None'}")
        
        if not data or 'frame' not in data:
            print("[API] Error: No frame data provided")
            return jsonify({
                'success': False,
                'error': 'No frame data provided',
                'count': 0,
                'detections': [],
                'stats': None
            }), 400
        
        # Decode base64 image
        frame_base64 = data['frame']
        print(f"[API] Frame data length: {len(frame_base64)} characters")
        
        # Remove data URL prefix if present
        if ',' in frame_base64:
            frame_base64 = frame_base64.split(',')[1]
            print("[API] Removed data URL prefix")
        
        try:
            frame_bytes = base64.b64decode(frame_base64)
            print(f"[API] Decoded frame size: {len(frame_bytes)} bytes")
        except Exception as e:
            print(f"[API] Error decoding base64: {e}")
            return jsonify({
                'success': False,
                'error': f'Invalid base64 data: {str(e)}',
                'count': 0,
                'detections': [],
                'stats': None
            }), 400
        
        # Get confidence threshold (lower default for better detection in blurred videos)
        conf_threshold = data.get('conf_threshold', 0.25)
        print(f"[API] Using confidence threshold: {conf_threshold}")
        
        # Decode frame for detection and occupancy
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame_img is None:
            return jsonify({'success': False, 'error': 'Could not decode image'}), 400

        # Detect people only (no chairs)
        print("[API] Processing frame with detector (people)...")
        people = detector.detect_people(frame_img, conf_threshold)
        detections = people
        print(f"[API] People: {len(people)}")

        # Extract date/time from top-right corner (CCTV OSD) if available
        video_datetime = extract_video_datetime(frame_img)

        stats = detector.get_detection_stats(detections)
        h, w = frame_img.shape[:2]
        response_data = {
            'success': True,
            'detections': detections,
            'stats': stats,
            'count': len(detections),
            'total_people': len(people),
            'video_datetime': video_datetime,
            'frame_width': w,
            'frame_height': h,
        }
        print(f"[API] people={len(detections)}")
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Detection error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'count': 0,
            'detections': [],
            'stats': None
        }), 500

@app.route('/api/detect-with-annotations', methods=['POST'])
def detect_with_annotations():
    """
    Detect people and return annotated frame
    
    Expected request:
    - Content-Type: application/json
    - Body: {
        "frame": "base64_encoded_image",
        "conf_threshold": 0.5 (optional)
    }
    
    Returns:
    - Annotated frame as base64
    - Detections list
    """
    if detector is None:
        return jsonify({
            'error': 'Detector not initialized'
        }), 500
    
    try:
        data = request.get_json()
        
        if not data or 'frame' not in data:
            return jsonify({
                'error': 'No frame data provided'
            }), 400
        
        # Decode base64 image
        frame_base64 = data['frame']
        if ',' in frame_base64:
            frame_base64 = frame_base64.split(',')[1]
        
        frame_bytes = base64.b64decode(frame_base64)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({
                'error': 'Invalid image data'
            }), 400
        
        # Get confidence threshold
        conf_threshold = data.get('conf_threshold', 0.5)
        
        # Detect people
        detections = detector.detect_people(frame, conf_threshold)
        
        # Draw detections
        annotated_frame = detector.draw_detections(frame, detections)
        
        # Encode annotated frame
        _, buffer = cv2.imencode('.jpg', annotated_frame)
        annotated_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # Get statistics
        stats = detector.get_detection_stats(detections)
        
        return jsonify({
            'success': True,
            'annotated_frame': annotated_base64,
            'detections': detections,
            'stats': stats,
            'count': len(detections)
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


def _dav_to_mp4_temp(dav_path: str) -> str:
    """
    Convert a .dav (Dahua) file to a temporary .mp4 using FFmpeg so OpenCV can read it.
    Returns path to the temp .mp4 file. Caller must delete it when done.
    """
    ffmpeg_cmd = shutil.which('ffmpeg')
    if not ffmpeg_cmd:
        raise RuntimeError(
            'FFmpeg is required to process .dav files. '
            'Install FFmpeg and add it to your PATH (https://ffmpeg.org/download.html).'
        )
    fd, out_path = tempfile.mkstemp(suffix='.mp4')
    os.close(fd)
    try:
        # -y overwrite; -c copy for speed (no re-encode). Fallback to recode if copy fails.
        result = subprocess.run(
            [ffmpeg_cmd, '-y', '-i', dav_path, '-c', 'copy', out_path],
            capture_output=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
        if result.returncode != 0:
            # Try with re-encode for compatibility
            result = subprocess.run(
                [ffmpeg_cmd, '-y', '-i', dav_path, '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', out_path],
                capture_output=True,
                timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
        if result.returncode != 0:
            stderr = (result.stderr or b'').decode('utf-8', errors='replace')[:500]
            raise RuntimeError(f'FFmpeg failed to convert .dav file: {stderr}')
        return out_path
    except Exception:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass
        raise


def _is_room_lighted(frame, threshold=45):
    """Return True if frame mean luminance >= threshold, False if dark, None if no frame."""
    if frame is None or frame.size == 0:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()) >= threshold


_camera_mapping_cache = None


def _get_room_type(camera_id: str) -> str | None:
    """Return room_type for camera from config/camera_mapping.json, or None if not found."""
    global _camera_mapping_cache
    if camera_id is None or not str(camera_id).strip():
        return None
    if _camera_mapping_cache is None:
        tried = []
        for base in [
            Path(__file__).resolve().parent,  # backend/
            Path(__file__).resolve().parent.parent / "backend_new",  # backend_new/
            Path.cwd(),
        ]:
            mapping_path = base / "config" / "camera_mapping.json"
            tried.append(str(mapping_path))
            if mapping_path.is_file():
                try:
                    with open(mapping_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    _camera_mapping_cache = data.get("camera_mapping") or {}
                    break
                except Exception:
                    pass
        if _camera_mapping_cache is None:
            _camera_mapping_cache = {}
    key = str(camera_id).strip().upper()
    if key.isdigit():
        key = f"CH{key}"
    entry = _camera_mapping_cache.get(key)
    if isinstance(entry, dict):
        return entry.get("room_type")
    return None


def _video_path_for_opencv(file_path: str) -> tuple:
    """
    Return (path_to_open, temp_path_or_none).
    If file_path is .dav or OpenCV cannot open it, convert with FFmpeg and return temp path.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    cap = cv2.VideoCapture(file_path)
    if cap.isOpened():
        cap.release()
        return file_path, None
    cap.release()
    if ext == '.dav':
        temp_mp4 = _dav_to_mp4_temp(file_path)
        return temp_mp4, temp_mp4
    raise RuntimeError(
        'Could not open video file (unsupported format or corrupted). '
        'Supported: common formats (e.g. MP4, AVI). For .dav (Dahua) files, install FFmpeg and add it to PATH.'
    )


@app.route('/api/detect-video-file', methods=['POST'])
def detect_video_file():
    """
    Run person detection on an uploaded video file (supports .dav and other formats).
    Uses FFmpeg to convert .dav (Dahua) to a temporary format OpenCV can read.

    Request: multipart/form-data with field "video" (file).
    Optional form fields: frame_interval (int, default 50), max_frames (int, default 500), conf_threshold (float, default 0.25).

    Returns: JSON with per-frame counts and summary.
    """
    if detector is None:
        return jsonify({'success': False, 'error': 'Detector not initialized'}), 500

    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'No video file provided'}), 400

    file = request.files['video']
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No video file selected'}), 400

    frame_interval = request.form.get('frame_interval', type=int) or 50
    max_frames = request.form.get('max_frames', type=int) or 500
    conf_threshold = request.form.get('conf_threshold', type=float) or 0.25
    camera_id = request.form.get('camera_id') or None

    frame_interval = max(1, min(frame_interval, 100))
    max_frames = max(1, min(max_frames, 2000))

    video_path_to_use = None
    paths_to_clean = []

    try:
        fd, save_path = tempfile.mkstemp(suffix=Path(file.filename).suffix or '.bin')
        os.close(fd)
        file.save(save_path)
        paths_to_clean.append(save_path)

        try:
            video_path_to_use, converted_path = _video_path_for_opencv(save_path)
            if converted_path:
                paths_to_clean.append(converted_path)
        except Exception as e:
            for p in paths_to_clean:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            return jsonify({'success': False, 'error': str(e)}), 400

        cap = cv2.VideoCapture(video_path_to_use)
        if not cap.isOpened():
            return jsonify({
                'success': False,
                'error': 'Could not open video. For .dav files ensure FFmpeg is installed.'
            }), 400

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames_in_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_results = []
        frames_processed = 0
        frame_index = 0
        sample_frames_b64 = []  # annotated frames to show on frontend (max 3)
        max_count_so_far = -1
        best_frame_b64 = None

        # Use agentic video pipeline when available (motion, mode, presence, alerts)
        use_agentic_video = AgenticVideoProcessor is not None
        if use_agentic_video:
            from datetime import timedelta
            video_processor = AgenticVideoProcessor(camera_id=camera_id)
            start_ts = datetime.utcnow()

        while frames_processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_index % frame_interval != 0:
                frame_index += 1
                continue
            time_sec = frame_index / fps if fps > 0 else 0
            if use_agentic_video:
                ts = start_ts + timedelta(seconds=time_sec)
                out = video_processor.process_frame(frame, ts=ts, frame_index=frame_index, fps=fps)
                detections = out['detections']
                count = out['count']
            else:
                detections = detector.detect_people(frame, conf_threshold)
                count = len(detections)
            annotated = detector.draw_detections(frame.copy(), detections)
            _, buf = cv2.imencode('.jpg', annotated)
            frame_b64 = base64.b64encode(buf).decode('utf-8')

            # First frame: always include so user sees video content
            if frames_processed == 0 and len(sample_frames_b64) < 3:
                sample_frames_b64.append(frame_b64)
            # Keep one frame with most people for display
            if count > max_count_so_far:
                max_count_so_far = count
                best_frame_b64 = frame_b64

            frame_results.append({
                'frame_index': frame_index,
                'time_sec': round(time_sec, 2),
                'count': count,
                'detections': detections,
            })
            frames_processed += 1
            frame_index += 1

        cap.release()

        if best_frame_b64 and (len(sample_frames_b64) == 0 or best_frame_b64 != sample_frames_b64[0]) and len(sample_frames_b64) < 3:
            sample_frames_b64.append(best_frame_b64)
        # If we only have one sample, ensure we have at least the first
        if not sample_frames_b64 and frame_results:
            pass  # already added first above

        frames_with_people = sum(1 for r in frame_results if r['count'] > 0)
        max_count = max((r['count'] for r in frame_results), default=0)
        avg_count = (sum(r['count'] for r in frame_results) / len(frame_results)) if frame_results else 0

        return jsonify({
            'success': True,
            'total_frames_in_video': total_frames_in_video,
            'frames_processed': len(frame_results),
            'frame_interval': frame_interval,
            'results': frame_results,
            'summary': {
                'max_count': max_count,
                'avg_count': round(avg_count, 2),
                'frames_with_people': frames_with_people,
            },
            'sample_frames': sample_frames_b64[:3],
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        for p in paths_to_clean:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def _stream_dav_frames():
    """
    Generator used by detect_video_file_stream. Yields NDJSON lines: one per frame, then a final 'done' line.
    """
    print("[Backend] _stream_dav_frames started (reading request body)", flush=True)
    if detector is None:
        yield json.dumps({'error': 'Detector not initialized'}) + '\n'
        yield json.dumps({'done': True, 'success': False}) + '\n'
        return
    if 'video' not in request.files:
        yield json.dumps({'error': 'No video file provided'}) + '\n'
        yield json.dumps({'done': True, 'success': False}) + '\n'
        return
    file = request.files['video']
    if not file or file.filename == '':
        yield json.dumps({'error': 'No video file selected'}) + '\n'
        yield json.dumps({'done': True, 'success': False}) + '\n'
        return

    # Default: process 1 in 15 frames for speed (detection is expensive). Higher = faster, fewer samples per minute.
    frame_interval = request.form.get('frame_interval', type=int) or 50
    max_frames = request.form.get('max_frames', type=int) or 5000
    conf_threshold = request.form.get('conf_threshold', type=float) or 0.15
    frame_interval = max(1, min(frame_interval, 60))
    max_frames = max(1, min(max_frames, 10000))

    filename = file.filename or ''
    # Parse filename for camera/date; use fallback so we always push when we have detection data
    parsed_filename = parse_dav_filename(filename) if parse_dav_filename else None
    if not parsed_filename:
        now = datetime.utcnow()
        parsed_filename = {
            'camera_number': Path(filename).stem if filename else 'VIDEO',
            'occupancy_date': now.strftime('%Y-%m-%d'),
            'start_hour': now.hour, 'start_min': now.minute, 'start_sec': now.second,
        }
    occupancy_buckets = {}  # bucket_index -> {max_people}
    last_pushed_minute = -1  # push each minute as it completes during processing

    print(f"[DB] Video file stream starting: filename={filename!r}, push_available={OCCUPANCY_PUSH_CONFIGURED}", flush=True)
    paths_to_clean = []
    save_path = None
    try:
        fd, save_path = tempfile.mkstemp(suffix=Path(file.filename).suffix or '.bin')
        os.close(fd)
        file.save(save_path)
        paths_to_clean.append(save_path)

        try:
            video_path_to_use, converted_path = _video_path_for_opencv(save_path)
            if converted_path:
                paths_to_clean.append(converted_path)
        except Exception as e:
            yield json.dumps({'error': str(e)}) + '\n'
            yield json.dumps({'done': True, 'success': False}) + '\n'
            return

        cap = cv2.VideoCapture(video_path_to_use)
        if not cap.isOpened():
            yield json.dumps({'error': 'Could not open video. For .dav ensure FFmpeg is installed.'}) + '\n'
            yield json.dumps({'done': True, 'success': False}) + '\n'
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if not OCCUPANCY_PUSH_CONFIGURED:
            if insert_occupancy_buckets:
                print("[DB] Oracle credentials not set in .env — skipping push to OCCUPANCY_DATA.", flush=True)
            else:
                print("[DB] Cannot push: oracle_occupancy not loaded. Check oracledb and .env", flush=True)
        else:
            print(f"[DB] Video opened. Will push to OCCUPANCY_DATA as each minute completes. camera={parsed_filename['camera_number']}", flush=True)
        total_frames_in_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_index = 0
        frames_processed = 0
        frame_results = []

        use_agentic_video = AgenticVideoProcessor is not None
        if use_agentic_video:
            from datetime import timedelta
            stream_camera_id = request.form.get('camera_id') or (parsed_filename.get('camera_number') if parsed_filename else None)
            video_processor = AgenticVideoProcessor(camera_id=stream_camera_id)
            start_ts = datetime.utcnow()

        while frames_processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_index % frame_interval != 0:
                frame_index += 1
                continue
            time_sec = frame_index / fps if fps > 0 else 0
            if use_agentic_video:
                ts = start_ts + timedelta(seconds=time_sec)
                out = video_processor.process_frame(frame, ts=ts, frame_index=frame_index, fps=fps)
                people = out['detections']
                count = out['count']
            else:
                people = detector.detect_people(frame, conf_threshold, fast_inference=True)
                count = len(people)
            annotated = detector.draw_detections(frame.copy(), people)
            _, buf = cv2.imencode('.jpg', annotated)
            frame_b64 = base64.b64encode(buf).decode('utf-8')
            # 1-minute buckets: keep max people detected across all frames in that minute
            bucket_idx = int(time_sec // 60)
            prev = occupancy_buckets.get(bucket_idx)
            if prev is None or count > prev['max_people']:
                occupancy_buckets[bucket_idx] = {'max_people': count}
            # Push completed minutes only (when we've left that minute, so we have final max_people). One row per minute.
            if OCCUPANCY_PUSH_CONFIGURED and bucket_idx > last_pushed_minute + 1:
                for m in range(last_pushed_minute + 1, bucket_idx):
                    if m in occupancy_buckets:
                        ok, err = insert_occupancy_buckets(
                            camera_number=parsed_filename['camera_number'],
                            occupancy_date=parsed_filename['occupancy_date'],
                            start_hour=parsed_filename['start_hour'],
                            start_min=parsed_filename['start_min'],
                            start_sec=parsed_filename['start_sec'],
                            buckets=[occupancy_buckets[m]],
                            mins_per_bucket=1,
                            bucket_start_index=m,
                        )
                        if ok:
                            print(f"[DB] Pushed 1 row (minute {m}) | camera={parsed_filename['camera_number']} max_people={occupancy_buckets[m].get('max_people', 0)}", flush=True)
                        else:
                            print(f"[DB] Push failed (minute {m}): {err}", flush=True)
                last_pushed_minute = bucket_idx - 1
            video_datetime = extract_video_datetime(frame)
            fh, fw = frame.shape[:2]
            frame_results.append({'frame_index': frame_index, 'time_sec': round(time_sec, 2), 'count': count})
            payload = {
                'frame': frame_b64,
                'frame_index': frame_index,
                'time_sec': round(time_sec, 2),
                'count': count,
                'detections': people,
                'total_people': count,
                'video_datetime': video_datetime,
                'frame_width': fw,
                'frame_height': fh,
                'room_lighted': _is_room_lighted(frame),
            }
            if use_agentic_video and out.get('mode') is not None:
                payload['agent_mode'] = out['mode']
                payload['presence_seconds'] = out.get('presence_seconds')
                if out.get('alert'):
                    payload['alert'] = out['alert']
            # Include parsed filename info for frontend (camera name, video date/time, room type)
            if parsed_filename:
                h, m, s = parsed_filename['start_hour'], parsed_filename['start_min'], parsed_filename['start_sec']
                # Format: DD/MM/YYYY, HH:MM:SS (from YYYY-MM-DD)
                d = parsed_filename['occupancy_date']
                parts = d.split('-')
                date_display = f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else d
                time_display = f"{h:02d}:{m:02d}:{s:02d}"
                payload['parsed_camera_name'] = parsed_filename['camera_number']
                payload['parsed_video_date_time'] = f"{date_display}, {time_display}"
                payload['parsed_video_date'] = date_display
                payload['parsed_video_time'] = time_display
                room_type = _get_room_type(parsed_filename['camera_number'])
                if room_type is not None:
                    payload['room_type'] = room_type
            yield json.dumps(payload) + '\n'
            frames_processed += 1
            frame_index += 1

        cap.release()
        # Push any remaining (last) minute that wasn't pushed during the loop
        db_saved = False
        db_error = None
        db_skip_reason = None
        if OCCUPANCY_PUSH_CONFIGURED and occupancy_buckets:
            max_bucket = max(occupancy_buckets.keys())
            for m in range(last_pushed_minute + 1, max_bucket + 1):
                if m in occupancy_buckets:
                    ok, err = insert_occupancy_buckets(
                        camera_number=parsed_filename['camera_number'],
                        occupancy_date=parsed_filename['occupancy_date'],
                        start_hour=parsed_filename['start_hour'],
                        start_min=parsed_filename['start_min'],
                        start_sec=parsed_filename['start_sec'],
                        buckets=[occupancy_buckets[m]],
                        mins_per_bucket=1,
                        bucket_start_index=m,
                    )
                    if ok:
                        print(f"[DB] Pushed 1 row (minute {m}) | camera={parsed_filename['camera_number']} max_people={occupancy_buckets[m].get('max_people', 0)}", flush=True)
                        db_saved = True
                    else:
                        db_error = err
                        print(f"[DB] Push failed (minute {m}): {err}", flush=True)
        print(f"[DB] Video stream ended. Buckets: {len(occupancy_buckets)}, last_pushed_minute={last_pushed_minute}, push_available={OCCUPANCY_PUSH_CONFIGURED}.", flush=True)
        frames_with_people = sum(1 for r in frame_results if r['count'] > 0)
        max_count = max((r['count'] for r in frame_results), default=0)
        avg_count = (sum(r['count'] for r in frame_results) / len(frame_results)) if frame_results else 0
        summary = {
            'max_count': max_count,
            'avg_count': round(avg_count, 2),
            'frames_with_people': frames_with_people,
        }
        yield json.dumps({
            'done': True,
            'success': True,
            'total_frames_in_video': total_frames_in_video,
            'frames_processed': len(frame_results),
            'frame_interval': frame_interval,
            'summary': summary,
            'db_saved': db_saved,
            'db_error': db_error,
            'db_skip_reason': db_skip_reason,
        }) + '\n'
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield json.dumps({'error': str(e)}) + '\n'
        yield json.dumps({'done': True, 'success': False}) + '\n'
    finally:
        for p in paths_to_clean:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


@app.route('/api/detect-video-file-stream', methods=['POST'])
def detect_video_file_stream():
    """
    Stream person detection on an uploaded video file (.dav or other). Each frame is sent to the client
    as it is processed so the frontend can show live video with detection (like MP4 playback).
    """
    print("[Backend] POST /api/detect-video-file-stream received", flush=True)
    return Response(
        stream_with_context(_stream_dav_frames()),
        mimetype='application/x-ndjson',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# Initialize detector when app is loaded (e.g. by gunicorn)
try:
    init_detector()
except Exception as e:
    print(f"Warning: init_detector failed: {e}", flush=True)

if __name__ == '__main__':
    print("Initializing CCTV Hackathon Backend...")
    app.run(debug=True, host='0.0.0.0', port=5000)

