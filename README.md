# CaptionNexus

CaptionNexus is a web application that uses artificial intelligence to generate descriptive captions for images. It leverages the Salesforce BLIP (Bootstrapping Language-Image Pre-training) model to understand visual content and translate it into natural language.

---

##  Features

- **AI Captioning**: Real-time image-to-text generation using Vision-Language models.
- **User Authentication**: Secure signup and login system to manage personal history.
- **Inference History**: Automatically saves your processed images and captions to a database.
- **Performance Metrics**: Displays confidence scores and processing latency for each caption.
- **Responsive Design**: A modern, dark-themed UI built with Tailwind CSS.

---

##  Tech Stack

- **Backend**: Flask (Python)
- **AI Engine**: PyTorch & Transformers (Salesforce BLIP-base)
- **Database**: MongoDB Atlas for scalable cloud storage
- **Frontend**: Responsive UI with Javascript & CSS
- **Concurrency**: ThreadPoolExecutor for asynchronous AI inference

---

##  Setup & Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/Somansh25/caption-nexus.git
   cd image-captioning
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your_secret_key
   MONGO_URI=your_mongodb_connection_string
   ```

4. **Run the Application**
   ```bash
   python app.py
   ```
   Access the app at `http://127.0.0.1:5000`

---
