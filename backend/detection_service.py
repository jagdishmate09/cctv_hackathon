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
    
    # COCO class ids: 0 = person, 56 = chair
    COCO_CHAIR_CLASS_ID = 56

    def _run_inference(self, frame: np.ndarray, conf: float, imgsz: int, classes: List[int] = None) -> List[Dict]:
        """Run YOLO and return list of detection dicts (bbox, confidence, class). classes defaults to [0] (person)."""
        if classes is None:
            classes = [0]
        class_names = {0: 'person', 56: 'chair'}
        results = self.model(
            frame,
            imgsz=imgsz,
            classes=classes,
            conf=conf,
            iou=0.45,
            max_det=100,
            verbose=False,
            agnostic_nms=False,
        )
        out = []
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cid = int(box.cls[0].cpu().numpy())
                out.append({
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'confidence': float(box.conf[0].cpu().numpy()),
                    'class': class_names.get(cid, 'object'),
                    'class_id': cid,
                })
        return out

    def _nms_merge(self, detections: List[Dict], iou_threshold: float = 0.5) -> List[Dict]:
        """Merge overlapping detections via NMS (keep highest confidence per overlap)."""
        if len(detections) <= 1:
            return detections
        boxes_xyxy = np.array([d['bbox'] for d in detections], dtype=np.float32)
        scores = np.array([d['confidence'] for d in detections], dtype=np.float32)
        # NMSBoxes expects list of (x, y, w, h)
        x, y = boxes_xyxy[:, 0], boxes_xyxy[:, 1]
        w = boxes_xyxy[:, 2] - boxes_xyxy[:, 0]
        h = boxes_xyxy[:, 3] - boxes_xyxy[:, 1]
        boxes_xywh = np.column_stack((x, y, w, h)).tolist()
        indices = cv2.dnn.NMSBoxes(
            boxes_xywh,
            scores.tolist(),
            score_threshold=0.0,
            nms_threshold=iou_threshold,
        )
        if len(indices) == 0:
            indices = np.arange(len(detections))
        if hasattr(indices, 'flatten'):
            indices = indices.flatten()
        return [detections[int(i)] for i in indices]

    def detect_people(self, frame: np.ndarray, conf_threshold: float = 0.2, iou_threshold: float = 0.45) -> List[Dict]:
        """
        Detect people in a video frame, including sitting/static and small (distant) persons.
        Runs on both enhanced and original frame and merges results for more consistent detection.
        
        Args:
            frame: Input frame as numpy array (BGR format)
            conf_threshold: Confidence threshold (default 0.2 for better recall on static/small people)
            iou_threshold: IoU threshold for NMS (default: 0.45)
        
        Returns:
            List of detection dictionaries with bbox, confidence, and class
        """
        enhanced_frame = self.enhance_image(frame, fast_mode=True)
        imgsz = 1280 if max(frame.shape[:2]) >= 720 else 640
        conf_lo = max(0.1, conf_threshold * 0.75)

        # Pass 1: enhanced frame at main threshold (better for motion/blur)
        dets_enhanced = self._run_inference(enhanced_frame, conf_threshold, imgsz)
        # Pass 2: original frame at lower threshold (catches static/sitting when enhancement drops confidence)
        dets_original = self._run_inference(frame, conf_lo, imgsz)
        merged = self._nms_merge(dets_enhanced + dets_original, iou_threshold=iou_threshold)

        print(f"[Detector] Frame {frame.shape} imgsz={imgsz} conf={conf_threshold} -> enhanced={len(dets_enhanced)} original={len(dets_original)} -> merged={len(merged)}")
        for i, d in enumerate(merged):
            print(f"[Detector] Detection {i+1}: conf={d['confidence']:.3f}, bbox={d['bbox']}")
        return merged

    def detect_chairs(self, frame: np.ndarray, conf_threshold: float = 0.15) -> List[Dict]:
        """
        Detect chairs in the frame (COCO class 56), including occluded chairs (with people sitting).
        Uses dual-pass (enhanced + original at lower conf) and NMS merge for better recall.
        """
        enhanced_frame = self.enhance_image(frame, fast_mode=True)
        imgsz = 1280 if max(frame.shape[:2]) >= 720 else 640
        conf_lo = max(0.08, conf_threshold * 0.6)
        chairs_enhanced = self._run_inference(enhanced_frame, conf_threshold, imgsz, classes=[self.COCO_CHAIR_CLASS_ID])
        chairs_original = self._run_inference(frame, conf_lo, imgsz, classes=[self.COCO_CHAIR_CLASS_ID])
        merged = self._nms_merge(chairs_enhanced + chairs_original, iou_threshold=0.5)
        print(f"[Detector] Chairs: enhanced={len(chairs_enhanced)} original={len(chairs_original)} -> merged={len(merged)}")
        return merged

    def detect_people_and_chairs(self, frame: np.ndarray, conf_threshold: float = 0.2, iou_threshold: float = 0.45) -> Tuple[List[Dict], List[Dict]]:
        """
        Detect both people and chairs. Returns (people_detections, chair_detections).
        Use for occupancy by chairs: occupancy = (len(people) / len(chairs)) * 100.
        """
        people = self.detect_people(frame, conf_threshold, iou_threshold)
        chairs = self.detect_chairs(frame, conf_threshold)
        return people, chairs

    def draw_detections_people_and_chairs(self, frame: np.ndarray, people: List[Dict], chairs: List[Dict]) -> np.ndarray:
        """Draw people in green, chairs in yellow (BGR)."""
        annotated = frame.copy()
        for det in people:
            x1, y1, x2, y2 = det['bbox']
            conf = det['confidence']
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            label = f"Person {conf:.2f}"
            sz, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (int(x1), int(y1) - sz[1] - 10), (int(x1) + sz[0], int(y1)), (0, 255, 0), -1)
            cv2.putText(annotated, label, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        for det in chairs:
            x1, y1, x2, y2 = det['bbox']
            conf = det['confidence']
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)
            label = f"Chair {conf:.2f}"
            sz, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (int(x1), int(y1) - sz[1] - 10), (int(x1) + sz[0], int(y1)), (0, 255, 255), -1)
            cv2.putText(annotated, label, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        return annotated

    def process_frame_bytes(self, frame_bytes: bytes, conf_threshold: float = 0.2) -> List[Dict]:
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

