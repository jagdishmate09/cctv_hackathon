# Backend - CCTV Hackathon

This is the backend API built with Python Flask and YOLOv8n for people detection.

## Features

- **People Detection**: Real-time people detection using YOLOv8n model
- **REST API**: Flask-based API endpoints for video frame processing
- **CORS Enabled**: Ready for frontend integration

## Getting Started

### 1. Create a virtual environment (recommended):

```bash
python -m venv venv
```

### 2. Activate the virtual environment:

- **Windows**: `venv\Scripts\activate`
- **Linux/Mac**: `source venv/bin/activate`

### 3. Install dependencies:

```bash
pip install -r requirements.txt
```

**Note**: The first time you run the app, YOLOv8n model will be automatically downloaded (~6MB).

### 4. Run the server:

```bash
python app.py
```

The API will be available at [http://localhost:5000](http://localhost:5000)

## API Endpoints

### Health Check
- `GET /` - Home endpoint
- `GET /api/health` - Health check endpoint

### People Detection

#### Detect People (returns detections only)
- `POST /api/detect`
- **Request Body**:
```json
{
  "frame": "base64_encoded_image",
  "conf_threshold": 0.5
}
```
- **Response**:
```json
{
  "success": true,
  "detections": [
    {
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95,
      "class": "person",
      "class_id": 0
    }
  ],
  "stats": {
    "count": 2,
    "avg_confidence": 0.92,
    "max_confidence": 0.95,
    "min_confidence": 0.89
  },
  "count": 2
}
```

#### Detect with Annotations (returns annotated frame)
- `POST /api/detect-with-annotations`
- **Request Body**: Same as above
- **Response**: Includes `annotated_frame` (base64 encoded image with bounding boxes)

## Usage Example

### Python Example:

```python
import requests
import base64

# Read image
with open('test_image.jpg', 'rb') as f:
    image_bytes = f.read()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

# Send to API
response = requests.post('http://localhost:5000/api/detect', json={
    'frame': image_base64,
    'conf_threshold': 0.5
})

result = response.json()
print(f"Found {result['count']} people")
```

### JavaScript/React Example:

```javascript
// Capture frame from video element
const canvas = document.createElement('canvas');
canvas.width = videoElement.videoWidth;
canvas.height = videoElement.videoHeight;
const ctx = canvas.getContext('2d');
ctx.drawImage(videoElement, 0, 0);

const frameBase64 = canvas.toDataURL('image/jpeg');

// Send to API
fetch('http://localhost:5000/api/detect', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    frame: frameBase64,
    conf_threshold: 0.5
  })
})
.then(res => res.json())
.then(data => {
  console.log(`Found ${data.count} people`);
  console.log(data.detections);
});
```

## Model Information

- **Model**: YOLOv8s (small) - Upgraded from nano for better accuracy
- **Dataset**: COCO (class 0 = person)
- **Speed**: ~40-60 FPS on GPU, ~15-25 FPS on CPU
- **Accuracy**: Enhanced accuracy with image preprocessing for blurred videos
- **Size**: ~22MB
- **Features**:
  - Image enhancement (sharpening, contrast adjustment, denoising)
  - Optimized for blurred/low-quality video detection
  - Lower confidence threshold for better recall

## Configuration

You can adjust the confidence threshold:
- **Lower (0.2-0.25)**: More detections, better for blurred videos (default)
- **Medium (0.3-0.4)**: Balanced approach
- **Higher (0.5-0.7)**: Fewer detections, higher precision

## Image Enhancement

The detector automatically applies:
- CLAHE (Contrast Limited Adaptive Histogram Equalization)
- Sharpening filters
- Bilateral filtering for noise reduction
- These enhancements improve detection accuracy in blurred or low-quality videos

