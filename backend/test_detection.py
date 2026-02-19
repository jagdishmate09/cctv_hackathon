"""
Simple test script to verify YOLOv8n detection is working
"""
import requests
import base64
import cv2
import numpy as np

def test_detection():
    # Create a simple test image (white background with a rectangle)
    test_image = np.ones((480, 640, 3), dtype=np.uint8) * 255
    cv2.rectangle(test_image, (200, 150), (400, 350), (0, 0, 0), -1)
    
    # Encode as JPEG
    _, buffer = cv2.imencode('.jpg', test_image)
    image_base64 = base64.b64encode(buffer).decode('utf-8')
    
    try:
        # Test health endpoint
        print("Testing health endpoint...")
        health_response = requests.get('http://localhost:5000/api/health', timeout=5)
        print(f"Health Status: {health_response.status_code}")
        print(f"Response: {health_response.json()}")
        
        # Test detection endpoint
        print("\nTesting detection endpoint...")
        detection_response = requests.post(
            'http://localhost:5000/api/detect',
            json={
                'frame': image_base64,
                'conf_threshold': 0.5
            },
            timeout=10
        )
        
        print(f"Detection Status: {detection_response.status_code}")
        result = detection_response.json()
        print(f"People Detected: {result.get('count', 0)}")
        print(f"Detections: {result.get('detections', [])}")
        
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to backend server!")
        print("Make sure the server is running: python app.py")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    test_detection()

