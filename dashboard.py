import streamlit as st
import json
import os
from dotenv import load_dotenv
import constants

# Load environment variables to get the dashboard password
load_dotenv()
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")

st.set_page_config(page_title="Bot Dashboard", page_icon="🤖", layout="wide")

# 1. Authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Bot Dashboard Login")
    password = st.text_input("Enter Dashboard Password", type="password")
    if st.button("Login"):
        if password == DASHBOARD_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

# 2. Main Dashboard UI
st.title("🤖 Telegram Bot Configuration")
st.markdown("Changes are saved to `config.json` and apply to the bot **instantly** (no restart required).")

# Load current config
config = constants.get_config()

with st.form("config_form"):
    st.subheader("🧠 AI Model Settings")
    new_model = st.text_input("Primary Model Name", value=config.get("MODEL_NAME", ""))
    st.caption(f"Fallback model is set in .env as: `{constants.FALLBACK_MODEL}`")

    st.divider()

    st.subheader("📝 Prompts")
    new_system_prompt = st.text_area("System Prompt (Private & Group Chats)", value=config.get("SYSTEM_PROMPT", ""),
                                     height=150)
    new_analyze_en = st.text_area("Analyze Prompt (English)", value=config.get("ANALYZE_PROMPT_EN", ""), height=200)
    new_analyze_ru = st.text_area("Analyze Prompt (Russian)", value=config.get("ANALYZE_PROMPT_RU", ""), height=200)

    submitted = st.form_submit_button("💾 Save Changes")

if submitted:
    # Validate and Save
    new_config = {
        "MODEL_NAME": new_model.strip(),
        "SYSTEM_PROMPT": new_system_prompt.strip(),
        "ANALYZE_PROMPT_EN": new_analyze_en.strip(),
        "ANALYZE_PROMPT_RU": new_analyze_ru.strip()
    }

    try:
        constants.save_config(new_config)
        st.success("✅ Configuration saved successfully! The bot will use these settings on the next request.")
        # Update local config variable for immediate UI reflection
        config = new_config
    except Exception as e:
        st.error(f"❌ Failed to save configuration: {e}")

st.divider()
st.markdown(f"**Current Active Model:** `{config.get('MODEL_NAME')}`")
st.markdown(f"**Admin Usernames:** `{', '.join(constants.ADMIN_USERNAMES)}`")

if st.button("🚪 Logout"):
    st.session_state.authenticated = False
    st.rerun()