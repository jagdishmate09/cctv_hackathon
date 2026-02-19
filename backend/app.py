from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import numpy as np
import cv2
import os
import sys

# Try to import PeopleDetector, but allow server to start even if it fails
try:
    from detection_service import PeopleDetector
    DETECTOR_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not import PeopleDetector: {e}")
    print("Server will start but detection features will be disabled.")
    PeopleDetector = None
    DETECTOR_AVAILABLE = False

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Initialize people detector
detector = None

def init_detector():
    """Initialize the people detector"""
    global detector
    if not DETECTOR_AVAILABLE:
        print("Detector not available - detection features disabled")
        detector = None
        return
    
    try:
        # Using yolov8s.pt for better accuracy (can switch to yolov8m.pt for even better accuracy)
        detector = PeopleDetector('yolov8s.pt')
        print("People detector initialized successfully")
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
        
        # Detect people
        print("[API] Processing frame with detector...")
        detections = detector.process_frame_bytes(frame_bytes, conf_threshold)
        print(f"[API] Detections found: {len(detections)}")
        
        if detections:
            print(f"[API] First detection: {detections[0]}")
        
        # Get statistics
        stats = detector.get_detection_stats(detections)
        
        response_data = {
            'success': True,
            'detections': detections,
            'stats': stats,
            'count': len(detections)
        }
        print(f"[API] Returning response: count={len(detections)}")
        
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

if __name__ == '__main__':
    print("Initializing CCTV Hackathon Backend...")
    init_detector()
    app.run(debug=True, host='0.0.0.0', port=5000)

