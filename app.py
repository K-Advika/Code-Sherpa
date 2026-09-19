import streamlit as st
import requests

st.set_page_config(page_title="Code Sherpa", page_icon="🧭", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0A0A0A;
        color: #EDEDED;
    }
    
    [data-testid="stSidebar"] {
        background-color: #111111;
        border-right: 1px solid #222222;
    }
    
    .stTextInput input {
        background-color: #000000 !important;
        border: 1px solid #333333 !important;
        border-radius: 4px !important;
        color: #FFFFFF !important;
        font-family: 'JetBrains Mono', monospace;
        padding: 12px !important;
        box-shadow: none !important;
    }
    .stTextInput input:focus { border-color: #666666 !important; }
    
    .stButton > button {
        background-color: #FFFFFF;
        color: #000000;
        border: none;
        border-radius: 4px;
        font-weight: 600;
        padding: 12px 24px;
        width: 100%;
    }
    .stButton > button:hover { background-color: #CCCCCC; color: #000000; }
    
    code {
        font-family: 'JetBrains Mono', monospace !important;
        background-color: #141414 !important;
        border: 1px solid #2A2A2A !important;
        border-radius: 4px !important;
    }
    
    .status-badge.cloud { 
        background-color: #0A141A; 
        color: #3399FF; 
        border: 1px solid #1A334D; 
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
        padding: 2px 6px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. Main UI Layout ---
st.title("Code Sherpa 🧭")
st.markdown("Issue-driven onboarding for open-source beginners. <span class='status-badge cloud'>AWS Cloud Backend Active</span>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Workspace Setup")
    # We removed the "Local Repository Path" because your backend downloads it automatically!
    issue_url = st.text_input("GitHub Issue URL", placeholder="https://api.github.com/repos/pallets/flask/issues/5000")
    start_button = st.button("Analyze Issue", type="primary", use_container_width=True)

# --- 3. Cloud Backend Connection ---
if start_button and issue_url:
    with st.status("🚀 Connecting to Cloud Backend...", expanded=True) as status:
        st.write("Fetching GitHub issue...")
        st.write("Downloading repository into memory...")
        st.write("Running AWS Bedrock / Gemini analysis...")
        
        # Point this to your live Render API
        BACKEND_URL = "https://code-sherpa-server.onrender.com/scan"
        payload = {"github_url": issue_url}
        
        try:
            # Send the URL to your FastAPI server
            response = requests.post(BACKEND_URL, json=payload, timeout=120)
            response.raise_for_status()
            
            data = response.json()
            verdict_markdown = data["verdict"]
            
            status.update(label="Analysis complete! Receipt saved to AWS S3.", state="complete", expanded=False)
            
            # Render the Markdown perfectly on the screen
            st.markdown("---")
            st.markdown(verdict_markdown)
            
        except requests.exceptions.ReadTimeout:
            status.update(label="Timeout Error", state="error")
            st.error("The backend took too long. The free cloud server is waking up—please click Analyze again!")
        except Exception as e:
            status.update(label="Connection Error", state="error")
            st.error(f"Failed to connect to backend: {e}")
            
elif start_button:
    st.warning("Please provide a GitHub Issue URL.")