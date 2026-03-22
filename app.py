import streamlit as st
import sqlite3
import uuid
import os
import json
import time
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
import PyPDF2
import docx
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import base64
import io
from streamlit_chat_message_history import message_history_container
import streamlit.components.v1 as components

# -------- LOAD API --------
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# -------- DB --------
conn = sqlite3.connect("orion_pro.db", check_same_thread=False)
c = conn.cursor()

# Advanced DB Schema
c.execute("""CREATE TABLE IF NOT EXISTS users(
    username TEXT PRIMARY KEY,
    password_hash TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_premium INTEGER DEFAULT 0
)""")

c.execute("""CREATE TABLE IF NOT EXISTS chats(
    id TEXT PRIMARY KEY,
    username TEXT,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_starred INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0
)""")

c.execute("""CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    role TEXT,
    content TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tokens INTEGER DEFAULT 0,
    model_used TEXT DEFAULT 'llama-3.3-70b'
)""")

c.execute("""CREATE TABLE IF NOT EXISTS user_settings(
    username TEXT PRIMARY KEY,
    theme TEXT DEFAULT 'dark',
    model_preference TEXT DEFAULT 'llama-3.3-70b',
    temperature REAL DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 4000
)""")

c.execute("""CREATE TABLE IF NOT EXISTS feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    message_id INTEGER,
    rating INTEGER,
    comment TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

conn.commit()

# -------- SECURITY & UTILS --------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_avatar(username):
    img = Image.new('RGB', (100, 100), color=(32, 34, 41))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except:
        font = ImageFont.load_default()
    
    # Simple hash-based color and letter
    hash_val = hash(username) % 360
    color = (int(255 * (hash_val/360)), int(255 * ((hash_val+60)%360/360)), int(255 * ((hash_val+120)%360/360)))
    first_letter = username[0].upper()
    bbox = d.textbbox((0, 0), first_letter, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (100 - text_width) / 2
    y = (100 - text_height) / 2
    d.text((x, y), first_letter, font=font, fill=color)
    return img

def get_user_stats(username):
    stats = {}
    stats['total_chats'] = c.execute("SELECT COUNT(*) FROM chats WHERE username=?", (username,)).fetchone()[0]
    stats['total_messages'] = c.execute("SELECT COUNT(*) FROM messages m JOIN chats c ON m.chat_id=c.id WHERE c.username=?", (username,)).fetchone()[0]
    stats['avg_rating'] = c.execute("SELECT AVG(rating) FROM feedback f JOIN messages m ON f.message_id=m.id JOIN chats c ON f.chat_id=c.id WHERE c.username=?", (username,)).fetchone()[0] or 0
    return stats

# -------- AUTHENTICATION --------
if "user" not in st.session_state:
    st.session_state.user = None
    st.session_state.settings = {}

def login_page():
    st.markdown("""
    <style>
    .main-header {
        text-align: center;
        margin-bottom: 3rem;
    }
    .auth-card {
        max-width: 400px;
        margin: 0 auto;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="main-header">
        <h1 style='color: #38bdf8; font-size: 3.5rem; margin-bottom: 1rem;'>🧠 ORION AI</h1>
        <p style='color: #94a3b8; font-size: 1.2rem;'>Advanced AI Assistant for Professionals & Students</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.container():
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["🔐 Login", "📝 Sign Up"])
        
        with tab1:
            user = st.text_input("👤 Username", placeholder="Enter your username")
            pwd = st.text_input("🔒 Password", type="password", placeholder="Enter your password")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🚀 Login", type="primary", use_container_width=True):
                    res = c.execute("SELECT * FROM users WHERE username=? AND password_hash=?", 
                                  (user, hash_password(pwd))).fetchone()
                    if res:
                        st.session_state.user = user
                        # Load user settings
                        settings = c.execute("SELECT * FROM user_settings WHERE username=?", (user,)).fetchone()
                        if settings:
                            st.session_state.settings = {
                                'theme': settings[1],
                                'model': settings[2],
                                'temp': settings[3],
                                'max_tokens': settings[4]
                            }
                        st.success("✅ Welcome back!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid credentials")
        
        with tab2:
            new_user = st.text_input("👤 New Username", placeholder="Choose a username")
            new_pwd = st.text_input("🔒 Password", type="password", placeholder="Create password")
            email = st.text_input("📧 Email (optional)")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("✅ Create Account", type="primary", use_container_width=True):
                    try:
                        c.execute("INSERT INTO users (username, password_hash, email) VALUES (?,?,?)", 
                                (new_user, hash_password(new_pwd), email))
                        c.execute("INSERT INTO user_settings (username) VALUES (?)", (new_user,))
                        conn.commit()
                        st.success("🎉 Account created successfully!")
                        st.info("🔄 Please login now")
                    except sqlite3.IntegrityError:
                        st.error("❌ Username already exists")
        
        st.markdown('</div>', unsafe_allow_html=True)

# -------- ADVANCED AI --------
@st.cache_data(ttl=3600)
def ask_ai(prompt, model="llama-3.3-70b-versatile", temperature=0.7, max_tokens=4000):
    try:
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return res.choices[0].message.content, res.usage.total_tokens
    except Exception as e:
        return f"❌ AI Error: {str(e)}", 0

def analyze_file(file_text):
    """AI-powered file analysis"""
    analysis_prompt = f"""
    Analyze this document and provide:
    1. Summary (3 sentences)
    2. Key topics
    3. Action items
    4. Important numbers/dates
    
    Document: {file_text[:4000]}"""
    
    summary, _ = ask_ai(analysis_prompt)
    return summary

# -------- MAIN APP --------
@st.cache_resource
def load_css():
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * { font-family: 'Inter', sans-serif; }
    
    .main {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
        min-height: 100vh;
    }
    
    .header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 20px;
        margin-bottom: 2rem;
        box-shadow: 0 20px 40px rgba(102, 126, 234, 0.3);
    }
    
    .chat-container {
        background: rgba(255,255,255,0.05);
        backdrop-filter: blur(20px);
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.1);
        padding: 2rem;
        margin-bottom: 2rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, rgba(56,189,248,0.2) 0%, rgba(139,92,246,0.2) 100%);
        border-radius: 16px;
        padding: 1.5rem;
        border: 1px solid rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
    }
    
    .stButton > button {
        border-radius: 12px !important;
        background: linear-gradient(135deg, #38bdf8, #6366f1) !important;
        color: white !important;
        border: none !important;
        font-weight: 600;
        height: 44px;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 25px rgba(56,189,248,0.4) !important;
    }
    
    .stTextInput > div > div > input {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 12px !important;
        color: white !important;
        padding: 12px 16px !important;
    }
    
    .stChatMessage {
        background: rgba(255,255,255,0.02) !important;
        border-radius: 18px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        margin-bottom: 1rem !important;
    }
    
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f0f23 0%, #1a1a2e 100%);
        backdrop-filter: blur(20px);
    }
    
    .starred { color: #fbbf24 !important; }
    </style>
    """

def main_app():
    st.set_page_config(
        page_title="Orion AI Pro",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load CSS
    st.markdown(load_css(), unsafe_allow_html=True)
    
    # HEADER
    st.markdown("""
    <div class="header">
        <div style='display: flex; justify-content: space-between; align-items: center;'>
            <div>
                <h1 style='color: white; margin: 0; font-size: 2.5rem;'>🧠 ORION AI Pro</h1>
                <p style='color: rgba(255,255,255,0.8); margin: 0;'>Advanced AI Assistant | {}</p>
            </div>
            <div style='text-align: right;'>
                <img src="data:image/png;base64,{}" width="50" style='border-radius: 50%;'>
                <div style='color: white; font-weight: 600; margin-top: 0.5rem;'>{}</div>
            </div>
        </div>
    </div>
    """.format(
        datetime.now().strftime("%B %d, %Y"),
        base64.b64encode(generate_avatar(st.session_state.user).tobytes()).decode(),
        st.session_state.user
    ), unsafe_allow_html=True)
    
    # STATS ROW
    stats = get_user_stats(st.session_state.user)
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3 style='color: #38bdf8; margin: 0;'>📊 {stats['total_chats']}</h3>
            <p style='color: rgba(255,255,255,0.7); margin: 0.5rem 0 0 0;'>Total Chats</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3 style='color: #10b981; margin: 0;'>💬 {stats['total_messages']}</h3>
            <p style='color: rgba(255,255,255,0.7); margin: 0.5rem 0 0 0;'>Messages</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <h3 style='color: #f59e0b; margin: 0;'>{stats['avg_rating']:.1f}</h3>
            <p style='color: rgba(255,255,255,0.7); margin: 0.5rem 0 0 0;'>Avg Rating</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        logout_btn = st.button("🚪 Logout", use_container_width=True)
        if logout_btn:
            st.session_state.user = None
            st.rerun()
    
    # SIDEBAR - Enhanced Chat Management
    with st.sidebar:
        st.markdown("## 💾 Chat History")
        
        # Quick Actions
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("➕ New Chat", use_container_width=True):
                chat_id = str(uuid.uuid4())
                c.execute("INSERT INTO chats VALUES (?,?,?,datetime('now'),datetime('now'),0,0)",
                         (chat_id, st.session_state.user, "New Chat"))
                conn.commit()
                st.session_state.chat_id = chat_id
                st.rerun()
        
        with col_s2:
            if st.button("⭐ Starred", use_container_width=True):
                st.session_state.filter_starred = True
                st.rerun()
        
        # Filter
        filter_starred = st.session_state.get('filter_starred', False)
        show_starred = st.checkbox("⭐ Show Starred Only", value=filter_starred)
        if show_starred != filter_starred:
            st.session_state.filter_starred = show_starred
            st.rerun()
        
        # Chats List
        where_clause = "WHERE username=?" 
        params = [st.session_state.user]
        if show_starred:
            where_clause += " AND is_starred=1"
        
        chats = c.execute(f"SELECT id, title, updated_at, is_starred, usage_count FROM chats {where_clause} ORDER BY updated_at DESC", params).fetchall()
        
        for chat in chats:
            star_icon = "⭐" if chat[3] else "☆"
            btn_label = f"{star_icon} {chat[1]} ({chat[4]} uses)"
            if st.button(btn_label, key=f"chat_{chat[0]}"):
                st.session_state.chat_id = chat[0]
                st.rerun()
    
    # MAIN CONTENT
    if "chat_id" not in st.session_state:
        st.info("👆 Start a new chat from the sidebar")
        return
    
    # File Upload & Analysis
    col_file, col_model = st.columns([2, 1])
    
    with col_file:
        uploaded_file = st.file_uploader("📁 Upload Document", type=["pdf","txt","docx","csv"], help="Supports PDF, TXT, DOCX, CSV")
    
    with col_model:
        model_options = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "mixtral-8x7b-32768"]
        selected_model = st.selectbox("🤖 Model", model_options, index=0)
    
    file_text = ""
    file_summary = ""
    
    if uploaded_file:
        if uploaded_file.type == "application/pdf":
            pdf = PyPDF2.PdfReader(uploaded_file)
            file_text = "".join(page.extract_text() or "" for page in pdf.pages)
        elif uploaded_file.type == "text/plain":
            file_text = uploaded_file.read().decode()
        elif "word" in uploaded_file.type:
            doc = docx.Document(uploaded_file)
            file_text = "\n".join(para.text for para in doc.paragraphs)
        elif "csv" in uploaded_file.type:
            df = pd.read_csv(uploaded_file)
            file_text = df.to_string()
            st.dataframe(df, use_container_width=True)
        
        with st.spinner("🔍 Analyzing document..."):
            file_summary = analyze_file(file_text)
    
    # Chat Display
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    messages = c.execute("""
        SELECT role, content, timestamp 
        FROM messages 
        WHERE chat_id=? 
        ORDER BY id
    """, (st.session_state.chat_id,)).fetchall()
    
    for role, content, timestamp in messages:
        with st.chat_message(role):
            st.write(content)
            st.caption(f"*{timestamp}*")
            
            if role == "assistant":
                col1, col2 = st.columns([3, 1])
                with col2:
                    rating = st.select_slider("⭐ Rate", [1,2,3,4,5], key=f"rate_{len(messages)}")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Chat Input
    prompt = st.chat_input("💭 Ask Orion AI anything...", key="chat_input")
    
    if prompt:
        final_prompt = f"Context: {file_summary}\n\nQuestion: {prompt}"
        
        # Save user message
        c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)",
                 (st.session_state.chat_id, "user", prompt))
        c.execute("UPDATE chats SET updated_at=datetime('now'), usage_count=usage_count+1 WHERE id=?",
                 (st.session_state.chat_id,))
        conn.commit()
        
        with st.chat_message("user"):
            st.write(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("🧠 Orion is thinking..."):
                response, tokens = ask_ai(final_prompt, selected_model)
                st.write(response)
                st.caption(f"*{datetime.now().strftime('%H:%M')} | {tokens} tokens*")
            
            # Save assistant response
            c.execute("INSERT INTO messages (chat_id, role, content, tokens, model_used) VALUES (?,?,?,?,?)",
                     (st.session_state.chat_id, "assistant", response, tokens, selected_model))
            conn.commit()
        
        st.rerun()

# -------- RUN --------
if st.session_state.user is None:
    login_page()
else:
    main_app()
