import { useState, useRef, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import '../styles/dashboard.css';

const SSO_TOKEN_KEY = 'sso_token';

function Dashboard() {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [selectedCamera, setSelectedCamera] = useState('Select Camera');
    const [isStreaming, setIsStreaming] = useState(false);
    const [availableCameras, setAvailableCameras] = useState([]);
    const [videoMode, setVideoMode] = useState('camera'); // 'camera' or 'file'
    const [selectedVideoFile, setSelectedVideoFile] = useState(null);
    const [videoFileUrl, setVideoFileUrl] = useState(null);
    const [detectionData, setDetectionData] = useState({
        count: 0,
        detections: [],
        stats: null
    });
    const [isDetecting, setIsDetecting] = useState(false);
    const [backendConnected, setBackendConnected] = useState(false);
    const [detectionError, setDetectionError] = useState(null);
    const [davProcessing, setDavProcessing] = useState(false);
    const [davPaused, setDavPaused] = useState(false);
    const [davResults, setDavResults] = useState(null);
    const [davLiveFrame, setDavLiveFrame] = useState(null);
    const [occupancyStats, setOccupancyStats] = useState(null); // { total_people, unoccupied_chairs, occupied_chairs, total_chairs, occupancy_rate }
    const [videoDateTime, setVideoDateTime] = useState(null);   // date/time extracted from video (top-right OSD)
    const [featureTab, setFeatureTab] = useState('occupancy_rate'); // 'occupancy_rate' | 'occupancy_analysis' | 'threat_detection'
    const [threatBox, setThreatBox] = useState(null);                 // { x1, y1, x2, y2 } normalized 0-1 (red box)
    const [isDrawingBoundary, setIsDrawingBoundary] = useState(false);
    const [dragStart, setDragStart] = useState(null);                // { x, y } normalized while drawing
    const [dragCurrent, setDragCurrent] = useState(null);            // { x, y } normalized while drawing
    const [threatAlert, setThreatAlert] = useState(false);
    const [lastFrameDimensions, setLastFrameDimensions] = useState({ w: 0, h: 0 });
    const videoRef = useRef(null);
    const davLiveImgRef = useRef(null);
    const streamRef = useRef(null);
    const fileInputRef = useRef(null);
    const detectionIntervalRef = useRef(null);
    const davAbortControllerRef = useRef(null);
    const davPausedRef = useRef(false);
    const videoFeedContainerRef = useRef(null);
    const boundaryCanvasRef = useRef(null);
    const boundaryOverlayRef = useRef(null);
    const threatBoxRef = useRef(null);
    useEffect(() => { threatBoxRef.current = threatBox; }, [threatBox]);

    const getNormalizedCoords = (e) => {
        const el = isStreaming ? videoRef.current : (davLiveFrame && davLiveImgRef.current) ? davLiveImgRef.current : null;
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        const w = el.videoWidth ?? el.naturalWidth ?? 1;
        const h = el.videoHeight ?? el.naturalHeight ?? 1;
        const scale = Math.min(rect.width / w, rect.height / h);
        const dw = w * scale;
        const dh = h * scale;
        // Video content (letterbox) position in client coordinates – same space as e.clientX/clientY
        const contentLeft = rect.left + (rect.width - dw) / 2;
        const contentTop = rect.top + (rect.height - dh) / 2;
        const nx = (e.clientX - contentLeft) / dw;
        const ny = (e.clientY - contentTop) / dh;
        // Clamp so drawing works anywhere on overlay; edges map to video edges
        return { x: Math.max(0, Math.min(1, nx)), y: Math.max(0, Math.min(1, ny)) };
    };

    const handleBoundaryMouseDown = (e) => {
        if (!isDrawingBoundary) return;
        const pt = getNormalizedCoords(e);
        if (pt) setDragStart(pt);
    };

    const handleBoundaryMouseMove = (e) => {
        if (!isDrawingBoundary || !dragStart) return;
        const pt = getNormalizedCoords(e);
        if (pt) setDragCurrent(pt);
    };

    const handleBoundaryMouseUp = (e) => {
        if (!isDrawingBoundary || !dragStart) return;
        const pt = getNormalizedCoords(e) || dragCurrent;
        if (pt) {
            const x1 = Math.min(dragStart.x, pt.x);
            const y1 = Math.min(dragStart.y, pt.y);
            const x2 = Math.max(dragStart.x, pt.x);
            const y2 = Math.max(dragStart.y, pt.y);
            if (x2 - x1 > 0.01 && y2 - y1 > 0.01) setThreatBox({ x1, y1, x2, y2 });
        }
        setDragStart(null);
        setDragCurrent(null);
        setIsDrawingBoundary(false);
    };

    const handleBoundaryMouseLeave = () => {
        if (dragStart) {
            setDragStart(null);
            setDragCurrent(null);
        }
    };

    const checkThreatInFrame = (detections, frameWidth, frameHeight) => {
        const box = threatBoxRef.current;
        if (!box || !detections || !frameWidth || !frameHeight) {
            setThreatAlert(false);
            return;
        }
        const tx1 = box.x1 * frameWidth, ty1 = box.y1 * frameHeight, tx2 = box.x2 * frameWidth, ty2 = box.y2 * frameHeight;
        // Alert if any part of the person's bbox overlaps the red box (e.g. head entering counts)
        const anyOverlap = detections.some((det) => {
            const bbox = det.bbox || det;
            const px1 = bbox[0], py1 = bbox[1], px2 = bbox[2], py2 = bbox[3];
            return px1 < tx2 && px2 > tx1 && py1 < ty2 && py2 > ty1;
        });
        setThreatAlert(anyOverlap);
    };

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const token = params.get('token');
        if (token) {
            sessionStorage.setItem(SSO_TOKEN_KEY, token);
            params.delete('token');
            const newSearch = params.toString();
            const newPath = window.location.pathname + (newSearch ? '?' + newSearch : '');
            window.history.replaceState({}, '', newPath);
            setSearchParams(params);
        }
        if (!sessionStorage.getItem(SSO_TOKEN_KEY)) {
            navigate('/login', { replace: true });
            return;
        }
    }, [navigate, setSearchParams]);

    useEffect(() => {
        const overlay = boundaryOverlayRef.current;
        const canvas = boundaryCanvasRef.current;
        const el = isStreaming ? videoRef.current : (davLiveFrame && davLiveImgRef.current) ? davLiveImgRef.current : null;
        if (!overlay || !canvas || !el) return;
        const ow = overlay.clientWidth;
        const oh = overlay.clientHeight;
        if (ow <= 0 || oh <= 0) return;
        canvas.width = ow;
        canvas.height = oh;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const rect = el.getBoundingClientRect();
        const cr = canvas.getBoundingClientRect();
        const w = el.videoWidth ?? el.naturalWidth ?? 1;
        const h = el.videoHeight ?? el.naturalHeight ?? 1;
        const scale = Math.min(rect.width / w, rect.height / h);
        const dw = w * scale;
        const dh = h * scale;
        const contentLeft = rect.left + (rect.width - dw) / 2;
        const contentTop = rect.top + (rect.height - dh) / 2;
        const contentLeftCanvas = ((contentLeft - cr.left) / cr.width) * canvas.width;
        const contentTopCanvas = ((contentTop - cr.top) / cr.height) * canvas.height;
        const contentWCanvas = (dw / cr.width) * canvas.width;
        const contentHCanvas = (dh / cr.height) * canvas.height;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let x1, y1, x2, y2;
        if (isDrawingBoundary && dragStart && dragCurrent) {
            x1 = contentLeftCanvas + Math.min(dragStart.x, dragCurrent.x) * contentWCanvas;
            y1 = contentTopCanvas + Math.min(dragStart.y, dragCurrent.y) * contentHCanvas;
            x2 = contentLeftCanvas + Math.max(dragStart.x, dragCurrent.x) * contentWCanvas;
            y2 = contentTopCanvas + Math.max(dragStart.y, dragCurrent.y) * contentHCanvas;
        } else if (threatBox) {
            x1 = contentLeftCanvas + threatBox.x1 * contentWCanvas;
            y1 = contentTopCanvas + threatBox.y1 * contentHCanvas;
            x2 = contentLeftCanvas + threatBox.x2 * contentWCanvas;
            y2 = contentTopCanvas + threatBox.y2 * contentHCanvas;
        } else return;
        ctx.strokeStyle = '#ef4444';
        ctx.fillStyle = 'rgba(239, 68, 68, 0.25)';
        ctx.lineWidth = 3;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
    }, [isDrawingBoundary, dragStart, dragCurrent, threatBox, isStreaming, davLiveFrame]);

    useEffect(() => {
        // Get available cameras on component mount
        getAvailableCameras();
        
        // Check backend connection
        checkBackendConnection();
        
        // Cleanup on unmount
        return () => {
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(track => track.stop());
            }
            if (videoFileUrl) {
                URL.revokeObjectURL(videoFileUrl);
            }
            if (detectionIntervalRef.current) {
                clearInterval(detectionIntervalRef.current);
                detectionIntervalRef.current = null;
            }
        };
    }, [videoFileUrl]);

    // Auto-start detection when streaming begins
    useEffect(() => {
        if (isStreaming && videoRef.current) {
            console.log('[Effect] Streaming started, setting up detection...');
            // Wait a bit for video to be ready
            const timer = setTimeout(() => {
                if (videoRef.current && videoRef.current.readyState >= 2) {
                    console.log('[Effect] Video ready, starting detection');
                    startDetection();
                } else {
                    console.log('[Effect] Video not ready yet, will retry');
                    // Retry after a short delay
                    setTimeout(() => {
                        if (videoRef.current && videoRef.current.readyState >= 2) {
                            startDetection();
                        }
                    }, 500);
                }
            }, 500);
            
            return () => clearTimeout(timer);
        } else if (!isStreaming) {
            // Stop detection when streaming stops
            if (detectionIntervalRef.current) {
                console.log('[Effect] Streaming stopped, clearing detection interval');
                clearInterval(detectionIntervalRef.current);
                detectionIntervalRef.current = null;
            }
        }
    }, [isStreaming]);

    const checkBackendConnection = async () => {
        try {
            const response = await fetch('http://localhost:5000/api/health', {
                method: 'GET',
                timeout: 3000
            });
            if (response.ok) {
                const data = await response.json();
                setBackendConnected(data.detector_ready || false);
                setDetectionError(null);
            } else {
                setBackendConnected(false);
                setDetectionError('Backend server responded with error');
            }
        } catch (error) {
            setBackendConnected(false);
            setDetectionError('Cannot connect to backend server. Make sure it is running on http://localhost:5000');
            console.error('Backend connection error:', error);
        }
    };

    const getAvailableCameras = async () => {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(device => device.kind === 'videoinput');
            
            const cameraList = ['Select Camera', ...videoDevices.map(device => 
                device.label || `Camera ${videoDevices.indexOf(device) + 1}`
            )];
            
            setAvailableCameras(cameraList);
        } catch (error) {
            console.error('Error getting cameras:', error);
            // Fallback to default cameras
            setAvailableCameras([
                'Select Camera',
                'HD User Facing (04f2:b72b)',
                'Camera 2',
                'Camera 3'
            ]);
        }
    };

    const isDavFile = (file) => file && file.name && file.name.toLowerCase().endsWith('.dav');

    const handleFileSelect = (e) => {
        const file = e.target.files[0];
        if (file) {
            setDavResults(null);
            setDavLiveFrame(null);
            // Clean up previous file URL if exists
            if (videoFileUrl) {
                URL.revokeObjectURL(videoFileUrl);
            }
            
            // Stop camera if running
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(track => track.stop());
                streamRef.current = null;
            }
            
            setSelectedVideoFile(file);
            setVideoMode('file');
            
            if (isDavFile(file)) {
                // .dav files cannot be played in browser; process on server instead
                setVideoFileUrl(null);
                if (videoRef.current) {
                    videoRef.current.srcObject = null;
                    videoRef.current.removeAttribute('src');
                    videoRef.current.load();
                }
                setIsStreaming(false);
                return;
            }
            
            const url = URL.createObjectURL(file);
            setVideoFileUrl(url);
            
            if (videoRef.current) {
                videoRef.current.srcObject = null;
                videoRef.current.src = url;
                videoRef.current.load();
                
                videoRef.current.onloadedmetadata = () => {
                    console.log('Video file metadata loaded');
                    videoRef.current.play().catch(err => {
                        console.error('Error playing video file:', err);
                    });
                };
                
                videoRef.current.oncanplay = () => {
                    console.log('Video file can play');
                };
            }
            
            setIsStreaming(true);
            setTimeout(() => {
                startDetection();
            }, 500);
        }
    };

    const handleProcessDavFile = async () => {
        if (!selectedVideoFile || !isDavFile(selectedVideoFile)) return;
        setDavProcessing(true);
        setDavPaused(false);
        davPausedRef.current = false;
        setDavResults(null);
        setDavLiveFrame(null);
                        setOccupancyStats(null);
        setDetectionError(null);
        try {
            const formData = new FormData();
            formData.append('video', selectedVideoFile);
            formData.append('frame_interval', '5');
            formData.append('max_frames', '2000');
            formData.append('conf_threshold', '0.15');
            formData.append('draw_chairs', featureTab === 'threat_detection' ? 'false' : 'true');
            formData.append('save_occupancy_to_db', featureTab === 'occupancy_rate' ? 'true' : 'false');
            const controller = new AbortController();
            davAbortControllerRef.current = controller;
            const response = await fetch('http://localhost:5000/api/detect-video-file-stream', {
                method: 'POST',
                body: formData,
                signal: controller.signal,
            });
            if (!response.ok || !response.body) {
                setDetectionError('Streaming failed');
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let lastSummary = null;
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const data = JSON.parse(line);
                        if (data.error) {
                            setDetectionError(data.error);
                            continue;
                        }
                        if (data.frame !== undefined && !davPausedRef.current) {
                            setDavLiveFrame(data.frame);
                            if (data.video_datetime != null) setVideoDateTime(data.video_datetime);
                            if (data.frame_width != null && data.frame_height != null) setLastFrameDimensions({ w: data.frame_width, h: data.frame_height });
                            checkThreatInFrame(data.detections || [], data.frame_width, data.frame_height);
                            const dets = data.detections || [];
                            const confs = dets.map(d => d.confidence);
                            const stats = confs.length ? {
                                count: data.count,
                                avg_confidence: confs.reduce((a, b) => a + b, 0) / confs.length,
                                max_confidence: Math.max(...confs),
                                min_confidence: Math.min(...confs),
                            } : null;
                            setDetectionData({
                                count: data.count,
                                detections: dets,
                                stats,
                            });
                            if (data.total_people != null || data.occupancy_rate != null) setOccupancyStats({
                                total_people: data.total_people ?? data.count ?? 0,
                                unoccupied_chairs: data.unoccupied_chairs ?? data.chair_count ?? 0,
                                occupied_chairs: data.occupied_chairs ?? data.count ?? 0,
                                total_chairs: data.total_chairs ?? 0,
                                occupancy_rate: data.occupancy_rate ?? null,
                            });
                        }
                        if (data.done) {
                            lastSummary = data;
                            if (data.success && data.summary) {
                                setDavResults({
                                    success: true,
                                    frames_processed: data.frames_processed,
                                    summary: data.summary,
                                    total_frames_in_video: data.total_frames_in_video,
                                });
                                setDetectionData({
                                    count: data.summary.max_count,
                                    detections: [],
                                    stats: null,
                                });
                            }
                        }
                    } catch (_) { /* skip malformed line */ }
                }
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                console.log('DAV processing stopped by user');
                return;
            }
            setDetectionError(err.message || 'Failed to process DAV file');
            console.error(err);
        } finally {
            davAbortControllerRef.current = null;
            davPausedRef.current = false;
            setDavProcessing(false);
            setDavPaused(false);
        }
    };

    const handlePauseResumeDav = () => {
        davPausedRef.current = !davPausedRef.current;
        setDavPaused(davPausedRef.current);
    };

    const handleStopDavProcessing = () => {
        if (davAbortControllerRef.current) {
            davAbortControllerRef.current.abort();
        }
    };

    const handleStart = async () => {
        if (videoMode === 'file' && videoFileUrl) {
            // Resume file playback
            if (videoRef.current) {
                videoRef.current.play().catch(err => {
                    console.error('Error playing video:', err);
                });
            }
            setIsStreaming(true);
            // Start detection for file mode (faster)
            setTimeout(() => {
                startDetection();
            }, 500);
            return;
        }

        // Camera mode
        console.log('Starting camera feed...');

        try {
            // Try with ideal constraints first
            let constraints = {
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                },
                audio: false
            };

            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia(constraints);
            } catch (err) {
                // Fallback to basic constraints if ideal fails
                console.log('Trying with basic constraints...');
                constraints = {
                    video: true,
                    audio: false
                };
                stream = await navigator.mediaDevices.getUserMedia(constraints);
            }

            streamRef.current = stream;
            setVideoMode('camera');
            
            // Clean up file if switching from file to camera
            if (videoFileUrl) {
                URL.revokeObjectURL(videoFileUrl);
                setVideoFileUrl(null);
                setSelectedVideoFile(null);
            }
            
            if (videoRef.current) {
                videoRef.current.src = '';
                videoRef.current.srcObject = stream;
                
                // Wait for video to be ready
                videoRef.current.onloadedmetadata = () => {
                    console.log('Video metadata loaded');
                    videoRef.current.play().catch(err => {
                        console.error('Error playing video:', err);
                    });
                };

                videoRef.current.onplay = () => {
                    console.log('Video is playing');
                };

                videoRef.current.onerror = (e) => {
                    console.error('Video element error:', e);
                };
            }
            
            setIsStreaming(true);
            console.log('Video feed started successfully');
            // Start detection after state updates and video is ready (faster)
            setTimeout(() => {
                startDetection();
            }, 500);
        } catch (error) {
            console.error('Error accessing camera:', error);
            let errorMessage = 'Error accessing camera. ';
            if (error.name === 'NotAllowedError') {
                errorMessage += 'Please allow camera access in your browser settings.';
            } else if (error.name === 'NotFoundError') {
                errorMessage += 'No camera found. Please connect a camera.';
            } else if (error.name === 'NotReadableError') {
                errorMessage += 'Camera is being used by another application.';
            } else {
                errorMessage += error.message;
            }
            alert(errorMessage);
        }
    };

    const handleStop = () => {
        if (videoMode === 'camera' && streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
        
        if (videoRef.current) {
            if (videoMode === 'camera') {
                videoRef.current.srcObject = null;
            } else {
                videoRef.current.pause();
                videoRef.current.currentTime = 0;
            }
        }
        
        setIsStreaming(false);
        stopDetection();
        console.log('Video feed stopped');
    };

    const handleModeSwitch = (mode) => {
        // Stop current feed
        handleStop();
        
        // Clear file selection if switching to camera
        if (mode === 'camera') {
            if (videoFileUrl) {
                URL.revokeObjectURL(videoFileUrl);
                setVideoFileUrl(null);
            }
            setSelectedVideoFile(null);
            setDavResults(null);
            setDavLiveFrame(null);
            setOccupancyStats(null);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
        
        setVideoMode(mode);
    };

    const handleSnapshot = () => {
        if (!videoRef.current || !isStreaming) return;

        const canvas = document.createElement('canvas');
        canvas.width = videoRef.current.videoWidth;
        canvas.height = videoRef.current.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoRef.current, 0, 0);
        
        canvas.toBlob((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `snapshot-${Date.now()}.png`;
            a.click();
            URL.revokeObjectURL(url);
        });
        
        console.log('Snapshot taken');
    };

    const captureFrameForDetection = () => {
        if (!videoRef.current || !isStreaming) {
            console.log('Cannot capture: video not ready or not streaming');
            return null;
        }
        
        // Check if video is actually ready and has dimensions
        if (videoRef.current.readyState < 2 || 
            videoRef.current.videoWidth === 0 || 
            videoRef.current.videoHeight === 0) {
            console.log('Video not ready for capture');
            return null;
        }
        
        try {
            const canvas = document.createElement('canvas');
            canvas.width = videoRef.current.videoWidth;
            canvas.height = videoRef.current.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(videoRef.current, 0, 0);
            
            // Use lower quality (0.6) for faster processing and smaller payload
            return canvas.toDataURL('image/jpeg', 0.6);
        } catch (error) {
            console.error('Error capturing frame:', error);
            return null;
        }
    };

    const detectPeople = async () => {
        // Skip if already detecting or not streaming
        if (!isStreaming || isDetecting) {
            return; // Silently skip to avoid console spam
        }
        
        const frameBase64 = captureFrameForDetection();
        if (!frameBase64) {
            console.log('No frame captured for detection');
            return;
        }
        
        console.log('Starting detection - frame size:', frameBase64.length, 'bytes');
        setIsDetecting(true);
        
        try {
            const requestBody = {
                frame: frameBase64,
                conf_threshold: 0.25
            };
            
            console.log('Sending detection request to API...');
            const response = await fetch('http://localhost:5000/api/detect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });
            
            console.log('API Response status:', response.status);
            
            if (response.ok) {
                const data = await response.json();
                console.log('Detection response:', data);
                console.log('People detected:', data.count);
                console.log('Detections:', data.detections);
                
                if (data.success !== false) {
                    setDetectionData({
                        count: data.count || 0,
                        detections: data.detections || [],
                        stats: data.stats || null
                    });
                    if (data.total_people != null || data.occupancy_rate != null) setOccupancyStats({
                        total_people: data.total_people ?? data.count ?? 0,
                        unoccupied_chairs: data.unoccupied_chairs ?? data.chair_count ?? 0,
                        occupied_chairs: data.occupied_chairs ?? data.count ?? 0,
                        total_chairs: data.total_chairs ?? 0,
                        occupancy_rate: data.occupancy_rate ?? null,
                    });
                    if (data.video_datetime != null) setVideoDateTime(data.video_datetime);
                    if (data.frame_width != null && data.frame_height != null) setLastFrameDimensions({ w: data.frame_width, h: data.frame_height });
                    checkThreatInFrame(data.detections || [], data.frame_width, data.frame_height);
                    setDetectionError(null);
                    setBackendConnected(true);
                } else {
                    console.error('Detection failed:', data.error);
                    setDetectionError(data.error || 'Detection failed');
                    setDetectionData(prev => ({
                        ...prev,
                        count: 0
                    }));
                }
            } else {
                const errorText = await response.text();
                console.error('Detection API error:', response.status, errorText);
                try {
                    const errorData = JSON.parse(errorText);
                    setDetectionError(`API Error: ${response.status} - ${errorData.error || errorText}`);
                } catch {
                    setDetectionError(`API Error: ${response.status} - ${errorText}`);
                }
                setDetectionData(prev => ({
                    ...prev,
                    count: 0
                }));
            }
        } catch (error) {
            console.error('Error detecting people:', error);
            console.error('Error details:', error.message);
            console.error('Error stack:', error.stack);
            
            if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                setDetectionError('Cannot connect to backend. Make sure server is running on http://localhost:5000');
                setBackendConnected(false);
            } else {
                setDetectionError(`Detection error: ${error.message}`);
            }
            
            setDetectionData(prev => ({
                ...prev,
                count: 0
            }));
        } finally {
            setIsDetecting(false);
        }
    };

    const startDetection = () => {
        // Clear any existing interval
        if (detectionIntervalRef.current) {
            clearInterval(detectionIntervalRef.current);
            detectionIntervalRef.current = null;
        }
        
        console.log('Starting detection interval...');
        
        // Function to check and run detection - uses current refs/state
        const runDetectionIfReady = () => {
            // Check current streaming state from ref (more reliable)
            const currentVideo = videoRef.current;
            if (!currentVideo) {
                console.log('[Auto] No video element');
                return false;
            }
            
            // Check video readiness - be more lenient
            const readyState = currentVideo.readyState;
            const hasDimensions = currentVideo.videoWidth > 0 && currentVideo.videoHeight > 0;
            const isPlaying = !currentVideo.paused && !currentVideo.ended;
            
            // Video is ready if it has metadata loaded and dimensions
            if (readyState >= 2 && hasDimensions) {
                console.log(`[Auto] Video ready (state: ${readyState}, ${currentVideo.videoWidth}x${currentVideo.videoHeight}), triggering detection`);
                detectPeople();
                return true;
            } else {
                console.log(`[Auto] Video not ready - readyState: ${readyState}, dimensions: ${currentVideo.videoWidth}x${currentVideo.videoHeight}, playing: ${isPlaying}`);
            }
            return false;
        };
        
        // Try immediately after a very short delay
        setTimeout(() => {
            runDetectionIfReady();
        }, 300);
        
        // Set up interval - run every 500ms (0.5 seconds) for fast detection
        detectionIntervalRef.current = setInterval(() => {
            runDetectionIfReady();
        }, 500);
        
        console.log('Automatic detection interval active - running every 500ms (fast mode)');
    };

    const stopDetection = () => {
        if (detectionIntervalRef.current) {
            clearInterval(detectionIntervalRef.current);
            detectionIntervalRef.current = null;
        }
        setDetectionData({
            count: 0,
            detections: [],
            stats: null
        });
    };

    return (
        <div className="dashboard-container">
            <div className="dashboard-top-bar">
                <div className="logo-section">
                    <span className="logo-text">IntelliSpace AI</span>
                </div>
                <div className="header-bar">
                    <button 
                        className="logout-btn"
                        onClick={() => {
                            if (streamRef.current) {
                                streamRef.current.getTracks().forEach(track => track.stop());
                            }
                            if (detectionIntervalRef.current) {
                                clearInterval(detectionIntervalRef.current);
                            }
                            sessionStorage.removeItem(SSO_TOKEN_KEY);
                            navigate('/login', { replace: true });
                        }}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                            <polyline points="16 17 21 12 16 7"></polyline>
                            <line x1="21" y1="12" x2="9" y2="12"></line>
                        </svg>
                        <span>Logout</span>
                    </button>
                </div>
            </div>

            <div className="dashboard-content">
                {/* Left Panel - Features */}
                <div className="left-panel">
                    <div className="panel-header">
                        <h2>Features</h2>
                    </div>
                    <div className="panel-content">
                        <div className="feature-tabs">
                            <button
                                type="button"
                                className={`feature-tab ${featureTab === 'occupancy_rate' ? 'active' : ''}`}
                                onClick={() => setFeatureTab('occupancy_rate')}
                            >
                                Occupancy rate
                            </button>
                            <button
                                type="button"
                                className={`feature-tab ${featureTab === 'occupancy_analysis' ? 'active' : ''}`}
                                onClick={() => setFeatureTab('occupancy_analysis')}
                            >
                                Occupancy Analysis
                            </button>
                            <button
                                type="button"
                                className={`feature-tab ${featureTab === 'threat_detection' ? 'active' : ''}`}
                                onClick={() => setFeatureTab('threat_detection')}
                            >
                                Threat detection
                            </button>
                        </div>
                        <div className="feature-tab-content">
                            {featureTab === 'occupancy_rate' && (
                                <div className="feature-pane">
                                    <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255,255,255,0.6)', marginBottom: '10px' }}>Current occupancy</div>
                                    {occupancyStats ? (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                                                <span style={{ color: 'rgba(255,255,255,0.85)' }}>Occupancy rate</span>
                                                <span style={{ fontWeight: '600', color: 'var(--accent-color, #4ade80)' }}>
                                                    {occupancyStats.occupancy_rate != null ? `${Number(occupancyStats.occupancy_rate).toFixed(1)}%` : '—'}
                                                </span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                                                <span style={{ color: 'rgba(255,255,255,0.85)' }}>People</span>
                                                <span style={{ fontWeight: '600' }}>{occupancyStats.total_people}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                                                <span style={{ color: 'rgba(255,255,255,0.85)' }}>Total chairs</span>
                                                <span style={{ fontWeight: '600' }}>{occupancyStats.total_chairs}</span>
                                            </div>
                                        </div>
                                    ) : (
                                        <p className="placeholder-text" style={{ marginTop: '8px' }}>Start video or process a file to see occupancy rate.</p>
                                    )}
                                </div>
                            )}
                            {featureTab === 'occupancy_analysis' && (
                                <div className="feature-pane">
                                    <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255,255,255,0.6)', marginBottom: '10px' }}>Occupancy Analysis</div>
                                    <p className="placeholder-text">Occupancy analysis content will be added here.</p>
                                </div>
                            )}
                            {featureTab === 'threat_detection' && (
                                <div className="feature-pane">
                                    <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255,255,255,0.6)', marginBottom: '10px' }}>Threat detection</div>
                                    <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.8)', marginBottom: '12px', lineHeight: 1.5 }}>
                                        Drag on the video to draw a red box. When a person enters the box, an alert is triggered.
                                    </p>
                                    <button
                                        type="button"
                                        className="control-btn start-btn"
                                        style={{ marginBottom: '8px', width: '100%' }}
                                        onClick={() => { setIsDrawingBoundary(true); setDragStart(null); setDragCurrent(null); }}
                                    >
                                        {threatBox ? 'Redraw box' : 'Draw box on video'}
                                    </button>
                                    {threatBox && (
                                        <button
                                            type="button"
                                            className="control-btn stop-btn"
                                            style={{ marginBottom: '12px', width: '100%', justifyContent: 'center' }}
                                            onClick={() => { setThreatBox(null); setThreatAlert(false); }}
                                        >
                                            Clear box
                                        </button>
                                    )}
                                    <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', marginBottom: '8px' }}>
                                        {threatBox ? 'Red box set on video' : 'No box drawn'}
                                    </div>
                                    {isDrawingBoundary && (
                                        <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)', marginTop: '4px' }}>
                                            Drag on the video to draw the box, then release.
                                        </p>
                                    )}
                                    {threatAlert && (
                                        <div className="threat-alert-banner" style={{ padding: '12px', background: 'rgba(239, 68, 68, 0.25)', border: '1px solid rgba(239, 68, 68, 0.6)', borderRadius: '8px', color: '#fca5a5', fontWeight: '600', fontSize: '13px', marginTop: '8px' }}>
                                            Alert: Person in unrestricted area
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Center Panel - Video Feed */}
                <div className="center-panel">
                    <div className="video-controls">
                        <div className="mode-selector">
                            <label>Video Source</label>
                            <div className="mode-toggle">
                                <button
                                    className={`mode-btn ${videoMode === 'camera' ? 'active' : ''}`}
                                    onClick={() => handleModeSwitch('camera')}
                                >
                                    Camera
                                </button>
                                <button
                                    className={`mode-btn ${videoMode === 'file' ? 'active' : ''}`}
                                    onClick={() => handleModeSwitch('file')}
                                >
                                    File
                                </button>
                            </div>
                        </div>
                        
                        {videoMode === 'camera' ? (
                            <div className="camera-selector">
                                <label htmlFor="cameraSelect">Select Camera</label>
                                <select 
                                    id="cameraSelect"
                                    value={selectedCamera}
                                    onChange={(e) => setSelectedCamera(e.target.value)}
                                    className="camera-dropdown"
                                >
                                    {availableCameras.map((camera, index) => (
                                        <option key={index} value={camera}>
                                            {camera}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        ) : (
                            <div className="file-selector">
                                <label htmlFor="videoFileInput">Select Video File</label>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    id="videoFileInput"
                                    accept="video/*,.dav"
                                    onChange={handleFileSelect}
                                    style={{ display: 'none' }}
                                />
                                <button
                                    className="control-btn file-btn"
                                    onClick={() => fileInputRef.current?.click()}
                                >
                                    {selectedVideoFile ? selectedVideoFile.name : 'Choose File'}
                                </button>
                                {selectedVideoFile && isDavFile(selectedVideoFile) && (
                                    <button
                                        className="control-btn start-btn"
                                        onClick={handleProcessDavFile}
                                        disabled={davProcessing || !backendConnected}
                                        style={{ marginLeft: '8px' }}
                                    >
                                        {davProcessing ? 'Processing…' : 'Process on server'}
                                    </button>
                                )}
                            </div>
                        )}
                        
                        <div className="control-buttons">
                            {videoMode === 'camera' ? (
                                <>
                                    <button 
                                        className="control-btn start-btn" 
                                        onClick={handleStart}
                                        disabled={isStreaming}
                                    >
                                        Start
                                    </button>
                                    <button 
                                        className="control-btn stop-btn" 
                                        onClick={handleStop}
                                        disabled={!isStreaming}
                                    >
                                        Stop
                                    </button>
                                    <button 
                                        className="control-btn snapshot-btn" 
                                        onClick={handleSnapshot}
                                        disabled={!isStreaming}
                                    >
                                        Snapshot
                                    </button>
                                </>
                            ) : (
                                <>
                                    <button
                                        type="button"
                                        className="control-btn pause-btn"
                                        onClick={handlePauseResumeDav}
                                        disabled={!davProcessing}
                                        title={davPaused ? 'Resume' : 'Pause'}
                                    >
                                        {davPaused ? (
                                            <>
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                                                <span>Resume</span>
                                            </>
                                        ) : (
                                            <>
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
                                                <span>Pause</span>
                                            </>
                                        )}
                                    </button>
                                    <button
                                        type="button"
                                        className="control-btn stop-btn"
                                        onClick={handleStopDavProcessing}
                                        disabled={!davProcessing}
                                        title="Stop"
                                    >
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12"/></svg>
                                        <span>Stop</span>
                                    </button>
                                </>
                            )}
                        </div>
                    </div>

                    <div className="video-feed-container">
                        <div ref={videoFeedContainerRef} className={`video-feed ${!isStreaming && !davResults?.sample_frames?.length ? 'video-feed-disconnected' : ''}`}>
                            <video
                                ref={videoRef}
                                autoPlay
                                playsInline
                                muted={videoMode === 'camera'}
                                controls={videoMode === 'file'}
                                className="video-element"
                                style={{ display: isStreaming ? 'block' : 'none' }}
                                onError={(e) => {
                                    console.error('Video error:', e);
                                    alert('Error loading video. Please try again.');
                                }}
                            />
                            {davLiveFrame && !isStreaming && (
                                <div className="dav-live-container" style={{ width: '100%', height: '100%', position: 'absolute', inset: 0, background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <img
                                        ref={davLiveImgRef}
                                        src={`data:image/jpeg;base64,${davLiveFrame}`}
                                        alt="Live DAV processing"
                                        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                                    />
                                    {davProcessing && (
                                        <div style={{ position: 'absolute', top: '8px', left: '50%', transform: 'translateX(-50%)', background: 'rgba(0,0,0,0.7)', color: '#fff', padding: '6px 12px', borderRadius: '6px', fontSize: '12px' }}>
                                            {davPaused ? 'Paused' : 'Processing… (live)'}
                                        </div>
                                    )}
                                </div>
                            )}
                            {threatAlert && (
                                <div style={{ position: 'absolute', top: '8px', right: '8px', zIndex: 10, background: 'rgba(239, 68, 68, 0.9)', color: '#fff', padding: '8px 14px', borderRadius: '8px', fontSize: '13px', fontWeight: '600', boxShadow: '0 2px 8px rgba(0,0,0,0.3)' }}>
                                    Alert: Person in unrestricted area
                                </div>
                            )}
                            {(isDrawingBoundary || threatBox) && (isStreaming || davLiveFrame) && (
                                <div
                                    ref={boundaryOverlayRef}
                                    className="threat-boundary-overlay"
                                    style={{
                                        position: 'absolute', inset: 0, pointerEvents: isDrawingBoundary ? 'auto' : 'none',
                                        cursor: isDrawingBoundary ? 'crosshair' : 'default', zIndex: 5
                                    }}
                                >
                                    <canvas
                                        ref={boundaryCanvasRef}
                                        onMouseDown={handleBoundaryMouseDown}
                                        onMouseMove={handleBoundaryMouseMove}
                                        onMouseUp={handleBoundaryMouseUp}
                                        onMouseLeave={handleBoundaryMouseLeave}
                                        style={{ width: '100%', height: '100%', display: 'block' }}
                                    />
                                </div>
                            )}
                            {davResults?.sample_frames?.length > 0 && !isStreaming && !davLiveFrame && (
                                <div className="dav-preview-container" style={{ display: 'block', width: '100%', maxHeight: '100%', overflow: 'auto' }}>
                                    <p className="video-status" style={{ marginBottom: '8px', fontSize: '12px' }}>DAV file preview (sample frames from detection)</p>
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', alignItems: 'flex-start' }}>
                                        {davResults.sample_frames.map((base64, i) => (
                                            <img
                                                key={i}
                                                src={`data:image/jpeg;base64,${base64}`}
                                                alt={`Frame ${i + 1}`}
                                                style={{ maxWidth: '100%', maxHeight: '360px', objectFit: 'contain', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.2)' }}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}
                            {!isStreaming && !davLiveFrame && !davResults?.sample_frames?.length && (
                                <div className="video-placeholder">
                                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                        <path d="M23 7l-7 5 7 5V7z" />
                                        <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                                    </svg>
                                    <p>{videoMode === 'camera' ? 'Camera: Disconnected' : (selectedVideoFile && isDavFile(selectedVideoFile) ? 'DAV file selected' : 'No Video File Selected')}</p>
                                    <p className="video-instruction">
                                        {videoMode === 'camera' 
                                            ? 'Camera Not Started. Select camera and click Start. Snapshot feature available.'
                                            : (selectedVideoFile && isDavFile(selectedVideoFile))
                                                ? 'DAV (Dahua) files are processed on the server. Click "Process on server" to see live video with detection (like MP4).'
                                                : 'No video file selected. Click "Choose File" to select a video file (MP4, AVI, or .dav).'
                                        }
                                    </p>
                                </div>
                            )}
                            {isStreaming && (
                                <div className="video-overlay">
                                    <p>Video Feed Active</p>
                                    <p className="video-status">
                                        {videoMode === 'camera' 
                                            ? `Camera: ${selectedCamera === 'Select Camera' ? 'Default Camera' : selectedCamera}`
                                            : `File: ${selectedVideoFile?.name || 'Video File'}${selectedVideoFile && isDavFile(selectedVideoFile) ? ' (DAV — use Process on server)' : ''}`
                                        }
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right Panel - People Detection */}
                <div className="right-panel">
                    <div className="panel-header">
                        <h2>SYSTEM STATUS</h2>
                    </div>
                    <div className="panel-content">
                        <div className="detection-section">
                            <div className="video-datetime-card" style={{ padding: '16px', background: 'rgba(0,0,0,0.25)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '12px' }}>
                                <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255,255,255,0.6)', marginBottom: '8px' }}>Video date / time</div>
                                <div style={{ fontSize: '15px', fontWeight: '600', color: 'rgba(255,255,255,0.95)', fontFamily: 'monospace' }}>
                                    {videoDateTime != null && videoDateTime !== '' ? videoDateTime : '—'}
                                </div>
                            </div>
                            {featureTab !== 'threat_detection' && occupancyStats ? (
                                <div className="occupancy-card" style={{ padding: '16px', background: 'rgba(0,0,0,0.25)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}>
                                    <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255,255,255,0.6)', marginBottom: '14px' }}>Occupancy</div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                                            <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.85)' }}>Total people</span>
                                            <span style={{ fontSize: '14px', fontWeight: '600' }}>{occupancyStats.total_people}</span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                                            <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.85)' }}>Total unoccupied chairs</span>
                                            <span style={{ fontSize: '14px', fontWeight: '600' }}>{occupancyStats.unoccupied_chairs}</span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                                            <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.85)' }}>Total occupied chairs</span>
                                            <span style={{ fontSize: '14px', fontWeight: '600' }}>{occupancyStats.occupied_chairs}</span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                                            <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.85)' }}>Total chairs</span>
                                            <span style={{ fontSize: '14px', fontWeight: '600' }}>{occupancyStats.total_chairs}</span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0 4px' }}>
                                            <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.85)' }}>Occupancy rate</span>
                                            <span style={{ fontSize: '16px', fontWeight: '700', color: 'var(--accent-color, #4ade80)' }}>
                                                {occupancyStats.occupancy_rate != null ? `${Number(occupancyStats.occupancy_rate).toFixed(1)}%` : '—'}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            ) : null}

                            {davResults && davResults.success && (
                                <div className="detection-status" style={{ marginTop: '12px', padding: '12px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
                                    <div className="count-label">DAV file results</div>
                                    <p style={{ margin: '4px 0', fontSize: '13px' }}>Frames processed: {davResults.frames_processed}</p>
                                    <p style={{ margin: '4px 0', fontSize: '13px' }}>Max people in frame: {davResults.summary?.max_count ?? 0}</p>
                                    <p style={{ margin: '4px 0', fontSize: '13px' }}>Frames with people: {davResults.summary?.frames_with_people ?? 0}</p>
                                </div>
                            )}

                            {!backendConnected && (
                                <div className="detection-status">
                                    <div className="status-indicator-small error">
                                        <span className="status-dot"></span>
                                        <span>Backend Offline</span>
                                    </div>
                                </div>
                            )}

                            {backendConnected && isStreaming && (
                                <div className="detection-status">
                                    <div className={`status-indicator-small ${isDetecting ? 'detecting' : 'idle'}`}>
                                        <span className="status-dot"></span>
                                        <span>{isDetecting ? 'Detecting...' : 'Monitoring'}</span>
                                    </div>
                                </div>
                            )}

                            {detectionError && (
                                <div className="detection-error">
                                    <p>{detectionError}</p>
                                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '8px' }}>
                                        <button 
                                            className="retry-btn"
                                            onClick={checkBackendConnection}
                                        >
                                            Retry Connection
                                        </button>
                                        <button 
                                            className="retry-btn"
                                            onClick={() => {
                                                console.log('Manual detection test');
                                                detectPeople();
                                            }}
                                        >
                                            Test Detection
                                        </button>
                                    </div>
                                </div>
                            )}

                            {isStreaming && !detectionError && (
                                <div style={{ textAlign: 'center', marginTop: '12px' }}>
                                    <button 
                                        className="control-btn"
                                        onClick={() => {
                                            console.log('Manual detection trigger');
                                            detectPeople();
                                        }}
                                        style={{ fontSize: '12px', padding: '8px 16px' }}
                                    >
                                        Test Detection Now
                                    </button>
                                </div>
                            )}

                            {!isStreaming && !davResults && (
                                <div className="detection-message">
                                    <p>Start video feed or process a DAV file to begin people detection</p>
                                </div>
                            )}

                            {isStreaming && detectionData.count === 0 && !isDetecting && (
                                <div className="detection-message">
                                    <p>No people detected in current frame</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;

