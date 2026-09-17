import streamlit as st
import requests
import json

# --- 1. UI Configuration & Styling ---
st.set_page_config(page_title="code sherpa", page_icon="🧭", layout="wide")

st.markdown("""
    <style>
    /* Absolute reset and premium typography */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0A0A0A; /* Pure dark, no purple */
        color: #EDEDED;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #111111;
        border-right: 1px solid #222222;
    }
    
    /* Inputs */
    .stTextInput input {
        background-color: #000000 !important;
        border: 1px solid #333333 !important;
        border-radius: 4px !important;
        color: #FFFFFF !important;
        font-family: 'JetBrains Mono', monospace;
        padding: 12px !important;
        box-shadow: none !important;
        transition: border-color 0.2s ease;
    }
    .stTextInput input:focus {
        border-color: #666666 !important;
    }
    
    /* Primary Button - High Contrast */
    .stButton > button {
        background-color: #FFFFFF;
        color: #000000;
        border: none;
        border-radius: 4px;
        font-weight: 600;
        padding: 12px 24px;
        width: 100%;
        transition: transform 0.1s ease, opacity 0.2s;
    }
    .stButton > button:hover {
        background-color: #CCCCCC;
        border: none;
        color: #000000;
    }
    .stButton > button:active {
        transform: scale(0.98);
    }
    
    /* Code Blocks */
    code {
        font-family: 'JetBrains Mono', monospace !important;
        background-color: #141414 !important;
        border: 1px solid #2A2A2A !important;
        border-radius: 4px !important;
    }
    
    /* Badges */
    .status-badge.local { 
        background-color: #111111; 
        color: #888888; 
        border: 1px solid #333333; 
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: -0.5px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. Backend Integration Stubs ---
# Your teammate will replace this function's internals with their GitHub API/Scanner logic.
def fetch_backend_context(issue_url, repo_path):
    """Mocks the backend response so you can test the AI prompt right now."""
    # Simulate a delay for fetching and scanning
    import time
    time.sleep(1.5)
    
    return {
        "issue_description": "The login page crashes when a user submits an empty password field. It throws a NullPointerException in auth_handler.py.",
        "isolated_files": {
            "auth_handler.py": "def handle_login(user, pwd):\n    # TODO: add validation\n    if len(pwd) > 0:\n        return login_user(user, pwd)\n    return None",
            "utils/validation.py": "def is_valid(string):\n    return string is not None and len(string) > 0"
        }
    }

# --- 3. Ollama Integration & Prompt Engineering ---
def build_prompt(issue_desc, files_dict):
    """Constructs the strict instructional prompt for Qwen 2.5."""
    
    # Format the files into a readable string
    code_context = "\n\n".join([f"--- {filename} ---\n```python\n{code}\n```" for filename, code in files_dict.items()])
    
    return f"""You are 'code sherpa', a senior developer mentoring a first-time open-source contributor. 
Your goal is to help them understand the bug and how to investigate it. 
CRITICAL RULE: DO NOT WRITE THE FINAL CODE SOLUTION. Do not write the exact lines of code needed to fix the bug.

Issue Description:
{issue_desc}

Relevant Code Isolated in the Repository:
{code_context}

Provide a beginner-friendly crash course structured EXACTLY with these markdown headers:
## 🐛 The Bug Explained
(Explain what is going wrong in plain English, without jargon).

## 🧠 Concepts to Know
(List 2-3 core programming concepts or library methods the user should research to understand this area of the code).

## 🔍 Investigation Strategy
(Tell them exactly where to place print() statements or logs in the provided files to see the error happening. Walk them through the logic flow).
"""

def stream_ollama_response(prompt):
    """Sends the prompt to local Ollama and yields the text stream for Streamlit."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "qwen2.5-coder:7b",
        "prompt": prompt,
        "stream": True,
        "temperature": 0.2 # Low temperature for logical, instructional output rather than creative variance
    }
    
    try:
        with requests.post(url, json=payload, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if not chunk.get("done"):
                        yield chunk.get("response", "")
    except requests.exceptions.ConnectionError:
        yield "❌ Error: Could not connect to Ollama. Is `ollama run qwen2.5-coder:7b` running in your terminal?"

# --- 4. Main UI Layout ---
st.title("code sherpa 🧭")
st.markdown("Issue-driven onboarding for open-source beginners. <span class='status-badge local'>Local LLM Active</span>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Workspace Setup")
    issue_url = st.text_input("GitHub Issue URL", placeholder="https://github.com/org/repo/issues/123")
    repo_path = st.text_input("Local Repository Path", placeholder="/Users/mac/projects/repo")
    start_button = st.button("Analyze Issue", type="primary", use_container_width=True)

if start_button and issue_url and repo_path:
    # Step 1: Backend Fetch
    with st.status("🔍 Scanning repository and fetching issue...", expanded=True) as status:
        st.write("Calling GitHub API...")
        st.write("Ranking files via local semantic scan...")
        
        # Call the integration stub
        context = fetch_backend_context(issue_url, repo_path)
        status.update(label="Context gathered successfully!", state="complete", expanded=False)
    
    # Step 2: Display Isolated Context (Collapsible)
    with st.expander("📂 View Isolated Code Context", expanded=False):
        st.markdown("**Issue Description:**")
        st.info(context["issue_description"])
        st.markdown("**Relevant Files:**")
        for filename, code in context["isolated_files"].items():
            st.code(code, language="python")
            
    # Step 3: LLM Generation
    st.subheader("Mentor Crash Course")
    prompt = build_prompt(context["issue_description"], context["isolated_files"])
    
    # Stream the output directly to the UI
    st.write_stream(stream_ollama_response(prompt))
elif start_button:
    st.warning("Please provide both an Issue URL and a local repository path.")
