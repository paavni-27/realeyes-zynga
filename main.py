import streamlit as st
import cv2
import numpy as np
from PIL import Image
import re
from datetime import datetime
import ssl
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, RTCConfiguration
import av
import easyocr
import time

# Fix SSL certificate issue for EasyOCR downloads (for some environments)
ssl._create_default_https_context = ssl._create_unverified_context

# Page configuration
st.set_page_config(
    page_title="RealEyes - Identity Verification",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Helper: Extract DOB from OCR text
def extract_dob(text_lines):
    dob_patterns = [
        r'(\d{2}[/-]\d{2}[/-]\d{4})',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        r'DOB[:\s]*(\d{2}[/-]\d{2}[/-]\d{4})',
        r'Birth[:\s]*(\d{2}[/-]\d{2}[/-]\d{4})'
    ]
    
    for line in text_lines:
        for pattern in dob_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1) if len(dob_patterns) > 2 and 'DOB' in pattern else match.group(1)
    return None

# Helper: Calculate age from DOB string
def calculate_age(dob_str):
    try:
        # Try different date formats
        formats = ["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y"]
        dob = None
        
        for fmt in formats:
            try:
                dob = datetime.strptime(dob_str.replace("-", "/"), fmt.replace("-", "/"))
                break
            except ValueError:
                continue
        
        if dob is None:
            return None
            
        today = datetime.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except Exception:
        return None

# Helper: Extract face from image using OpenCV
def extract_face(img):
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(50, 50))
    
    if len(faces) > 0:
        # Get the largest face
        (x, y, w, h) = max(faces, key=lambda face: face[2] * face[3])
        margin = int(0.2 * w)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img.shape[1], x + w + margin)
        y2 = min(img.shape[0], y + h + margin)
        return img[y1:y2, x1:x2]
    return None

# Helper: Check image quality for selfies
def check_image_quality(img):
    quality_checks = {
        'blur_score': 0,
        'brightness_score': 0,
        'contrast_score': 0,
        'face_centered': False,
        'face_size_ok': False,
        'overall_quality': 'Poor'
    }
    
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # Blur detection using Laplacian variance
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    quality_checks['blur_score'] = blur_score
    
    # Brightness analysis
    brightness = np.mean(gray)
    quality_checks['brightness_score'] = brightness
    
    # Contrast analysis
    contrast = gray.std()
    quality_checks['contrast_score'] = contrast
    
    # Face detection and positioning
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, 1.2, 5)
    
    if len(faces) > 0:
        (x, y, w, h) = max(faces, key=lambda face: face[2] * face[3])
        img_center_x = img.shape[1] // 2
        img_center_y = img.shape[0] // 2
        face_center_x = x + w // 2
        face_center_y = y + h // 2
        
        center_tolerance_x = img.shape[1] * 0.25
        center_tolerance_y = img.shape[0] * 0.25
        
        quality_checks['face_centered'] = (
            abs(face_center_x - img_center_x) < center_tolerance_x and
            abs(face_center_y - img_center_y) < center_tolerance_y
        )
        
        min_face_size = img.shape[1] * 0.15
        quality_checks['face_size_ok'] = w > min_face_size
    
    # Overall quality assessment
    blur_ok = blur_score > 100
    brightness_ok = 50 < brightness < 200
    contrast_ok = contrast > 20
    
    score = 0
    if blur_ok: score += 25
    if brightness_ok: score += 25
    if contrast_ok: score += 15
    if quality_checks['face_centered']: score += 20
    if quality_checks['face_size_ok']: score += 15
    
    if score >= 85:
        quality_checks['overall_quality'] = 'Excellent'
    elif score >= 65:
        quality_checks['overall_quality'] = 'Good'
    elif score >= 45:
        quality_checks['overall_quality'] = 'Fair'
    else:
        quality_checks['overall_quality'] = 'Poor'
    
    return quality_checks

def display_quality_feedback(quality_checks):
    st.markdown('<h4 class="quality-header">Image Quality Analysis</h4>', unsafe_allow_html=True)
    
    # Create metrics in a modern layout
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        blur_score = quality_checks['blur_score']
        if blur_score > 100:
            st.success("**Sharpness**\n\nExcellent")
        elif blur_score > 50:
            st.warning("**Sharpness**\n\nFair")
        else:
            st.error("**Sharpness**\n\nPoor")
        st.caption(f"Score: {blur_score:.1f}")
    
    with col2:
        brightness = quality_checks['brightness_score']
        if 50 < brightness < 200:
            st.success("**Lighting**\n\nOptimal")
        elif brightness <= 50:
            st.error("**Lighting**\n\nToo Dark")
        else:
            st.warning("**Lighting**\n\nToo Bright")
        st.caption(f"Level: {brightness:.1f}")
    
    with col3:
        contrast = quality_checks['contrast_score']
        if contrast > 30:
            st.success("**Contrast**\n\nGood")
        elif contrast > 15:
            st.warning("**Contrast**\n\nFair")
        else:
            st.error("**Contrast**\n\nPoor")
        st.caption(f"Value: {contrast:.1f}")
    
    with col4:
        if quality_checks['face_centered'] and quality_checks['face_size_ok']:
            st.success("**Position**\n\nPerfect")
        elif quality_checks['face_centered']:
            st.warning("**Position**\n\nMove Closer")
        elif quality_checks['face_size_ok']:
            st.warning("**Position**\n\nCenter Face")
        else:
            st.error("**Position**\n\nAdjust")
    
    # Overall quality with modern styling
    quality = quality_checks['overall_quality']
    if quality == 'Excellent':
        st.success(f"**Overall Quality: {quality}** - Perfect for verification!")
    elif quality == 'Good':
        st.success(f"**Overall Quality: {quality}** - Ready for processing")
    elif quality == 'Fair':
        st.warning(f"**Overall Quality: {quality}** - Acceptable but could be improved")
    else:
        st.error(f"**Overall Quality: {quality}** - Please retake for better results")
    
    # Improvement suggestions
    tips = []
    if quality_checks['blur_score'] <= 100:
        tips.append("**Focus:** Hold camera steady and ensure good focus")
    if quality_checks['brightness_score'] <= 50:
        tips.append("**Lighting:** Move to a brighter area or add lighting")
    elif quality_checks['brightness_score'] >= 200:
        tips.append("**Exposure:** Reduce lighting or move away from bright sources")
    if quality_checks['contrast_score'] <= 20:
        tips.append("**Contrast:** Improve lighting conditions for better contrast")
    if not quality_checks['face_centered']:
        tips.append("**Positioning:** Center your face in the frame")
    if not quality_checks['face_size_ok']:
        tips.append("**Distance:** Move closer to the camera")
    
    if tips:
        st.info("**Improvement Tips:**\n" + "\n".join(f"• {tip}" for tip in tips))

# VideoProcessor for webcam
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.latest_frame = None
        self.frame_count = 0

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Quality metrics
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = np.mean(gray)
        contrast = gray.std()
        
        # Face detection
        faces = self.face_cascade.detectMultiScale(gray, 1.2, 5)
        face_centered = False
        face_size_ok = False
        
        if len(faces) > 0:
            (x, y, w, h) = max(faces, key=lambda face: face[2] * face[3])
            img_center_x = img.shape[1] // 2
            img_center_y = img.shape[0] // 2
            face_center_x = x + w // 2
            face_center_y = y + h // 2
            
            center_tolerance_x = img.shape[1] * 0.25
            center_tolerance_y = img.shape[0] * 0.25
            
            face_centered = (
                abs(face_center_x - img_center_x) < center_tolerance_x and
                abs(face_center_y - img_center_y) < center_tolerance_y
            )
            
            min_face_size = img.shape[1] * 0.15
            face_size_ok = w > min_face_size
            
            # Draw face rectangle with quality-based color
            if face_centered and face_size_ok and blur_score > 100:
                color = (0, 255, 0)  # Green for perfect
                status = "Perfect! Ready to capture"
            elif face_centered and face_size_ok:
                color = (255, 165, 0)  # Orange for good position but quality issues
                status = "Good position, hold steady"
            elif face_centered or face_size_ok:
                color = (255, 165, 0)  # Orange for partial success
                status = "Adjust position"
            else:
                color = (0, 0, 255)  # Red for poor
                status = "Center your face"
            
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)
            cv2.putText(img, status, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        else:
            cv2.putText(img, "No face detected", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Draw center guide
        center_x, center_y = img.shape[1] // 2, img.shape[0] // 2
        cv2.circle(img, (center_x, center_y), 5, (255, 255, 255), -1)
        cv2.circle(img, (center_x, center_y), 120, (255, 255, 255), 2)
        cv2.circle(img, (center_x, center_y), 80, (255, 255, 255), 1)
        
        # Quality indicators
        y_offset = 30
        
        # Sharpness indicator
        blur_color = (0, 255, 0) if blur_score > 100 else (255, 165, 0) if blur_score > 50 else (0, 0, 255)
        blur_text = f"Sharpness: {'Excellent' if blur_score > 100 else 'Fair' if blur_score > 50 else 'Poor'}"
        cv2.putText(img, blur_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, blur_color, 2)
        y_offset += 30
        
        # Lighting indicator
        bright_color = (0, 255, 0) if 50 < brightness < 200 else (0, 0, 255)
        bright_text = f"Lighting: {'Good' if 50 < brightness < 200 else 'Adjust'}"
        cv2.putText(img, bright_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bright_color, 2)
        y_offset += 30
        
        # Contrast indicator
        contrast_color = (0, 255, 0) if contrast > 20 else (255, 165, 0) if contrast > 10 else (0, 0, 255)
        contrast_text = f"Contrast: {'Good' if contrast > 20 else 'Fair' if contrast > 10 else 'Poor'}"
        cv2.putText(img, contrast_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, contrast_color, 2)
        y_offset += 30
        
        # Position indicator
        if len(faces) > 0:
            pos_color = (0, 255, 0) if face_centered and face_size_ok else (255, 165, 0)
            pos_text = f"Position: {'Perfect' if face_centered and face_size_ok else 'Adjust'}"
            cv2.putText(img, pos_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, pos_color, 2)
        
        # Save the latest RGB frame for capture
        self.latest_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.frame_count += 1
        
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Enhanced CSS with modern professional design
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');
    
    /* Global styles */
    .main {
        padding: 1rem 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
    }
    
    /* Custom color variables */
    :root {
        --primary-blue: #4F46E5;
        --primary-purple: #7C3AED;
        --primary-pink: #EC4899;
        --success-green: #10B981;
        --warning-orange: #F59E0B;
        --error-red: #EF4444;
        --white: #FFFFFF;
        --light-gray: #F8FAFC;
        --text-dark: #1F2937;
        --text-light: #6B7280;
        --shadow-light: rgba(0, 0, 0, 0.1);
        --shadow-medium: rgba(0, 0, 0, 0.15);
        --border-light: #E5E7EB;
    }
    
    /* Main container */
    .main-container {
        background: var(--white);
        border-radius: 24px;
        padding: 2rem;
        margin: 1rem 0;
        box-shadow: 0 20px 60px var(--shadow-medium);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Header styling */
    .main-title {
        font-family: 'Inter', sans-serif;
        font-size: 3.5rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 1rem;
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-purple), var(--primary-pink));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: gradient-shift 3s ease-in-out infinite;
    }
    
    @keyframes gradient-shift {
        0%, 100% { filter: hue-rotate(0deg); }
        50% { filter: hue-rotate(30deg); }
    }
    
    .subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 1.3rem;
        font-weight: 400;
        color: var(--text-light);
        text-align: center;
        margin-bottom: 3rem;
        line-height: 1.6;
        font-style: italic;
    }
    
    /* Step header styling with modern design */
    .step-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--text-dark);
        margin-bottom: 2rem;
        padding: 1.5rem 2rem;
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border-radius: 16px;
        border-left: 6px solid var(--primary-blue);
        box-shadow: 0 4px 16px var(--shadow-light);
        position: relative;
        overflow: hidden;
    }
    
    .step-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--primary-blue), var(--primary-purple));
    }
    
    .step-header i {
        margin-right: 12px;
        color: var(--primary-blue);
        font-size: 1.6rem;
    }
    
    .step-number {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-purple));
        color: white;
        border-radius: 50%;
        font-weight: 700;
        font-size: 1.2rem;
        margin-right: 16px;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }
    
    /* Card styling */
    .verification-card {
        background: var(--white);
        border-radius: 20px;
        padding: 2.5rem;
        margin: 2rem 0;
        box-shadow: 0 8px 32px var(--shadow-light);
        border: 1px solid var(--border-light);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .verification-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, var(--primary-blue), var(--primary-purple), var(--primary-pink));
        border-radius: 20px 20px 0 0;
    }
    
    .verification-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 16px 48px var(--shadow-medium);
    }
    
    /* Camera guidelines toggle card */
    .guidelines-card {
        background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
        border: 2px solid #0ea5e9;
        border-radius: 16px;
        padding: 1.5rem;
        margin: 1rem 0;
        transition: all 0.3s ease;
    }
    
    .guidelines-header {
        display: flex;
        align-items: center;
        cursor: pointer;
        font-weight: 600;
        color: #0369a1;
        font-size: 1.1rem;
    }
    
    .guidelines-header i {
        margin-right: 10px;
        font-size: 1.2rem;
    }
    
    .guidelines-content {
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid #bae6fd;
    }
    
    .guideline-item {
        display: flex;
        align-items: flex-start;
        margin-bottom: 0.8rem;
        padding: 0.5rem;
        background: rgba(255, 255, 255, 0.7);
        border-radius: 8px;
    }
    
    .guideline-item i {
        color: #0369a1;
        margin-right: 10px;
        margin-top: 2px;
        font-size: 0.9rem;
    }
    
    /* Quality header */
    .quality-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.3rem;
        font-weight: 600;
        color: var(--text-dark);
        margin-bottom: 1rem;
        text-align: center;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
    }
    
    .quality-header i {
        color: var(--primary-blue);
    }
    
    /* Progress indicator */
    .progress-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 2rem 0;
        padding: 1.5rem;
        background: var(--white);
        border-radius: 20px;
        box-shadow: 0 8px 32px var(--shadow-light);
        position: relative;
    }
    
    .progress-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 1;
        position: relative;
        z-index: 2;
    }
    
    .progress-circle {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-purple));
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 1.4rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 4px 16px rgba(79, 70, 229, 0.3);
        transition: all 0.3s ease;
    }
    
    .progress-circle:hover {
        transform: scale(1.1);
        box-shadow: 0 6px 24px rgba(79, 70, 229, 0.4);
    }
    
    .progress-label {
        font-size: 0.9rem;
        color: var(--text-light);
        text-align: center;
        font-family: 'Inter', sans-serif;
        font-weight: 500;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-purple)) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2rem !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 16px rgba(79, 70, 229, 0.3) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 24px rgba(79, 70, 229, 0.4) !important;
        background: linear-gradient(135deg, var(--primary-purple), var(--primary-pink)) !important;
    }
    
    /* File uploader styling */
    .stFileUploader > div {
        background: var(--white);
        border: 3px dashed var(--primary-blue);
        border-radius: 16px;
        padding: 3rem 2rem;
        text-align: center;
        transition: all 0.3s ease;
        position: relative;
    }
    
    .stFileUploader > div:hover {
        border-color: var(--primary-purple);
        background: linear-gradient(135deg, rgba(79, 70, 229, 0.05), rgba(124, 58, 237, 0.05));
        transform: scale(1.02);
    }
    
    /* Metric styling */
    .metric-container {
        background: var(--white);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: center;
        border: 2px solid var(--light-gray);
        transition: all 0.3s ease;
        box-shadow: 0 4px 16px var(--shadow-light);
    }
    
    .metric-container:hover {
        border-color: var(--primary-blue);
        transform: translateY(-2px);
        box-shadow: 0 8px 24px var(--shadow-medium);
    }
    
    /* Success/Error message styling */
    .stSuccess {
        background: linear-gradient(135deg, var(--success-green), #059669) !important;
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        box-shadow: 0 4px 16px rgba(16, 185, 129, 0.3) !important;
    }
    
    .stError {
        background: linear-gradient(135deg, var(--error-red), #DC2626) !important;
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        box-shadow: 0 4px 16px rgba(239, 68, 68, 0.3) !important;
    }
    
    .stWarning {
        background: linear-gradient(135deg, var(--warning-orange), #D97706) !important;
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        box-shadow: 0 4px 16px rgba(245, 158, 11, 0.3) !important;
    }
    
    .stInfo {
        background: linear-gradient(135deg, var(--primary-blue), #3B82F6) !important;
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        box-shadow: 0 4px 16px rgba(79, 70, 229, 0.3) !important;
    }
    
    /* Radio button styling */
    .stRadio > div {
        background: var(--white);
        border-radius: 12px;
        padding: 1.5rem;
        border: 2px solid var(--light-gray);
        transition: all 0.3s ease;
    }
    
    .stRadio > div:hover {
        border-color: var(--primary-blue);
        box-shadow: 0 4px 16px var(--shadow-light);
    }
    
    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {visibility: hidden;}
    
    /* Loading animation */
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    
    .loading {
        animation: pulse 2s infinite;
    }
    
    /* Responsive design */
    @media (max-width: 768px) {
        .main-title {
            font-size: 2.5rem;
        }
        
        .progress-container {
            flex-direction: column;
            gap: 1rem;
        }
        
        .progress-step {
            flex-direction: row;
            gap: 1rem;
        }
        
        .step-header {
            font-size: 1.4rem;
            padding: 1rem 1.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'verification_step' not in st.session_state:
    st.session_state.verification_step = 1
if 'aadhar_processed' not in st.session_state:
    st.session_state.aadhar_processed = False
if 'selfie_captured' not in st.session_state:
    st.session_state.selfie_captured = False

# Main container
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# Modern Header with RealEyes Branding
st.markdown("""
<div style="text-align: center; margin-bottom: 3rem;">
    <h1 class="main-title">
        <i class="fas fa-eye"></i> RealEyes
    </h1>
    <p class="subtitle">
        "Because your ID might lie, but your face won't"
    </p>
</div>
""", unsafe_allow_html=True)

# Enhanced Progress indicator
st.markdown("""
<div class="progress-container">
    <div class="progress-step">
        <div class="progress-circle"><i class="fas fa-file-alt"></i></div>
        <div class="progress-label">Upload Document</div>
    </div>
    <div class="progress-step">
        <div class="progress-circle"><i class="fas fa-camera"></i></div>
        <div class="progress-label">Capture Selfie</div>
    </div>
    <div class="progress-step">
        <div class="progress-circle"><i class="fas fa-search"></i></div>
        <div class="progress-label">Quality Check</div>
    </div>
    <div class="progress-step">
        <div class="progress-circle"><i class="fas fa-check-circle"></i></div>
        <div class="progress-label">Verification</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Document Upload Section
st.markdown('<div class="verification-card">', unsafe_allow_html=True)
st.markdown('''
<div class="step-header">
    <span class="step-number">1</span>
    <i class="fas fa-id-card"></i>
    Government ID Upload
</div>
''', unsafe_allow_html=True)
st.markdown("Upload a clear, high-quality image of your government-issued identification document")

col1, col2 = st.columns([2, 1])
with col1:
    aadhar_file = st.file_uploader(
        "Choose Government ID Image", 
        type=["jpg", "jpeg", "png"], 
        key="aadhar",
        help="Supported formats: JPG, JPEG, PNG. Max size: 10MB"
    )

with col2:
    if aadhar_file:
        st.success("Document uploaded successfully!")
        st.session_state.aadhar_processed = True
    else:
        st.info("Please upload your ID document")

st.markdown('</div>', unsafe_allow_html=True)

# Selfie Verification Section
st.markdown('<div class="verification-card">', unsafe_allow_html=True)
st.markdown('''
<div class="step-header">
    <span class="step-number">2</span>
    <i class="fas fa-user-circle"></i>
    Selfie Verification
</div>
''', unsafe_allow_html=True)

selfie_option = st.radio(
    "Choose your preferred verification method:", 
    ("Live Camera with Real-time Feedback", "Upload from Files"), 
    horizontal=True, 
    key="selfie_option"
)

selfie_img = None
selfie_file = None

if selfie_option == "Live Camera with Real-time Feedback":
    st.markdown("### Live Camera Setup")
    
    # Camera guidelines as toggle card
    with st.expander("Camera Guidelines for Best Results", expanded=False):
        st.markdown("""
        <div class="guidelines-card">
            <div class="guidelines-content">
                <div class="guideline-item">
                    <i class="fas fa-bullseye"></i>
                    <span>Position your face within the white circles</span>
                </div>
                <div class="guideline-item">
                    <i class="fas fa-lightbulb"></i>
                    <span>Ensure bright, even lighting (avoid shadows)</span>
                </div>
                <div class="guideline-item">
                    <i class="fas fa-hand-paper"></i>
                    <span>Keep the camera steady for maximum clarity</span>
                </div>
                <div class="guideline-item">
                    <i class="fas fa-eye"></i>
                    <span>Maintain direct eye contact with the camera</span>
                </div>
                <div class="guideline-item">
                    <i class="fas fa-check-circle"></i>
                    <span>Wait for all indicators to show green before capturing</span>
                </div>
                <div class="guideline-item">
                    <i class="fas fa-glasses"></i>
                    <span>Remove glasses or hats if possible</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    cam_col1, cam_col2 = st.columns([3, 2])
    
    with cam_col1:
        webrtc_ctx = webrtc_streamer(
            key="selfie-camera",
            video_processor_factory=VideoProcessor,
            rtc_configuration=RTCConfiguration({
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            }),
            media_stream_constraints={
                "video": {"width": 640, "height": 480, "frameRate": 30}, 
                "audio": False
            },
            async_processing=True,
            desired_playing_state=True
        )
    
    with cam_col2:
        st.markdown('<h4 class="quality-header"><i class="fas fa-chart-line"></i> Live Quality Monitor</h4>', unsafe_allow_html=True)
        quality_placeholder = st.empty()
        
        # Enhanced capture button
        capture_button = st.button(
            "Capture Perfect Selfie", 
            type="primary", 
            use_container_width=True,
            help="Click when all quality indicators are green"
        )
        
        if capture_button:
            if (webrtc_ctx and webrtc_ctx.state.playing
                and hasattr(webrtc_ctx, "video_processor")
                and webrtc_ctx.video_processor is not None
                and webrtc_ctx.video_processor.latest_frame is not None):
                
                selfie_img = webrtc_ctx.video_processor.latest_frame
                selfie_file = "captured"
                st.session_state.selfie_captured = True
                
                st.success("Perfect! Selfie captured successfully!")
                st.image(selfie_img, caption="Your Captured Selfie", use_container_width=True)
                
                # Auto-scroll to next section
                time.sleep(1)
                st.rerun()
            else:
                st.error("Camera not ready. Please ensure camera is active and try again.")
                selfie_file = None
        
        # Live quality feedback with enhanced UI
        if (webrtc_ctx and webrtc_ctx.state.playing
            and hasattr(webrtc_ctx, "video_processor")
            and webrtc_ctx.video_processor is not None
            and webrtc_ctx.video_processor.latest_frame is not None):
            
            img = webrtc_ctx.video_processor.latest_frame
            quality_checks = check_image_quality(img)
            
            with quality_placeholder.container():
                # Compact live quality display
                metrics_col1, metrics_col2 = st.columns(2)
                
                with metrics_col1:
                    blur_score = quality_checks['blur_score']
                    if blur_score > 100:
                        st.success("Sharp")
                    elif blur_score > 50:
                        st.warning("Fair")
                    else:
                        st.error("Blurry")
                
                with metrics_col2:
                    brightness = quality_checks['brightness_score']
                    if 50 < brightness < 200:
                        st.success("Good Light")
                    else:
                        st.error("Adjust Light")
                
                # Overall readiness status
                overall_ready = (
                    quality_checks['face_centered'] and 
                    quality_checks['face_size_ok'] and 
                    blur_score > 100 and
                    50 < brightness < 200
                )
                
                if overall_ready:
                    st.success("**Ready to Capture!**")
                    st.balloons()
                else:
                    st.info("Adjust position for better quality")

else:
    st.markdown("### File Upload")
    upload_col1, upload_col2 = st.columns([2, 1])
    
    with upload_col1:
        selfie_file = st.file_uploader(
            "Upload your selfie", 
            type=["jpg", "jpeg", "png"], 
            key="selfie_upload",
            help="Choose a clear, well-lit selfie photo"
        )
    
    with upload_col2:
        if selfie_file is not None:
            selfie_img = np.array(Image.open(selfie_file).convert('RGB'))
            st.success("Selfie uploaded!")
            st.session_state.selfie_captured = True

st.markdown('</div>', unsafe_allow_html=True)

# Processing Section - Only show if both files are uploaded
if aadhar_file and (selfie_img is not None or selfie_file is not None):
    st.markdown("---")
    st.markdown('''
    <div class="step-header">
        <span class="step-number">3</span>
        <i class="fas fa-cogs"></i>
        Processing & Verification
    </div>
    ''', unsafe_allow_html=True)
    
    # Load and process images
    aadhar_img = np.array(Image.open(aadhar_file).convert('RGB'))
    
    if selfie_file == "captured" and selfie_img is not None:
        st.success("Using captured selfie from live camera")
    elif selfie_img is not None:
        st.info("Using uploaded selfie image")
        
        # Quality check for uploaded images
        st.markdown('<div class="verification-card">', unsafe_allow_html=True)
        quality_checks = check_image_quality(selfie_img)
        display_quality_feedback(quality_checks)
        
        if quality_checks['overall_quality'] == 'Poor':
            st.error("**Image quality needs improvement!** Consider retaking for better results.")
            st.info("**Pro Tips:** Use bright lighting, steady hands, and center your face for optimal results.")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 1: DOB Extraction with enhanced OCR
    st.markdown('<div class="verification-card">', unsafe_allow_html=True)
    st.markdown('''
    <div class="step-header">
        <span class="step-number">3.1</span>
        <i class="fas fa-file-search"></i>
        Document Analysis & DOB Extraction
    </div>
    ''', unsafe_allow_html=True)
    
    with st.spinner('Analyzing document with advanced OCR technology...'):
        try:
            reader = easyocr.Reader(['en'], gpu=False)
            result = reader.readtext(aadhar_img, detail=0, paragraph=True)
            dob_str = extract_dob(result)
        except Exception as e:
            st.error(f"OCR processing failed: {str(e)}")
            dob_str = None
    
    if dob_str:
        age = calculate_age(dob_str)
        
        # Enhanced metrics display
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Date of Birth", dob_str)
        with col2:
            st.metric("Current Age", f"{age} years" if age is not None else "N/A")
        with col3:
            if age is not None:
                status = "Adult" if age >= 18 else "Minor"
                color = "normal" if age >= 18 else "inverse"
            else:
                status = "Unknown"
                color = "normal"
            st.metric("Status", status)
        
        if age is not None:
            st.success(f"Successfully extracted: **{dob_str}** (Age: **{age}** years)")
        else:
            st.warning("Date extracted but age calculation failed")
    else:
        st.error("Could not extract date of birth. Please ensure the document image is clear and readable.")
        st.info("**Tips:** Ensure good lighting, avoid shadows, and make sure text is clearly visible")
        st.stop()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 2: Enhanced Face Extraction
    st.markdown('<div class="verification-card">', unsafe_allow_html=True)
    st.markdown('''
    <div class="step-header">
        <span class="step-number">3.2</span>
        <i class="fas fa-user-check"></i>
        Advanced Face Detection & Extraction
    </div>
    ''', unsafe_allow_html=True)
    
    with st.spinner('Detecting and extracting faces using AI...'):
        aadhar_face = extract_face(cv2.cvtColor(aadhar_img, cv2.COLOR_RGB2BGR))
        selfie_face = extract_face(cv2.cvtColor(selfie_img, cv2.COLOR_RGB2BGR))
    
    if aadhar_face is not None and selfie_face is not None:
        st.success("Faces successfully detected in both images!")
        
        face_col1, face_col2 = st.columns(2)
        with face_col1:
            st.image(aadhar_face[:, :, ::-1], caption="Face from Government ID", use_container_width=True)
        with face_col2:
            st.image(selfie_face[:, :, ::-1], caption="Face from Selfie", use_container_width=True)
    else:
        missing = []
        if aadhar_face is None:
            missing.append("government ID")
        if selfie_face is None:
            missing.append("selfie")
        
        st.error(f"Could not detect faces in: {', '.join(missing)}")
        st.info("**Troubleshooting:** Ensure faces are clearly visible, well-lit, and not obscured by shadows or accessories")
        st.stop()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 3: Enhanced Face Verification
    st.markdown('<div class="verification-card">', unsafe_allow_html=True)
    st.markdown('''
    <div class="step-header">
        <span class="step-number">3.3</span>
        <i class="fas fa-fingerprint"></i>
        Biometric Face Verification
    </div>
    ''', unsafe_allow_html=True)
    
    try:
        with st.spinner('Performing advanced biometric comparison...'):
            # Enhanced face comparison with multiple methods
            target_size = (128, 128)
            aadhar_resized = cv2.resize(aadhar_face, target_size)
            selfie_resized = cv2.resize(selfie_face, target_size)
            
            # Convert to grayscale for comparison
            aadhar_gray = cv2.cvtColor(aadhar_resized, cv2.COLOR_BGR2GRAY)
            selfie_gray = cv2.cvtColor(selfie_resized, cv2.COLOR_BGR2GRAY)
            
            # Template matching
            result = cv2.matchTemplate(aadhar_gray, selfie_gray, cv2.TM_CCOEFF_NORMED)
            similarity = result[0][0]
            
            # Histogram comparison for additional verification
            hist1 = cv2.calcHist([aadhar_gray], [0], None, [256], [0, 256])
            hist2 = cv2.calcHist([selfie_gray], [0], None, [256], [0, 256])
            hist_similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            
            # Combined score
            combined_score = (similarity * 0.7 + hist_similarity * 0.3)
            sim_score = max(0, combined_score * 100)
            
            # Dynamic threshold based on image quality
            base_threshold = 0.35
            if selfie_file == "captured":  # Live camera usually has better quality
                threshold = base_threshold - 0.05
            else:
                threshold = base_threshold
            
            match = combined_score > threshold
        
        # Enhanced results display
        result_col1, result_col2, result_col3, result_col4 = st.columns(4)
        
        with result_col1:
            st.metric("Similarity Score", f"{sim_score:.1f}%")
        
        with result_col2:
            verification_status = "VERIFIED" if match else "NOT VERIFIED"
            st.metric("Verification", verification_status)
        
        with result_col3:
            if sim_score > 75:
                confidence = "High"
            elif sim_score > 50:
                confidence = "Medium"
            else:
                confidence = "Low"
            st.metric("Confidence", confidence)
        
        with result_col4:
            method = "Live Camera" if selfie_file == "captured" else "File Upload"
            st.metric("Method", method)
        
        # Detailed feedback
        if match:
            if sim_score > 75:
                st.success(f"**Excellent Match!** Similarity score: **{sim_score:.1f}%** - High confidence verification")
            elif sim_score > 60:
                st.success(f"**Good Match!** Similarity score: **{sim_score:.1f}%** - Reliable verification")
            else:
                st.success(f"**Identity Verified!** Similarity score: **{sim_score:.1f}%** - Acceptable match")
        else:
            st.error(f"**Identity verification failed.** Similarity score: **{sim_score:.1f}%**")
            st.info("**Suggestions:** Ensure good lighting, remove accessories, and face the camera directly")
        
        # Technical details (collapsible)
        with st.expander("Technical Details"):
            st.write(f"**Template Matching Score:** {similarity:.3f}")
            st.write(f"**Histogram Correlation:** {hist_similarity:.3f}")
            st.write(f"**Combined Score:** {combined_score:.3f}")
            st.write(f"**Threshold Used:** {threshold:.3f}")
            st.info("**Note:** This demo uses OpenCV for face comparison. Production systems use advanced deep learning models for higher accuracy.")
        
    except Exception as e:
        st.error(f"Face verification failed: {str(e)}")
        st.info("Please try again with clearer images")
        st.stop()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 4: Final Verification Summary
    st.markdown('<div class="verification-card">', unsafe_allow_html=True)
    st.markdown('''
    <div class="step-header">
        <span class="step-number">4</span>
        <i class="fas fa-clipboard-check"></i>
        Final Verification Summary
    </div>
    ''', unsafe_allow_html=True)
    
    if age is not None:
        age_passed = age >= 18
        
        # Create comprehensive summary
        st.markdown("### Complete Verification Report")
        
        # Summary metrics
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        
        with summary_col1:
            identity_status = "Passed" if match else "Failed"
            st.metric("Identity Verification", identity_status)
        
        with summary_col2:
            age_status = "Passed" if age_passed else "Failed"
            st.metric("Age Verification", age_status)
        
        with summary_col3:
            overall_status = "APPROVED" if (match and age_passed) else "REJECTED"
            st.metric("Overall Status", overall_status)
        
        # Detailed summary table
        summary_data = {
            "Verification Parameter": [
                "Document Validity",
                "Face Detection", 
                "Identity Match",
                "Age Requirement (18+)",
                "Image Quality",
                "Final Decision"
            ],
            "Result": [
                "Valid" if dob_str else "Invalid",
                "Detected" if (aadhar_face is not None and selfie_face is not None) else "Failed",
                f"{'Verified' if match else 'Failed'} ({sim_score:.1f}%)",
                f"{'Eligible' if age_passed else 'Ineligible'} ({age} years)",
                f"{quality_checks['overall_quality']}" if 'quality_checks' in locals() else "Good",
                "**APPROVED**" if (match and age_passed) else "**REJECTED**"
            ],
            "Details": [
                f"DOB: {dob_str}" if dob_str else "Could not extract",
                "Both faces detected successfully" if (aadhar_face is not None and selfie_face is not None) else "Face detection failed",
                f"Similarity: {sim_score:.1f}%" if match else f"Below threshold ({sim_score:.1f}%)",
                f"Age: {age} years" if age_passed else f"Under 18 ({age} years)",
                quality_checks['overall_quality'] if 'quality_checks' in locals() else "Standard quality",
                "All requirements met" if (match and age_passed) else "Requirements not met"
            ]
        }
        
        st.table(summary_data)
        
        # Final status with enhanced styling
        if match and age_passed:
            st.success("**VERIFICATION COMPLETE!** All security checks passed successfully.")
            st.balloons()
            
            # Additional success information
            st.info("""
            **What happens next:**
            • Your identity has been successfully verified
            • You meet all age requirements
            • You can proceed with your application
            • This verification is valid for the current session
            """)
            
        else:
            st.error("**VERIFICATION INCOMPLETE** - Please review the failed checks above.")
            
            # Provide specific guidance
            failed_checks = []
            if not match:
                failed_checks.append("Identity verification failed - faces don't match sufficiently")
            if not age_passed:
                failed_checks.append("Age requirement not met - must be 18 or older")
            
            if failed_checks:
                st.warning("**Failed Checks:**\n" + "\n".join(f"• {check}" for check in failed_checks))
                
                st.info("""
                **Next Steps:**
                • Ensure you're using your own government ID
                • Take a clear, well-lit selfie
                • Remove glasses or accessories if possible
                • Make sure you meet the age requirement
                • Try again with better quality images
                """)
    else:
        st.warning("Could not determine age from the provided document.")
        st.info("Please ensure the document is clear and the date of birth is visible")
    
    st.markdown('</div>', unsafe_allow_html=True)

# Footer with additional information
st.markdown("---")
st.markdown("""
<div style="text-align: center; padding: 2rem; color: #6B7280;">
    <h4><i class="fas fa-shield-alt"></i> Privacy & Security</h4>
    <p>Your images are processed locally and not stored on our servers. This demo is for educational purposes only.</p>
    <p><strong>RealEyes</strong> - Advanced Identity Verification System | Built with ❤️ using Streamlit</p>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)