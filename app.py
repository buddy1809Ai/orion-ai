import streamlit as st
import sqlite3
import uuid
import os
from dotenv import load_dotenv
from groq import Groq
import PyPDF2
import docx

# -------- LOAD API --------
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# -------- DB --------
conn = sqlite3.connect("orion.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users(
    username TEXT PRIMARY KEY,
    password TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS chats(
    id TEXT PRIMARY KEY,
    username TEXT,
    title TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    role TEXT,
    content TEXT
)""")

conn.commit()

# -------- AUTH --------
if "user" not in st.session_state:
    st.session_state.user = None

def login():
    st.title("🚀 ORION AI")

    mode = st.radio("Login / Signup", ["Login", "Signup"])

    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")

    if mode == "Signup":
        if st.button("Create Account"):
            try:
                c.execute("INSERT INTO users VALUES (?,?)", (user, pwd))
                conn.commit()
                st.success("Account created")
            except:
                st.error("User exists")

    else:
        if st.button("Login"):
            res = c.execute("SELECT * FROM users WHERE username=? AND password=?",
                            (user, pwd)).fetchone()
            if res:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid credentials")

# -------- AI --------
def ask_ai(prompt):
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"❌ ERROR: {e}"

# -------- MAIN --------
def main():
    st.set_page_config(layout="wide")

    # 🔥 UI (FIXED)
    st.markdown("""
    <style>
    body {
        background: linear-gradient(135deg,#020617,#0f172a);
        color:white;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #020617, #0f172a);
    }

    button {
        border-radius: 12px !important;
        background: linear-gradient(135deg,#6366f1,#8b5cf6) !important;
        color: white !important;
        border: none !important;
    }

    button:hover {
        transform: scale(1.05);
    }

    textarea, input {
        background:#020617 !important;
        color:white !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # TITLE
    st.markdown(f"""
    <h2 style='color:#38bdf8;'>🧠 ORION AI</h2>
    <p style='color:gray;'>Welcome, {st.session_state.user}</p>
    """, unsafe_allow_html=True)

    # SIDEBAR
    with st.sidebar:
        st.markdown("### 💬 Chat History")

        if st.button("➕ New Chat"):
            chat_id = str(uuid.uuid4())
            c.execute("INSERT INTO chats VALUES (?,?,?)",
                      (chat_id, st.session_state.user, "New Chat"))
            conn.commit()
            st.session_state.chat_id = chat_id
            st.rerun()

        chats = c.execute("SELECT id, title FROM chats WHERE username=?",
                          (st.session_state.user,)).fetchall()

        for chat in chats:
            if st.button(chat[1], key=chat[0]):
                st.session_state.chat_id = chat[0]

    # FILE
    uploaded_file = st.file_uploader("📂 Upload", type=["pdf","txt","docx"])

    file_text = ""

    if uploaded_file:
        if uploaded_file.type == "application/pdf":
            pdf = PyPDF2.PdfReader(uploaded_file)
            for page in pdf.pages:
                file_text += page.extract_text() or ""

        elif uploaded_file.type == "text/plain":
            file_text = uploaded_file.read().decode()

        elif "word" in uploaded_file.type:
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                file_text += para.text

        st.success("✅ File loaded")

    if "chat_id" not in st.session_state:
        return

    messages = c.execute("SELECT role, content FROM messages WHERE chat_id=?",
                         (st.session_state.chat_id,)).fetchall()

    for role, content in messages:
        st.chat_message(role).write(content)

    prompt = st.chat_input("Ask Orion AI...")

    if prompt:
        final_prompt = f"{file_text}\n\n{prompt}"

        c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)",
                  (st.session_state.chat_id, "user", prompt))
        conn.commit()

        st.chat_message("user").write(prompt)

        response = ask_ai(final_prompt)

        st.chat_message("assistant").write(response)

        c.execute("INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)",
                  (st.session_state.chat_id, "assistant", response))
        conn.commit()

        st.rerun()

# RUN
if st.session_state.user is None:
    login()
else:
    main()