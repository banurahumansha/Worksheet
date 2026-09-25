# from exceptiongroup import catch
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash ,send_file
from flask_mail import Mail, Message
import spacy
from dotenv import load_dotenv
import os
import requests
import re
import tempfile
from PyPDF2 import PdfReader  # or usec pdfplumber
import json
import pytesseract
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
import google.generativeai as genai
from io import BytesIO
from docx import Document
from docx.shared import Pt
from flask_login import current_user, login_required , login_user ,UserMixin ,LoginManager
import platform
# from flask_migrate import Migrate
from sqlalchemy import func
from pdf2image import convert_from_path
from pytesseract import image_to_string
import nltk
import nltk
nltk.download('punkt', quiet=True)
from nltk.tokenize import sent_tokenize

load_dotenv()    # Load variables from .env
groq_key = os.getenv("GROQ_API_KEY")
hf_key = os.getenv("HUGGINGFACE_API_KEY")
gpt_key = os.getenv("OPENAI_API_KEY")
gemini_key=os.getenv("GEMINI_API_KEY")
gpt_key = os.getenv("OPENAI_API_KEY")

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


groq_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
genai.configure(api_key=gemini_key)
gpt_client = OpenAI(api_key=gpt_key)

model = genai.GenerativeModel("gemini-2.0-flash")
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
    return render_template('home.html')
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
        username_or_email = request.form.get('username_or_email', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        if user and user.check_password(password):
            if not user.verified:
                flash("Please verify your email before logging in.", "warning")
                return redirect(url_for('login'))

            login_user(user)  # <-- This logs the user in using Flask-Login
            return redirect(url_for('guide'))

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
@login_required
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
        prompt = f"Summarize the following content:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return None

def summarize_with_groq(text, format=None):
    try:
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
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
def extract_text_from_docx(file_stream):
    doc = Document(file_stream)
    return '\n'.join([para.text for para in doc.paragraphs])
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
        common_entities = [item for item, count in counter.most_common(2)]
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

    # Add a class or level attribute to use in styling
    elements.append({
        "data": {
            "id": node_id,
            "label": node["name"],
            "level": level  # Optional: you can use this to assign style via JS later
        },
        "classes": f"level-{level}"  # Cytoscape class for styling
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
            file_name = session.get("filename") or "Manual Input"
            fname = os.path.splitext(file_name)[0]

            # Convert flat dict into hierarchical JSON
            structured_map = create_mindmap_structure(fname, final_mindmap)

        cytoscape_ready_map = convert_to_cytoscape_format(structured_map)

        session.pop('filename', None)

        if action == 'generateMindmap':
            print("🌳 Generating full mind map")
            return jsonify({
                "tree": structured_map,
                "cytoscape": cytoscape_ready_map
            })

        elif action == 'summarizeOnly':
            print("🔹 Summarizing only")
            doc = create_docx_from_nested_tree(structured_map)
            f = BytesIO()
            doc.save(f)
            f.seek(0)

            return send_file(
                f,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                as_attachment=True,
                download_name='mindmap.docx'
            )

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
            "mindmap": cytoscape_ready_map
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


if __name__ == '__main__':
    app.run(debug=False)
    FLASK_ENV = "production"
