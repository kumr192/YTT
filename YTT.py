import streamlit as st
import yt_dlp
import whisper
import os
import tempfile
import requests
import json
from pathlib import Path
import shutil
import time
import re
from urllib.parse import urlparse, parse_qs
from googletrans import Translator

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False

st.set_page_config(
    page_title="May The YouTube Transcript Be With You",
    layout="wide"
)

st.markdown("""
    <style>
    .main {
        background-color: black;
        color: #00FF41;
    }
    textarea {
        background-color: black !important;
        color: #00FF41 !important;
        font-family: 'Courier New', monospace !important;
        font-size: 16px !important;
        border: 1px solid #00FF41 !important;
        width: 100% !important;
    }
    .stTextInput > div > div > input {
        background-color: black !important;
        color: #00FF41 !important;
        font-family: 'Courier New', monospace;
        font-size: 16px;
    }
    </style>
""", unsafe_allow_html=True)

if 'transcript' not in st.session_state:
    st.session_state.transcript = ""
if 'video_title' not in st.session_state:
    st.session_state.video_title = ""
if 'translated' not in st.session_state:
    st.session_state.translated = ""

PERMANENT_AUDIO_DIR = os.path.join(os.getcwd(), "audio_cache")
os.makedirs(PERMANENT_AUDIO_DIR, exist_ok=True)

def extract_video_id(url):
    try:
        if 'youtu.be' in url:
            return url.split('/')[-1].split('?')[0]
        elif 'youtube.com' in url:
            parsed_url = urlparse(url)
            if parsed_url.path == '/watch':
                return parse_qs(parsed_url.query)['v'][0]
            elif parsed_url.path.startswith('/embed/'):
                return parsed_url.path.split('/')[2]
        return None
    except:
        return None

def get_youtube_transcript(url):
    if not TRANSCRIPT_API_AVAILABLE:
        return None, "YouTube Transcript API not available"
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return None, "Could not extract video ID"
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['en'])
            transcript_data = transcript.fetch()
            full_transcript = ' '.join([item['text'] for item in transcript_data])
            return full_transcript, "Success"
        except:
            for transcript in transcript_list:
                try:
                    transcript_data = transcript.fetch()
                    full_transcript = ' '.join([item['text'] for item in transcript_data])
                    return full_transcript, f"Success (Language: {transcript.language})"
                except:
                    continue
        return None, "No accessible transcripts found"
    except Exception as e:
        return None, f"Error accessing transcript: {str(e)}"

@st.cache_resource
def load_whisper_model():
    try:
        model = whisper.load_model("base")
        return model
    except Exception as e:
        st.error(f"Error loading Whisper model: {str(e)}")
        return None

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|：？]', "_", filename)

def download_youtube_audio(url):
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'noplaylist': True,
                'extract_flat': False,
                'writethumbnail': False,
                'writeinfojson': False,
                'ignoreerrors': False,
                'no_warnings': False,
                'extractaudio': True,
                'audioformat': 'wav',
                'audioquality': '192K',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'postprocessor_args': ['-ar', '16000']
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                ydl.download([url])
                for file_path in Path(temp_dir).glob('*.wav'):
                    safe_name = sanitize_filename(file_path.name)
                    permanent_path = Path(PERMANENT_AUDIO_DIR) / safe_name
                    shutil.copy(file_path, permanent_path)
                    return str(permanent_path), title
                for file_path in Path(temp_dir).glob('*'):
                    if file_path.suffix.lower() in ['.mp3', '.m4a', '.webm', '.ogg']:
                        safe_name = sanitize_filename(file_path.name)
                        permanent_path = Path(PERMANENT_AUDIO_DIR) / safe_name
                        shutil.copy(file_path, permanent_path)
                        return str(permanent_path), title
    except Exception as e:
        st.error(f"Error downloading video: {str(e)}")
        return None, None

def transcribe_audio(audio_path, model):
    try:
        result = model.transcribe(audio_path)
        os.remove(audio_path)
        return result["text"]
    except Exception as e:
        st.error(f"Error transcribing audio: {str(e)}")
        return None

st.title("May The YouTube Transcript Be With You")
col1, _ = st.columns([1, 1])

with col1:
    st.header("Video Processing")
    youtube_url = st.text_input("Enter YouTube URL:", placeholder="https://www.youtube.com/watch?v=...")
    if st.button("Process Video", type="primary"):
        if youtube_url:
            with st.spinner("Processing video..."):
                transcript = None
                if TRANSCRIPT_API_AVAILABLE:
                    transcript, status = get_youtube_transcript(youtube_url)
                    if transcript:
                        st.session_state.transcript = transcript
                    else:
                        audio_path, title = download_youtube_audio(youtube_url)
                        if audio_path and title:
                            model = load_whisper_model()
                            if model:
                                transcript = transcribe_audio(audio_path, model)
                                if transcript:
                                    st.session_state.transcript = transcript
        else:
            st.warning("Please enter a valid YouTube URL")

    if st.session_state.transcript:
        st.subheader("Transcript")
        st.text_area("", value=st.session_state.transcript, height=600, disabled=True)

        lang_choice = st.selectbox("Translate Transcript To:", ["None", "Spanish", "Hindi", "Tamil", "Telugu"])
        lang_codes = {
            "Spanish": "es",
            "Hindi": "hi",
            "Tamil": "ta",
            "Telugu": "te"
        }

        if lang_choice != "None":
            translator = Translator()
            translated = translator.translate(st.session_state.transcript, dest=lang_codes[lang_choice]).text
            st.subheader(f"Translated Transcript ({lang_choice})")
            st.text_area("", value=translated, height=600, disabled=True)
