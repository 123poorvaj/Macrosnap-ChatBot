import json

import streamlit as st
from google import genai
from google.genai import types
from twilio.rest import Client

from prompts import (
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
    SUMMARY_REQUEST_PROMPT,
)


# =========================
# API KEYS / CONFIGURATION
# =========================

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = st.secrets["TWILIO_WHATSAPP_FROM"]
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]

MODEL_NAME = "gemini-3.8-flash"


# =========================
# CLIENTS
# =========================

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)


@st.cache_resource
def get_twilio_client():
    return Client(
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN
    )


gemini_client = get_gemini_client()
twilio_client = get_twilio_client()


# =========================
# SESSION STATE
# =========================

if "onboarded" not in st.session_state:
    st.session_state.onboarded = False

if "messages" not in st.session_state:
    st.session_state.messages = []


# =========================
# DISPLAY MESSAGE
# =========================

def render_message(message):

    with st.chat_message(message["role"]):

        if message["kind"] == "text":
            st.write(message["content"])

        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):

    message = {
        "role": role,
        "kind": kind,
        "content": content
    }

    st.session_state.messages.append(message)

    render_message(message)


# =========================
# GEMINI FUNCTION
# =========================

def ask_gemini(parts):

    try:
        response = st.session_state.chat.send_message(parts)

        if response is None:
            return "Gemini returned no response."

        if response.text:
            return response.text

        return "Gemini returned an empty response."

    except Exception as error:
        return f"Gemini Error: {error}"

# =========================
# CLEAN WHATSAPP MESSAGE
# =========================

def clean_whatsapp_text(text):

    if not text:
        return "No summary available."

    text = " ".join(text.split())

    if len(text) > 1500:
        text = text[:1500] + "..."

    return text


# =========================
# SEND WHATSAPP
# =========================

def send_whatsapp(to_number, user_name, summary):

    try:

        content_variables = json.dumps(
            {
                "1": user_name,
                "2": clean_whatsapp_text(summary)
            },
            ensure_ascii=False
        )

        message = twilio_client.messages.create(

            from_=TWILIO_WHATSAPP_FROM,

            to=f"whatsapp:{to_number}",

            content_sid=TWILIO_CONTENT_SID,

            content_variables=content_variables
        )

        return True, message.sid

    except Exception as error:

        return False, str(error)


# ============================================================
# ONBOARDING
# ============================================================

if not st.session_state.onboarded:

    st.title("MacroSnap 🥗")

    st.caption(
        "Hi there! I'm MacroSnap, your friendly AI nutrition buddy."
    )

    with st.form("onboarding_form"):

        name = st.text_input(
            "Your name:"
        )

        whatsapp_number = st.text_input(
            "WhatsApp number (with country code):",
            placeholder="+91XXXXXXXXXX",
            help="This is the number MacroSnap will text."
        )

        submit_button = st.form_submit_button(
            "Let's go!"
        )

    if submit_button:

        if not name.strip() or not whatsapp_number.strip():

            st.warning(
                "Please fill in both fields."
            )

        else:

            st.session_state.name = name.strip()

            st.session_state.whatsapp_number = (
                whatsapp_number.strip()
            )

            # Create Gemini chat
            st.session_state.chat = gemini_client.chats.create(

                model=MODEL_NAME,

                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                )
            )

            st.session_state.messages = []

            st.session_state.onboarded = True

            st.rerun()

    st.stop()


# ============================================================
# MAIN HEADER
# ============================================================

header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center"
)


with header_col:

    st.title(
        f"Hey {st.session_state.name}! I'm MacroSnap 🥗"
    )


# ============================================================
# SEND TO WHATSAPP BUTTON
# ============================================================

with button_col:

    if st.button(
        "📤 Send to WhatsApp",
        use_container_width=True
    ):

        if len(st.session_state.messages) == 0:

            st.warning("Please chat with MacroSnap first.")

        else:

            with st.spinner("Summarizing your day..."):

                summary = ask_gemini(
                    [SUMMARY_REQUEST_PROMPT]
                )

            success, info = send_whatsapp(
                st.session_state.whatsapp_number,
                st.session_state.name,
                summary
            )

            if success:

                st.success(
                    "Sent! Check your WhatsApp 📲"
                )

            else:

                st.error(
                    f"Couldn't send that: {info}"
                )


# =========================
# USER INFORMATION
# =========================

st.caption(
    f"Logged in as {st.session_state.name} "
    f"- updates go to {st.session_state.whatsapp_number}"
)


# ============================================================
# CHAT HISTORY
# ============================================================

if not st.session_state.messages:

    welcome_message = WELCOME_MESSAGE_TEMPLATE.format(
        name=st.session_state.name
    )

    add_message(
        "assistant",
        "text",
        welcome_message
    )

else:

    for message in st.session_state.messages:

        render_message(message)



user_input = st.chat_input(
    "Ask a question, or attach a photo of your meal",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"]
)

if user_input:

    try:
        parts = []

        # -----------------------------
        # TEXT
        # -----------------------------
        text = user_input.text.strip()

        # -----------------------------
        # IMAGE
        # -----------------------------
        if user_input.files:

            photo = user_input.files[0]

            photo_bytes = photo.getvalue()

            if len(photo_bytes) == 0:
                st.error("The uploaded image is empty.")
                st.stop()

            st.write(
                f"Image received: {photo.name} "
                f"({len(photo_bytes)} bytes)"
            )

            # Show uploaded image
            add_message(
                "user",
                "image",
                photo_bytes
            )

            # Determine MIME type
            mime_type = photo.type

            if mime_type not in [
                "image/jpeg",
                "image/png"
            ]:

                if photo.name.lower().endswith(".png"):
                    mime_type = "image/png"
                else:
                    mime_type = "image/jpeg"

            # Convert image to Gemini Part
            image_part = types.Part.from_bytes(
                data=photo_bytes,
                mime_type=mime_type
            )

            parts.append(image_part)

        # -----------------------------
        # TEXT
        # -----------------------------
        if text:

            add_message(
                "user",
                "text",
                text
            )

            parts.append(text)

        # -----------------------------
        # IMAGE WITHOUT TEXT
        # -----------------------------
        elif user_input.files:

            parts.append(
                """
                Analyze this meal image.

                Identify the food.

                Estimate:
                - Calories
                - Protein
                - Carbohydrates
                - Fat

                Give a simple explanation.

                Clearly mention that the nutritional
                values are estimates.
                """
            )

        # -----------------------------
        # SEND TO GEMINI
        # -----------------------------
        if parts:

            with st.spinner("Analyzing your meal..."):

                answer = ask_gemini(parts)

            add_message(
                "assistant",
                "text",
                answer

            )

    except Exception as error:

        st.error(
            f"Photo processing error: {error}"
        )