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

# Fix SSL certificate issue for EasyOCR downloads (for some environments)
ssl._create_default_https_context = ssl._create_unverified_context

# Helper: Extract DOB from OCR text
def extract_dob(text_lines):
    dob_pattern = re.compile(r'(\d{2}[/-]\d{2}[/-]\d{4})')
    for line in text_lines:
        match = dob_pattern.search(line)
        if match:
            return match.group(1)
    return None

# Helper: Calculate age from DOB string
def calculate_age(dob_str):
    try:
        dob = datetime.strptime(dob_str.replace("-", "/"), "%d/%m/%Y")
        today = datetime.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except Exception:
        return None

# Helper: Extract face from image using OpenCV
def extract_face(img):
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.2, 5)
    for (x, y, w, h) in faces:
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
        'face_centered': False,
        'face_size_ok': False,
        'overall_quality': 'Poor'
    }
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    quality_checks['blur_score'] = blur_score
    brightness = np.mean(gray)
    quality_checks['brightness_score'] = brightness
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, 1.2, 5)
    if len(faces) > 0:
        (x, y, w, h) = max(faces, key=lambda face: face[2] * face[3])
        img_center_x = img.shape[1] // 2
        img_center_y = img.shape[0] // 2
        face_center_x = x + w // 2
        face_center_y = y + h // 2
        center_tolerance_x = img.shape[1] * 0.3
        center_tolerance_y = img.shape[0] * 0.3
        quality_checks['face_centered'] = (
            abs(face_center_x - img_center_x) < center_tolerance_x and
            abs(face_center_y - img_center_y) < center_tolerance_y
        )
        min_face_size = img.shape[1] * 0.2
        quality_checks['face_size_ok'] = w > min_face_size
    blur_ok = blur_score > 100
    brightness_ok = 50 < brightness < 200
    if (blur_ok and brightness_ok and quality_checks['face_centered'] and 
        quality_checks['face_size_ok']):
        quality_checks['overall_quality'] = 'Excellent'
    elif (blur_ok and brightness_ok and (quality_checks['face_centered'] or 
          quality_checks['face_size_ok'])):
        quality_checks['overall_quality'] = 'Good'
    elif blur_ok or brightness_ok:
        quality_checks['overall_quality'] = 'Fair'
    else:
        quality_checks['overall_quality'] = 'Poor'
    return quality_checks

def display_quality_feedback(quality_checks):
    st.markdown('<h4 class="step-header">📊 Quality Analysis Results</h4>', unsafe_allow_html=True)
    
    # Create metrics in a modern layout
    col1, col2, col3 = st.columns(3)
    
    with col1:
        blur_score = quality_checks['blur_score']
        if blur_score > 100:
            st.success("🔍 **Sharpness**\n\nExcellent")
        elif blur_score > 50:
            st.warning("🔍 **Sharpness**\n\nFair")
        else:
            st.error("🔍 **Sharpness**\n\nPoor")
        st.caption(f"Score: {blur_score:.1f}")
    
    with col2:
        brightness = quality_checks['brightness_score']
        if 50 < brightness < 200:
            st.success("💡 **Lighting**\n\nOptimal")
        elif brightness <= 50:
            st.error("💡 **Lighting**\n\nToo Dark")
        else:
            st.warning("💡 **Lighting**\n\nToo Bright")
        st.caption(f"Level: {brightness:.1f}")
    
    with col3:
        if quality_checks['face_centered'] and quality_checks['face_size_ok']:
            st.success("🎯 **Position**\n\nPerfect")
        elif quality_checks['face_centered']:
            st.warning("🎯 **Position**\n\nMove Closer")
        elif quality_checks['face_size_ok']:
            st.warning("🎯 **Position**\n\nCenter Face")
        else:
            st.error("🎯 **Position**\n\nAdjust")
    
    # Overall quality with modern styling
    quality = quality_checks['overall_quality']
    if quality == 'Excellent':
        st.success(f"🌟 **Overall Quality: {quality}** - Ready for verification!")
    elif quality == 'Good':
        st.success(f"✅ **Overall Quality: {quality}** - Good for processing")
    elif quality == 'Fair':
        st.warning(f"⚠️ **Overall Quality: {quality}** - Could be improved")
    else:
        st.error(f"❌ **Overall Quality: {quality}** - Please retake")
    
    # Improvement suggestions
    tips = []
    if quality_checks['blur_score'] <= 100:
        tips.append("🔍 **Focus:** Hold camera steady and ensure good focus")
    if quality_checks['brightness_score'] <= 50:
        tips.append("💡 **Lighting:** Move to a brighter area or add lighting")
    elif quality_checks['brightness_score'] >= 200:
        tips.append("🌤️ **Exposure:** Reduce lighting or move away from bright sources")
    if not quality_checks['face_centered']:
        tips.append("🎯 **Positioning:** Center your face in the frame")
    if not quality_checks['face_size_ok']:
        tips.append("📏 **Distance:** Move closer to the camera")
    
    if tips:
        st.info("💡 **Improvement Tips:**\n" + "\n".join(f"• {tip}" for tip in tips))

# VideoProcessor for webcam
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.latest_frame = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = np.mean(gray)
        faces = self.face_cascade.detectMultiScale(gray, 1.2, 5)
        face_centered = False
        face_size_ok = False
        if len(faces) > 0:
            (x, y, w, h) = max(faces, key=lambda face: face[2] * face[3])
            img_center_x = img.shape[1] // 2
            img_center_y = img.shape[0] // 2
            face_center_x = x + w // 2
            face_center_y = y + h // 2
            center_tolerance_x = img.shape[1] * 0.3
            center_tolerance_y = img.shape[0] * 0.3
            face_centered = (
                abs(face_center_x - img_center_x) < center_tolerance_x and
                abs(face_center_y - img_center_y) < center_tolerance_y
            )
            min_face_size = img.shape[1] * 0.2
            face_size_ok = w > min_face_size
            if face_centered and face_size_ok:
                color = (0, 255, 0)
                status = "Perfect!"
            elif face_centered or face_size_ok:
                color = (255, 165, 0)
                status = "Adjust position"
            else:
                color = (0, 0, 255)
                status = "Center your face"
            cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)
            cv2.putText(img, status, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        else:
            cv2.putText(img, "No face detected", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        center_x, center_y = img.shape[1] // 2, img.shape[0] // 2
        cv2.circle(img, (center_x, center_y), 5, (255, 255, 255), -1)
        cv2.circle(img, (center_x, center_y), 100, (255, 255, 255), 2)
        y_offset = 30
        blur_color = (0, 255, 0) if blur_score > 100 else (255, 165, 0) if blur_score > 50 else (0, 0, 255)
        blur_text = f"Sharpness: {'Good' if blur_score > 100 else 'Fair' if blur_score > 50 else 'Poor'}"
        cv2.putText(img, blur_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, blur_color, 2)
        y_offset += 30
        bright_color = (0, 255, 0) if 50 < brightness < 200 else (0, 0, 255)
        bright_text = f"Lighting: {'Good' if 50 < brightness < 200 else 'Adjust lighting'}"
        cv2.putText(img, bright_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bright_color, 2)
        y_offset += 30
        if len(faces) > 0:
            pos_color = (0, 255, 0) if face_centered and face_size_ok else (255, 165, 0)
            pos_text = f"Position: {'Perfect' if face_centered and face_size_ok else 'Adjust'}"
            cv2.putText(img, pos_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, pos_color, 2)
        # Save the latest RGB frame for capture
        self.latest_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Custom CSS for modern UI
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global styles */
    .main {
        padding: 1rem 2rem;
        background: #FFFFFF; /* Clean white background */
    }
    
    /* Custom color variables */
    :root {
        --primary-red: #F36C4A;
        --primary-blue: #215DF2;
        --primary-yellow: #FFC733;
        --white: #FFFFFF;
        --light-gray: #F8F9FA; /* Light background for subtle sections */
        --text-dark: #2C3E50; /* Dark text for headings */
        --text-light: #6C757D; /* Lighter text for body/subtitles */
    }
    
    /* Main title styling */
    .main-title {
        font-family: 'Inter', sans-serif;
        font-size: 2.5rem;
        font-weight: 700;
        color: var(--text-dark);
        text-align: center;
        margin-bottom: 1rem;
        background: linear-gradient(90deg, var(--primary-blue), var(--primary-red)); /* Gradient text */
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    /* Subtitle styling */
    .subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 1.1rem;
        font-weight: 400;
        color: var(--text-light);
        text-align: center;
        margin-bottom: 2rem;
        line-height: 1.6;
    }
    
    /* Card container */
    .card {
        background: var(--white);
        border-radius: 16px; /* More rounded corners */
        padding: 1.5rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08); /* Softer shadow */
        border: 1px solid #E9ECEF; /* Subtle border */
        margin-bottom: 1.5rem;
        transition: all 0.3s ease; /* Smooth transitions */
    }
    
    .card:hover {
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12); /* Enhanced shadow on hover */
        transform: translateY(-2px); /* Slight lift effect */
    }
    
    /* Step headers */
    .step-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.3rem;
        font-weight: 600;
        color: var(--text-dark);
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        # border-bottom: 2px solid var(--primary-blue); /* Blue underline */
        display: inline-block; /* Ensures underline only covers text */
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-red)) !important; /* Gradient button */
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.6rem 1.5rem !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(33, 93, 242, 0.3) !important; /* Soft shadow */
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(33, 93, 242, 0.4) !important; /* Enhanced shadow on hover */
    }
    
    /* Radio button styling */
    .stRadio > div {
        background: var(--white);
        border-radius: 10px;
        padding: 1rem;
        border: 2px solid #E9ECEF; /* Subtle border */
    }
    
    /* File uploader styling */
    .stFileUploader > div {
        background: var(--white);
        border: 2px dashed var(--primary-blue); /* Dashed blue border */
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        transition: all 0.3s ease;
    }
    
    .stFileUploader > div:hover {
        border-color: var(--primary-red); /* Red border on hover */
        background: rgba(243, 108, 74, 0.05); /* Light red background on hover */
    }
    
    /* Success/Error message styling */
    .stSuccess {
        background: linear-gradient(90deg, #10B981, #059669) !important; /* Green gradient */
        color: white !important;
        border-radius: 10px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    .stError {
        background: linear-gradient(90deg, var(--primary-red), #E53E3E) !important; /* Red gradient */
        color: white !important;
        border-radius: 10px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    .stWarning {
        background: linear-gradient(90deg, var(--primary-yellow), #F59E0B) !important; /* Yellow gradient */
        color: #1F2937 !important; /* Dark text for warning */
        border-radius: 10px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    .stInfo {
        background: linear-gradient(90deg, var(--primary-blue), #3B82F6) !important; /* Blue gradient */
        color: white !important;
        border-radius: 10px !important;
        border: none !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Quality metrics styling */
    .quality-metric {
        background: var(--white);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        border: 2px solid #E9ECEF;
        margin: 0.5rem 0;
        transition: all 0.3s ease;
    }
    
    .quality-metric:hover {
        border-color: var(--primary-blue);
        box-shadow: 0 4px 15px rgba(33, 93, 242, 0.1);
    }
    
    /* Sidebar styling */
    .css-1d391kg { /* Target Streamlit's sidebar class */
        background: linear-gradient(180deg, var(--white) 0%, var(--light-gray) 100%); /* Light gradient for sidebar */
    }
    
    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Progress indicator */
    .progress-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 2rem 0;
        padding: 1rem;
        background: var(--white);
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
    }
    
    .progress-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 1;
        position: relative;
    }
    
    .progress-circle {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: var(--primary-blue);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    
    .progress-label {
        font-size: 0.85rem;
        color: var(--text-light);
        text-align: center;
        font-family: 'Inter', sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# Modern Header with RealEyes Branding
st.markdown("""
<div style="text-align: center; margin-bottom: 2rem;">
    <h1 class="main-title">
        <span style="font-size: 2.8rem;"></span> RealEyes
    </h1>
    <p class="subtitle" style="font-style: italic; font-size: 1.2rem; color: #6C757D;">
        "Because your ID might lie, but your face won't"
    </p>
</div>
""", unsafe_allow_html=True)

# Progress indicator
st.markdown("""
<div class="progress-container">
    <div class="progress-step">
        <div class="progress-circle">1</div>
        <div class="progress-label">Upload Documents</div>
    </div>
    <div class="progress-step">
        <div class="progress-circle">2</div>
        <div class="progress-label">Quality Check</div>
    </div>
    <div class="progress-step">
        <div class="progress-circle">3</div>
        <div class="progress-label">Face Verification</div>
    </div>
    <div class="progress-step">
        <div class="progress-circle">4</div>
        <div class="progress-label">Age Verification</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Document Upload Section - Step 1: Aadhar Card
st.markdown('<h3 class="step-header"> Step 1: Any Government ID Upload</h3>', unsafe_allow_html=True)
st.markdown("Please upload a clear image of your Aadhar card for identity verification")
aadhar_file = st.file_uploader("Choose Aadhar Card Image", type=["jpg", "jpeg", "png"], key="aadhar")
st.markdown('</div>', unsafe_allow_html=True)

# Selfie Verification Section - Step 2
# st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<h3 class="step-header"> Step 2: Selfie Verification</h3>', unsafe_allow_html=True)
selfie_option = st.radio("Choose verification method:", 
                        (" Live Camera with Real-time Feedback", "Upload from Files"), 
                        horizontal=True, key="selfie_option")
selfie_img = None
selfie_file = None

if selfie_option == " Live Camera with Real-time Feedback":
    st.markdown("###  Live Camera Setup")
    st.info(" **Camera Guidelines:**\n"
            "• Position face within the white circle\n"
            "• Ensure bright, even lighting\n"
            "• Keep camera steady for clarity\n"
            "• Maintain direct eye contact\n"
            "• Capture when indicators show green")
    
    cam_col1, cam_col2 = st.columns([3, 2])
    
    with cam_col1:
        webrtc_ctx = webrtc_streamer(
            key="selfie-camera",
            video_processor_factory=VideoProcessor,
            rtc_configuration=RTCConfiguration({
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            }),
            media_stream_constraints={"video": {"width": 640, "height": 480}, "audio": False},
            async_processing=True,
            desired_playing_state=True
        )
    
    with cam_col2:
        st.markdown('<h4 class="step-header"> Live Quality Monitor</h4>', unsafe_allow_html=True)
        quality_placeholder = st.empty()
        
        # Capture button with custom styling
        if st.button(" Capture Perfect Selfie", type="primary", use_container_width=True):
            if (webrtc_ctx and webrtc_ctx.state.playing
                and hasattr(webrtc_ctx, "video_processor")
                and webrtc_ctx.video_processor is not None
                and webrtc_ctx.video_processor.latest_frame is not None):
                selfie_img = webrtc_ctx.video_processor.latest_frame
                selfie_file = "captured"
                st.success(" Perfect! Selfie captured successfully!")
                st.image(selfie_img, caption="Your Captured Selfie", use_container_width=True)
            else:
                st.error(" Camera not ready. Please ensure camera is active.")
                selfie_file = None
        
        # Live quality feedback
        if (webrtc_ctx and webrtc_ctx.state.playing
            and hasattr(webrtc_ctx, "video_processor")
            and webrtc_ctx.video_processor is not None
            and webrtc_ctx.video_processor.latest_frame is not None):
            img = webrtc_ctx.video_processor.latest_frame
            quality_checks = check_image_quality(img)
            
            # Compact quality display for live camera
            with quality_placeholder.container():
                metrics_col1, metrics_col2 = st.columns(2)
                with metrics_col1:
                    blur_score = quality_checks['blur_score']
                    if blur_score > 100:
                        st.success(" Sharp")
                    elif blur_score > 50:
                        st.warning(" Fair")
                    else:
                        st.error(" Blurry")
                
                with metrics_col2:
                    brightness = quality_checks['brightness_score']
                    if 50 < brightness < 200:
                        st.success(" Good Light")
                    else:
                        st.error(" Adjust Light")
                
                # Overall status
                if quality_checks['face_centered'] and quality_checks['face_size_ok'] and blur_score > 100:
                    st.success(" **Ready to Capture!**")
                else:
                    st.info(" Adjust position for better quality")
else:
    st.markdown("### 📁 File Upload")
    selfie_file = st.file_uploader("Upload your selfie", type=["jpg", "jpeg", "png"], key="selfie_upload", label_visibility="collapsed")
    if selfie_file is not None:
        selfie_img = np.array(Image.open(selfie_file).convert('RGB'))

st.markdown('</div>', unsafe_allow_html=True)

if aadhar_file and (selfie_img is not None or selfie_file is not None):
    # Processing Section
    st.markdown("---")
    st.markdown('<h2 class="step-header"> Processing & Verification</h2>', unsafe_allow_html=True)
    
    aadhar_img = np.array(Image.open(aadhar_file).convert('RGB'))
    
    if selfie_file == "captured" and selfie_img is not None:
        st.success(" Using captured selfie from live camera")
    elif selfie_img is not None:
        st.info(" Using uploaded selfie image")
        
        # Quality check for uploaded images
        # st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<h3 class="step-header"> Image Quality Analysis</h3>', unsafe_allow_html=True)
        quality_checks = check_image_quality(selfie_img)
        display_quality_feedback(quality_checks)
        
        if quality_checks['overall_quality'] == 'Poor':
            st.error(" **Image quality needs improvement!** Consider retaking for better results.")
            st.info("💡 **Pro Tips:** Use bright lighting, steady hands, and center your face for optimal results.")
        # st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 1: DOB Extraction
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<h3 class="step-header">1️⃣ Date of Birth Extraction</h3>', unsafe_allow_html=True)
    
    with st.spinner(' Analyzing Aadhar card with advanced OCR...'):
        reader = easyocr.Reader(['en'])
        result = reader.readtext(aadhar_img, detail=0)
        dob_str = extract_dob(result)
    
    if dob_str:
        age = calculate_age(dob_str)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Date of Birth", dob_str)
        with col2:
            st.metric(" Current Age", f"{age} years" if age is not None else "N/A")
        with col3:
            status = " Adult" if age and age >= 18 else " Minor"
            st.metric(" Status", status)
        st.success(f"Successfully extracted: **{dob_str}** (Age: **{age}** years)")
    else:
        st.error(" Could not extract date of birth. Please ensure the Aadhar card image is clear and readable.")
        st.stop()
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 2: Face Extraction
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<h3 class="step-header">2️⃣ Face Detection & Extraction</h3>', unsafe_allow_html=True)
    
    with st.spinner('👤 Detecting and extracting faces...'):
        aadhar_face = extract_face(cv2.cvtColor(aadhar_img, cv2.COLOR_RGB2BGR))
        selfie_face = extract_face(cv2.cvtColor(selfie_img, cv2.COLOR_RGB2BGR))
    
    if aadhar_face is not None and selfie_face is not None:
        st.success(" Faces successfully detected in both images!")
        
        face_col1, face_col2 = st.columns(2)
        with face_col1:
            st.image(aadhar_face[:, :, ::-1], caption="📄 Face from Aadhar Card", use_container_width=True)
        with face_col2:
            st.image(selfie_face[:, :, ::-1], caption="📸 Face from Selfie", use_container_width=True)
    else:
        st.error(" Could not detect faces in one or both images. Please ensure clear, well-lit photos with visible faces.")
        st.stop()
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 3: Face Verification
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<h3 class="step-header">3️⃣ Biometric Face Verification</h3>', unsafe_allow_html=True)
    
    try:
        with st.spinner('🔍 Performing biometric comparison...'):
            h1, w1 = aadhar_face.shape[:2]
            h2, w2 = selfie_face.shape[:2]
            target_size = (100, 100)
            aadhar_resized = cv2.resize(aadhar_face, target_size)
            selfie_resized = cv2.resize(selfie_face, target_size)
            aadhar_gray = cv2.cvtColor(aadhar_resized, cv2.COLOR_BGR2GRAY)
            selfie_gray = cv2.cvtColor(selfie_resized, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(aadhar_gray, selfie_gray, cv2.TM_CCOEFF_NORMED)
            similarity = result[0][0]
            sim_score = max(0, similarity * 100)
            match = similarity > 0.4
        
        # Results display
        result_col1, result_col2, result_col3 = st.columns(3)
        with result_col1:
            st.metric("Similarity Score", f"{sim_score:.1f}%")
        with result_col2:
            verification_status = " VERIFIED" if match else "NOT VERIFIED"
            st.metric(" Verification", verification_status)
        with result_col3:
            confidence = "High" if sim_score > 70 else "Medium" if sim_score > 40 else "Low"
            st.metric("📊 Confidence", confidence)
        
        if match:
            st.success(f" **Identity Verified!** Similarity score: **{sim_score:.1f}%**")
        else:
            st.error(f"❌ **Identity verification failed.** Similarity score: **{sim_score:.1f}%**")
        
        st.info("ℹ️ **Note:** This uses basic template matching. Production systems use advanced AI models for higher accuracy.")
    except Exception as e:
        st.error(f"❌ Face verification failed: {str(e)}")
        st.stop()
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 4: Final Age Verification
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<h3 class="step-header">4️⃣ Age Eligibility Check</h3>', unsafe_allow_html=True)
    
    if age is not None:
        if age >= 18:
            st.success(" **Age Verification Passed!** User is 18 years or older.")
        else:
            st.warning(" **Age Verification Failed.** User is under 18 years old.")
        
        # Final summary
        st.markdown("### 📋 Verification Summary")
        summary_data = {
            "Parameter": ["Identity Match", "Age Verification", "Document Validity", "Overall Status"],
            "Result": [
                "✅ Verified" if match else "❌ Failed",
                "✅ Passed" if age >= 18 else "❌ Failed", 
                "✅ Valid" if dob_str else "❌ Invalid",
                "✅ **APPROVED**" if (match and age >= 18) else "❌ **REJECTED**"
            ]
        }
        
        st.table(summary_data)
        
        if match and age >= 18:
            st.success(" **Verification Complete!** All checks passed successfully.")
        else:
            st.error(" **Verification Incomplete.** Please review failed checks above.")
    else:
        st.warning(" Could not determine age from the provided document.")
    
    st.markdown('</div>', unsafe_allow_html=True)
