# RealEyes: Face & Age Verification System

> **"Because your ID might lie, but your face won't"**

## What is this?
RealEyes is a Streamlit-based web application that performs age and identity verification using any government identification card. It compares a user's selfie to the extracted face from an ID image and verifies whether they match and meet the age criteria (18+). Built as part of a Zynga hackathon by Team CodeVita

Features:
- Upload a government ID
- Capture a live selfie using your webcam with real-time blur/light/centering feedback
- Extract DOB and ID photo using OCR (EasyOCR)
- Detect and compare faces using OpenCV and cosine similarity
- Display face match confidence score
- Calculate and verify if the person is 18+

---

## How To Run

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/realeyes-id-verification.git
cd realeyes-id-verification
```

### 2. Install Dependencies

- It's best to use a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate       # On Windows: venv\Scripts\activate
    ```
- Then:
    ```bash
    pip install -r requirements.txt
    ```

### 3. Start the App

```bash
streamlit run main.py
```

- Go to the shown URL (usually [http://localhost:8501](http://localhost:8501))

---

## How It Works

1. **Upload Aadhar Card:**  
   Upload a clear photo of a (sample/fake) Aadhar card.

2. **Selfie Verification:**  
   Use your live webcam or upload a file.  
   The app checks for blur, lighting, and face centering in real time.

3. **Face & Age Check:**  
   The app extracts your DOB, calculates age, and verifies the selfie against the document.

4. **Result:**  
   See a modern summary table and pass/fail feedback.
---
## 🎥 Demo Video
[![Watch the Demo](https://img.youtube.com/vi/PbGk8W_R8uI/0.jpg)](https://youtu.be/PbGk8W_R8uI?si=cO-Fsr4r1U79rf21)
> Click the image above to watch the RealEyes demo on YouTube!

---

## ⚡ Build an Executable 

You can create a **one-click executable** using [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --onefile --add-data ".streamlit:./.streamlit" main.py
```

- The binary will be in the `dist/` folder as `main` (Linux/Mac) or `main.exe` (Windows).
- To run:  
  ```bash
  ./dist/main
  ```

> **Note:** This will launch the Streamlit server, and users must still open the shown URL in a browser.  
> For a single-file GUI, look into [Streamlit Desktop](https://github.com/streamlit/streamlit-desktop) or [Eel](https://github.com/ChrisKnott/Eel).

---

## Credits

- [Streamlit](https://streamlit.io/)
- [EasyOCR](https://github.com/JaidedAI/EasyOCR)
- [OpenCV](https://opencv.org/)
- [streamlit-webrtc](https://github.com/whitphx/streamlit-webrtc)

---

##License

MIT License (see [LICENSE](LICENSE) file)
