import os
import sys
import pathlib

# Set custom Ultralytics home directory to avoid conflicts with other projects
PROJECT_ROOT = pathlib.Path(__file__).parent
ULTRALYTICS_HOME = PROJECT_ROOT / ".ultralytics"

# Ensure the custom directory exists
try:
    ULTRALYTICS_HOME.mkdir(parents=True, exist_ok=True)
    print(f"Using custom Ultralytics home: {ULTRALYTICS_HOME}")
except Exception as e:
    print(f"Warning: Could not create Ultralytics home directory: {e}")

# Patch pathlib.Path.mkdir to handle the conflicting Ultralytics path
# This intercepts the mkdir call and redirects it to our custom directory
_original_mkdir = pathlib.Path.mkdir
_default_ultralytics_path = pathlib.Path.home() / "AppData" / "Roaming" / "Ultralytics"

def _patched_mkdir(self, mode=0o777, parents=False, exist_ok=False):
    """Patched mkdir that redirects Ultralytics default path to custom path"""
    # If trying to create the default Ultralytics path, redirect to custom path
    try:
        if str(self) == str(_default_ultralytics_path):
            # Redirect to custom path
            custom_path = pathlib.Path(ULTRALYTICS_HOME)
            if not custom_path.exists():
                return _original_mkdir(custom_path, mode, parents, exist_ok)
            return None
    except:
        pass
    # For all other paths, use original behavior
    return _original_mkdir(self, mode, parents, exist_ok)

# Apply the patch
pathlib.Path.mkdir = _patched_mkdir

try:
    from ultralytics import YOLO
    print("YOLO imported successfully")
    # Restore original mkdir after import
    pathlib.Path.mkdir = _original_mkdir
except Exception as e:
    # Restore original mkdir on error
    pathlib.Path.mkdir = _original_mkdir
    print(f"Error importing YOLO: {e}")
    raise

import cv2
import numpy as np
from typing import List, Dict, Tuple

class PeopleDetector:
    """YOLOv8-based people detection service with enhanced accuracy for blurred videos"""
    
    def __init__(self, model_path: str = 'yolov8s.pt'):
        """
        Initialize the people detector with YOLOv8 model
        Using 's' (small) model for better accuracy than 'n' (nano)
        
        Args:
            model_path: Path to YOLOv8 model file (will download if not exists)
                       Options: yolov8n.pt (fastest), yolov8s.pt (balanced), yolov8m.pt (more accurate)
        """
        self.model = YOLO(model_path)
        self.model.fuse()  # Fuse model for faster inference
        print(f"YOLOv8 model ({model_path}) loaded successfully")
    
    def enhance_image(self, frame: np.ndarray, fast_mode: bool = True) -> np.ndarray:
        """
        Enhance image quality for better detection in blurred/low-quality videos
        Fast mode uses lighter processing for real-time performance
        
        Args:
            frame: Input frame as numpy array (BGR format)
            fast_mode: If True, uses faster but lighter enhancement
        
        Returns:
            Enhanced frame
        """
        if fast_mode:
            # Fast mode: Light sharpening only for speed
            kernel = np.array([[-1, -1, -1],
                              [-1,  9, -1],
                              [-1, -1, -1]])
            sharpened = cv2.filter2D(frame, -1, kernel * 0.3)  # Light sharpening
            # Quick blend (60% sharpened, 40% original)
            result = cv2.addWeighted(sharpened, 0.6, frame, 0.4, 0)
            return result
        else:
            # Full enhancement mode (slower but better quality)
            # Convert to LAB color space for better processing
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            
            # Merge channels back
            lab = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            
            # Apply sharpening filter
            kernel = np.array([[-1, -1, -1],
                              [-1,  9, -1],
                              [-1, -1, -1]])
            sharpened = cv2.filter2D(enhanced, -1, kernel * 0.5)
            
            # Blend original and sharpened
            result = cv2.addWeighted(sharpened, 0.7, enhanced, 0.3, 0)
            
            # Apply bilateral filter for noise reduction
            denoised = cv2.bilateralFilter(result, 5, 50, 50)
            
            return denoised
    
    def detect_people(self, frame: np.ndarray, conf_threshold: float = 0.25, iou_threshold: float = 0.45) -> List[Dict]:
        """
        Detect people in a video frame with enhanced accuracy
        
        Args:
            frame: Input frame as numpy array (BGR format)
            conf_threshold: Confidence threshold for detections (default: 0.25 for better recall)
            iou_threshold: IoU threshold for NMS (default: 0.45)
        
        Returns:
            List of detection dictionaries with bbox, confidence, and class
        """
        # Enhance image quality for better detection (fast mode for real-time)
        enhanced_frame = self.enhance_image(frame, fast_mode=True)
        
        # Run inference with optimized parameters for blurred videos
        # Using lower confidence, higher IOU, and max_det for better recall
        print(f"[Detector] Running YOLO inference on frame shape {frame.shape} with threshold {conf_threshold}")
        results = self.model(
            enhanced_frame, 
            classes=[0],  # Only detect 'person' class
            conf=conf_threshold,
            iou=iou_threshold,
            max_det=100,  # Allow more detections
            verbose=False,
            agnostic_nms=False  # Class-aware NMS
        )
        
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is not None and len(boxes) > 0:
                print(f"[Detector] Found {len(boxes)} bounding boxes")
                for i, box in enumerate(boxes):
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    print(f"[Detector] Detection {i+1}: conf={confidence:.3f}, bbox=[{x1:.1f}, {y1:.1f}, {x2:.1f}, {y2:.1f}]")
                    
                    detections.append({
                        'bbox': [float(x1), float(y1), float(x2), float(y2)],
                        'confidence': confidence,
                        'class': 'person',
                        'class_id': class_id
                    })
            else:
                print(f"[Detector] No boxes found in result")
        
        print(f"[Detector] Total detections: {len(detections)}")
        return detections
    
    def process_frame_bytes(self, frame_bytes: bytes, conf_threshold: float = 0.25) -> List[Dict]:
        """
        Process frame from bytes (e.g., from API request)
        
        Args:
            frame_bytes: Frame as bytes
            conf_threshold: Confidence threshold
        
        Returns:
            List of detections
        """
        print(f"[Detector] Processing frame - size: {len(frame_bytes)} bytes, threshold: {conf_threshold}")
        
        # Convert bytes to numpy array
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            print("[Detector] ERROR: Could not decode image from bytes")
            return []
        
        print(f"[Detector] Decoded frame - shape: {frame.shape}")
        
        detections = self.detect_people(frame, conf_threshold)
        print(f"[Detector] Found {len(detections)} people")
        
        return detections
    
    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        Draw bounding boxes on frame
        
        Args:
            frame: Input frame
            detections: List of detection dictionaries
        
        Returns:
            Frame with drawn bounding boxes
        """
        annotated_frame = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            confidence = det['confidence']
            
            # Draw bounding box
            cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            
            # Draw label with confidence
            label = f"Person {confidence:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated_frame, (int(x1), int(y1) - label_size[1] - 10),
                         (int(x1) + label_size[0], int(y1)), (0, 255, 0), -1)
            cv2.putText(annotated_frame, label, (int(x1), int(y1) - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        return annotated_frame
    
    def get_detection_stats(self, detections: List[Dict]) -> Dict:
        """
        Get statistics about detections
        
        Args:
            detections: List of detections
        
        Returns:
            Dictionary with statistics
        """
        if not detections:
            return {
                'count': 0,
                'avg_confidence': 0,
                'max_confidence': 0,
                'min_confidence': 0
            }
        
        confidences = [det['confidence'] for det in detections]
        
        return {
            'count': len(detections),
            'avg_confidence': float(np.mean(confidences)),
            'max_confidence': float(np.max(confidences)),
            'min_confidence': float(np.min(confidences))
        }

