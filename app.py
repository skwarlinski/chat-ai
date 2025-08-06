import os
import json
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from langfuse.decorators import observe
from langfuse.openai import OpenAI

model_pricings = {
    "gpt-4o": {
        "input_tokens": 5.00 / 1_000_000,  # per token
        "output_tokens": 15.00 / 1_000_000,  # per token
    },
    "gpt-4o-mini": {
        "input_tokens": 0.150 / 1_000_000,  # per token
        "output_tokens": 0.600 / 1_000_000,  # per token
    }
}

DEFAULT_MODEL_INDEX = 0
models = list(model_pricings.keys())
if "model" not in st.session_state:
    st.session_state["model"] = models[DEFAULT_MODEL_INDEX]

USD_TO_PLN = 3.97
PRICING = model_pricings[st.session_state["model"]]

load_dotenv()

def get_openai_client():
    """Pobiera klienta OpenAI z kluczem API z session_state lub z .env"""
    api_key = None
    
    # Spróbuj najpierw session_state
    if "openai_api_key" in st.session_state and st.session_state["openai_api_key"]:
        api_key = st.session_state["openai_api_key"]
    # Następnie spróbuj plik .env
    elif os.environ.get("OPENAI_API_KEY"):
        api_key = os.environ["OPENAI_API_KEY"]
    
    if api_key:
        return OpenAI(api_key=api_key)
    else:
        return None

def show_api_key_input():
    """Wyświetla formularz do wprowadzenia klucza API"""
    st.title("🔑 Ustawienia klucza OpenAI API")
    st.markdown("Do korzystania z aplikacji potrzebny jest klucz OpenAI API.")
    
    with st.form("api_key_form"):
        st.markdown("### Opcje:")
        st.markdown("1. **Wprowadź klucz tutaj** - klucz będzie zapisany tylko na czas sesji")
        st.markdown("2. **Dodaj do pliku .env** - utwórz plik `.env` z zawartością: `OPENAI_API_KEY=twoj_klucz`")
        
        api_key_input = st.text_input(
            "Klucz OpenAI API:",
            type="password",
            placeholder="sk-..."
        )
        
        submitted = st.form_submit_button("💾 Zapisz klucz", type="primary")
        
        if submitted:
            if api_key_input and api_key_input.startswith("sk-"):
                st.session_state["openai_api_key"] = api_key_input
                st.success("✅ Klucz API został pomyślnie zapisany!")
                st.rerun()
            elif api_key_input:
                st.error("❌ Nieprawidłowy klucz API. Klucz powinien zaczynać się od 'sk-'")
            else:
                st.error("❌ Proszę wprowadzić klucz API")
    
    with st.expander("ℹ️ Jak uzyskać klucz OpenAI API?"):
        st.markdown("""
        1. Przejdź na [platform.openai.com](https://platform.openai.com)
        2. Zaloguj się lub zarejestruj
        3. Przejdź do sekcji API Keys
        4. Utwórz nowy klucz API
        5. Skopiuj klucz i wklej go powyżej
        """)

#
# CHATBOT
#
@observe()
def chatbot_reply(user_prompt, memory):
    openai_client = get_openai_client()
    if not openai_client:
        return None
        
    messages = [
        {
            "role": "system",
            "content": st.session_state["chatbot_personality"],
        },
    ]
    for message in memory:
        messages.append({"role": message["role"], "content": message["content"]})

    messages.append({"role": "user", "content": user_prompt})

    try:
        response = openai_client.chat.completions.create(
            model=st.session_state["model"],
            messages=messages
        )
        usage = {}
        if response.usage:
            usage = {
                "completion_tokens": response.usage.completion_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return {
            "role": "assistant",
            "content": response.choices[0].message.content,
            "usage": usage,
        }
    except Exception as e:
        st.error(f"❌ Błąd przy wywołaniu OpenAI API: {str(e)}")
        return None

#
# CONVERSATION HISTORY AND DATABASE
#
DEFAULT_PERSONALITY = """
Jesteś pomocnikiem, który odpowiada na wszystkie pytania użytkownika.
Odpowiadaj na pytania w sposób zwięzły i zrozumiały.
""".strip()

DB_PATH = Path("db")
DB_CONVERSATIONS_PATH = DB_PATH / "conversations"

def load_conversation_to_state(conversation):
    st.session_state["id"] = conversation["id"]
    st.session_state["name"] = conversation["name"]
    st.session_state["messages"] = conversation["messages"]
    st.session_state["chatbot_personality"] = conversation["chatbot_personality"]


def load_current_conversation():
    if not DB_PATH.exists():
        DB_PATH.mkdir()
        DB_CONVERSATIONS_PATH.mkdir()
        conversation_id = 1
        conversation = {
            "id": conversation_id,
            "name": "Konwersacja 1",
            "chatbot_personality": DEFAULT_PERSONALITY,
            "messages": [],
        }

        # tworzymy nową konwersację
        with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(conversation, ensure_ascii=False, indent=2))

        # która od razu staje się aktualną
        with open(DB_PATH / "current.json", "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "current_conversation_id": conversation_id,
            }, ensure_ascii=False, indent=2))

    else:
        with open(DB_PATH / "current.json", "r", encoding="utf-8") as f:
            data = json.loads(f.read())
            conversation_id = data["current_conversation_id"]

        with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "r", encoding="utf-8") as f:
            conversation = json.loads(f.read())

    load_conversation_to_state(conversation)


def save_current_conversation_messages():
    conversation_id = st.session_state["id"]
    new_messages = st.session_state["messages"]

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "r", encoding="utf-8") as f:
        conversation = json.loads(f.read())

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            **conversation,
            "messages": new_messages,
        }, ensure_ascii=False, indent=2))


def save_current_conversation_name():
    conversation_id = st.session_state["id"]
    new_conversation_name = st.session_state["new_conversation_name"]

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "r", encoding="utf-8") as f:
        conversation = json.loads(f.read())

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            **conversation,
            "name": new_conversation_name,
        }, ensure_ascii=False, indent=2))


def save_current_conversation_personality():
    conversation_id = st.session_state["id"]
    new_chatbot_personality = st.session_state["new_chatbot_personality"]

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "r", encoding="utf-8") as f:
        conversation = json.loads(f.read())

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            **conversation,
            "chatbot_personality": new_chatbot_personality,
        }, ensure_ascii=False, indent=2))


def create_new_conversation():
    conversation_ids = []
    for p in DB_CONVERSATIONS_PATH.glob("*.json"):
        conversation_ids.append(int(p.stem))

    conversation_id = max(conversation_ids) + 1 if conversation_ids else 1
    personality = DEFAULT_PERSONALITY
    if "chatbot_personality" in st.session_state and st.session_state["chatbot_personality"]:
        personality = st.session_state["chatbot_personality"]

    conversation = {
        "id": conversation_id,
        "name": f"Konwersacja {conversation_id}",
        "chatbot_personality": personality,
        "messages": [],
    }

    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(conversation, ensure_ascii=False, indent=2))

    with open(DB_PATH / "current.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "current_conversation_id": conversation_id,
        }, ensure_ascii=False, indent=2))

    load_conversation_to_state(conversation)
    st.rerun()


def switch_conversation(conversation_id):
    with open(DB_CONVERSATIONS_PATH / f"{conversation_id}.json", "r", encoding="utf-8") as f:
        conversation = json.loads(f.read())

    with open(DB_PATH / "current.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "current_conversation_id": conversation_id,
        }, ensure_ascii=False, indent=2))

    load_conversation_to_state(conversation)
    st.rerun()


def list_conversations():
    conversations = []
    for p in DB_CONVERSATIONS_PATH.glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            conversation = json.loads(f.read())
            conversations.append({
                "id": conversation["id"],
                "name": conversation["name"],
            })

    return conversations


def delete_conversation(conversation_id):
    """Usuwa konwersację z bazy danych"""
    conversations = list_conversations()
    
    # Nie można usunąć jedynej pozostałej konwersacji
    if len(conversations) <= 1:
        st.error("Nie można usunąć jedynej konwersacji!")
        return False
    
    # Nie można usunąć aktualnie aktywnej konwersacji
    if conversation_id == st.session_state["id"]:
        st.error("Nie można usunąć aktualnie aktywnej konwersacji!")
        return False
    
    # Usuń plik konwersacji
    conversation_file = DB_CONVERSATIONS_PATH / f"{conversation_id}.json"
    if conversation_file.exists():
        conversation_file.unlink()
        st.success("Konwersacja została usunięta!")
        return True
    else:
        st.error("Nie znaleziono konwersacji do usunięcia!")
        return False


@st.dialog("Potwierdzenie usunięcia")
def confirm_delete_dialog(conversation_id, conversation_name):
    st.write(f"Czy na pewno chcesz usunąć konwersację: **{conversation_name}**?")
    st.write("**Ta operacja jest nieodwracalna!**")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Tak, usuń", type="primary"):
            if delete_conversation(conversation_id):
                st.rerun()
    
    with col2:
        if st.button("Anuluj"):
            st.rerun()


#
# GŁÓWNY PROGRAM
#

# Sprawdź czy dostępny jest klucz OpenAI API
openai_client = get_openai_client()

if not openai_client:
    show_api_key_input()
    st.stop()

# Jeśli klucz API jest dostępny, kontynuuj normalną funkcjonalność
load_current_conversation()

st.title("✨ Chat AI")

# Vyświetlanie wiadomości
for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input użytkownika
prompt = st.chat_input("O co chcesz spytać?")
if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state["messages"].append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        response = chatbot_reply(prompt, memory=st.session_state["messages"][-10:])
        if response:
            st.markdown(response["content"])
            st.session_state["messages"].append({"role": "assistant", "content": response["content"], "usage": response["usage"]})
            save_current_conversation_messages()
        else:
            st.error("❌ Nie udało się uzyskać odpowiedzi od AI. Sprawdź klucz API.")

# Sidebar
with st.sidebar:
    # Informacje o kluczu API
    with st.expander("🔑 Klucz API", expanded=False):
        if "openai_api_key" in st.session_state:
            st.success("✅ Klucz API z sesji")
            if st.button("🗑️ Usuń klucz z sesji"):
                del st.session_state["openai_api_key"]
                st.rerun()
        elif os.environ.get("OPENAI_API_KEY"):
            st.success("✅ Klucz API z pliku .env")
        else:
            st.error("❌ Nie znaleziono klucza API")
    
    # Obliczanie kosztów
    total_cost = 0

    c0, c1 = st.columns(2)
    with c0:
        selected_model = st.selectbox("Wybrany model", models, index=DEFAULT_MODEL_INDEX)
    st.session_state["model"] = selected_model
    PRICING = model_pricings[st.session_state["model"]]

    for message in st.session_state.get("messages") or []:
        if "usage" in message:
            total_cost += message["usage"]["prompt_tokens"] * PRICING["input_tokens"]
            total_cost += message["usage"]["completion_tokens"] * PRICING["output_tokens"]

    with st.expander("Aktualny koszt konwersacji", expanded=True):
        c0, c1 = st.columns(2)
        with c0:
            st.metric("", f"${total_cost:.4f}")

        with c1:
            st.metric("", f"{total_cost * USD_TO_PLN:.4f}zł")

    # Ustawienia konwersacji
    st.session_state["name"] = st.text_input(
        "Nazwa konwersacji",
        value=st.session_state["name"],
        key="new_conversation_name",
        on_change=save_current_conversation_name,
    )
    
    st.session_state["chatbot_personality"] = st.text_area(
        "Osobowość chatbota",
        max_chars=1000,
        height=200,
        value=st.session_state["chatbot_personality"],
        key="new_chatbot_personality",
        on_change=save_current_conversation_personality,
    )

    # Lista konwersacji
    
    col1, col2 = st.columns([3, 2])
    with col1:
        if st.button("➕ Nowa konwersacja"):
            create_new_conversation()
    
    with col2:
        delete_mode = st.checkbox("🗑️", help="Tryb usuwania")

    conversations = list_conversations()
    sorted_conversations = sorted(conversations, key=lambda x: x["id"], reverse=True)
    
    for conversation in sorted_conversations[:5]:
        if delete_mode:
            # Tryb usuwania - 3 kolumny
            c0, c1, c2 = st.columns([7, 2, 2])
            with c0:
                # Pokaż aktywną konwersację z emoji
                if conversation["id"] == st.session_state["id"]:
                    st.write(f"✅ {conversation['name']}")
                else:
                    st.write(conversation["name"])
            
            with c1:
                if st.button("⚡", key=f"load_{conversation['id']}", 
                            disabled=conversation["id"] == st.session_state["id"], 
                            help="Załaduj konwersację"):
                    switch_conversation(conversation["id"])
            
            with c2:
                if st.button("🗑️", key=f"delete_{conversation['id']}", 
                            disabled=conversation["id"] == st.session_state["id"] or len(conversations) <= 1,
                            help="Usuń konwersację"):
                    confirm_delete_dialog(conversation["id"], conversation["name"])
        else:
            # Normalny tryb - 2 kolumny
            c0, c1 = st.columns([8, 2])
            with c0:
                # Pokaż aktywną konwersację z emoji
                if conversation["id"] == st.session_state["id"]:
                    st.write(f"✅ {conversation['name']}")
                else:
                    st.write(conversation["name"])

            with c1:
                if st.button("⚡", key=conversation["id"], 
                            disabled=conversation["id"] == st.session_state["id"], 
                            help="Załaduj konwersację"):
                    switch_conversation(conversation["id"])