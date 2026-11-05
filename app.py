# from exceptiongroup import catch
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash ,send_file,Response
from flask_mail import Mail, Message
import spacy
from dotenv import load_dotenv
import requests
import tempfile
from PyPDF2 import PdfReader  # or usec pdfplumber
import json
from pathlib import Path
import pytesseract
from fpdf import FPDF
import re, base64, os
from io import BytesIO
from PIL import Image
from collections import Counter
import xml.etree.ElementTree as ET
import uuid
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
# Verification Token Generator
from itsdangerous import URLSafeTimedSerializer
from openai import OpenAI
import tiktoken  #OpenAI-compatible models
import traceback
#   (New Google GenAI SDK syntax)
from google import genai
from google.genai import types

from flask_login import current_user, login_required , login_user ,UserMixin ,LoginManager
import platform
# from flask_migrate import Migrate
from sqlalchemy import func
from pdf2image import convert_from_path
from pytesseract import image_to_string
from docx.oxml.ns import qn
import nltk
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement, ns
import base64, io, re, cairosvg
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
nltk.download('punkt', quiet=True)
from nltk.tokenize import sent_tokenize
load_dotenv()    # Load variables from .env
groq_key = os.getenv("GROQ_API_KEY")
hf_key = os.getenv("HUGGINGFACE_API_KEY")
gpt_key = os.getenv("OPENAI_API_KEY")
gemini_key=os.getenv("GEMINI_API_KEY")
pixabay_key = os.getenv("PIXABAY_API_KEY")
# DB setup
app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY")
s = URLSafeTimedSerializer(app.secret_key)
basedir = os.path.abspath(os.path.dirname(__file__))
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url

# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')  # For Railway
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# migrate = Migrate(app, db)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Or your email provider
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'mapbuddy.app@gmail.com'
app.config['MAIL_PASSWORD'] = 'mxms jerm rnlr sapc'       # app password, not your Gmail password
app.config['MAIL_DEFAULT_SENDER'] = 'mapbuddy.app@gmail.com'
mail = Mail(app)  # Initialize Mail extension here

gemini_client = genai.Client(
    vertexai=True,
    project='my-project-8112-283009',
    location='global'
)

groq_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# gemini_client = genai.Client(
#     api_key=os.getenv("GEMINI_API_KEY")
# )
gpt_client = OpenAI(api_key=gpt_key)
HF_MODEL_LOCAL = "tiiuae/falcon-7b-instruct"
# Initialize the new SDK client instead of a 'GenerativeModel'
client = genai.Client()

# model = genai.GenerativeModel("gemini-2.0-flash")
# Create and initialize LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # your login route endpoint name

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    verified = db.Column(db.Boolean, default=False)
    download_count = db.Column(db.Integer, default=0)
    subscription_type = db.Column(db.String(20), default='free')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

MAX_DOWNLOADS = 3  # Free limit
# Create DB and tables if not exist
with app.app_context():
    db.create_all()

# Load heavy resources once
# tokenizer = AutoTokenizer.from_pretrained("sshleifer/distilbart-cnn-12-6")
nlp = spacy.load("en_core_web_sm")
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")  # Faster than bart-large-cnn
# summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# Routes
@app.route('/')
def home():
    return render_template('main_dashboard.html')
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
@app.route('/check-and-increment', methods=['POST'])
@login_required
def check_and_increment():
    if current_user.download_count >= MAX_DOWNLOADS:
        return jsonify({"allowed": False, "message": "You have reached your free limit of downloads/summaries"}), 403

    current_user.download_count += 1
    db.session.commit()
    return jsonify({"allowed": True, "count": current_user.download_count})


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email', '').strip().lower()
        password = request.form.get('password', '').strip()
        print(f"username_or_email {username_or_email}")
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        if user and user.check_password(password):
            if not user.verified:
                flash("Please verify your email before logging in.", "warning")
                return redirect(url_for('login'))

            login_user(user)  # <-- This logs the user in using Flask-Login
            # return redirect(url_for('guide'))
            return redirect(url_for('dashboard'))


        else:
            error = "Invalid username/email or password."

    return render_template('login.html', error=error)

# def login():
#     error = None
#
#     if request.method == 'POST':
#         username_or_email = request.form.get('username_or_email', '').strip()
#         password = request.form.get('password', '').strip()
#         user = User.query.filter(
#             (User.username == username_or_email) | (User.email == username_or_email)
#         ).first()
#         if user and user.check_password(password):
#             if not user.verified:
#                 flash("Please verify your email before logging in.", "warning")
#                 return redirect(url_for('login'))
#
#             session['user_id'] = user.id
#             session['username'] = user.username
#             return redirect(url_for('guide'))
#
#             # return redirect(url_for('dashboard'))
#         else:
#             error = "Invalid username/email or password."
#
#     return render_template('login.html', error=error)
@app.route('/dashboard')
def dashboard():
    # User is logged in, render dashboard
    return render_template('dashboard.html')
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        username = request.form['username'].strip().lower()
        name = request.form['name']
        password = request.form['password']
        if User.query.filter(func.lower(User.email) == email).first():
            flash("Email already registered.", "danger")
            return redirect(url_for('signup'))

        if User.query.filter(func.lower(User.username) == username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('signup'))

        # Create user without verifying yet
        new_user = User(name=name, email=email, username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        # Send verification email
        token = s.dumps(email, salt='email-confirm')
        verify_url = url_for('verify_email', token=token, _external=True)

        msg = Message('Confirm your Email for MapBuddy', recipients=[email])
        msg.body = f'Hi {name},\n\nClick the link to verify your email:\n{verify_url}\n\nThanks,\nMapBuddy Team'
        mail.send(msg)

        # ✅ Redirect to verify notice page
        return render_template('verify_notice.html', email=email)

    return render_template('signup.html')
@app.route('/guide')
@login_required
def guide():
    return render_template('guide.html')

@app.route('/verify_email/<token>')
def verify_email(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)  # 1 hour expiration
    except:
        flash('The verification link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if user:
        if user.verified:
            flash('Email already verified. Please log in.', 'info')
        else:
            user.verified = True
            db.session.commit()
            flash('Your email has been verified. You can now log in!', 'success')
    else:
        flash('User not found.', 'danger')

    return redirect(url_for('login'))
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()

        if user:
            token = s.dumps(user.email, salt='reset-password')
            reset_url = url_for('reset_password', token=token, _external=True)

            msg = Message('Reset Your Password for MapBuddy', recipients=[user.email])
            msg.body = f'Hi {user.name},\n\nClick the link to reset your password:\n{reset_url}\n⚠️ This link will expire in 1 hour.If you did not request this, please ignore this email. \n\nThanks,\nMapBuddy Team'

            mail.send(msg)

            flash("Password reset link sent to your email.", "info")
            return redirect(url_for('login'))
        else:
            flash("Email not found. Try again.", "danger")

    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = s.loads(token, salt='reset-password', max_age=3600)
    except Exception as e:
        flash("Invalid or expired token.", "danger")
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(request.url)

        user.set_password(password)
        db.session.commit()
        flash("Password updated successfully. Please login.", "success")
        return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/feedback')
def feedback():
    flash("Before you go, we’d love your feedback! Share your thoughts below.")
    return render_template('feedback.html')  #  feedback form page
@app.route('/intrest')
def intrest():
    flash("Thanks for your interest in MapBuddyAI! Our payment module is coming soon—stay tuned!")
    return render_template('intrest.html')
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')
@app.route('/privacy')
def privacy():
    return render_template('privacy.html')
@app.route('/terms')
def terms():
    return render_template('terms.html')
@app.route('/refund')
def refund():
    return render_template('refund.html')

HEADING_MAX_WORDS = 16
HEADING_MAX_CHARS = 120
from flask import redirect, url_for

# bullet / list patterns to *exclude* from heading detection
_BULLET_RE = re.compile(r'^[\u2022\-\*\u25CF\d]+\s')  # bullet chars, -, *, numbers
def convert_freeplane_to_cytoscape(xml_string):
    tree = ET.ElementTree(ET.fromstring(xml_string))
    root = tree.getroot()

    root_node = root.find('node')  # Find the first actual content node

    elements = []

    def add_node(node_element, parent_id=None, level=0):
        node_id = str(uuid.uuid4())
        label = node_element.attrib.get('TEXT', 'Unnamed')

        # Add the node with level info
        elements.append({
            "data": {
                "id": node_id,
                "label": label,
                "level": level
            },
            "classes": f"level-{level}"
        })

        # Add the edge if there's a parent
        if parent_id:
            elements.append({
                "data": {
                    "id": str(uuid.uuid4()),
                    "source": parent_id,
                    "target": node_id
                }
            })

        # Recursively process children
        for child in node_element.findall('node'):
            add_node(child, parent_id=node_id, level=level + 1)

    add_node(root_node)

    return {
        "elements": elements
    }



def group_sentences_token_budget(sentences, max_tokens=400):
    enc = tiktoken.get_encoding("cl100k_base")  # Common encoding used by OpenAI GPT-3.5 & GPT-4

    chunks = []
    current_chunk = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = len(enc.encode(sent))
        if current_tokens + sent_tokens > max_tokens and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sent]
            current_tokens = sent_tokens
        else:
            current_chunk.append(sent)
            current_tokens += sent_tokens

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

def coalesce_small_chunks(chunks, min_chars=80):
    merged = []
    buffer = ""

    for chunk in chunks:
        if len(buffer) + len(chunk) < min_chars:
            buffer += " " + chunk
        else:
            if buffer:
                merged.append(buffer.strip())
                buffer = ""
            merged.append(chunk)
    if buffer:
        merged.append(buffer.strip())
    return merged
def merge_points(points, target_nodes=3):
    """Split points into exactly target_nodes groups, preserving order."""
    n = len(points)
    if n <= target_nodes:
        return points  # no need to merge

    merged = []
    base_size = n // target_nodes
    remainder = n % target_nodes  # extra points to distribute

    start = 0
    for i in range(target_nodes):
        # distribute the remainder evenly among the first few chunks
        end = start + base_size + (1 if i < remainder else 0)
        merged.append(" ".join(points[start:end]))
        start = end

    return merged

def decide_group_size_by_length(line_count):
    if line_count < 20:
        return 2
    elif line_count < 40:
        return 3
    elif line_count < 60:
        return 5
    elif line_count < 80:
        return 7
    elif line_count < 120:
        return 10
    elif line_count < 150:
        return 15
    else:
        return 20

# def split_heading_body_pairs(text):
#     chunks = text
#     heading_body_pairs = []
#     current_heading = None
#     current_body = []
#
#     for chunk in chunks:
#         lines = chunk.strip().split("\n")
#         if len(lines) == 1 and len(lines[0].split()) < 10 and lines[0][0].isupper():
#             if current_heading and current_body:
#                 heading_body_pairs.append((current_heading, " ".join(current_body)))
#             current_heading = lines[0].strip()
#             current_body = []
#         else:
#             current_body.append(chunk.strip())
#     if current_heading and current_body:
#         heading_body_pairs.append((current_heading, " ".join(current_body)))
#
#     if not heading_body_pairs:  # fallback to dynamic headings
#         for chunk in chunks:
#             heading = generate_dynamic_heading(chunk)
#             heading_body_pairs.append((heading, chunk))
#     return heading_body_pairs


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    if _BULLET_RE.match(line):
        return False
    if len(line) > HEADING_MAX_CHARS:
        return False

    words = line.split()
    if len(words) > HEADING_MAX_WORDS:
        return False

    # Must begin with a letter
    if not words[0][0].isalpha():
        return False

    # Percent alphabetic (ignore punctuation)
    alpha_ratio = sum(ch.isalpha() for ch in line) / max(len(line), 1)
    if alpha_ratio < 0.5:
        return False

    # Heading style: ALL CAPS or Title Case
    is_all_caps = line.upper() == line and any(c.isalpha() for c in line)
    # crude Title Case check: most words capitalized
    cap_words = sum(1 for w in words if w[0].isupper())
    title_ratio = cap_words / len(words)
    is_title_case = title_ratio >= 0.6

    return is_all_caps or is_title_case

def summarize_with_gpt(text, max_tokens=300, temperature=0.3):
    try:
        response = gpt_client.chat.completions.create(
            model="gpt-3.5-turbo",  # or "gpt-4o", "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes text clearly and concisely."},
                {"role": "user", "content": f"Summarize the following text:\n\n{text}"}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"Error during GPT summarization: {e}")
        return ""

def summarize_with_hf(text):
    API_URL = "https://api-inference.huggingface.co/models/sshleifer/distilbart-cnn-12-6"
    headers = {"Authorization": f"Bearer {hf_key}"}
    payload = {
        "inputs": text,
        "parameters": {"max_length": 150, "min_length": 30, "do_sample": False}
    }

    response = requests.post(API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        summary = response.json()
        if isinstance(summary, list) and "summary_text" in summary[0]:
            return summary[0]["summary_text"]
        else:
            print("Unexpected response format:", summary)
    else:
        print("Error:", response.status_code, response.text)
    return ""
def summarize_with_gemini(text):
    try:
        prompt = f"""
Summarize the following content clearly and concisely:

{text}
"""

        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1000,
                thinking_config=types.ThinkingConfig(
                    thinking_level="MINIMAL"
                )
            )
        )

        return response.text.strip()

    except Exception as e:
        print(f"Gemini error: {e}")
        return None
def summarize_with_groq(text, format=None):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes text clearly and concisely."},
                {"role": "user", "content": f"Summarize the following text:\n\n{text}"}
            ],
            temperature=0.3,
            max_tokens=300
        )

        summary = response.choices[0].message.content.strip()

        # Remove leading phrase up to the first colon (optional cleanup)
        colon_pos = summary.find(":")
        if colon_pos != -1:
            summary = summary[colon_pos + 1:].strip()

        # Optional formatting
        if format == "bullet":
            summary = "\n- " + "\n- ".join([s.strip() for s in summary.split(". ") if s])
        elif format == "tag":
            summary = ", ".join([phrase.strip() for phrase in summary.split(".") if phrase])

        return summary

    except Exception as e:
        print(f"Error during summarization: {e}")
        return ""
def split_heading_body_pairs(chunks):
    heading_body_pairs = []
    current_heading = None
    current_body = []

    for i, chunk in enumerate(chunks):

        lines = chunk.strip().split("\n")

        if len(lines) == 1 and len(lines[0].split()) < 10 and lines[0][0].isupper():
            if current_heading and current_body:
                heading_body_pairs.append((current_heading, " ".join(current_body)))
            current_heading = lines[0].strip()
            current_body = []
        else:
            current_body.append(chunk.strip())
    # Append last collected heading & body
    if current_heading and current_body:
        heading_body_pairs.append((current_heading, " ".join(current_body)))

    # Fallback for no headings found (optional)
    if not heading_body_pairs:
        for chunk in chunks:
            heading = generate_dynamic_heading(chunk)
            heading_body_pairs.append((heading, chunk))

    return heading_body_pairs
def ocr_from_scanned_pdf(pdf_path):
    text = ""
    images = convert_from_path(pdf_path)
    for img in images:
        text += image_to_string(img) + "\n"
    return text
def extract_from_image(image_path):
    from PIL import Image
    from pytesseract import image_to_string
    img = Image.open(image_path)
    return image_to_string(img)
def extract_text_from_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text
def extract_and_clean_text_from_pdf(filepath):
    raw_text = extract_text_from_pdf(filepath)
    return clean_extracted_text(raw_text)
def clean_extracted_text(text):
    import re
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s+', '\n', text)
    text = re.sub(r'\f+', '', text)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if not line.strip():
            cleaned.append('')
            continue
        if re.match(r'^\s*\d+\s*$', line.strip()):
            continue
        if "Page" in line or "Confidential" in line:
            continue
        cleaned.append(line.strip())
    return '\n'.join(cleaned).strip()
from docx import Document

def extract_text_from_docx(file_stream):
    doc = Document(file_stream)
    full_text = []

    # 1. Main paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)

    # 2. Tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    full_text.append(cell.text)

    # 3. Inline shapes / text boxes
    for shape in doc.inline_shapes:
        try:
            text = shape.text_frame.text
            if text.strip():
                full_text.append(text)
        except AttributeError:
            pass  # Not all shapes have text_frame

    # 4. Headers and footers
    for section in doc.sections:
        header = section.header
        footer = section.footer
        for para in header.paragraphs:
            if para.text.strip():
                full_text.append(para.text)
        for para in footer.paragraphs:
            if para.text.strip():
                full_text.append(para.text)

    # 5. Optional: remove empty lines
    return '\n'.join([line for line in full_text if line.strip()])

# def extract_text_from_docx(file_stream):
#     doc = Document(file_stream)
#     return '\n'.join([para.text for para in doc.paragraphs])
def generate_dynamic_heading(text):
    doc = nlp(text)

    # Step 1: Extract relevant named entities (including scientific and technical types)
    relevant_labels = ['ORG', 'MONEY', 'PRODUCT', 'GPE', 'NORP', 'EVENT', 'WORK_OF_ART', 'LAW', 'LANGUAGE', 'PERSON']
    entities = [ent.text.strip() for ent in doc.ents if ent.label_ in relevant_labels]

    # Filter out single word entities, keep those with 2+ words or meaningful single words
    filtered_entities = [e for e in entities if len(e.split()) > 1 or len(e) > 3]

    if filtered_entities:
        # Return top 2 most common entities joined by ' | '
        counter = Counter(filtered_entities)
        common_entities = [item for item, count in counter.most_common(1)]
        return " | ".join(common_entities)

    # Step 2: Extract noun chunks and filter stop words, short chunks
    noun_phrases = [chunk.text.strip() for chunk in doc.noun_chunks
                    if chunk.root.pos_ == "NOUN"
                    and len(chunk.text.split()) > 1
                    and chunk.text.lower() not in nlp.Defaults.stop_words]

    # Rank noun phrases by frequency
    if noun_phrases:
        counter = Counter(noun_phrases)
        common_nouns = [item for item, count in counter.most_common(2)]
        return " | ".join(common_nouns)

    # Fallback
    return "Document Overview"


def group_sentences_into_chunks(sentences, group_size):
    return [' '.join(sentences[i:i + group_size]) for i in range(0, len(sentences), group_size)]

def refined_split_into_sentences(text):
    return [sent.text.strip() for sent in nlp(text).sents if sent.text.strip()]

def process_text_to_chunks(text, group_size):
    # Use double-newline for paragraph splitting if available
    if text.count('\n\n') >= 2:
        chunks = [chunk.strip() for chunk in text.strip().split('\n\n') if chunk.strip()]
    else:
        # Otherwise, split into sentences and group
        sentences = refined_split_into_sentences(text)
        chunks = group_sentences_into_chunks(sentences, group_size)
    return chunks

def safe_summarize_batch(chunks):
    summaries = []
    if not chunks:
        return summaries

    combined_text = "\n\n".join(chunks)

    summary_text = None

    # Try Groq first
    try:
        summary_text = summarize_with_groq(combined_text)
    except Exception as e:
        print(f"Groq summarization failed: {e}")

    # If Groq failed, try Gemini
    if not summary_text:
        try:
            print(f"Gemini summarization")
            summary_text = summarize_with_gemini(combined_text)
            print(f"summary_text {summary_text}")
        except Exception as e:
            print(f"Gemini summarization failed: {e}")

    # If Gemini also failed, try GPT
    if not summary_text:
        try:
            print("GPT summarization")
            summary_text = summarize_with_gpt(combined_text)
        except Exception as e:
            print(f"HF summarization failed: {e}")
            summary_text = ""  # Final fallback to avoid None

    # ✅ Split into short sentences (1 idea per child node)
    points = re.split(r'(?<=[.!?])\s+', summary_text)
    points = [p.strip() for p in points if len(p.split()) > 3]
    summaries.extend(points)

    return summaries

# def safe_summarize_batch(chunks):
#     summaries = []
#     if not chunks:
#         return summaries
#
#     # Combine all chunks into one input string
#     combined_text = "\n\n".join(chunks)
#
#     # summary_text = summarize_with_gpt(combined_text)
#     summary_text = summarize_with_groq(combined_text)
#     # summary_text=summarize_with_hf(combined_text)
#     # summary_text=summarize_with_gemini(combined_text)
#
#     # ✅ Split into short sentences (1 idea per child node)
#     points = re.split(r'(?<=[.!?])\s+', summary_text)
#     points = [p.strip() for p in points if len(p.split()) > 3]
#     summaries.extend(points)
#
#     return summaries
# def summarize_topic_with_gemini(topic):
#     try:
#         prompt = f"""
#         Summarize this topic into a hierarchical mind map with **only 2 levels**:
#         - Level 1: Main headings
#         - Level 2: Key points under each heading
#         Output in JSON format with: id, label, level, and children.
#         Topic/Text:
#         \"\"\"{topic}\"\"\"
#         """
#
#         response = model.generate_content(prompt)
#         raw = response.text.strip()
#
#         # ✅ Extract the first JSON block only (in case Gemini adds text)
#         match = re.search(r'\{.*\}', raw, re.DOTALL)
#         if not match:
#             print("❌ No JSON object found in response")
#             return None
#
#         mindmap_json = match.group(0)
#         mindmap = json.loads(mindmap_json)
#         print(f"AI creaed mindmap {mindmap}")
#         return mindmap
#
#     except json.JSONDecodeError as e:
#         print(f"❌ JSON decode error: {e}")
#         print("Raw response:", raw[:500])  # debug: show first 500 chars
#         return None
#     except Exception as e:
#         print(f"Gemini error: {e}")
#         return None

def create_mindmap_with_gemini(topic):
    try:
        prompt = f"""
You are a mind map generator.

Given the topic or text below, return ONLY a hierarchical mind map.

Strict rules:
- Output valid JSON only.
- Do not include markdown or explanations.
- The root node must have level 0.
- Level 0 = main topic, short.
- Level 1 = major subtopics, short keywords or phrases.
- Level 2 and deeper = more detailed descriptive sentences.
- Every node must contain exactly these fields:
  "id", "label", "level", "children"
- "children" must always be an array.
- IDs must be unique within the mind map.

Example structure:
{{
  "id": "root",
  "label": "Climate Change",
  "level": 0,
  "children": [
    {{
      "id": "causes",
      "label": "Causes",
      "level": 1,
      "children": [
        {{
          "id": "co2",
          "label": "Burning fossil fuels releases carbon dioxide, which traps heat in the atmosphere.",
          "level": 2,
          "children": []
        }}
      ]
    }}
  ]
}}

Topic/Text:
\"\"\"{topic}\"\"\"
"""

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=4000,
            thinking_config=types.ThinkingConfig(
                thinking_level="MINIMAL"
            )
        )

        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=config
        )

        print("Response object:", response)

        raw = response.text.strip()

        print("Response text:", repr(raw))

        # Gemini is instructed to return JSON directly,
        # so no regex extraction is required.
        mindmap = json.loads(raw)

        print(f"AI created mindmap: {mindmap}")

        return mindmap

    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        print("Raw response:", raw[:500] if 'raw' in locals() else "No response")
        return None

    except Exception as e:
        print(f"Gemini error: {e}")
        return None
# def create_mindmap_with_gemini(topic):
#     try:
#         prompt = f"""
# You are a mind map generator.
# Given the topic or text below, return ONLY a hierarchical mind map in pure JSON format.
#
# ⚠️ Strict rules:
# - Output valid JSON only.
# - No extra text, no explanations.
# - Each node must include: "id", "label", "level", and "children".
#
# Example:
# {{
#   "id": "root",
#   "label": "Main Topic",
#   "level": 0,
#   "children": [
#     {{
#       "id": "sub1",
#       "label": "Subtopic 1",
#       "level": 1,
#       "children": []
#     }}
#   ]
# }}
#
# Topic/Text:
# \"\"\"{topic}\"\"\"
# """
#         response = model.generate_content(prompt)
#         raw = response.text.strip()
#
#         # ✅ Extract the first JSON block only (in case Gemini adds text)
#         match = re.search(r'\{.*\}', raw, re.DOTALL)
#         if not match:
#             print("❌ No JSON object found in response")
#             return None
#
#         mindmap_json = match.group(0)
#         mindmap = json.loads(mindmap_json)
#         print(f"AI creaed mindmap {mindmap}")
#         return mindmap
#
#     except json.JSONDecodeError as e:
#         print(f"❌ JSON decode error: {e}")
#         print("Raw response:", raw[:500])  # debug: show first 500 chars
#         return None
#     except Exception as e:
#         print(f"Gemini error: {e}")
#         return None

def group_sentences_token_budget(sentences, max_tokens=4000):
    enc = tiktoken.get_encoding("cl100k_base")
    chunks = []
    current_chunk = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = len(enc.encode(sent))
        if current_tokens + sent_tokens > max_tokens and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sent]
            current_tokens = sent_tokens
        else:
            current_chunk.append(sent)
            current_tokens += sent_tokens

    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks
def clean_and_parse_groq_response(reply_text):
    try:
        # Extract JSON block from markdown-style response
        match = re.search(r'```\s*({.*?})\s*```', reply_text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Fallback: try to find JSON manually
            start = reply_text.find('{')
            end = reply_text.rfind('}') + 1
            json_str = reply_text[start:end]
        return json.loads(json_str)
    except Exception as e:
        raise ValueError(f"Groq JSON extraction error: {e}")
def generate_mindmap_json_from_gpt(text, model="gpt-3.5-turbo"):


    # Pefect one
    prompt = (
        "You are an AI assistant that converts educational text into a structured hierarchical mind map in JSON format.\n"
        "Your goals:\n"
        "- Identify clear sections or logical groupings (even if headings are missing).\n"
        "- Use appropriate section titles as parent node names.\n"
        "- Summarize content into meaningful, concise child nodes (avoid overly short or vague labels).\n"
        "- If there are any formulas, chemical equations, or word equations, place them under a dedicated child node titled "
        "'Chemical Equation' or 'Word Equation'.\n"
        "- Lists should be broken into multiple child nodes.\n\n"

        "Output should follow this JSON format:\n"
        "{\n"
        "  \"name\": \"Root Topic\",\n"
        "  \"children\": [\n"
        "    {\n"
        "      \"name\": \"Section Title\",\n"
        "      \"children\": [\n"
        "        { \"name\": \"Summary point 1\" },\n"
        "        { \"name\": \"Summary point 2\" }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"

        f"Here is the text:\n{text}"
    )

    # my working version
    # prompt = (
    #     "You are an AI assistant that converts educational text into hierarchical mind map JSON. "
    #     "Identify logical sections even if headings are not present. The root node should be the main topic, "
    #     " Clear section titles or headings"
    #     "If the text contains important equations or formulas (like chemical equations), include them as child nodes inside a section titled 'Word Equation' or 'Chemical Equation'.\n\n"
    #                 "Lists as multiple child nodes\n"
    #     "and child nodes should contain summarized points. Output JSON in this format:\n\n"
    #
    #     "{\n"
    #     "  \"name\": \"Root Topic\",\n"
    #     "  \"children\": [\n"
    #     "    {\n"
    #     "      \"name\": \"Section Title\",\n"
    #     "      \"children\": [\n"
    #     "        { \"name\": \"Summary point 1\" },\n"
    #     "        { \"name\": \"Summary point 2\" }\n"
    #     "      ]\n"
    #     "    }\n"
    #     "  ]\n"
    #     "}\n\n"
    #     f"Here is the text:\n{text}"
    # )

    try:
        response = gpt_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=3000
        )

        reply = response.choices[0].message.content

        mindmap_data = extract_json_from_text(reply)
        return mindmap_data

    except Exception as e:
        print("Error during LLM processing:", str(e))
        return None


def generate_mindmap_json_from_groq(text, model="llama3-70b-8192"):
    prompt = (
        "You are an AI assistant that converts educational text into hierarchical mind map JSON. "
        "Identify logical sections even if headings are not present. The root node should be the main topic, "
        "and child nodes should contain summarized points. Output JSON in this format:\n\n"
        "{\n"
        "  \"name\": \"Root Topic\",\n"
        "  \"children\": [\n"
        "    {\n"
        "      \"name\": \"Section Title\",\n"
        "      \"children\": [\n"
        "        { \"name\": \"Summary point 1\" },\n"
        "        { \"name\": \"Summary point 2\" }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Here is the text:\n{text}"
    )

    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=3000
        )
        reply = response.choices[0].message.content.strip()
        mindmap_data = clean_and_parse_groq_response(reply)
        return mindmap_data

    except Exception as e:
        print("Groq JSON generation error:", e)
        return None

def extract_json_from_text(text):
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        json_str = text[start:end]
        return json.loads(json_str)
    except Exception as e:
        print("Error parsing JSON:", str(e))
        return None


def decide_max_nodes(num_points, num_headings):
    """
    Dynamically decide how many nodes to keep per heading
    based on the total number of headings.
    """
    # Start with a base maximum
    base_max = 5

    # Scale down nodes if there are many headings
    scaled_max = max(1, int(base_max * 10 / num_headings))
    # Ensure we never return more nodes than actually exist
    return min(scaled_max, num_points)


def process_large_text_into_mindmap(full_text, max_tokens=4000):

    file_name = session.get("filename") or "Manual Input"
    session["filename"] = file_name
    fname = os.path.splitext(file_name)[0]

    # 1. Tokenize full text into sentences
    sentences = sent_tokenize(full_text)

    # 2. Chunk sentences into token-limited groups
    chunks = group_sentences_token_budget(sentences, max_tokens=max_tokens)
    merged_map = {
        "name": file_name,
        "children": []
    }

    for idx, chunk in enumerate(chunks, 1):
        # chunk_json = generate_mindmap_json_from_groq(chunk)
        chunk_json=generate_mindmap_json_from_gpt(chunk)
        if not chunk_json or 'children' not in chunk_json:
            continue
        merged_map["children"].extend(chunk_json["children"])


    return merged_map

def create_summary_structure(filename, heading_body_map):
    return {
        "name": filename,
        "children": [
            {
                "name": heading,
                "children": [
                    {"name": " ".join(points)}  # merge all points into one string
                ]
            }
            for heading, points in heading_body_map.items()
        ]
    }
def create_mindmap_structure(filename, heading_body_map):
    return {
        "name": filename,
        "children": [
            {
                "name": heading,
                "children": [{"name": point} for point in points]
            }
            for heading, points in heading_body_map.items()
        ]
    }
def convert_to_cytoscape_format(node, parent_id=None, elements=None, level=0):
    import uuid
    if elements is None:
        elements = []

    node_id = str(uuid.uuid4())

    # Use "label" (from Gemini JSON), fallback to "name" if ever needed
    label = node.get("label") or node.get("name", "Untitled")

    elements.append({
        "data": {
            "id": node_id,
            "label": label,
            "level": level
        },
        "classes": f"level-{level}"
    })

    if parent_id:
        edge_id = str(uuid.uuid4())
        elements.append({
            "data": {
                "id": edge_id,
                "source": parent_id,
                "target": node_id
            }
        })

    for child in node.get("children", []):
        convert_to_cytoscape_format(child, node_id, elements, level + 1)

    return {"elements": elements}

@app.route('/curriculum/topics', methods=['POST'])
def get_curriculum_topics():
    try:
        data = request.get_json(silent=True) or {}

        curriculum = data.get("curriculum", "").strip()
        grade = data.get("grade", "").strip()
        subject = data.get("subject", "").strip()

        print("\n================================")
        print("📚 CURRICULUM TOPICS REQUEST")
        print("Curriculum:", curriculum)
        print("Grade:", grade)
        print("Subject:", subject)
        print("================================")

        # -----------------------------------------
        # Load curriculum dynamically
        # -----------------------------------------

        curriculum_data = load_curriculum_json(
            curriculum,
            grade,
            subject
        )

        if not curriculum_data:
            return jsonify({
                "success": False,
                "error": "Curriculum could not be loaded.",
                "curriculum": curriculum,
                "grade": grade,
                "subject": subject
            }), 404

        # -----------------------------------------
        # Get topics from JSON
        # -----------------------------------------

        topics = curriculum_data.get("topics", {})

        result = []

        for topic_key, topic_data in topics.items():

            if isinstance(topic_data, dict):
                label = topic_data.get(
                    "display_name",
                    topic_key.replace("_", " ").title()
                )
            else:
                label = topic_key.replace("_", " ").title()

            result.append({
                "key": topic_key,
                "label": label
            })

        print("✅ Topics found:", len(result))

        return jsonify({
            "success": True,
            "curriculum": curriculum,
            "grade": grade,
            "subject": subject,
            "topics": result
        })

    except Exception as e:

        print("❌ Error loading curriculum topics:", str(e))

        return jsonify({
            "success": False,
            "error": "Failed to load curriculum topics."
        }), 500
@app.route('/extract_text_preview', methods=['POST'])
def extract_text_preview():
    session["filename"] = "Manual Input"
    if 'file' not in request.files:
        session["filename"] = "Manual Input"
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file name'}), 400

    filename = file.filename.lower()
    session["filename"] = filename  # Store it in the session

    try:
        if filename.endswith('.pdf'):
            filetype_detected = 'pdf'
            # Step 1: Save PDF to temp and CLOSE it
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                temp_path = temp_pdf.name
                file.save(temp_path)
            # Step 2: Now it's safe to read
            input_text = extract_and_clean_text_from_pdf(temp_path)

            #Step :3 check if the pdf has screenshort

            if not input_text.strip():
                print("⚠️ No text found in PDF, using OCR...")
                input_text = ocr_from_scanned_pdf(temp_path)
                input_text = clean_extracted_text(input_text)
            # Step 4: Remove file
            os.remove(temp_path)

        elif filename.endswith('.txt'):
            filetype_detected = 'txt'
            input_text = file.read().decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')

        elif filename.endswith('.docx'):
            filetype_detected = 'docx'
            input_text = extract_text_from_docx(file)

        elif filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_img:
                temp_path = temp_img.name
                file.save(temp_path)

            input_text = extract_from_image(temp_path)
            input_text = clean_extracted_text(input_text)  # Clean OCR text here
            os.remove(temp_path)

        else:
            return jsonify(
                {'error': 'Unsupported file type. Upload a .txt, .docx, .pdf, json or freeplane(.mm).'}), 400

        if not input_text.strip():
            return jsonify({'error': 'No readable text found in file.'}), 400

        # return jsonify({'preview': input_text.strip()})
        return jsonify({
            'preview': input_text.strip(),
            'filetype_detected': filetype_detected

        })

    except Exception as e:
        return jsonify({'error': f'Failed to extract text: {str(e)}'}), 500
@app.route('/create_map', methods=['POST'])
def create_map():
    data = request.get_json()
    action = data.get('action', 'generateMindmap')  # default fallback
    input_text = data['text'].strip()
    if not input_text:
        return jsonify({'error': 'Empty text provided'}), 400
    # structured_map=create_mindmap_with_gemini(input_text)
    structured_map=    generate_mindmap_json_from_gpt(input_text)

    print("Returned from Gemini:", structured_map)
    print("Type:", type(structured_map))

    fname=input_text
    structured_map["name"] = fname
    cytoscape_ready_map = convert_to_cytoscape_format(structured_map)
    session.pop('filename', None)
    if action == 'generateAI':
        print("🌳 Generating full mind map")
        return jsonify({
            "tree": structured_map,
            "cytoscape": cytoscape_ready_map
        })
    elif action == 'summarize':
        summary_json=summarize_with_gemini(input_text)
        print("🔹 Returning structured tree for full-screen view")
        # summary_mindmap_struct = create_summary_structure(fname, summary_json)

        return jsonify({"tree": summary_json})

    return None


@app.route('/process_preview_text', methods=['POST'])
def process_preview_text():
    data = request.get_json()
    action = data.get('action', 'generateMindmap')  # default fallback
    filetype = data.get('filetype', 'text')  # You can pass this from frontend

    if not data or 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400

    input_text = data['text'].strip()
    if not input_text:
        return jsonify({'error': 'Empty text provided'}), 400

    try:
            if filetype == 'pdf':
                # For PDF: process_large_text_into_mindmap returns hierarchical JSON directly
                structured_map = process_large_text_into_mindmap(input_text)
                # Use filename from session or fallback
                file_name = session.get("filename") or "Manual Input"
                # Clean filename for display (remove extension)
                fname = os.path.splitext(file_name)[0]
                # Replace root name with clean filename for consistency
                structured_map["name"] = fname

            else:
                # For normal text, create flat heading-body dict first
                final_mindmap = {}
                summary_mindmap = {}
                # Decide group size based online count
                line_count = input_text.count('\n')
                group_size = decide_group_size_by_length(line_count)
                input_text_chunk = process_text_to_chunks(input_text, group_size)
                heading_body_pairs = split_heading_body_pairs(input_text_chunk)
                num_headings = len(heading_body_pairs)
                for heading, body in heading_body_pairs:
                    sentences = refined_split_into_sentences(body)
                    chunks = group_sentences_token_budget(sentences, max_tokens=120)
                    summarized_chunks = safe_summarize_batch(chunks)

                    # --- NEW: join all summaries into one text per heading ---
                    joined_summary = " ".join(summarized_chunks)
                    refined_points = []
                    # Cleaning the summary
                    # Split the joined summary into sentences
                    points = re.split(r'(?<=[.!?])\s+', joined_summary)
                    # Remove very short sentences
                    refined_points = [p.strip() for p in points if len(p.split()) > 3]
                    if not refined_points:
                        refined_points = sentences[:5]
                    max_points = decide_max_nodes(len(refined_points), num_headings)

                    # Merge sentences into fewer nodes
                    refined_points_nodes = merge_points(refined_points, target_nodes=max_points)
                    final_mindmap[heading] = refined_points_nodes
                    summary_mindmap[heading] = refined_points

                file_name = session.get("filename") or "Manual Input"
                fname = os.path.splitext(file_name)[0]

                # Summary mindmap

                # Convert flat dict into hierarchical JSON
                structured_map = create_mindmap_structure(fname, final_mindmap)
                summary_mindmap_struct = create_summary_structure(fname, summary_mindmap)

            cytoscape_ready_map = convert_to_cytoscape_format(structured_map)
            session.pop('filename', None)
            if action == 'generateMindmap':
                print("🌳 Generating full mind map")
                return jsonify({
                    "tree": structured_map,
                    "cytoscape": cytoscape_ready_map
                })
            elif action == 'summarizeOnly':
                print("🔹 Returning structured tree for full-screen view")
                return jsonify({"tree": summary_mindmap_struct})

            return None

    except Exception as e:
            err_str = traceback.format_exc()
            print("Exception in /process_preview_text:")
            print(err_str)
            traceback.print_exc()
            return jsonify({'error': f'Failed to generate mind map: {str(e)}'}), 500


@app.route('/upload-json', methods=['POST'])
def upload_json():
    try:
        uploaded_file = request.files.get('file')
        filename = uploaded_file.filename.lower()

        if not uploaded_file or (not filename.endswith('.json') and not filename.endswith('.mm')):
            return jsonify({"status": "error", "message": "Please upload a valid JSON or Freeplane (.mm) file"}), 400

        # Handle Freeplane .mm files
        if filename.endswith('.mm'):
            xml_string = uploaded_file.read().decode('utf-8')
            cytoscape_ready_map = convert_freeplane_to_cytoscape(xml_string)
            structured_tree=xml_string
        # Handle JSON files
        else:
            structured_map = json.load(uploaded_file)
            cytoscape_ready_map = convert_to_cytoscape_format(structured_map)
            structured_tree =structured_map
        return jsonify({
            "status": "success",
            "tree": structured_tree,
            "cytoscape": cytoscape_ready_map
        })

    except json.JSONDecodeError:
        return jsonify({"status": "error", "message": "Invalid JSON format"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

#  DOC

def create_docx_from_nested_tree(node, doc=None, level=0):

    if doc is None:
        doc = Document()
        # Optional: Add title for the root node if level == 0
        if node.get('name'):
            doc.add_heading(node['name'], level=0)
        level = 1  # Start subheadings from level 1 for children

    # For all children, add heading + (optionally paragraph)
    for child in node.get('children', []):
        # Add heading (bold) with size decreasing by level (max 9)
        heading_level = min(level, 9)
        if child.get('name'):
            doc.add_heading(child['name'], level=heading_level)

        # Recursively add grandchildren
        create_docx_from_nested_tree(child, doc, level + 1)

    return doc


@app.route('/export-docx', methods=['POST'])
def export_docx():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No mind map data received"}), 400

    try:
        doc = create_docx_from_nested_tree(data)

        # Save doc to bytes buffer
        f = BytesIO()
        doc.save(f)
        f.seek(0)

        return send_file(
            f,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name='mindmap.docx'
        )
    except Exception as e:
        return jsonify({"error": f"Failed to generate DOCX: {str(e)}"}), 500
def normalize_math_latex_advanced(text: str) -> str:
    """
    Safely normalize mathematical notation.

    Gemini is responsible for generating MathJax notation.
    This function only performs minimal cleanup and does not
    modify currency or ordinary worksheet text.
    """

    if not text:
        return text

    text = text.strip()

    # ---------------------------------------------------------
    # Keep Gemini-generated MathJax intact.
    # Examples:
    #   \( \frac{3}{4} \)
    #   \( 5 \times 2 \)
    #   \( x \leq 10 \)
    #
    # Do NOT:
    #   - wrap the whole question
    #   - modify $
    #   - modify normal + - / = characters
    # ---------------------------------------------------------

    return text
# def normalize_math_latex_advanced(text: str) -> str:
#     """
#     Normalize math expressions into LaTeX/MathJax-friendly format for web.
#     Wraps valid LaTeX portions in $...$ for MathJax rendering.
#     """
#     # 1. Exponents
#     text = re.sub(r'(\w+)\^(\d+)', r'\1^{\2}', text)
#
#     # 2. Fractions
#     def frac_repl(match):
#         return f"\\frac{{{match.group(1)}}}{{{match.group(2)}}}"
#     text = re.sub(r'\(\s*([^)]+)\s*\)\s*/\s*\(\s*([^)]+)\s*\)', frac_repl, text)
#     text = re.sub(r'(?<!\\frac\{)(\d+)\s*/\s*(\d+)', frac_repl, text)
#
#     # 3. Roots
#     text = re.sub(r'sqrt\(([^)]+)\)', r'\\sqrt{\1}', text)
#     text = re.sub(r'root\((\d+),\s*([^)]+)\)', r'\\sqrt[\1]{\2}', text)
#
#     # 4. Inequalities & arrows
#     text = text.replace('<=', '\\leq ').replace('>=', '\\geq ').replace('!=', '\\neq ').replace('->', '\\to ')
#
#     # 5. Multiplication
#     text = re.sub(r'(\d+|\w)\s*\*\s*(\d+|\w)', r'\1 \\times \2', text)
#
#     # 6. Vectors
#     text = re.sub(r'vector\s+([A-Za-z]+)', r'\\vec{\1}', text)
#
#     # 7. Matrices
#     def matrix_repl(match):
#         rows = [r.strip() for r in match.group(1).split(';')]
#         latex_rows = [' & '.join(r.split(',')) for r in rows]
#         return '\\begin{bmatrix}' + ' \\\\ '.join(latex_rows) + '\\end{bmatrix}'
#     text = re.sub(r'\[([^\[\]]+;[^\[\]]+)\]', matrix_repl, text)
#
#     # 8. Greek letters
#     greek = ['alpha','beta','gamma','delta','epsilon','zeta','eta','theta','iota','kappa','lambda',
#              'mu','nu','xi','omicron','pi','rho','sigma','tau','upsilon','phi','chi','psi','omega']
#     for g in greek:
#         text = re.sub(rf'\b{g}\b', f'\\\\{g}', text)
#
#     # 9. Trig/log functions
#     funcs = ['sin','cos','tan','csc','sec','cot','log','ln','exp']
#     for f in funcs:
#         text = re.sub(rf'\b{f}\b', f'\\\\{f}', text)
#
#     # 10. Probability / set symbols
#     replacements = {
#         '∩': r'\cap', '∪': r'\cup', '∈': r'\in', '∉': r'\notin',
#         '⊂': r'\subset', '⊆': r'\subseteq', '⊃': r'\supset',
#         '⊇': r'\supseteq', '∅': r'\emptyset'
#     }
#     for k, v in replacements.items():
#         text = text.replace(k, v)
#
#     # 11. Clean spacing around operators
#     text = re.sub(r'\s*([+\-*/=<>])\s*', r' \1 ', text)
#
#     # 12. Escape underscores used for blanks
#     text = text.replace('__', r'\_\_')
#     text = re.sub(r'_(\s|$)', r'\\_\1', text)
#
#     # 13. Add space in mixed numbers like 2\frac{1}{2}
#     text = re.sub(r'(\d)\s*\\frac', r'\1\,\\frac', text)
#     text = re.sub(r'_{2,}', r'\\underline{\\qquad}', text)
#
#     # 14. Wrap valid math expressions in $...$
#     text = wrap_math_for_web(text)
#
#     return text

def fix_mathjax_latex(text):
    if not text:
        return text
    # collapse \\frac -> \frac, \\_ -> \_, etc.
    text = re.sub(r'\\\\(frac|sqrt|times|div|cdot|pi|_|\^)', r'\\\1', text)
    # replace double underscores with a blank line
    text = text.replace('__', r'\underline{\quad}')
    # fix mixed numbers spacing like 2\frac{1}{2}
    text = re.sub(r'(\d)\\frac', r'\1\,\\frac', text)
    return text

def wrap_math_for_web(text: str) -> str:
    """
    Gemini already returns MathJax-ready LaTeX
    using \\(...\\) and \\[...\\].

    Do not add mathematical delimiters here.
    """
    if not text:
        return text

    return text.strip()
# def wrap_math_for_web(text: str) -> str:
#     """
#     Wraps text in $...$ only if it contains true LaTeX math commands.
#     """
#     text = text.strip()
#
#     if (text.startswith("$") and text.endswith("$")) or (text.startswith("$$") and text.endswith("$$")):
#         return text
#
#     # Detect real math patterns only
#     if re.search(r'\\frac|\\sqrt|\\times|\\cap|\\cup|\\in|\\notin|\\subset|\\supset|\\leq|\\geq', text):
#         return f"${text}$"
#
#     return text



def wrap_math(text: str) -> str:
    text = text.strip()
    # Already wrapped?
    if text.startswith("$") and text.endswith("$"):
        return text

    # Detect numeric or simple math expressions
    # Examples: 3, 0.25, x+1, C(x)=200+15x
    math_pattern = r'^(\d+(\.\d+)?|[A-Za-z0-9\s\+\-\*/\^\(\)=]+)$'

    if re.fullmatch(math_pattern, text):
        return f"${text}$"  # inline math
    else:
        return text  # treat as plain text
def load_curriculum_json(curriculum, grade, subject):
        """
        Load curriculum JSON dynamically based on
        curriculum + grade + subject.
        """

        # -----------------------------------------
        # Curriculum folder
        # -----------------------------------------

        curriculum_key = curriculum.strip().lower()

        if "moe" in curriculum_key:
            curriculum_folder = "moe"

        elif "igcse" in curriculum_key:
            curriculum_folder = "igcse"

        else:
            print("❌ Unsupported curriculum:", curriculum)
            return None


        # -----------------------------------------
        # Subject folder
        # -----------------------------------------

        subject_key = subject.strip().lower()

        subject_map = {
            "math": "maths",
            "maths": "maths",
            "mathematics": "maths",

            "science": "science",

            "english": "english"
        }

        subject_folder = subject_map.get(subject_key)

        if not subject_folder:
            print("❌ Unsupported subject:", subject)
            return None


        # -----------------------------------------
        # Grade
        # -----------------------------------------

        grade_key = grade.strip().lower()

        if grade_key.startswith("primary"):
            grade_key = grade_key.replace("primary", "").strip()

        if grade_key.startswith("p"):
            grade_number = grade_key[1:]
        else:
            grade_number = grade_key

        # For now:
        grade_file = f"p{grade_number}.json"


        # -----------------------------------------
        # Build path
        # -----------------------------------------

        path = (
                Path(__file__).resolve().parent
                / "curriculum"
                / curriculum_folder
                / subject_folder
                / grade_file
        )

        print("\n📚 Curriculum JSON")
        print("Curriculum folder:", curriculum_folder)
        print("Subject folder:", subject_folder)
        print("Grade file:", grade_file)
        print("Full path:", path)


        # -----------------------------------------
        # Check file
        # -----------------------------------------

        if not path.exists():
            print("❌ Curriculum JSON NOT FOUND:", path)
            return None


        # -----------------------------------------
        # Load JSON
        # -----------------------------------------

        try:

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            print("✅ Curriculum JSON loaded successfully.")

            return data

        except Exception as e:

            print("❌ Error loading curriculum JSON:", e)

            return None

@app.route('/generate_worksheet_test', methods=['POST'])

def generate_worksheet_test():
    try:
        # ============================================================
        # LOAD TEST RESPONSE FROM PROJECT ROOT
        # ============================================================

        response_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "response.json"
        )

        print("\n================ TEST JSON RESPONSE ================")
        print("Loading file:", response_path)

        if not os.path.exists(response_path):
            return jsonify({
                "success": False,
                "error": "response.json was not found in the project root."
            }), 404

        with open(response_path, "r", encoding="utf-8") as file:
            worksheet_text = file.read()

        print(worksheet_text)
        print("====================================================\n")

        # ============================================================
        # CLEAN MARKDOWN CODE FENCES
        # ============================================================

        worksheet_text_clean = re.sub(
            r"^\s*```(?:json)?\s*|\s*```\s*$",
            "",
            worksheet_text.strip(),
            flags=re.IGNORECASE
        )

        # ============================================================
        # FIND JSON OBJECT
        # ============================================================

        match = re.search(
            r"\{.*\}",
            worksheet_text_clean,
            flags=re.DOTALL
        )

        if match:
            worksheet_text_clean = match.group(0)
        else:
            return jsonify({
                "success": False,
                "error": "No valid JSON structure found in the test response.",
                "raw_text": worksheet_text
            }), 500

        # ============================================================
        # REMOVE COMMENTS
        # ============================================================

        worksheet_text_clean = re.sub(
            r"//.*?$",
            "",
            worksheet_text_clean,
            flags=re.MULTILINE
        )

        worksheet_text_clean = re.sub(
            r"/\*.*?\*/",
            "",
            worksheet_text_clean,
            flags=re.DOTALL
        )

        # ============================================================
        # REMOVE TRAILING COMMAS
        # ============================================================

        worksheet_text_clean = re.sub(
            r",\s*([\]}])",
            r"\1",
            worksheet_text_clean
        )

        # ============================================================
        # LOAD / VALIDATE JSON
        # ============================================================

        try:
            worksheet_json = json.loads(worksheet_text_clean)

        except json.JSONDecodeError as e:
            print("JSON structural corruption error:", str(e))

            return jsonify({
                "success": False,
                "error": f"JSON structural corruption error: {str(e)}",
                "raw_text": worksheet_text_clean
            }), 500

        # ============================================================
        # SUCCESS
        # ============================================================

        print(
            "Successfully loaded test worksheet:",
            worksheet_json.get("header", "")
        )

        return jsonify({
            "success": True,
            "worksheet": worksheet_json
        })

    # ================================================================
    # GLOBAL ERROR HANDLING
    # ================================================================

    except Exception as e:
        print(traceback.format_exc())

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/generate_worksheet_Gemini', methods=['POST'])

def generate_worksheet_Gemini():
    try:
        # ============================================================
        # GET FORM FIELDS
        # ============================================================

        curriculum = request.form.get(
            'curriculum',
            ''
        )

        grade = request.form.get(
            'grade',
            ''
        )

        subject = request.form.get(
            'subject',
            ''
        )

        custom_subject = request.form.get(
            'customSubject',
            ''
        )

        topic_text = request.form.get(
            'textContent',
            ''
        ).strip()

        notes = request.form.get(
            'notes',
            ''
        )

        # ------------------------------------------------------------
        # Settings mode
        #
        # "ai"     = Let AI decide
        # "custom" = Customize myself
        # ------------------------------------------------------------

        settings_mode = request.form.get(
            'settingsMode',
            'ai'
        )

        practice_mode = request.form.get(
            'practiceMode',
            ''
        )

        # ------------------------------------------------------------
        # Question types
        #
        # JS sends these as separate FormData values:
        #
        # formData.append("questionTypes", input.value)
        #
        # Therefore getlist() is correct.
        # ------------------------------------------------------------

        question_types = request.form.getlist(
            'questionTypes' , "mix"
        )

        num_questions = request.form.get(
            'numQuestions',
            5
        )

        difficulty = request.form.get(
            "difficulty"
        ) or "Medium"

        exam_type = request.form.get(
            "examType"
        ) or "Worksheet"

        duration = request.form.get(
            'duration',
            ''
        )

        total_marks = request.form.get(
            'totalMarks',
            ''
        )

        # ============================================================
        # SUBTOPICS
        #
        # IMPORTANT:
        #
        # Your JS sends:
        #
        # formData.append(
        #     "subtopics",
        #     JSON.stringify(selectedSubtopics)
        # );
        #
        # Therefore request.form.getlist() is NOT correct.
        # ============================================================

        subtopics_raw = request.form.get(
            'subtopics',
            '[]'
        )

        try:
            subtopics = json.loads(
                subtopics_raw
            )
        except (
            json.JSONDecodeError,
            TypeError
        ):
            subtopics = []

        if not isinstance(
            subtopics,
            list
        ):
            subtopics = []

        # ============================================================
        # PRACTICE FOCUS
        #
        # Your JS sends:
        #
        # formData.append(
        #     "practiceFocus",
        #     JSON.stringify(selectedPracticeFocus)
        # );
        # ============================================================

        practice_focus_raw = request.form.get(
            'practiceFocus',
            '[]'
        )

        try:
            practice_focus = json.loads(
                practice_focus_raw
            )
        except (
            json.JSONDecodeError,
            TypeError
        ):
            practice_focus = []

        if not isinstance(
            practice_focus,
            list
        ):
            practice_focus = []

        # ============================================================
        # NORMALIZE SUBTOPICS
        #
        # Convert the objects received from JS into readable labels.
        #
        # Example:
        #
        # [
        #   {
        #       "label": "Equivalent Fractions",
        #       "ruleset_key": "fractions_equivalent",
        #       "question_type": "conceptual"
        #   }
        # ]
        #
        # becomes:
        #
        # "Equivalent Fractions"
        # ============================================================

        subtopics_for_prompt = []

        for item in subtopics:

            if isinstance(
                item,
                dict
            ):

                label = item.get(
                    "label",
                    ""
                )

                if label:
                    subtopics_for_prompt.append(
                        label
                    )

            elif isinstance(
                item,
                str
            ):

                if item.strip():
                    subtopics_for_prompt.append(
                        item.strip()
                    )

        subtopics_str = (
            ", ".join(
                subtopics_for_prompt
            )
            if subtopics_for_prompt
            else ""
        )

        # ============================================================
        # NORMALIZE PRACTICE FOCUS
        #
        # Example:
        #
        # [
        #     "Multi-step questions",
        #     "Visual / Timeline models"
        # ]
        #
        # becomes:
        #
        # "Multi-step questions, Visual / Timeline models"
        # ============================================================

        practice_focus_for_prompt = []

        for item in practice_focus:

            if isinstance(
                item,
                str
            ):

                if item.strip():
                    practice_focus_for_prompt.append(
                        item.strip()
                    )

            elif isinstance(
                item,
                dict
            ):

                label = item.get(
                    "label",
                    ""
                )

                if label:
                    practice_focus_for_prompt.append(
                        label
                    )

        practice_focus_str = (
            ", ".join(
                practice_focus_for_prompt
            )
            if practice_focus_for_prompt
            else ""
        )

        # ============================================================
        # DETERMINE FINAL SUBJECT
        # ============================================================

        final_subject = (
            custom_subject
            if custom_subject
            else subject
        )

        # ============================================================
        # HANDLE UPLOADED FILE
        # ============================================================

        input_text = topic_text

        file = request.files.get(
            "file"
        )

        if file:

            filename = file.filename.lower()

            try:

                # ----------------------------------------------------
                # PDF
                # ----------------------------------------------------

                if filename.endswith('.pdf'):

                    with tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix='.pdf'
                    ) as temp_pdf:

                        temp_path = temp_pdf.name

                        file.save(
                            temp_path
                        )

                    extracted = (
                        extract_and_clean_text_from_pdf(
                            temp_path
                        )
                    )

                    if not extracted.strip():

                        extracted = (
                            ocr_from_scanned_pdf(
                                temp_path
                            )
                        )

                        extracted = (
                            clean_extracted_text(
                                extracted
                            )
                        )

                    input_text += (
                        "\n" + extracted
                    )

                    os.remove(
                        temp_path
                    )

                # ----------------------------------------------------
                # TXT
                # ----------------------------------------------------

                elif filename.endswith('.txt'):

                    input_text += (
                        "\n"
                        + file.read()
                        .decode(
                            'utf-8'
                        )
                        .replace(
                            '\r\n',
                            '\n'
                        )
                    )

                # ----------------------------------------------------
                # DOCX
                # ----------------------------------------------------

                elif filename.endswith('.docx'):

                    input_text += (
                        "\n"
                        + extract_text_from_docx(
                            file
                        )
                    )

                # ----------------------------------------------------
                # IMAGE
                # ----------------------------------------------------

                elif filename.endswith(
                    (
                        '.png',
                        '.jpg',
                        '.jpeg'
                    )
                ):

                    with tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix='.png'
                    ) as temp_img:

                        temp_path = temp_img.name

                        file.save(
                            temp_path
                        )

                    input_text += (
                        "\n"
                        + extract_from_image(
                            temp_path
                        )
                    )

                    os.remove(
                        temp_path
                    )

            except Exception as e:

                return jsonify({
                    "success": False,
                    "error":
                        f"File processing error: {str(e)}"
                }), 400

        # ============================================================
        # ENSURE USER ENTERED SOMETHING
        # ============================================================

        if not input_text.strip():

            return jsonify({
                "success": False,
                "error":
                    "Please enter Topic/Notes or upload a file."
            }), 400

        # ============================================================
        # NUMBER OF QUESTIONS
        # ============================================================

        try:

            total_q = int(
                num_questions
            )

        except (
            ValueError,
            TypeError
        ):

            total_q = 5

        if total_q <= 0:
            total_q = 5

        # ============================================================
        # QUESTION TYPES
        # ============================================================

        qtypes_str = (
            ", ".join(
                question_types
            )
            if question_types
            else "Mix"
        )

        # ============================================================
        # EXAM INSTRUCTIONS
        # ============================================================

        exam_instructions = {

            "Worksheet": (
                "Provide mixed practice questions. "
                "Questions should reinforce learning and "
                "encourage self-study."
            ),

            "Test": (
                "Questions should be exam-style, formal, "
                "and cover a balanced range of topics. "
                "No hints. Require complete answers. "
                "Assign marks per question."
            ),

            "Homework": (
                "Provide practice questions students can "
                "solve at home. Include a mix of easy and "
                "medium difficulty."
            ),

            "Quiz": (
                "Keep it short and focused on quick "
                "recall/application. Mostly objective "
                "questions (MCQ, FIB, short answers)."
            )
        }

        # ============================================================
        # DIFFICULTY RULES
        # ============================================================

        difficulty_rules = {

            "Easy": (
                "Overall Baseline: EASY. Focus primarily on "
                "factual recall, foundational definitions, "
                "and straightforward procedures using simple "
                "grade-appropriate vocabulary."
            ),

            "Medium": (
                "Overall Baseline: MEDIUM. Focus on standard "
                "application, simple multi-step problems, "
                "conceptual understanding and clear explanations."
            ),

            "Hard": (
                "Overall Baseline: HARD. Focus on complex "
                "scenarios, non-routine application, reasoning, "
                "critical evaluation and multi-step problems."
            )
        }

        rules_to_send = difficulty_rules.get(
            difficulty,
            difficulty_rules["Medium"]
        )

        # ============================================================
        # LOAD CURRICULUM KNOWLEDGE
        # ============================================================

        curriculum_data = (
            load_curriculum_json(
                curriculum,
                grade,
                subject
            )        )

        if not curriculum_data:

            return jsonify({
                "success": False,
                "error":
                    " curriculum JSON "
                    "could not be loaded."
            }), 500

        # ============================================================
        # FIND RELEVANT TOPIC
        # ============================================================
        #
        # IMPORTANT:
        #
        # Previously:
        #
        # search_text = f"{topic_text} {subtopics}".lower()
        #
        # That would search the Python list/object representation.
        #
        # Now we use subtopics_str.
        # ============================================================

        topics = curriculum_data.get(
            "topics",
            {}
        )

        search_text = (
            f"{topic_text} {subtopics_str}"
        ).lower()

        matched_topic_key = None
        matched_topic_data = None

        for topic_key, topic_data in topics.items():

            display_name = topic_data.get(
                "display_name",
                ""
            ).lower()

            topic_key_lower = (
                topic_key.lower()
            )

            if (
                topic_key_lower in search_text
                or (
                    display_name
                    and display_name in search_text
                )
            ):

                matched_topic_key = topic_key

                matched_topic_data = (
                    topic_data
                )

                break

        # ============================================================
        # PREPARE CURRICULUM KNOWLEDGE
        # ============================================================

        if matched_topic_data:

            curriculum_knowledge = json.dumps(
                {
                    matched_topic_key:
                        matched_topic_data
                },
                indent=2,
                ensure_ascii=False
            )

            print(
                f"Matched curriculum topic: "
                f"{matched_topic_key}"
            )

        else:

            curriculum_knowledge = json.dumps(
                curriculum_data,
                indent=2,
                ensure_ascii=False
            )

            print(
                "No specific topic matched. "
                "Sending complete curriculum JSON."
            )

        # ============================================================
        # PROMPT VALUES
        # ============================================================

        selected_subtopics_text = (
            subtopics_str
            if subtopics_str
            else "None selected"
        )

        selected_practice_focus_text = (
            practice_focus_str
            if practice_focus_str
            else "None selected"
        )

        # ============================================================
        # BUILD LLM PROMPT
        # ============================================================

        prompt = f"""
You are an expert AI Curriculum Designer and Professional Teacher's Assistant.

Your task is to generate a high-quality {exam_type} for the student.

The most important requirement is that the generated questions must
respect the supplied curriculum knowledge base.

============================================================
[CORE TARGET DATA]
============================================================

Curriculum:
{curriculum}

Grade:
{grade}

Subject:
{final_subject}

Primary Reference Material / User Topic:
{input_text}

Target Subtopics:
{selected_subtopics_text}

Additional Teacher Requests:
{notes if notes else "None"}

Allowed Question Types:
{qtypes_str}

Total Number of Questions:
{total_q}

Target Difficulty:
{difficulty}

Duration:
{duration if duration else "Not specified"}

Total Marks:
{total_marks if total_marks else "Not specified"}


============================================================
[PRACTICE MODE]
============================================================

Practice Mode:
{practice_mode if practice_mode else "Not specified"}

Use the selected Practice Mode as additional context
when designing the worksheet.


============================================================
[SETTINGS MODE]
============================================================

Settings Mode:
{settings_mode}

If Settings Mode is "ai":

Use sensible educational defaults appropriate for the
selected curriculum, grade, subject and topic.

If Settings Mode is "custom":

Respect the explicitly supplied settings.


============================================================
[SELECTED SUBTOPICS]
============================================================

{selected_subtopics_text}

The selected subtopics represent the specific areas
the student wants to practise.

If subtopics are selected:

- Match questions to the selected subtopics.
- Ensure the questions actually assess those concepts.
- Do not replace selected subtopics with unrelated concepts.
- Closely related selected subtopics may be combined
  when appropriate.
- Do not introduce unrelated curriculum areas.


============================================================
[PRACTICE FOCUS]
============================================================

{selected_practice_focus_text}

Practice Focus describes HOW the student's understanding
should be tested.

If Practice Focus values are supplied:

- Use them to guide question design.
- Make the selected focus meaningful in the questions.
- Ensure the focus affects the way the concept is tested.
- Do not introduce a practice focus that was not selected.

For example:

If the Practice Focus includes "Multi-step questions":

Include suitable multi-step problems where appropriate
for the selected grade and curriculum.

If the Practice Focus includes "Visual / Timeline models":

Use appropriate visual, model-based or timeline reasoning
where suitable for the topic.

If no Practice Focus is selected:

Use the curriculum, topic and grade to determine suitable
question-design approaches.


============================================================
[CURRICULUM KNOWLEDGE BASE]
============================================================

The following information comes from the application's
curriculum knowledge base.

This knowledge base defines the intended curriculum scope,
rules, heuristics, vocabulary and solution approach.

CURRICULUM KNOWLEDGE:

{curriculum_knowledge}


============================================================
[HOW TO USE THE CURRICULUM KNOWLEDGE]
============================================================

You MUST use the supplied curriculum knowledge when designing
the questions.

1. CURRICULUM SCOPE

Do not introduce concepts that are outside the supplied
curriculum knowledge for this grade and topic.

2. CURRICULUM RULES

Treat explicit rules in the curriculum knowledge as HARD
generation constraints.

For example, if the curriculum states that certain numbers,
operations, denominators, units or representations must be
used or avoided, follow those restrictions.

Do NOT override an explicit curriculum rule merely because
a more advanced question would be possible.

3. HEURISTICS

Use the supplied heuristics as question-design patterns.

The heuristics describe appropriate ways of testing the
student's understanding.

Do not copy an example or mechanically repeat the same pattern.

Create new questions using the underlying idea.

4. VOCABULARY

Prefer the vocabulary supplied by the curriculum knowledge
when it is appropriate.

Use language suitable for the selected grade.

5. SOLUTION METHOD

Use the supplied solution_steps as guidance for the answer key.

The step-by-step solution must demonstrate the appropriate
method for this grade and topic.

6. PROGRESSION

Create a sensible progression from simpler understanding
towards application and reasoning.

Do NOT impose a universal percentage such as 30% easy,
40% medium and 30% hard.

The curriculum knowledge and requested difficulty should
determine the appropriate progression.

7. ORIGINALITY

Generate completely new questions.

Do not reproduce questions from the curriculum knowledge
verbatim.

Do not invent past-paper questions or claim that a generated
question is an official examination question.


============================================================
[DIFFICULTY]
============================================================

{rules_to_send}


============================================================
[EXAM FORMAT]
============================================================

{exam_instructions.get(
    exam_type,
    "Use a standard educational worksheet format."
)}


============================================================
[QUESTION DESIGN]
============================================================

Design the questions so that they:

- Match the selected grade.
- Match the selected curriculum.
- Match the selected topic.
- Match the selected subtopics when provided.
- Respect the selected Practice Focus when provided.
- Follow the curriculum rules.
- Use the curriculum heuristics.
- Use appropriate grade-level vocabulary.
- Test genuine understanding rather than random variation.
- Progress naturally in complexity.
- Avoid concepts that have not been introduced within the
  supplied curriculum scope.
- Have clear and unambiguous wording.


============================================================
[MULTIPLE CHOICE RULES]
============================================================

For MCQ questions:

- Provide exactly four options.
- There must be exactly one correct answer.
- Every distractor must represent a realistic student mistake.
- Do not create obviously silly or impossible distractors.
- Distractors should relate to the actual calculation,
  reasoning or misconception involved.


============================================================
[QUALITY CONTROL]
============================================================

Before producing the final JSON, internally verify:

- Every question is within curriculum scope.
- Every question matches the selected topic.
- Every question matches the selected subtopics when provided.
- Every question respects the selected Practice Focus when provided.
- Every calculation is correct.
- Every MCQ has exactly one correct answer.
- Every answer matches the question.
- Every step-by-step solution reaches the stated answer.
- No contradictory information exists.
- No unsupported advanced concepts have been introduced.
- The number of questions exactly equals {total_q}.


============================================================
[OUTPUT FORMAT]
============================================================

Return ONLY one valid JSON object.

Do not include markdown.
Do not include ```json.
Do not include explanations outside the JSON.

Use exactly this structure:

{{
    "header": "{exam_type} Title and Clear Student Instructions",

    "questions": [
        {{
            "id": "Q1",
            "text": "The precise question text",
            "type": "MCQ/FIB/Short Answer",
            "options": [
                "Option A",
                "Option B",
                "Option C",
                "Option D"
            ],
            "distractor_analysis": {{
                "Option A": "Explain the student misconception.",
                "Option B": "Explain the student misconception.",
                "Option C": "Explain the student misconception.",
                "Option D": "Explain the student misconception."
            }}
        }}
    ],

    "answer_key": [
        {{
            "id": "Q1",
            "answer": "The exact correct answer",
            "step_by_step_solution": "Clear step-by-step solution appropriate for the grade."
        }}
    ]
}}

Important:
MATHEMATICAL NOTATION:
- Return valid JSON only.
- Do NOT use LaTeX.
- Do NOT use MathJax delimiters such as $, $$, \(, \), \[, or \].
- Use ordinary text symbols for mathematics.
- Use × for multiplication.
- Use ÷ for division.
- Use ≤ and ≥ for inequalities.
- Write fractions as words or simple forms such as 3/4.
- Currency must use the normal $ symbol, e.g. $2.80, $10.00.
- Never use $ as a mathematical delimiter.
If the question type is not MCQ, the options array may be empty
and distractor_analysis may be an empty object.

The final response MUST be valid JSON.
"""

        # ============================================================
        # DEBUG
        # ============================================================

        print(
            "\n================ WORKSHEET INPUT ================"
        )

        print(
            "Curriculum:",
            curriculum
        )

        print(
            "Grade:",
            grade
        )

        print(
            "Subject:",
            final_subject
        )

        print(
            "Topic:",
            topic_text
        )

        print(
            "Subtopics:",
            subtopics
        )

        print(
            "Practice Focus:",
            practice_focus
        )

        print(
            "Practice Mode:",
            practice_mode
        )

        print(
            "Settings Mode:",
            settings_mode
        )

        print(
            "Question Types:",
            question_types
        )

        print(
            "Number of Questions:",
            total_q
        )

        print(
            "Difficulty:",
            difficulty
        )

        print(
            "Exam Type:",
            exam_type
        )

        print(
            "Duration:",
            duration
        )

        print(
            "Total Marks:",
            total_marks
        )

        print(
            "================================================\n"
        )

        # ============================================================
        # EXECUTE GEMINI
        # ============================================================

        config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8192,
            response_mime_type="application/json"
        )

        gemini_client = genai.Client(
            vertexai=True,
            project='my-project-8112-283009',
            location='us-central1'
        )

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )

        # ============================================================
        # EXTRACT GEMINI RESPONSE
        # ============================================================

        worksheet_text = response.text

        print(
            "\n================ GEMINI RAW RESPONSE ================"
        )

        print(
            worksheet_text
        )

        print(
            "======================================================\n"
        )

        # ============================================================
        # CLEAN MARKDOWN CODE FENCES
        # ============================================================

        worksheet_text_clean = re.sub(
            r"^```json\s*|\s*```$",
            "",
            worksheet_text.strip(),
            flags=re.MULTILINE
        )

        # ============================================================
        # FIND JSON OBJECT
        # ============================================================

        match = re.search(
            r"\{.*\}",
            worksheet_text_clean,
            flags=re.DOTALL
        )

        if match:

            worksheet_text_clean = (
                match.group(0)
            )

        else:

            return jsonify({
                "success": False,
                "error":
                    "No valid JSON structure found "
                    "in the LLM response.",
                "raw_text":
                    worksheet_text
            }), 500

        # ============================================================
        # REMOVE COMMENTS
        # ============================================================

        worksheet_text_clean = re.sub(
            r"//.*?$",
            "",
            worksheet_text_clean,
            flags=re.MULTILINE
        )

        worksheet_text_clean = re.sub(
            r"/\*.*?\*/",
            "",
            worksheet_text_clean,
            flags=re.DOTALL
        )

        # ============================================================
        # REMOVE TRAILING COMMAS
        # ============================================================

        worksheet_text_clean = re.sub(
            r",\s*([\]}])",
            r"\1",
            worksheet_text_clean
        )

        # ============================================================
        # LOAD / VALIDATE JSON
        # ============================================================

        # ============================================================
        # PARSE GEMINI RESPONSE; RETRY ONCE IF JSON IS INVALID
        # ============================================================

        worksheet_text = (response.text or "").strip()

        try:
            worksheet_json = json.loads(worksheet_text)

        except (json.JSONDecodeError, TypeError) as first_error:

            print(
                "Initial JSON parsing failed:",
                str(first_error)
            )

            # Retry once by asking Gemini to repair the JSON.
            repair_prompt = f"""
            The following response is a worksheet that contains invalid JSON syntax.

            Repair the JSON syntax ONLY.

            STRICT REQUIREMENTS:
            1. Preserve all original questions, answers, values and wording.
            2. Do not invent new questions or remove valid questions.
            3. Do not summarize or shorten the worksheet.
            4. Preserve the exact property names and their spelling.
            5. The root MUST be a JSON object containing:
               - "header": string
               - "questions": array
               - "answer_key": array
            6. Every question must retain these fields:
               - "id": string
               - "text": string
               - "type": string
               - "options": array
               - "distractor_analysis": object
            7. Every answer_key entry must retain these fields:
               - "id": string
               - "answer": string
               - "step_by_step_solution": string
            8. Escape quotation marks and special characters correctly.
            9. Return one complete, syntactically valid JSON object.
            10. Do not include Markdown fences or explanations.

            REQUIRED STRUCTURE:
            {{
                "header": "Worksheet title and instructions",
                "questions": [
                    {{
                        "id": "Q1",
                        "text": "Question text",
                        "type": "Short Answer",
                        "options": [],
                        "distractor_analysis": {{}}
                    }}
                ],
                "answer_key": [
                    {{
                        "id": "Q1",
                        "answer": "Correct answer",
                        "step_by_step_solution": "Solution steps"
                    }}
                ]
            }}

            Repair the following JSON. Return only the repaired JSON:

            {worksheet_text}
            """

            try:
                retry_response = (
                    gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=repair_prompt,
                        config=config
                    )
                )

                repaired_text = (
                        retry_response.text or ""
                ).strip()

                worksheet_json = json.loads(repaired_text)

                print("JSON repair retry succeeded.")

            except Exception as retry_error:

                print(
                    "JSON repair retry failed:",
                    str(retry_error)
                )

                return jsonify({
                    "success": False,
                    "error": (
                        "We couldn't prepare your worksheet "
                        "correctly. Please try generating it again."
                    )
                }), 500

        # ============================================================
        # VALIDATE WORKSHEET STRUCTURE
        # ============================================================

        if (
                not isinstance(worksheet_json, dict)
                or not isinstance(worksheet_json.get("questions"), list)
                or not isinstance(worksheet_json.get("answer_key"), list)
        ):
            print("Invalid worksheet JSON structure.")

            return jsonify({
                "success": False,
                "error": (
                    "The worksheet response was incomplete. "
                    "Please try generating it again."
                )
            }), 500

        # ============================================================
        # SUCCESS
        # ============================================================

        print(
            "Successfully generated worksheet:",
            worksheet_json.get("header", "")
        )

        return jsonify({
            "success": True,
            "worksheet": worksheet_json
        })

        # try:
        #
        #     worksheet_json = json.loads(
        #         worksheet_text_clean
        #     )
        #
        # except json.JSONDecodeError as e:
        #
        #     print(
        #         "JSON structural corruption error:",
        #         str(e)
        #     )
        #
        #     return jsonify({
        #         "success": False,
        #         "error":
        #             f"JSON structural corruption error: {str(e)}",
        #         "raw_text":
        #             worksheet_text_clean
        #     }), 500

        # ============================================================
        # SUCCESS
        # ============================================================

        print(
            "Successfully generated worksheet:",
            worksheet_json.get(
                'header',
                ''
            )
        )

        return jsonify({
            "success": True,
            "worksheet": worksheet_json
        })

    # ================================================================
    # GLOBAL ERROR HANDLING
    # ================================================================

    except Exception as e:

        print(
            traceback.format_exc()
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
# def generate_worksheet_Gemini():
#     try:
#         # -------------------------
#         # Get form fields
#         # -------------------------
#         curriculum = request.form.get('curriculum', '')
#         grade = request.form.get('grade', '')
#         subject = request.form.get('subject', '')
#         custom_subject = request.form.get('customSubject', '')
#         topic_text = request.form.get('textContent', '').strip()
#         notes = request.form.get('notes', '')
#         question_types = request.form.getlist('questionTypes')
#         num_questions = request.form.get('numQuestions', 5)
#         difficulty = request.form.get("difficulty") or "Medium"
#         exam_type = request.form.get("examType") or "Worksheet"
#         duration = request.form.get('duration', '')
#         total_marks = request.form.get('totalMarks', '')
#         practice_focus = request.form.getlist('practiceFocus')
#         subtopics = request.form.getlist('subtopics')
#
#         # Determine  final subject
#         final_subject = custom_subject if custom_subject else subject
#
#         # -------------------------
#         # Handle uploaded file
#         # -------------------------
#         input_text = topic_text
#         file = request.files.get("file")
#
#         if file:
#             filename = file.filename.lower()
#
#             try:
#                 if filename.endswith('.pdf'):
#
#                     with tempfile.NamedTemporaryFile(
#                             delete=False,
#                             suffix='.pdf'
#                     ) as temp_pdf:
#
#                         temp_path = temp_pdf.name
#                         file.save(temp_path)
#
#                     extracted = extract_and_clean_text_from_pdf(temp_path)
#
#                     if not extracted.strip():
#                         extracted = ocr_from_scanned_pdf(temp_path)
#                         extracted = clean_extracted_text(extracted)
#
#                     input_text += "\n" + extracted
#
#                     os.remove(temp_path)
#
#                 elif filename.endswith('.txt'):
#
#                     input_text += "\n" + file.read().decode(
#                         'utf-8'
#                     ).replace('\r\n', '\n')
#
#                 elif filename.endswith('.docx'):
#
#                     input_text += "\n" + extract_text_from_docx(file)
#
#                 elif filename.endswith(('.png', '.jpg', '.jpeg')):
#
#                     with tempfile.NamedTemporaryFile(
#                             delete=False,
#                             suffix='.png'
#                     ) as temp_img:
#
#                         temp_path = temp_img.name
#                         file.save(temp_path)
#
#                     input_text += "\n" + extract_from_image(temp_path)
#
#                     os.remove(temp_path)
#
#             except Exception as e:
#                 return jsonify({
#                     "success": False,
#                     "error": f"File processing error: {str(e)}"
#                 }), 400
#
#         # -------------------------
#         # Ensure user entered something
#         # -------------------------
#         if not input_text.strip():
#             return jsonify({
#                 "success": False,
#                 "error": "Please enter Topic/Notes or upload a file."
#             }), 400
#
#         # -------------------------
#         # Number of questions
#         # -------------------------
#         try:
#             total_q = int(num_questions)
#         except:
#             total_q = 5
#
#         # -------------------------
#         # Question types
#         # -------------------------
#         qtypes_str = ", ".join(question_types) if question_types else "Mix"
#
#         # -------------------------
#         # Exam instructions
#         # -------------------------
#         exam_instructions = {
#             "Worksheet": (
#                 "Provide mixed practice questions. "
#                 "Questions should reinforce learning and encourage self-study."
#             ),
#
#             "Test": (
#                 "Questions should be exam-style, formal, and cover a balanced "
#                 "range of topics. No hints. Require complete answers. "
#                 "Assign marks per question."
#             ),
#
#             "Homework": (
#                 "Provide practice questions students can solve at home. "
#                 "Include a mix of easy and medium difficulty."
#             ),
#
#             "Quiz": (
#                 "Keep it short and focused on quick recall/application. "
#                 "Mostly objective questions (MCQ, FIB, short answers)."
#             )
#         }
#
#         # -------------------------
#         # Difficulty rules
#         # -------------------------
#         difficulty_rules = {
#             "Easy": (
#                 "Overall Baseline: EASY. Focus primarily on factual recall, "
#                 "foundational definitions, and straightforward procedures "
#                 "using simple grade-appropriate vocabulary."
#             ),
#
#             "Medium": (
#                 "Overall Baseline: MEDIUM. Focus on standard application, "
#                 "simple multi-step problems, conceptual understanding and "
#                 "clear explanations."
#             ),
#
#             "Hard": (
#                 "Overall Baseline: HARD. Focus on complex scenarios, "
#                 "non-routine application, reasoning, critical evaluation "
#                 "and multi-step problems."
#             )
#         }
#
#         rules_to_send = difficulty_rules.get(
#             difficulty,
#             difficulty_rules["Medium"]
#         )
#
#         # ============================================================
#         # LOAD CURRICULUM KNOWLEDGE
#         # ============================================================
#
#         curriculum_data = load_p3_maths_curriculum()
#
#         if not curriculum_data:
#             return jsonify({
#                 "success": False,
#                 "error": "P3 Mathematics curriculum JSON could not be loaded."
#             }), 500
#
#         # ============================================================
#         # FIND THE RELEVANT TOPIC FROM THE JSON
#         # ============================================================
#
#         topics = curriculum_data.get("topics", {})
#
#         search_text = f"{topic_text} {subtopics}".lower()
#
#         matched_topic_key = None
#         matched_topic_data = None
#
#         for topic_key, topic_data in topics.items():
#
#             display_name = topic_data.get(
#                 "display_name",
#                 ""
#             ).lower()
#
#             topic_key_lower = topic_key.lower()
#
#             if (
#                 topic_key_lower in search_text
#                 or display_name in search_text
#             ):
#                 matched_topic_key = topic_key
#                 matched_topic_data = topic_data
#                 break
#
#         # ------------------------------------------------------------
#         # If no exact topic match, send the complete curriculum JSON
#         # for now so we don't accidentally ignore curriculum knowledge.
#         # ------------------------------------------------------------
#
#         if matched_topic_data:
#
#             curriculum_knowledge = json.dumps(
#                 {
#                     matched_topic_key: matched_topic_data
#                 },
#                 indent=2,
#                 ensure_ascii=False
#             )
#
#             print(
#                 f"Matched curriculum topic: {matched_topic_key}"
#             )
#
#         else:
#
#             curriculum_knowledge = json.dumps(
#                 curriculum_data,
#                 indent=2,
#                 ensure_ascii=False
#             )
#
#             print(
#                 "No specific topic matched. "
#                 "Sending complete P3 Maths curriculum JSON."
#             )
#
#         # ============================================================
#         # BUILD LLM PROMPT
#         # ============================================================
#
#         prompt = f"""
# You are an expert AI Curriculum Designer and Professional Teacher's Assistant.
#
# Your task is to generate a high-quality {exam_type} for the student.
#
# The most important requirement is that the generated questions must
# respect the supplied curriculum knowledge base.
#
# ============================================================
# [CORE TARGET DATA]
# ============================================================
#
# Curriculum:
# {curriculum}
#
# Grade:
# {grade}
#
# Subject:
# {final_subject}
#
# Primary Reference Material / User Topic:
# {input_text}
#
# Target Subtopics:
# {subtopics if subtopics else "Assess the relevant topic from the supplied material."}
#
# Additional Teacher Requests:
# {notes if notes else "None"}
#
# Allowed Question Types:
# {qtypes_str}
#
# Total Number of Questions:
# {total_q}
#
# Target Difficulty:
# {difficulty}
#
# Duration:
# {duration if duration else "Not specified"}
#
# Total Marks:
# {total_marks if total_marks else "Not specified"}
#
#
# ============================================================
# [CURRICULUM KNOWLEDGE BASE]
# ============================================================
#
# The following information comes from the application's
# curriculum knowledge base.
#
# This knowledge base defines the intended curriculum scope,
# rules, heuristics, vocabulary and solution approach.
#
# CURRICULUM KNOWLEDGE:
#
# {curriculum_knowledge}
#
#
# ============================================================
# [HOW TO USE THE CURRICULUM KNOWLEDGE]
# ============================================================
#
# You MUST use the supplied curriculum knowledge when designing
# the questions.
#
# 1. CURRICULUM SCOPE
#
# Do not introduce concepts that are outside the supplied
# curriculum knowledge for this grade and topic.
#
# 2. CURRICULUM RULES
#
# Treat explicit rules in the curriculum knowledge as HARD
# generation constraints.
#
# For example, if the curriculum states that certain numbers,
# operations, denominators, units or representations must be
# used or avoided, follow those restrictions.
#
# Do NOT override an explicit curriculum rule merely because
# a more advanced question would be possible.
#
# 3. HEURISTICS
#
# Use the supplied heuristics as question-design patterns.
#
# The heuristics describe appropriate ways of testing the
# student's understanding.
#
# Do not copy an example or mechanically repeat the same pattern.
# Create new questions using the underlying idea.
#
# 4. VOCABULARY
#
# Prefer the vocabulary supplied by the curriculum knowledge
# when it is appropriate.
#
# Use language suitable for the selected grade.
#
# 5. SOLUTION METHOD
#
# Use the supplied solution_steps as guidance for the answer key.
#
# The step-by-step solution must demonstrate the appropriate
# method for this grade and topic.
#
# 6. PROGRESSION
#
# Create a sensible progression from simpler understanding
# towards application and reasoning.
#
# Do NOT impose a universal percentage such as 30% easy,
# 40% medium and 30% hard.
#
# The curriculum knowledge and requested difficulty should
# determine the appropriate progression.
#
# 7. ORIGINALITY
#
# Generate completely new questions.
#
# Do not reproduce questions from the curriculum knowledge
# verbatim.
#
# Do not invent past-paper questions or claim that a generated
# question is an official examination question.
#
#
# ============================================================
# [DIFFICULTY]
# ============================================================
#
# {rules_to_send}
#
#
# ============================================================
# [EXAM FORMAT]
# ============================================================
#
# {exam_instructions.get(
#     exam_type,
#     "Use a standard educational worksheet format."
# )}
#
#
# ============================================================
# [QUESTION DESIGN]
# ============================================================
#
# Design the questions so that they:
#
# - Match the selected grade.
# - Match the selected curriculum.
# - Match the selected topic.
# - Follow the curriculum rules.
# - Use the curriculum heuristics.
# - Use appropriate grade-level vocabulary.
# - Test genuine understanding rather than random variation.
# - Progress naturally in complexity.
# - Avoid concepts that have not been introduced within the
#   supplied curriculum scope.
# - Have clear and unambiguous wording.
#
#
# ============================================================
# [MULTIPLE CHOICE RULES]
# ============================================================
#
# For MCQ questions:
#
# - Provide exactly four options.
# - There must be exactly one correct answer.
# - Every distractor must represent a realistic student mistake.
# - Do not create obviously silly or impossible distractors.
# - Distractors should relate to the actual calculation,
#   reasoning or misconception involved.
#
#
# ============================================================
# [QUALITY CONTROL]
# ============================================================
#
# Before producing the final JSON, internally verify:
#
# - Every question is within curriculum scope.
# - Every question matches the selected topic.
# - Every calculation is correct.
# - Every MCQ has exactly one correct answer.
# - Every answer matches the question.
# - Every step-by-step solution reaches the stated answer.
# - No contradictory information exists.
# - No unsupported advanced concepts have been introduced.
# - The number of questions exactly equals {total_q}.
#
#
# ============================================================
# [OUTPUT FORMAT]
# ============================================================
#
# Return ONLY one valid JSON object.
#
# Do not include markdown.
# Do not include ```json.
# Do not include explanations outside the JSON.
#
# Use exactly this structure:
#
# {{
#     "header": "{exam_type} Title and Clear Student Instructions",
#
#     "questions": [
#         {{
#             "id": "Q1",
#             "text": "The precise question text",
#             "type": "MCQ/FIB/Short Answer",
#             "options": [
#                 "Option A",
#                 "Option B",
#                 "Option C",
#                 "Option D"
#             ],
#             "distractor_analysis": {{
#                 "Option A": "Explain the student misconception.",
#                 "Option B": "Explain the student misconception.",
#                 "Option C": "Explain the student misconception.",
#                 "Option D": "Explain the student misconception."
#             }}
#         }}
#     ],
#
#     "answer_key": [
#         {{
#             "id": "Q1",
#             "answer": "The exact correct answer",
#             "step_by_step_solution": "Clear step-by-step solution appropriate for the grade."
#         }}
#     ]
# }}
#
# Important:
#
# If the question type is not MCQ, the options array may be empty
# and distractor_analysis may be an empty object.
#
# The final response MUST be valid JSON.
# """
#         print("\n================ GEMINI RAW RESPONSE input ================")
#         print(prompt)
#         print("======================================================\n")
#
#
#         # ============================================================
#         # EXECUTE GEMINI
#         # ============================================================
#
#         config = types.GenerateContentConfig(
#             temperature=0.7,
#             max_output_tokens=8192,
#             response_mime_type="application/json"
#         )
#
#         gemini_client = genai.Client(
#             vertexai=True,
#             project='my-project-8112-283009',
#             location='us-central1'
#         )
#
#         response = gemini_client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=prompt,
#             config=config
#         )
#
#         # ============================================================
#         # EXTRACT GEMINI RESPONSE
#         # ============================================================
#
#         worksheet_text = response.text
#
#         # Remove markdown code fences if Gemini adds them
#         worksheet_text_clean = re.sub(
#             r"^```json\s*|\s*```$",
#             "",
#             worksheet_text.strip(),
#             flags=re.MULTILINE
#         )
#
#         # Find JSON object
#         match = re.search(
#             r"\{.*\}",
#             worksheet_text_clean,
#             flags=re.DOTALL
#         )
#
#         if match:
#             worksheet_text_clean = match.group(0)
#         else:
#             return jsonify({
#                 "success": False,
#                 "error": "No valid JSON structure found in the LLM response.",
#                 "raw_text": worksheet_text
#             }), 500
#
#         # Remove comments
#         worksheet_text_clean = re.sub(
#             r"//.*?$",
#             "",
#             worksheet_text_clean,
#             flags=re.MULTILINE
#         )
#
#         worksheet_text_clean = re.sub(
#             r"/\*.*?\*/",
#             "",
#             worksheet_text_clean,
#             flags=re.DOTALL
#         )
#
#         # Remove trailing commas
#         worksheet_text_clean = re.sub(
#             r",\s*([\]}])",
#             r"\1",
#             worksheet_text_clean
#         )
#
#         # ============================================================
#         # LOAD / VALIDATE JSON
#         # ============================================================
#
#         try:
#             worksheet_json = json.loads(
#                 worksheet_text_clean
#             )
#
#         except json.JSONDecodeError as e:
#
#             print(
#                 f"JSON structural corruption error: {str(e)}"
#             )
#
#             return jsonify({
#                 "success": False,
#                 "error": f"JSON structural corruption error: {str(e)}",
#                 "raw_text": worksheet_text_clean
#             }), 500
#
#         print(
#             f"Successfully generated worksheet: "
#             f"{worksheet_json.get('header', '')}"
#         )
#
#         return jsonify({
#             "success": True,
#             "worksheet": worksheet_json
#         })
#
#     except Exception as e:
#
#         print(traceback.format_exc())
#
#         return jsonify({
#             "success": False,
#             "error": str(e)
#         }), 500




# def generate_worksheet_Gemini():
#     try:
#         # -------------------------
#         # Get form fields
#         # -------------------------
#         curriculum = request.form.get('curriculum', '')
#         grade = request.form.get('grade', '')
#         subject = request.form.get('subject', '')
#         custom_subject = request.form.get('customSubject', '')
#         topic_text = request.form.get('textContent', '').strip()
#         subtopics = request.form.get('subtopics', '')
#         notes = request.form.get('notes', '')
#         question_types = request.form.getlist('questionTypes')
#         num_questions = request.form.get('numQuestions', 5)
#         difficulty = request.form.get("difficulty") or "Medium"
#         exam_type = request.form.get("examType") or "Worksheet"
#         duration = request.form.get('duration', '')
#         total_marks = request.form.get('totalMarks', '')
#
#         # Determine final subject
#         final_subject = custom_subject if custom_subject else subject
#
#         # -------------------------
#         # Handle uploaded file
#         # -------------------------
#         input_text = topic_text  # start with textarea content
#         file = request.files.get("file")
#
#         if file:
#             filename = file.filename.lower()
#             try:
#                 if filename.endswith('.pdf'):
#                     with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
#                         temp_path = temp_pdf.name
#                         file.save(temp_path)
#                     extracted = extract_and_clean_text_from_pdf(temp_path)
#                     if not extracted.strip():
#                         extracted = ocr_from_scanned_pdf(temp_path)
#                         extracted = clean_extracted_text(extracted)
#                     input_text += "\n" + extracted
#                     os.remove(temp_path)
#                 elif filename.endswith('.txt'):
#                     input_text += "\n" + file.read().decode('utf-8').replace('\r\n', '\n')
#                 elif filename.endswith('.docx'):
#                     input_text += "\n" + extract_text_from_docx(file)
#                 elif filename.endswith(('.png', '.jpg', '.jpeg')):
#                     with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_img:
#                         temp_path = temp_img.name
#                         file.save(temp_path)
#                     input_text += "\n" + extract_from_image(temp_path)
#                     os.remove(temp_path)
#             except Exception as e:
#                 return jsonify({"success": False, "error": f"File processing error: {str(e)}"}), 400
#
#         # Ensure user entered something
#         if not input_text.strip():
#             return jsonify({"success": False, "error": "Please enter Topic/Notes or upload a file."}), 400
#
#         # -------------------------
#         # Advanced Pedagogical Scaffolding Logic
#         # -------------------------
#         try:
#             total_q = int(num_questions)
#         except:
#             total_q = 5
#
#         scaffolding_rule = f"""
#         Scaffolding & Progression Rules:
#         - Out of the {total_q} questions requested, organize them sequentially to build concept mastery:
#           - The first 30% of questions must be foundational (direct recall, basic vocabulary, core concepts).
#           - The middle 40% must require light conceptual application (combining variables, identifying operations, basic inferences).
#           - The final 30% must offer an analytical challenge (multi-step problems, real-world context application, or identifying a mistake in a broken solution).
#         - This sequential step-up is strictly mandatory to ensure educational depth.
#         """
#
#         qtypes_str = ", ".join(question_types) if question_types else "Mix"
#
#         exam_instructions = {
#             "Worksheet": "Provide mixed practice questions. Questions should reinforce learning and encourage self-study.",
#             "Test": "Questions should be exam-style, formal, and cover a balanced range of topics. No hints. Require complete answers. Assign marks per question.",
#             "Homework": "Provide practice questions students can solve at home. Include a mix of easy and medium difficulty.",
#             "Quiz": "Keep it short and focused on quick recall/application. Mostly objective questions (MCQ, FIB, short answers)."
#         }
#
#         difficulty_rules = {
#             "Easy": "Overall Baseline: EASY. Focus primarily on factual recall, foundational definitions, and straightforward procedures using simple grade-appropriate vocabulary.",
#             "Medium": "Overall Baseline: MEDIUM. Focus on standard application, reading comprehension inferences, simple multi-step combining of raw facts, and clear conceptual explanations.",
#             "Hard": "Overall Baseline: HARD. Focus on complex scenarios, non-routine application of concepts to novel situations, critical evaluations, and multi-layered reasoning frameworks."
#         }
#
#         rules_to_send = difficulty_rules[difficulty]
#
#         # -------------------------
#         # Build LLM Prompt
#         # -------------------------
#         prompt = f"""
# You are an expert AI Curriculum Designer and Professional Teacher's Assistant. Generate a highly structured, accurate {exam_type}.
#
# [CORE TARGET DATA]
# Curriculum Alignment Framework: {curriculum}
# Grade Level: {grade}
# Subject Domain: {final_subject}
# Primary Reference Material/Source Text: {input_text}
# Target Subtopics to Assess: {subtopics if subtopics else 'Assess full coverage of material'}
# Additional Teacher Requests: {notes if notes else 'None'}
# Allowed Question Archetypes: {qtypes_str}
# Total Quantity of Questions Required: {total_q}
# Target Baseline Difficulty: {difficulty}
# Allocated Exam Duration: {duration if duration else 'Not specified'}
# Maximum Exam Marks: {total_marks if total_marks else 'Not specified'}
#
# [PEDAGOGICAL INSTRUCTIONS]
# {scaffolding_rule}
#
# Difficulty Level Boundaries:
# {rules_to_send}
#
# Exam Format Specifications:
# {exam_instructions.get(exam_type, "Use standard exam format.")}
#
# [STRICT ALIGNMENT & QUALITY RULES]
# - Curriculum Matching: Adhere stringently to the specific learning objectives of {curriculum} for Grade {grade}. Use the precise terminology, grading structures, notations, and formatting standards associated with {curriculum}.
# - Distractor Design Rules (For Multiple-Choice Questions): Every single incorrect option (distractor) must be realistic and deliberately mapped to a common student misconception (e.g., in math, an option showing an addition slip, inverted fraction, or skipped unit conversion step). Never output arbitrary or obviously false options.
# - Logical Flawlessness: Ensure there is precisely one unarguably correct answer per question. Double check all calculations internally before writing options.
#
# [OUTPUT FORMAT INSTRUCTIONS]
# Format your response as a single, perfectly structured JSON object using this layout. Do not include markdown wraps, code fences (such as ```json), or text outside the brackets.
#
# {{
#     "header": "{exam_type} Title and Clear Student Instructions",
#     "questions": [
#         {{
#             "id": "Q1",
#             "text": "The precise question text",
#             "type": "MCQ/FIB/Short Answer",
#             "options": ["Option A", "Option B", "Option C", "Option D"],
#             "distractor_analysis": {{
#                 "Option A": "Explain why this mistake happens (e.g. Student multiplied instead of adding)",
#                 "Option B": "Explain the misconception for this specific option",
#                 "Option C": "Explain the procedural slip for this option"
#             }}
#         }}
#     ],
#     "answer_key": [
#         {{
#             "id": "Q1",
#             "answer": "The exact correct answer text",
#             "step_by_step_solution": "A crystal-clear, pedagogically thorough breakdown outlining how to calculate or reach the exact answer."
#         }}
#     ]
# }}
#
# Ensure the JSON is completely closed, valid, and fully structural.
# """
#
#         # -------------------------
#         # Execute Request to Gemini Client
#         # -------------------------
#         config = types.GenerateContentConfig(
#             temperature=0.7,
#             max_output_tokens=8192,  # CRITICAL: Raised to maximum to fit thinking tokens
#             response_mime_type="application/json"  # CRITICAL: Forces Gemini to output pure JSON natively
#         )
#         gemini_client = genai.Client(
#             vertexai=True,
#             project='my-project-8112-283009',
#             location='us-central1'
#         )
#
#         response = gemini_client.models.generate_content(
#             model="gemini-2.5-flash",  # The required modern reasoning model
#             contents=prompt,
#             config=config
#         )
#
#         # Extract text directly using the new SDK standard
#         worksheet_text = response.text
#
#         # Sanitize JSON from any leftover margins
#         worksheet_text_clean = re.sub(r"^```json\s*|\s*```$", "", worksheet_text.strip(), flags=re.MULTILINE)
#         match = re.search(r"\{.*\}", worksheet_text_clean, flags=re.DOTALL)
#         if match:
#             worksheet_text_clean = match.group(0)
#         else:
#             return jsonify({"success": False, "error": "No valid JSON structural maps found in the LLM response.",
#                             "raw_text": worksheet_text}), 500
#
#         # Remove trailing commas or stray annotation tags
#         worksheet_text_clean = re.sub(r"//.*?$", "", worksheet_text_clean, flags=re.MULTILINE)
#         worksheet_text_clean = re.sub(r"/\*.*?\*/", "", worksheet_text_clean, flags=re.DOTALL)
#         worksheet_text_clean = re.sub(r",\s*([\]}])", r"\1", worksheet_text_clean)
#
#         # Load and validate the finalized dataset
#         try:
#             worksheet_json = json.loads(worksheet_text_clean)
#         except json.JSONDecodeError as e:
#             # Added this indented block to handle parsing failures cleanly:
#             print(f"JSON structural corruption error: {str(e)}")
#             return jsonify({
#                 "success": False,
#                 "error": f"JSON structural corruption error: {str(e)}",
#                 "raw_text": worksheet_text_clean
#             }), 500
#
#         print(f"Successfully generated worksheet: {worksheet_json.get('header', '')}")
#         return jsonify({"success": True, "worksheet": worksheet_json})
#
#     except Exception as e:
#         print(traceback.format_exc())
#         return jsonify({"success": False, "error": str(e)}), 500


@app.route('/generate_worksheet_GPT', methods=['POST'])
def generate_worksheet_GPT():
    try:
        # -------------------------
        # Get form fields
        # -------------------------
        curriculum = request.form.get('curriculum', '')
        grade = request.form.get('grade', '')
        subject = request.form.get('subject', '')
        custom_subject = request.form.get('customSubject', '')
        topic_text = request.form.get('textContent', '').strip()
        subtopics = request.form.get('subtopics', '')
        notes = request.form.get('notes', '')
        question_types = request.form.getlist('questionTypes')
        num_questions = request.form.get('numQuestions', 5)
        difficulty = request.form.get("difficulty") or "Medium"
        exam_type = request.form.get("examType") or "Worksheet"
        duration = request.form.get('duration', '')
        total_marks = request.form.get('totalMarks', '')

        final_subject = custom_subject if custom_subject else subject

        # -------------------------
        # Handle uploaded file
        # -------------------------
        input_text = topic_text
        file = request.files.get("file")

        if file:
            filename = file.filename.lower()
            try:
                if filename.endswith('.pdf'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                        temp_path = temp_pdf.name
                        file.save(temp_path)
                    extracted = extract_and_clean_text_from_pdf(temp_path)
                    if not extracted.strip():
                        extracted = ocr_from_scanned_pdf(temp_path)
                        extracted = clean_extracted_text(extracted)
                    input_text += "\n" + extracted
                    os.remove(temp_path)
                elif filename.endswith('.txt'):
                    input_text += "\n" + file.read().decode('utf-8').replace('\r\n', '\n')
                elif filename.endswith('.docx'):
                    input_text += "\n" + extract_text_from_docx(file)
                elif filename.endswith(('.png', '.jpg', '.jpeg')):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_img:
                        temp_path = temp_img.name
                        file.save(temp_path)
                    input_text += "\n" + extract_from_image(temp_path)
                    os.remove(temp_path)
            except Exception as e:
                return jsonify({"success": False, "error": f"File processing error: {str(e)}"}), 400

        if not input_text.strip():
            return jsonify({"success": False, "error": "Please enter Topic/Notes or upload a file."}), 400

        qtypes_str = ", ".join(question_types) if question_types else "Mix"
        exam_instructions = {
            "Worksheet": "Provide mixed practice questions. Questions should reinforce learning and encourage self-study.",
            "Test": "Questions should be exam-style, formal, and cover a balanced range of topics. No hints. Require complete answers. Assign marks per question.",
            "Homework": "Provide practice questions students can solve at home. Include a mix of easy and medium difficulty. Allow for extended responses or projects.",
            "Quiz": "Keep it short and focused on quick recall/application. Mostly objective questions (MCQ, FIB, short answers). Limited marks."
        }

        # -------------------------
        # Build LLM prompt
        # -------------------------
        prompt = f"""
        You are an AI teacher assistant. Generate a {exam_type} worksheet.

        IMPORTANT ACCURACY RULE:
        Before generating questions and answers, identify the subject (e.g., Physics, Math, Biology).
        Apply the following rules:

        - For Physics:
          - Use correct formulas for electricity and circuits when relevant.
          - Do not guess numerical answers.
          - Apply Ohm’s Law, current/voltage rules, resistance formulas, and verify all calculations.

        - For Math:
          - All numerical answers must be computed exactly.
          - Show correct reasoning internally before producing the final answer.

        - For Science (Biology/Chemistry):
          - Use correct definitions, processes, and scientific terminology.
          - No invented facts.

        - For Humanities (History/Geography):
          - Use factual, verifiable information appropriate for Grade {grade}.
        -LOGIC VALIDATION RULE (MANDATORY FOR MATH PUZZLES):
        - When a question provides a fixed list of numbers and clues:
          - Verify that ALL clues together match EXACTLY ONE number from the list.
          - If zero or multiple numbers match, revise the clues before finalizing the question.
          - Do not output questions with contradictory or unsatisfiable clues.
        - For number puzzles:
          - Cross-check every clue against the provided options.
          - Ensure only one option satisfies all clues simultaneously.
        - Re-evaluate each question using the answer key.
        - Confirm the answer satisfies every clue in the question.
        - If any mismatch exists, correct the question.
        - Ensure correctness, avoid contradictions, and double-check answers before output.
    DIGIT RULE:
        - All digit-based clues must use whole-number logic only.
        - Do NOT use ranges like “greater than 1 but less than 2”.
        - Use valid digit values: 0–9 only.


        Curriculum: {curriculum}
        Grade: {grade}
        Subject: {final_subject}
        Topic / Notes: {input_text}
        Subtopics: {subtopics if subtopics else 'None'} 
        Addition information :{notes if subtopics else 'None'}
        Question Types: {qtypes_str}
        Number of Questions: {num_questions}
        Difficulty: {difficulty}  (Ensure the difficulty level matches exactly: 
          - Easy = recall/basic understanding,
          - Medium = application & explanation,
          - Hard = higher-order thinking, multi-step reasoning, real-life context)
        Curriculum Alignment:
        - Ensure questions follow the {curriculum} learning objectives for Grade {grade}.
        - Select subtopics, wording style, and difficulty as per {curriculum} standards.
        - Use terminology, notations, and examples consistent with {curriculum}.
        - Do not include topics outside {curriculum} scope for this grade/subject.

        ExamType: {exam_type}

        Suggested Duration: {duration if duration else 'Not specified'}
        Total Marks: {total_marks if total_marks else 'Not specified'}
        Instructions for {exam_type}:
        {exam_instructions.get(exam_type, "Use standard exam format.")}

        Format the worksheet as a JSON object with the following structure:

        {{
            "header": " Worksheet title and instructions",
            "questions": [
                {{
                    "id": "Q1",
                    "text": "Question text here",
                    "type": "MCQ/FIB/Short Answer/etc.",
                    "options": ["Option A", "Option B", ...]
                }},
                ...
                ]
            # ],
            # "answer_key": [
            #     {{
            #         "id": "Q1",
            #         "answer": "Correct answer text"
            #     }},
            #     ...
            # ]
        }}

        Make sure:
        - Each question has a unique ID (Q1, Q2, etc.)
        - The answer key lists all questions and their answers.
        - JSON is properly formatted and parsable.
        - Return output ONLY as valid JSON, no extra text, no markdown, no code fences. 
        - Do not include comments (// or /* */).
        - Do not include trailing commas.
        """
#         prompt = f"""
# You are an AI teacher assistant. Generate a {exam_type} worksheet.
#
# Curriculum: {curriculum}
# Grade: {grade}
# Subject: {final_subject}
# Topic / Notes: {input_text}
# Subtopics: {subtopics if subtopics else 'None'}
# Additional Info: {notes if notes else 'None'}
# Question Types: {qtypes_str}
# Number of Questions: {num_questions}
# Difficulty: {difficulty}
# Suggested Duration: {duration if duration else 'Not specified'}
# Total Marks: {total_marks if total_marks else 'Not specified'}
#
# Instructions:
# {exam_instructions.get(exam_type, "Use standard exam format.")}
#
# Format as JSON ONLY with this structure:
#
# {{
#     "header": "Worksheet title and instructions",
#     "questions": [
#         {{
#             "id": "Q1",
#             "text": "Question text here",
#             "type": "MCQ/FIB/Short Answer/etc.",
#             "options": ["Option A", "Option B", ...]
#         }}
#     ],
#     "answer_key": [
#         {{
#             "id": "Q1",
#             "answer": "Correct answer text"
#         }}
#     ]
# }}
#
# - Each question must have a unique ID.
# - JSON must be valid and parsable.
# - Do NOT include explanations, markdown, or code fences.
# """

        if "FIB" in qtypes_str:
            prompt += """
            - For Fill-in-the-Blank (FIB) questions:
              - Use '__' in the question text where the student should fill in the blank.
              - In the "answer_key", provide the correct answer, not '__'.
            - Format each question in JSON like this:
            {
              "id": "Q1",
              "text": "The numerator of a fraction is __",
              "type": "FIB",
              "answer_key": [
                {
                  "id": "Q1",
                  "answer": "the number above the line"
                }
              ]
            }
            """

        if "Match" in qtypes_str:
            prompt += """
        -  questions must be 'Match the Following'. Provide two lists (Column A and Column B) 
          with corresponding items. Format in JSON like:
          {
            "id": "Q1",
            "text": "Match the countries with their capitals",
            "type": "Match",
            "options": {
                "ColumnA": ["France", "Germany", "Japan"],
                "ColumnB": ["Berlin", "Tokyo", "Paris"]
            }   
          } 
          and answer key 
           "answer_key": [
                {
                    "id": "Q1",
                    "answer": {
                        "ColumnA": ["Ban on single-use plastics", "Recycling", "Using cloth bags"],
                        "ColumnB": ["Using alternatives to plastics", "Recycling and reusing materials", "Metal straws"]
                    }
                }
        """
        # -------------------------
        # Call GPT API
        # -------------------------

        response = gpt_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )

        worksheet_text = response.choices[0].message.content
        print(f"prompt {prompt}")
        # --------- ----------------
        # Clean and parse JSON
        # -------------------------
        worksheet_text_clean = re.sub(r"^```json\s*|\s*```$", "", worksheet_text.strip(), flags=re.MULTILINE)
        match = re.search(r"\{.*\}", worksheet_text_clean, flags=re.DOTALL)
        if match:
            worksheet_text_clean = match.group(0)
        else:
            return jsonify({"success": False, "error": "No JSON object found in LLM output", "raw_text": worksheet_text}), 500

        worksheet_text_clean = re.sub(r"//.*?$", "", worksheet_text_clean, flags=re.MULTILINE)
        worksheet_text_clean = re.sub(r"/\*.*?\*/", "", worksheet_text_clean, flags=re.DOTALL)
        worksheet_text_clean = re.sub(r",\s*([\]}])", r"\1", worksheet_text_clean)

        try:
            worksheet_json = json.loads(worksheet_text_clean)
        except json.JSONDecodeError as e:
            return jsonify({"success": False, "error": f"Failed to parse JSON: {str(e)}", "raw_text": worksheet_text_clean}), 500
        print(f"response {worksheet_json}")
        return jsonify({"success": True, "worksheet": worksheet_json})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

def normalize_questions_math(worksheet_json):
    for q in worksheet_json.get("questions", []):
        # Normalize question text
        q["text"] = normalize_math_latex_advanced(q["text"])

        # Normalize options if present
        if "options" in q:
            q["options"] = [normalize_math_latex_advanced(opt) for opt in q["options"]]

    # Normalize answer key
    for a in worksheet_json.get("answer_key", []):
        a["answer"] = normalize_math_latex_advanced(a["answer"])

    return worksheet_json

@app.route("/generate_worksheet_3_step", methods=["POST"])

# Placeholder for your LLM API call
def call_llm(prompt):
   response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
   content = response.choices[0].message.content
   return content

def generate_questions_only(input_text, grade, subject, exam_type, num_questions, difficulty):
    prompt = f"""
    You are an AI teacher assistant. Generate {num_questions} {exam_type} questions.
    Grade: {grade}, Subject: {subject}
    Topic/Notes: {input_text}

    Instructions:
    - Output JSON only.
    - Each question should include:
      - id
      - type (e.g., number_puzzle, MCQ)
      - options (if any)
      - clues_text (student-facing clues)
    - DO NOT provide answers.
    """
    response = call_llm(prompt)
    return json.loads(response)

def solve_questions(questions_json):
    prompt = f"""
    Here are the questions (JSON format) with options and clues:
    {json.dumps(questions_json, indent=2)}

    Determine the correct answer for each question.
    Return JSON only: list of objects with 'id' and 'answer'.
    """
    response = call_llm(prompt)
    return json.loads(response)

def validate_answers(questions_json, answer_key):
    prompt = f"""
    Validate each answer against the clues in the questions:
    Questions JSON: {json.dumps(questions_json, indent=2)}
    Answer Key JSON: {json.dumps(answer_key, indent=2)}

    For each answer, return:
      - id
      - status: valid or invalid
      - corrected_answer (if invalid)

    Return JSON only.
    """
    response = call_llm(prompt)
    return json.loads(response)

def generate_worksheet_3_step():
    try:
        curriculum = request.form.get('curriculum', '')
        grade = request.form.get('grade', '')
        subject = request.form.get('subject', '')
        custom_subject = request.form.get('customSubject', '')
        topic_text = request.form.get('textContent', '').strip()
        subtopics = request.form.get('subtopics', '')
        notes = request.form.get('notes', '')
        # include_charts = request.form.get('includeCharts', 'false') == 'true'
        # include_diagrams = request.form.get('includeDiagrams', 'false') == 'true'
        # include_scenarios = request.form.get('includeScenarios', 'false') == 'true'
        question_types = request.form.getlist('questionTypes')
        num_questions = request.form.get('numQuestions', 5)
        difficulty = request.form.get("difficulty") or "Medium"
        exam_type = request.form.get("examType") or "Worksheet"
        duration = request.form.get('duration', '')
        total_marks = request.form.get('totalMarks', '')

        if not topic_text:
            return jsonify({"success": False, "error": "Please enter Topic/Notes."}), 400

        # -----------------------------
        # Step 1: Generate Questions Only
        # -----------------------------
        questions_json = generate_questions_only(topic_text, grade, subject, exam_type, num_questions, difficulty)

        # -----------------------------
        # Step 2: Solve Questions
        # -----------------------------
        answer_key = solve_questions(questions_json)

        # -----------------------------
        # Step 3: Validate Answers
        # -----------------------------
        validation_results = validate_answers(questions_json, answer_key)

        # Optional: regenerate invalid answers/questions
        for result in validation_results:
            if result.get("status") == "invalid":
                # For prototype: we can just update answer with corrected_answer
                for ans in answer_key:
                    if ans["id"] == result["id"]:
                        ans["answer"] = result.get("corrected_answer")
                        break

        # -----------------------------
        # Build final worksheet JSON
        # -----------------------------
        final_worksheet = {
            "header": f"{exam_type} for Grade {grade} - {subject}",
            "questions": questions_json,
            "answer_key": answer_key
        }

        return jsonify({"success": True, "worksheet": final_worksheet})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/export-worksheet", methods=["POST"])
def export_worksheet():
    payload = request.get_json()  # the whole JSON from JS
    worksheet = payload.get("data")  # this is your worksheetData
    action = payload.get("action", "saveDoc")

    try:
        if action == 'saveDoc':
            # DOCX
            doc = create_docx_from_json(worksheet)
            doc_buffer = BytesIO()
            doc.save(doc_buffer)
            doc_buffer.seek(0)

            return send_file(
                doc_buffer,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name="worksheet.docx"
            )

        else:
            # PDF
            pdf = create_pdf_from_json(worksheet)
            pdf_buffer = BytesIO()
            # FPDF example: output to bytes
            pdf_buffer.write(pdf.output(dest='S').encode('latin-1'))
            pdf_buffer.seek(0)

            return send_file(
                pdf_buffer,
                mimetype="application/pdf",
                as_attachment=True,
                download_name="worksheet.pdf"
            )

    except Exception as e:
        print("Error in export_worksheet:")
        traceback.print_exc()  # prints full traceback
        return jsonify({"error": f"Failed to save: {str(e)}"}), 500


class PDFWithHeader(FPDF):
    def __init__(self, title="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title
        self.show_brand_header = True

    def header(self):
        # Repeating MapBuddyAI branding
        self.set_y(10)

        self.set_font("DejaVu", "B", 10)
        self.set_text_color(105, 75, 190)
        self.cell(0, 7, "MapBuddyAI", border=0, ln=1, align="L")

        # Subtle divider
        self.set_draw_color(220, 213, 245)
        self.line(
            self.l_margin,
            self.get_y() + 1,
            self.w - self.r_margin,
            self.get_y() + 1
        )

        self.set_y(self.get_y() + 5)

    def footer(self):
        self.set_y(-15)

        self.set_draw_color(220, 213, 245)
        self.line(
            self.l_margin,
            self.get_y(),
            self.w - self.r_margin,
            self.get_y()
        )

        self.set_y(-12)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(130, 130, 145)
        self.cell(0, 8, f"MapBuddyAI | Page {self.page_no()}", 0, 0, "C")
# def create_pdf_from_json(data):
#     title = str(data.get("title") or data.get("header", "Worksheet"))
#     pdf = PDFWithHeader(title=title)
#     pdf.add_page()
#
#     # Register Unicode fonts ONCE
#     pdf.add_font("DejaVu", "", "fonts/DejaVuSans.ttf", uni=True)
#     pdf.add_font("DejaVu", "B", "fonts/DejaVuSans-Bold.ttf", uni=True)
#
#     # ---------------- Student Info ----------------
#     student_name = data.get("student_name", "__________")
#     date = data.get("date", "__________")
#     grade = data.get("grade", "")
#     subject = data.get("subject", "")
#
#     pdf.set_font("DejaVu", "", 10)
#     pdf.cell(90, 8, f"Name: {student_name}", ln=0)
#     pdf.cell(0, 8, f"Date: {date}", ln=1)
#     pdf.cell(90, 8, f"Grade: {grade}", ln=0)
#     pdf.cell(0, 8, f"Subject: {subject}", ln=1)
#     pdf.ln(10)
#
#     # ---------------- Questions ----------------
#     for q in data.get("questions", []):
#         img_matches = re.findall(r'<img.*?src="(data:image/[^"]+)".*?>', q['text'])
#         text_only = re.sub(r'<img.*?>', '', q['text']).strip()
#
#         pdf.set_font("DejaVu", "", 10)
#         pdf.multi_cell(0, 8, f"{q['id']}. {text_only}")
#         pdf.ln(2)
#
#         # Options
#         if q.get("type") == "Match" and q.get("options"):
#             colA = q["options"].get("ColumnA", [])
#             colB = q["options"].get("ColumnB", [])
#             cell_width = 90
#             cell_height = 8
#
#             pdf.set_font("DejaVu", "B", 12)
#             pdf.cell(cell_width, cell_height, "Column A", ln=0)
#             pdf.cell(cell_width, cell_height, "Column B", ln=1)
#
#             pdf.set_font("DejaVu", "", 12)
#             for a, b in zip(colA, colB):
#                 pdf.cell(cell_width, cell_height, a, ln=0)
#                 pdf.cell(cell_width, cell_height, b, ln=1)
#             pdf.ln(3)
#
#         elif q.get("options"):
#             for opt in q["options"]:
#                 pdf.multi_cell(0, 8, f"   - {opt}")
#             pdf.ln(2)
#
#         # Insert images
#         for img_data_url in img_matches:
#             header, encoded = img_data_url.split(",", 1)
#             img_bytes = base64.b64decode(encoded)
#
#             if header.startswith("data:image/svg+xml"):
#                 png_bytes = cairosvg.svg2png(bytestring=img_bytes)
#                 image = Image.open(BytesIO(png_bytes))
#             else:
#                 image = Image.open(BytesIO(img_bytes))
#
#             temp_path = f"temp_{q['id']}.png"
#             image.save(temp_path)
#             pdf.image(temp_path, w=50)
#             os.remove(temp_path)
#
#         pdf.ln(5)
#
#     # ---------------- Answer Key ----------------
#     pdf.add_page()
#     pdf.set_font("DejaVu", "B", 14)
#     pdf.multi_cell(0, 10, "Answer Key")
#     pdf.ln(5)
#
#     pdf.set_font("DejaVu", "", 12)
#     for ans in data.get("answer_key", []):
#         pdf.multi_cell(0, 10, f"{ans['id']}:")
#         pdf.ln(2)
#
#         answer = ans.get("answer")
#
#         if isinstance(answer, dict) and "ColumnA" in answer and "ColumnB" in answer:
#             colA = answer["ColumnA"]
#             colB = answer["ColumnB"]
#             cell_width = 90
#             cell_height = 8
#
#             pdf.set_font("DejaVu", "B", 12)
#             pdf.cell(cell_width, cell_height, "Column A", ln=0)
#             pdf.cell(cell_width, cell_height, "Column B", ln=1)
#
#             pdf.set_font("DejaVu", "", 12)
#             for a, b in zip(colA, colB):
#                 pdf.cell(cell_width, cell_height, a, ln=0)
#                 pdf.cell(cell_width, cell_height, b, ln=1)
#             pdf.ln(3)
#
#         else:
#             pdf.multi_cell(0, 8, str(answer))
#             pdf.ln(2)
#
#     return pdf

import os
import re
import base64
import tempfile
import html

from io import BytesIO
from PIL import Image

try:
    import cairosvg
except ImportError:
    cairosvg = None


# ============================================================
# MAPBUDDYAI PDF CONFIGURATION
# ============================================================

PDF_FONT = "DejaVu"

PAGE_MARGIN = 15
BOTTOM_MARGIN = 18

BODY_FONT_SIZE = 10
QUESTION_FONT_SIZE = 10.5

LINE_HEIGHT = 7
WRITING_LINE_GAP = 8

PURPLE = (112, 71, 235)
BLUE = (55, 91, 220)
LIGHT_PURPLE = (246, 243, 255)
DARK_TEXT = (45, 48, 65)
MUTED_TEXT = (105, 110, 125)
LINE_COLOUR = (195, 195, 210)


# ============================================================
# 1. REGISTER FONTS AND PREPARE PDF
# ============================================================

def setup_worksheet_pdf(title):
    """
    Initialise the existing PDFWithHeader class.

    Font registration happens before add_page(), because the
    PDF header may use the registered font.
    """

    pdf = PDFWithHeader(title=title)

    pdf.add_font(
        PDF_FONT,
        "",
        "fonts/DejaVuSans.ttf",
        uni=True
    )

    pdf.add_font(
        PDF_FONT,
        "B",
        "fonts/DejaVuSans-Bold.ttf",
        uni=True
    )

    pdf.set_margins(
        PAGE_MARGIN,
        PAGE_MARGIN,
        PAGE_MARGIN
    )

    pdf.set_auto_page_break(
        auto=True,
        margin=BOTTOM_MARGIN
    )

    pdf.set_text_color(*DARK_TEXT)
    pdf.set_draw_color(*LINE_COLOUR)

    return pdf


# ============================================================
# 2. TEXT AND HTML HELPERS
# ============================================================

def clean_question_html(value):
    """
    Convert basic HTML question content into readable text.

    Embedded Base64 images are removed separately before this
    function is called.
    """

    if value is None:
        return ""

    text = str(value)

    # Preserve basic paragraph breaks.
    text = re.sub(
        r"<\s*br\s*/?\s*>",
        "\n",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"</\s*(p|div|li)\s*>",
        "\n",
        text,
        flags=re.IGNORECASE
    )

    # Remove remaining HTML tags.
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities.
    text = html.unescape(text)

    # Normalise whitespace without removing paragraph breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_question_images(value):
    """
    Extract embedded Base64 image data URLs from question HTML.

    Supports PNG, JPEG, GIF, WebP and SVG data URLs.
    SVG conversion requires cairosvg.
    """

    if not value:
        return []

    pattern = (
        r"""<img\b[^>]*?\bsrc\s*=\s*"""
        r"""(["'])(data:image/.*?;base64,.*?)\1"""
    )

    matches = re.findall(
        pattern,
        str(value),
        flags=re.IGNORECASE | re.DOTALL
    )

    return [match[1] for match in matches]


def extract_instructions(data):
    """
    Get instructions from the dedicated JSON field.

    If instructions are embedded in the header, extract them
    as a fallback.
    """

    instructions = data.get("instructions")

    if instructions:
        return clean_question_html(instructions)

    header = str(data.get("header") or "")

    match = re.search(
        r"Instructions\s*:\s*(.*)",
        header,
        flags=re.IGNORECASE | re.DOTALL
    )

    if match:
        return clean_question_html(match.group(1))

    return ""


# ============================================================
# 3. WORKSHEET TITLE AND INSTRUCTIONS
# ============================================================

def add_worksheet_title(pdf, data):
    """
    Render the worksheet title with automatic line wrapping.
    Long titles are allowed to occupy multiple lines.
    """

    title = str(
        data.get("title")
        or data.get("header")
        or "Worksheet"
    ).strip()

    # Remove an embedded Instructions section from the title.
    title = re.split(
        r"\s*Instructions\s*:",
        title,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0].strip()

    pdf.set_font(PDF_FONT, "B", 17)
    pdf.set_text_color(*PURPLE)

    pdf.multi_cell(
        0,
        8,
        title,
        align="L"
    )

    pdf.ln(2)

    pdf.set_draw_color(*PURPLE)
    pdf.set_line_width(0.7)

    y = pdf.get_y()

    pdf.line(
        PAGE_MARGIN,
        y,
        pdf.w - PAGE_MARGIN,
        y
    )

    pdf.set_line_width(0.2)
    pdf.set_draw_color(*LINE_COLOUR)

    pdf.ln(5)


def add_instructions(pdf, instructions):
    """
    Render instructions inside a light purple section.

    The box height is calculated from the wrapped text.
    """

    if not instructions:
        return

    pdf.set_font(PDF_FONT, "B", 10)
    pdf.set_text_color(*PURPLE)

    pdf.cell(
        0,
        6,
        "INSTRUCTIONS",
        ln=1
    )

    pdf.set_font(PDF_FONT, "", 9.5)
    pdf.set_text_color(*DARK_TEXT)

    # Use multi_cell's built-in wrapping.
    pdf.multi_cell(
        0,
        5.5,
        instructions
    )

    pdf.ln(4)


# ============================================================
# 4. STUDENT INFORMATION
# ============================================================

def add_student_info(pdf, data):
    """
    Render student details in a compact two-row layout.
    """

    student_name = str(
        data.get("student_name") or "__________"
    )

    date = str(
        data.get("date") or "__________"
    )

    grade = str(
        data.get("grade") or ""
    )

    subject = str(
        data.get("subject") or ""
    )

    pdf.set_font(PDF_FONT, "", 10)
    pdf.set_text_color(*DARK_TEXT)

    half_width = (pdf.w - pdf.l_margin - pdf.r_margin) / 2
    pdf.cell(
        half_width,
        7,
        f"Name: {student_name}",
        ln=0
    )

    pdf.cell(
        half_width,
        7,
        f"Date: {date}",
        ln=1
    )

    pdf.cell(
        half_width,
        7,
        f"Grade: {grade}",
        ln=0
    )

    pdf.cell(
        half_width,
        7,
        f"Subject: {subject}",
        ln=1
    )

    pdf.ln(5)

    pdf.set_draw_color(*LINE_COLOUR)

    y = pdf.get_y()

    pdf.line(
        PAGE_MARGIN,
        y,
        pdf.w - PAGE_MARGIN,
        y
    )

    pdf.ln(6)


# ============================================================
# 5. PAGE-SPACE MANAGEMENT
# ============================================================

def ensure_page_space(pdf, required_height):
    """
    Start a new page when the requested content will not fit.

    Use this before rendering a question and its writing space.
    """

    usable_bottom = pdf.h - BOTTOM_MARGIN

    if pdf.get_y() + required_height > usable_bottom:
        pdf.add_page()


# ============================================================
# 6. QUESTION TYPE AND WRITING SPACE
# ============================================================

def get_writing_line_count(question):
    q_type = str(question.get("type", "")).lower()
    question_text = str(question.get("text", "")).lower()

    if q_type in ["mcq", "match"]:
        return 0

    if q_type in ["fib", "fill in the blanks"]:
        return 1

    if any(word in question_text for word in ["word problem", "explain", "show your working"]):
        return 4

    return 3

def add_writing_lines(pdf, count):
    if count <= 0:
        return

    # Blank writing space only — no horizontal lines
    pdf.ln(count * 25)
# def add_writing_lines(pdf, count):
#     if count <= 0:
#         return
# 
#     pdf.set_draw_color(225, 225, 235)
#     pdf.set_line_width(0.25)
# 
#     for _ in range(count):
#         pdf.ln(7)
#         y = pdf.get_y()
#         pdf.line(
#             pdf.l_margin,
#             y,
#             pdf.w - pdf.r_margin,
#             y
#         )
# 
#     pdf.ln(4)

# ============================================================
# 7. QUESTION OPTIONS
# ============================================================

def add_question_options(pdf, question):
    """
    Render MCQ, FIB and legacy Match question options.
    """

    options = question.get("options")

    if not options:
        return

    pdf.set_font(PDF_FONT, "", BODY_FONT_SIZE)
    pdf.set_text_color(*DARK_TEXT)

    # Legacy matching question format.
    if isinstance(options, dict):

        column_a = options.get("ColumnA", [])
        column_b\
            = options.get("ColumnB", [])

        if not column_a and not column_b:
            return

        ensure_page_space(pdf, 12)

        column_width = pdf.epw / 2

        pdf.set_font(PDF_FONT, "B", 10)
        pdf.set_text_color(*BLUE)

        pdf.cell(
            column_width,
            7,
            "Column A",
            ln=0
        )

        pdf.cell(
            column_width,
            7,
            "Column B",
            ln=1
        )

        pdf.set_font(PDF_FONT, "", 10)
        pdf.set_text_color(*DARK_TEXT)

        rows = max(
            len(column_a),
            len(column_b)
        )

        for index in range(rows):

            a = (
                str(column_a[index])
                if index < len(column_a)
                else ""
            )

            b = (
                str(column_b[index])
                if index < len(column_b)
                else ""
            )

            # Allow each row to move to a new page.
            ensure_page_space(pdf, 8)

            pdf.cell(
                column_width,
                7,
                a,
                ln=0
            )

            pdf.cell(
                column_width,
                7,
                b,
                ln=1
            )

        pdf.ln(3)

        return

    # Standard list of MCQ or FIB options.
    if isinstance(options, list):

        for index, option in enumerate(options):

            option_text = clean_question_html(option)

            if not option_text:
                continue

            ensure_page_space(pdf, 8)

            label = chr(65 + index) if index < 26 else str(index + 1)

            pdf.set_x(PAGE_MARGIN + 8)

            pdf.set_font(PDF_FONT, "", 10)

            pdf.multi_cell(
                0,
                6,
                f"{label}.  {option_text}"
            )

        pdf.ln(2)

    # Support a single string option if encountered.
    elif isinstance(options, str):

        pdf.set_x(PAGE_MARGIN + 8)

        pdf.multi_cell(
            0,
            6,
            clean_question_html(options)
        )

        pdf.ln(2)


# ============================================================
# 8. EMBEDDED QUESTION IMAGES
# ============================================================

def add_question_images(pdf, question, image_data_urls):
    """
    Decode and render embedded Base64 images.

    SVG files are converted to PNG when CairoSVG is available.
    Temporary files are removed automatically.
    """

    for image_data_url in image_data_urls:

        try:
            header, encoded = image_data_url.split(",", 1)

            image_bytes = base64.b64decode(
                encoded,
                validate=True
            )

            if "image/svg+xml" in header.lower():

                if cairosvg is None:
                    print(
                        "Skipping SVG image: "
                        "CairoSVG is not installed."
                    )
                    continue

                image_bytes = cairosvg.svg2png(
                    bytestring=image_bytes
                )

            # Verify and normalise the image.
            with Image.open(BytesIO(image_bytes)) as source:
                source.load()

                image = source.convert("RGBA")

                buffer = BytesIO()

                image.save(
                    buffer,
                    format="PNG"
                )

                png_bytes = buffer.getvalue()

            # Use a managed temporary file.
            with tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False
            ) as temp_file:

                temp_path = temp_file.name
                temp_file.write(png_bytes)

            try:
                ensure_page_space(pdf, 40)

                pdf.image(
                    temp_path,
                    w=min(75, pdf.epw),
                    keep_aspect_ratio=True
                )

                pdf.ln(4)

            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as exc:
            # Keep a single invalid image from stopping the
            # generation of the entire worksheet.
            print(
                f"Could not render image for question "
                f"{question.get('id', '?')}: {exc}"
            )


# ============================================================
# 9. RENDER A SINGLE QUESTION
# ============================================================

def add_question(pdf, question):
    """
    Render a complete question, options, images and writing lines.
    """

    question_id = question.get("id", "")
    question_text_html = str(
        question.get("text") or ""
    )

    # Extract images before stripping HTML.
    image_data_urls = extract_question_images(
        question_text_html
    )

    # Remove image tags from the printable question text.
    text_without_images = re.sub(
        r"<img\b[^>]*>",
        "",
        question_text_html,
        flags=re.IGNORECASE | re.DOTALL
    )

    question_text = clean_question_html(
        text_without_images
    )

    # Avoid splitting the question heading and its text.
    ensure_page_space(pdf, 18)

    # Question number.
    pdf.set_font(
        PDF_FONT,
        "B",
        QUESTION_FONT_SIZE
    )

    pdf.set_text_color(*PURPLE)

    question_label = f"Q{question_id}."

    pdf.cell(
        13,
        7,
        question_label,
        ln=0
    )

    # Question text.
    pdf.set_font(
        PDF_FONT,
        "",
        QUESTION_FONT_SIZE
    )

    pdf.set_text_color(*DARK_TEXT)

    pdf.multi_cell(
        0,
        LINE_HEIGHT,
        question_text
    )

    pdf.ln(2)

    # Options.
    add_question_options(
        pdf,
        question
    )

    # Images.
    add_question_images(
        pdf,
        question,
        image_data_urls
    )

    # Dedicated writing space.
    writing_lines = get_writing_line_count(
        question
    )

    if writing_lines > 0:

        pdf.set_font(
            PDF_FONT,
            "B",
            9
        )

        pdf.set_text_color(*MUTED_TEXT)

        pdf.cell(
            0,
            6,
            "Working / Answer:",
            ln=1
        )

        pdf.set_text_color(*DARK_TEXT)

        add_writing_lines(
            pdf,
            writing_lines
        )

    else:
        pdf.ln(4)

    # Subtle divider between questions.
    pdf.set_draw_color(225, 225, 235)

    y = pdf.get_y()

    pdf.line(
        PAGE_MARGIN,
        y,
        pdf.w - PAGE_MARGIN,
        y
    )

    pdf.ln(6)


# ============================================================
# 10. ANSWER KEY
# ============================================================

def add_answer_key(pdf, data):
    """
    Render the answer key on a new page.

    Supports:
      - Standard text answers
      - Matching question answers
      - Step-by-step solutions
    """

    answers = data.get("answer_key", [])

    if not answers:
        return

    # Always start the answer key on a new page.
    pdf.add_page()

    pdf.set_font(
        PDF_FONT,
        "B",
        18
    )

    pdf.set_text_color(*PURPLE)

    pdf.cell(
        0,
        10,
        "Answer Key",
        ln=1
    )

    pdf.set_font(
        PDF_FONT,
        "",
        10
    )

    pdf.set_text_color(*MUTED_TEXT)

    pdf.multi_cell(
        0,
        6,
        "Answers and step-by-step solutions"
    )

    pdf.ln(5)

    for answer_item in answers:

        answer_id = answer_item.get("id", "")

        answer = answer_item.get("answer", "")

        solution = (
            answer_item.get("step_by_step_solution")
            or answer_item.get("solution")
            or answer_item.get("explanation")
            or ""
        )

        # Ensure the answer heading has room.
        ensure_page_space(pdf, 18)

        pdf.set_font(
            PDF_FONT,
            "B",
            11
        )

        pdf.set_text_color(*BLUE)

        pdf.cell(
            0,
            7,
            f"Q{answer_id}",
            ln=1
        )

        # Matching answers.
        if (
            isinstance(answer, dict)
            and "ColumnA" in answer
            and "ColumnB" in answer
        ):

            column_a = answer.get("ColumnA", [])
            column_b = answer.get("ColumnB", [])

            column_width = pdf.epw / 2

            pdf.set_font(
                PDF_FONT,
                "B",
                10
            )

            pdf.set_text_color(*PURPLE)

            pdf.cell(
                column_width,
                7,
                "Column A",
                ln=0
            )

            pdf.cell(
                column_width,
                7,
                "Column B",
                ln=1
            )

            pdf.set_font(
                PDF_FONT,
                "",
                10
            )

            pdf.set_text_color(*DARK_TEXT)

            rows = max(
                len(column_a),
                len(column_b)
            )

            for index in range(rows):

                a = (
                    str(column_a[index])
                    if index < len(column_a)
                    else ""
                )

                b = (
                    str(column_b[index])
                    if index < len(column_b)
                    else ""
                )

                ensure_page_space(pdf, 8)

                pdf.cell(
                    column_width,
                    7,
                    a,
                    ln=0
                )

                pdf.cell(
                    column_width,
                    7,
                    b,
                    ln=1
                )

        else:

            if isinstance(answer, (dict, list)):
                answer_text = str(answer)
            else:
                answer_text = clean_question_html(answer)

            pdf.set_font(
                PDF_FONT,
                "B",
                10
            )

            pdf.set_text_color(*DARK_TEXT)

            pdf.multi_cell(
                0,
                7,
                f"Answer: {answer_text}"
            )

        # Step-by-step solution.
        if solution:

            ensure_page_space(pdf, 15)

            pdf.ln(2)

            pdf.set_font(
                PDF_FONT,
                "B",
                9.5
            )

            pdf.set_text_color(*PURPLE)

            pdf.cell(
                0,
                6,
                "Step-by-step solution",
                ln=1
            )

            pdf.set_font(
                PDF_FONT,
                "",
                10
            )

            pdf.set_text_color(*DARK_TEXT)

            if isinstance(solution, list):

                for step_number, step in enumerate(
                    solution,
                    start=1
                ):

                    ensure_page_space(pdf, 8)

                    step_text = clean_question_html(step)

                    pdf.multi_cell(
                        0,
                        6,
                        f"{step_number}. {step_text}"
                    )

            else:

                solution_text = clean_question_html(
                    solution
                )

                pdf.multi_cell(
                    0,
                    6,
                    solution_text
                )

        pdf.ln(5)

        # Subtle divider between answers.
        pdf.set_draw_color(225, 225, 235)

        y = pdf.get_y()

        pdf.line(
            PAGE_MARGIN,
            y,
            pdf.w - PAGE_MARGIN,
            y
        )

        pdf.ln(5)


# ============================================================
# 11. MAIN PDF GENERATION FUNCTION
# ============================================================

def create_pdf_from_json(data):
    """
    Generate a MapBuddyAI worksheet PDF.

    Expected data fields:
        title / header
        instructions
        student_name
        date
        grade
        subject
        questions
        answer_key
    """

    if not isinstance(data, dict):
        raise ValueError(
            "Worksheet data must be a dictionary."
        )

    title = str(
        data.get("title")
        or data.get("header")
        or "Worksheet"
    )

    # Prepare PDF and register fonts.
    pdf = setup_worksheet_pdf(title)

    # First page.
    pdf.add_page()

    # Worksheet title.
    add_worksheet_title(
        pdf,
        data
    )

    # Instructions.
    instructions = extract_instructions(data)

    add_instructions(
        pdf,
        instructions
    )

    # Student details.
    add_student_info(
        pdf,
        data
    )

    # Questions.
    questions = data.get("questions", [])

    for question in questions:

        if not isinstance(question, dict):
            continue

        add_question(
            pdf,
            question
        )

    # Answer key.
    add_answer_key(
        pdf,
        data
    )

    return pdf
def remove_table_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)

    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top','left','bottom','right','insideH','insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(ns.qn('w:val'), 'nil')  # correct namespace usage
        tblBorders.append(border)

    tblPr.append(tblBorders)
def remove_table_borders(table):
    # Optional: function to remove table borders
    for row in table.rows:
        for cell in row.cells:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcBorders = OxmlElement('w:tcBorders')
            for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
                border = OxmlElement(f'w:{border_name}')
                border.set(qn('w:val'), 'nil')
                tcBorders.append(border)
            tcPr.append(tcBorders)
# Add your remove_table_borders function here
def add_docx_writing_space(doc, count):
    if count <= 0:
        return

    # Blank writing space only — no horizontal lines
    paragraph = doc.add_paragraph("")
    paragraph.paragraph_format.space_after = Pt(count * 35)
def add_page_number(footer_para):
    run = footer_para.add_run("Page ")
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')

    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = 'PAGE'

    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'separate')

    fldChar3 = OxmlElement('w:fldChar')
    fldChar3.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)

def create_docx_from_json(data):
    doc = Document()
    title = data.get("title") or data.get("header", "Worksheet")

    # ---------------- Page Setup ----------------
    section = doc.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.7)
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.35)

    # ---------------- Header: MapBuddyAI Branding ----------------
    header = section.header
    header_para = header.paragraphs[0]
    header_para.clear()
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_para.paragraph_format.space_after = Pt(6)

    brand_run = header_para.add_run("MapBuddyAI")
    brand_run.bold = True
    brand_run.font.name = "Arial"
    brand_run.font.size = Pt(10)
    brand_run.font.color.rgb = RGBColor(105, 75, 190)

    # Subtle divider below header
    pPr = header_para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom_border = OxmlElement("w:bottom")
    bottom_border.set(qn("w:val"), "single")
    bottom_border.set(qn("w:sz"), "6")
    bottom_border.set(qn("w:space"), "4")
    bottom_border.set(qn("w:color"), "DCD5F5")
    pBdr.append(bottom_border)
    pPr.append(pBdr)

    # ---------------- Footer: Divider and Page Number ----------------
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.clear()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_para.paragraph_format.space_before = Pt(4)

    # Divider above footer
    pPr = footer_para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    top_border = OxmlElement("w:top")
    top_border.set(qn("w:val"), "single")
    top_border.set(qn("w:sz"), "6")
    top_border.set(qn("w:space"), "4")
    top_border.set(qn("w:color"), "DCD5F5")
    pBdr.append(top_border)
    pPr.append(pBdr)

    footer_run = footer_para.add_run("MapBuddyAI  |  Page ")
    footer_run.font.name = "Arial"
    footer_run.font.size = Pt(8)
    footer_run.font.color.rgb = RGBColor(130, 130, 145)

    # Dynamic Word page number field
    page_field = OxmlElement("w:fldSimple")
    page_field.set(qn("w:instr"), "PAGE")
    footer_para._p.append(page_field)

    # ---------------- Student Information ----------------
    student_name = data.get("student_name", "__________")
    date = data.get("date", "__________")
    grade = data.get("grade", "")
    subject = data.get("subject", "")

    # Name / Date row
    table1 = doc.add_table(rows=1, cols=2)
    table1.autofit = True
    table1.cell(0, 0).text = f"Name: {student_name}"
    table1.cell(0, 1).text = f"Date: {date}"
    remove_table_borders(table1)

    # Grade / Subject row
    table2 = doc.add_table(rows=1, cols=2)
    table2.autofit = True
    table2.cell(0, 0).text = f"Grade: {grade}"
    table2.cell(0, 1).text = f"Subject: {subject}"
    remove_table_borders(table2)

    # ---------------- Worksheet Title ----------------
    doc.add_paragraph("")

    title_para = doc.add_paragraph(title)
    title_para.style = "Heading 1"
    title_para.paragraph_format.space_after = Pt(12)

    # ---------------- Questions ----------------
    for q in data.get("questions", []):
        question_text = q.get("text", "")

        img_matches = re.findall(
            r'<img.*?src="(data:image/[^"]+)".*?>',
            question_text
        )

        text_only = re.sub(r'<img.*?>', '', question_text).strip()

        para = doc.add_paragraph(f"{q.get('id', '')}. {text_only}")
        para.paragraph_format.space_after = Pt(12)
        writing_space = get_writing_line_count(q)
        add_docx_writing_space(doc, writing_space)
        # Match-type questions
        if q.get("type") == "Match" and q.get("options"):
            colA = q["options"].get("ColumnA", [])
            colB = q["options"].get("ColumnB", [])
            rows = max(len(colA), len(colB))

            table = doc.add_table(rows=1, cols=2)
            table.autofit = True
            remove_table_borders(table)

            table.cell(0, 0).text = "Column A"
            table.cell(0, 1).text = "Column B"

            for i in range(rows):
                row_cells = table.add_row().cells
                row_cells[0].text = colA[i] if i < len(colA) else ""
                row_cells[1].text = colB[i] if i < len(colB) else ""

            doc.add_paragraph("")

        # Other question options
        elif q.get("options"):
            for opt in q["options"]:
                opt_para = doc.add_paragraph(f"  - {opt}")
                opt_para.paragraph_format.space_after = Pt(6)

        # Embedded images
        for img_data_url in img_matches:
            image_header, encoded = img_data_url.split(",", 1)
            img_bytes = base64.b64decode(encoded)

            if image_header.startswith("data:image/svg+xml"):
                png_bytes = cairosvg.svg2png(bytestring=img_bytes)
                image_stream = io.BytesIO(png_bytes)
            else:
                image_stream = io.BytesIO(img_bytes)

            doc.add_picture(image_stream, width=Inches(2))

        doc.add_paragraph("")

    # ---------------- Answer Key ----------------
    doc.add_page_break()
    doc.add_heading("Answer Key", level=2)

    for ans in data.get("answer_key", []):
        para = doc.add_paragraph(f"{ans.get('id', '')}:")
        para.paragraph_format.space_after = Pt(6)

        answer = ans.get("answer")

        # Matching-question answers
        if (
            isinstance(answer, dict)
            and "ColumnA" in answer
            and "ColumnB" in answer
        ):
            colA = answer["ColumnA"]
            colB = answer["ColumnB"]
            rows = max(len(colA), len(colB))

            table = doc.add_table(rows=1, cols=2)
            table.autofit = True
            remove_table_borders(table)

            table.cell(0, 0).text = "Column A"
            table.cell(0, 1).text = "Column B"

            for i in range(rows):
                row_cells = table.add_row().cells
                row_cells[0].text = colA[i] if i < len(colA) else ""
                row_cells[1].text = colB[i] if i < len(colB) else ""

            doc.add_paragraph("")

        else:
            ans_para = doc.add_paragraph(str(answer or ""))
            ans_para.paragraph_format.space_after = Pt(6)

    return doc


# from docx.shared import Inches, Pt, RGBColor
# from docx.enum.text import WD_ALIGN_PARAGRAPH
# from docx.oxml import OxmlElement
# from docx.oxml.ns import qn

def add_bottom_border(paragraph, color="DCD5F5", size="6"):
    """Add a subtle divider below a paragraph."""
    p = paragraph._p
    pPr = p.get_or_add_pPr()

    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)

    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)

    pBdr.append(bottom)


def setup_docx_header_footer(section):
    """Set up repeating MapBuddyAI branding and page numbering."""

    # ---------------- Header ----------------
    header = section.header
    header_para = header.paragraphs[0]
    header_para.clear()
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_para.paragraph_format.space_before = Pt(0)
    header_para.paragraph_format.space_after = Pt(6)

    run = header_para.add_run("MapBuddyAI")
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(105, 75, 190)

    add_bottom_border(header_para)

    # ---------------- Footer ----------------
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.clear()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_para.paragraph_format.space_before = Pt(4)
    footer_para.paragraph_format.space_after = Pt(0)

    add_bottom_border(footer_para, color="DCD5F5")

    run = footer_para.add_run("MapBuddyAI  |  Page ")
    run.font.name = "Arial"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(130, 130, 145)

    # Dynamic page number field
    page_field = OxmlElement("w:fldSimple")
    page_field.set(qn("w:instr"), "PAGE")
    footer_para._p.append(page_field)


@app.route("/mindmap")
def mindmap():
    return render_template("mindmap.html")
@app.route("/newmap")
def newmap():
    return render_template("newmap.html")
@app.route("/worksheet_input")
def worksheet_input():
    return render_template(""
                           "worksheet_input.html")
@app.route("/worksheet_output")
def worksheet_output():
    return render_template("worksheet_output.html")

@app.route("/search_images", methods=["GET"])
def search_images():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    url = "https://pixabay.com/api/"
    params = {
        "key": pixabay_key,
        "q": query,
        "image_type": "vector",
        "category": "education",
        "per_page": 10,
        "safesearch": "true"
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Return only relevant info
        images = [{"url": hit["largeImageURL"], "tags": hit["tags"]} for hit in data.get("hits", [])]

        return jsonify(images)

    except requests.exceptions.RequestException as e:
        print("Error in /search_images:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/openverse")
# def openverse_proxy():
#     query = request.args.get("q", "")
#     limit = request.args.get("limit", 5, type=int)
#
#     url = f"https://api.openverse.engineering/v1/images?q={query}&per_page={limit}&format=json"
#     headers = {"User-Agent": "Mozilla/5.0"}  # required for proper response
#
#     try:
#         resp = requests.get(url, headers=headers)
#         resp.raise_for_status()
#         data = resp.json()
#
#         images = []
#         for img in data.get("results", []):
#             # Use actual thumbnail or full image URL from Openverse
#             image_url = img.get("thumbnail_url") or img.get("url")
#             if not image_url:
#                 continue
#
#             images.append({
#                 "url": image_url,
#                 "title": img.get("title", "Openverse"),
#                 "source": "Openverse"
#             })
#         print(f"images {images}")
#         return jsonify({"results": images})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
def openverse_proxy():
    query = request.args.get("q", "")
    limit = request.args.get("limit", 5, type=int)

    url = f"https://api.openverse.engineering/v1/images?q={query}&per_page={limit}&format=json"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        images = []
        for img in data.get("results", []):
            # Use actual thumbnail or full image URL
            image_url = img.get("thumbnail_url") or img.get("url")
            if not image_url:
                continue

            title = img.get("title", "").lower()
            description = (img.get("description") or "").lower()

            # Simple filter: ignore images if title/description contains irrelevant keywords
            irrelevant_keywords = ["party", "friends", "concert", "beach", "event", "flyer", "festival"]
            if any(k in title or k in description for k in irrelevant_keywords):
                continue

            images.append({
                "url": image_url,
                "title": img.get("title", "Openverse"),
                "source": "Openverse"
            })

        return jsonify({"results": images})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/proxy-image")
def proxy_image():
    url = request.args.get("url")
    if not url:
        return "Missing URL", 400

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ProxyImage/1.0)"}
        r = requests.get(url, headers=headers, timeout=10, stream=True)
        r.raise_for_status()

        return Response(
            r.content,
            mimetype=r.headers.get("Content-Type", "image/png")  # fallback default
        )
    except requests.exceptions.RequestException as e:
        return f"Error fetching image: {e}", 502
    except Exception as e:
        return f"Internal error: {e}", 500
@app.route("/suggest", methods=["POST"])

# ============================================================
# SUGGEST SUBTOPICS
# ============================================================
@app.route("/suggest", methods=["POST"])

def suggest():

    data = request.get_json() or {}

    grade = data.get("grade", "")
    subject = data.get("subject", "")
    topic = data.get("topic", "")
    curriculum = data.get("curriculum", "")

    print("\n================================")
    print("🔥 /suggest")
    print("Curriculum:", curriculum)
    print("Grade:", grade)
    print("Subject:", subject)
    print("Topic:", topic)
    print("================================")

    # ==================================================
    # LOAD CURRICULUM
    # ==================================================

    curriculum_data = load_curriculum_json(
    curriculum,
    grade,
    subject
)

    if not curriculum_data:
        return jsonify({
            "error": "Curriculum knowledge could not be loaded."
        }), 500

    # ==================================================
    # FIND TOPIC
    # ==================================================

    topics = curriculum_data.get("topics", {})

    topic_input = topic.strip().lower()
    topic_key = topic_input.replace(" ", "_")

    curriculum_knowledge = topics.get(topic_key)

    # --------------------------------------------------
    # Match display_name
    # --------------------------------------------------

    if not curriculum_knowledge:

        for key, value in topics.items():

            display_name = value.get(
                "display_name",
                ""
            ).strip().lower()

            if display_name == topic_input:

                topic_key = key
                curriculum_knowledge = value
                break

    # --------------------------------------------------
    # Match singular / plural
    #
    # fraction -> fractions
    # --------------------------------------------------

    if not curriculum_knowledge:

        normalized_input = topic_input.rstrip("s")

        for key, value in topics.items():

            normalized_key = key.lower().rstrip("s")

            display_name = value.get(
                "display_name",
                ""
            ).strip().lower().rstrip("s")

            if (
                normalized_input == normalized_key
                or normalized_input == display_name
            ):

                topic_key = key
                curriculum_knowledge = value
                break

    # ==================================================
    # TOPIC NOT FOUND → GEMINI FALLBACK
    # ==================================================

    if not curriculum_knowledge:

        print("⚠️ Topic not found:", topic)
        print("🤖 Using Gemini fallback...")

        fallback_prompt = f"""
You are a curriculum-aware worksheet intent analyzer.

The parent selected:

Curriculum:
{curriculum}

Grade:
{grade}

Subject:
{subject}

Topic:
{topic}

The topic was NOT found in the application's curriculum
knowledge base.

Your job is to determine whether this topic is reasonably
appropriate for the selected curriculum, grade and subject.

STRICT RULES:

1. Respect the selected curriculum.
2. Respect the selected grade.
3. Respect the selected subject.
4. Do not move the topic into another subject.
5. Do not introduce advanced concepts inappropriate for
   the selected grade.
6. If the topic is relevant, generate exactly 4 useful
   subtopics.
7. If the topic is unrelated, return no subtopics.
8. Do not claim AI-generated topics are official curriculum
   topics.

If the topic is relevant, generate:

- exactly 4 subtopics
- exactly 4 practice-focus options

Each subtopic must contain:

- label
- ruleset_key
- question_type

Because the topic is not currently in the curriculum
knowledge base, ruleset_key must be an empty string.

Practice focus describes HOW to practise the topic.

If the topic is unrelated, return empty arrays.

Return ONLY valid JSON.

For a relevant topic:

{{
    "subtopics": [
        {{
            "label": "...",
            "ruleset_key": "",
            "question_type": "..."
        }},
        {{
            "label": "...",
            "ruleset_key": "",
            "question_type": "..."
        }},
        {{
            "label": "...",
            "ruleset_key": "",
            "question_type": "..."
        }},
        {{
            "label": "...",
            "ruleset_key": "",
            "question_type": "..."
        }}
    ],
    "practice_focus": [
        "...",
        "...",
        "...",
        "..."
    ],
    "status": "ai_fallback",
    "message": "Suggestions generated because this topic is not yet in the curriculum knowledge base."
}}

For an unrelated topic:

{{
    "subtopics": [],
    "practice_focus": [],
    "status": "unrelated",
    "message": "The requested topic does not appear suitable for the selected subject and grade."
}}
"""

        try:

            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=fallback_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=1200,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(
                        thinking_level="MINIMAL"
                    )
                )
            )

            print("🤖 Gemini fallback response:")
            print(response.text)

            result = json.loads(response.text)

            return jsonify(result)

        except Exception as e:

            print("❌ Gemini fallback error:", e)

            return jsonify({
                "subtopics": [],
                "practice_focus": [],
                "status": "error",
                "error": str(e)
            }), 500

    # ==================================================
    # TOPIC FOUND → USE CURRICULUM KNOWLEDGE
    # ==================================================

    print("✅ Matched topic:", topic_key)

    print(
        "Curriculum knowledge:",
        json.dumps(
            curriculum_knowledge,
            indent=2,
            ensure_ascii=False
        )
    )

    prompt = f"""
You are a Singapore MOE Primary worksheet intent analyzer.

The parent selected:

Curriculum:
{curriculum}

Grade:
{grade}

Subject:
{subject}

Topic:
{topic}

The following curriculum knowledge is authoritative:

{json.dumps(
    curriculum_knowledge,
    indent=2,
    ensure_ascii=False
)}

STRICT RULES:

1. Follow the supplied curriculum knowledge strictly.
2. Do not introduce concepts outside the supplied knowledge.
3. Do not introduce concepts from another grade.
4. Follow all numerical and content restrictions.
5. Generate exactly 4 suitable subtopics.
6. Generate exactly 4 practice-focus options.
7. Subtopics describe WHAT to practise.
8. Practice focus describes HOW to practise.
9. ruleset_key must begin with the topic key.

Topic key:

{topic_key}

Return ONLY valid JSON.

{{
    "subtopics": [
        {{
            "label": "...",
            "ruleset_key": "...",
            "question_type": "..."
        }},
        {{
            "label": "...",
            "ruleset_key": "...",
            "question_type": "..."
        }},
        {{
            "label": "...",
            "ruleset_key": "...",
            "question_type": "..."
        }},
        {{
            "label": "...",
            "ruleset_key": "...",
            "question_type": "..."
        }}
    ],
    "practice_focus": [
        "...",
        "...",
        "...",
        "..."
    ],
    "status": "curriculum",
    "message": "Suggestions generated using the curriculum knowledge base."
}}
"""

    # ==================================================
    # GEMINI CALL
    # ==================================================

    try:

        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1200,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level="MINIMAL"
                )
            )
        )

        print("\n🔥 Gemini /suggest result:")
        print(response.text)

        result = json.loads(response.text)

        return jsonify(result)

    except Exception as e:

        print("❌ Gemini suggestion error:", e)

        return jsonify({
            "subtopics": [],
            "practice_focus": [],
            "status": "error",
            "error": str(e)
        }), 500


#
# def suggest():
#
#     data = request.get_json()
#
#     grade = data.get("grade", "")
#     subject = data.get("subject", "")
#     topic = data.get("topic", "")
#     curriculum = data.get("curriculum", "")
#
#     print("\n================ SUGGEST REQUEST ================")
#     print("Grade:", grade)
#     print("Subject:", subject)
#     print("Topic:", topic)
#     print("Curriculum:", curriculum)
#     print("==================================================\n")
#
#     prompt = f"""
# You are a worksheet intent analyzer for primary school students.
#
# Suggest exactly 4 suitable subtopics and exactly 4 suitable
# practice-focus options for a {grade} student studying {subject}
# on the topic "{topic}" for the {curriculum} curriculum.
#
# IMPORTANT:
#
# The main topic is "{topic}".
#
# Do NOT use the main topic itself as a subtopic.
#
# ================ SUBTOPICS ================
#
# For EACH subtopic, return:
#
# - label: short, teacher-friendly name
# - ruleset_key: machine-friendly identifier
# - question_type: recommended question type
#
# Rules for subtopics:
#
# - Suggestions must be directly related to the topic.
# - Suggestions must be appropriate for the student's grade.
# - Follow the {curriculum} curriculum level.
# - Do not repeat the main topic.
# - Use concise labels.
# - If the topic is pronouns, the ruleset_key MUST start with "pronouns.".
#
# ================ PRACTICE FOCUS ================
#
# Suggest exactly 4 practice-focus options that make sense
# for this subject, grade, curriculum and topic.
#
# Practice focus describes HOW the student should practise,
# not WHAT the student should learn.
#
# Examples:
#
# Math:
# - Word problems
# - Reasoning
# - Multi-step questions
# - Visual / bar model
#
# Science:
# - Concept understanding
# - Application
# - Reasoning
# - Diagram labelling
#
# English:
# - Grammar
# - Vocabulary
# - Sentence construction
# - Reading comprehension
#
# IMPORTANT:
# These are only examples. Choose practice-focus options
# that are genuinely appropriate for the selected subject,
# grade and topic.
#
# Do not use "Word problems" for subjects where it does not
# make sense.
#
# ================ OUTPUT RULES ================
#
# - Return exactly 4 subtopics.
# - Return exactly 4 practice-focus options.
# - Output STRICT JSON only.
# - No explanations.
# - No markdown.
# - No code fences.
#
# Output format:
#
# {{
#   "subtopics": [
#     {{
#       "label": "",
#       "ruleset_key": "",
#       "question_type": ""
#     }}
#   ],
#   "practice_focus": [
#     ""
#   ]
# }}
# """
#
#     try:
#
#         config = types.GenerateContentConfig(
#             max_output_tokens=1500,
#             response_mime_type="application/json",
#             thinking_config=types.ThinkingConfig(
#                 thinking_level="MINIMAL"
#             )
#         )
#
#         response = gemini_client.models.generate_content(
#             model="gemini-3.6-flash",
#             contents=prompt,
#             config=config
#         )
#
#         print("\n================ GEMINI RAW RESPONSE ================")
#         print(response.text)
#         print("======================================================\n")
#
#         result = json.loads(response.text)
#
#         print("\n================ PARSED SUGGESTIONS ================")
#         print(result)
#         print("=====================================================\n")
#
#         # Basic validation
#         if not isinstance(result, dict):
#             raise ValueError("Gemini response is not an object")
#
#         subtopics = result.get("subtopics", [])
#         practice_focus = result.get("practice_focus", [])
#
#         if not isinstance(subtopics, list):
#             raise ValueError("subtopics is not a list")
#
#         if not isinstance(practice_focus, list):
#             raise ValueError("practice_focus is not a list")
#
#         # Keep maximum of 4
#         subtopics = subtopics[:4]
#         practice_focus = practice_focus[:4]
#
#     except Exception as e:
#
#         print("Gemini suggestion error:", e)
#
#         subtopics = []
#         practice_focus = []
#
#     return jsonify({
#         "subtopics": subtopics,
#         "practice_focus": practice_focus
#     })


@app.route("/rephrase_question", methods=["POST"])
def rephrase_question():
    data = request.get_json()
    question_text = data.get("topic")
    grade = data.get("grade", "")
    subject = data.get("subject", "")
    curriculum = data.get("curriculum", "")
    if not question_text:
        return jsonify({"success": False, "error": "No question text provided"}), 400

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }

    prompt = f"""
Rephrase the following question for grade {grade} {subject} students in 3 different ways for worksheets:

{question_text}

Rules:
- Output must ONLY be 3 rephrased questions.
- Do not add explanations or answers.
- Each question should be a short, clear sentence.
- Do not number the questions.

"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            },
            timeout=15
        )

        print(f"prompt {prompt}")

        response.raise_for_status()
        result_json = response.json()

        rephrased_list = []
        for choice in result_json.get("choices", []):
            content = choice.get("message", {}).get("content", "").strip()
            if content:
                lines = [line.strip("-• ").strip() for line in content.split("\n") if line.strip()]
                rephrased_list.extend(lines)

        # fallback
        if not rephrased_list:
            rephrased_list = [
                f"{question_text} (rephrased 1)",
                f"{question_text} (rephrased 2)",
                f"{question_text} (rephrased 3)"
            ]
        print(f"prompt {prompt}")
        print(f"rephrased_list{rephrased_list}")
        return jsonify({"success": True, "rephrases": rephrased_list[:3]})

    except Exception as e:
        print("Groq rephrase error:", e)
        rephrased_list = [
            f"{question_text} (rephrased 1)",
            f"{question_text} (rephrased 2)",
            f"{question_text} (rephrased 3)"
        ]
        return jsonify({"success": True, "rephrases": rephrased_list})

@app.route("/ai_search_suggestions", methods=["POST"])
def ai_search_suggestions():
    data = request.get_json()
    query = data.get("query", "")
    print(f"query {query}")
    if not query:
        return jsonify([])

    prompt = f"""
    You are helping a teacher search for images from Wikimedia, Pixabay, or Openverse.

    Original query: "{query}"

    Task:
    1. Rewrite this query into 5 **short, image-friendly keywords or phrases**.  
    2. Each should be suitable for searching in Wikimedia, Pixabay, or Openverse (no long sentences).  
    3. Focus on simple **educational concepts, diagrams, or objects** likely to exist as images.  
    4. Do not include words like "worksheet", "exercise", "question" – just the core visual keywords.  
    5. Return only a JSON array of strings, no explanation.

    Example:
    Input: "photosynthesis worksheet"
    Output: ["photosynthesis diagram", "plant leaf cells", "sunlight and plants", "chloroplast", "plant energy cycle"]
    """

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        },
        timeout=10
    )

    result = response.json()
    try:
        suggestions = eval(result["choices"][0]["message"]["content"])
    except:
        suggestions = []
    print(f"suggestions {suggestions}")
    return jsonify(suggestions)
@app.route('/main-dashboard')
@login_required
def main_dashboard():
    # User is logged in, render dashboard
    return render_template('main_dashboard.html')
if __name__ == '__main__':
    app.run(debug=False)
    FLASK_ENV = "production"
