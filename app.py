import os
from dotenv import load_dotenv
import streamlit as st
import sqlite3
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq

# Global variables for API keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

# Function to connect to the db
def init_db(database: str) -> SQLDatabase:
    db_path = database
    db_uri = f"sqlite:///{db_path}"
    db = SQLDatabase.from_uri(db_uri)
    return db

def fetch_table_info(database: str):
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    table_info = {}
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        table_info[table_name] = column_names
    conn.close()
    return table_info

# Initialize session state variables
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="Hello! I am a database assistant. Ask me anything about your database.")
    ]

if "db_connected" not in st.session_state:
    st.session_state.db_connected = False

if "table_info" not in st.session_state:
    st.session_state.table_info = {}

def get_sql_chain(db, model):
    template = """
    You are a data analyst at a company. You are interacting with a user who is asking you questions about the company's database.
    Based on the table schema below, write a SQL query that would answer the user's question. Take the conversation history into account.
    
    <SCHEMA>{schema}</SCHEMA>
    
    Conversation History: {chat_history}
    
    Write only the SQL query and nothing else. Do not wrap the SQL query in any other text, not even backticks. Remove any special characters such as / or \\
    
    For example:
    Question: which 3 artists have the most tracks?
    SQL Query: SELECT ArtistId, COUNT(*) as track_count FROM Track GROUP BY ArtistId ORDER BY track_count DESC LIMIT 3;
    Question: Name 10 artists
    SQL Query: SELECT Name FROM Artist LIMIT 10;
    
    Your turn:
    
    Question: {question}
    SQL Query:
    """
    prompt = ChatPromptTemplate.from_template(template)

    if model == "mixtral-8x7b-32768":
        llm = ChatGroq(model="mixtral-8x7b-32768", temperature=0, api_key=GROQ_API_KEY)
    elif model == "gemini-1.5-flash":
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", api_key=GOOGLE_API_KEY)
    
    def get_schema(_):
        return db.get_table_info()
    
    return (
        RunnablePassthrough.assign(schema=get_schema)
        | prompt
        | llm
        | StrOutputParser()
    )

def get_response(user_query: str, db: SQLDatabase, chat_history: list, model: str):
    sql_chain = get_sql_chain(db, model)

    template = """
    You are a data analyst at a company. You are interacting with a user who is asking you questions about the company's database.
    Based on the table schema below, question, sql query, and sql response, write a natural language response.
    <SCHEMA>{schema}</SCHEMA>

    Conversation History: {chat_history}
    SQL Query: <SQL>{query}</SQL>
    User question: {question}
    SQL Response: {response}"""

    prompt = ChatPromptTemplate.from_template(template)

    if model == "mixtral-8x7b-32768":
        llm = ChatGroq(model="mixtral-8x7b-32768", temperature=0, api_key=GROQ_API_KEY)
    elif model == "gemini-1.5-flash":
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", api_key=GOOGLE_API_KEY)

    chain = (
        RunnablePassthrough.assign(query=sql_chain).assign(
            schema=lambda _: db.get_table_info(),
            response=lambda vars: db.run(vars["query"])
        )
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain.invoke({
        "question": user_query,
        "chat_history": chat_history
    })

# Load environment variables
load_dotenv()

# Set up Streamlit page
st.set_page_config(page_title="Chat with DB", page_icon=":speech_balloon")
st.title("Chat with my DB")

# Sidebar settings
with st.sidebar:
    st.subheader("Settings")
    st.write("This is a simple database chat application. Connect to the database and start chatting.")
    model = st.radio(
        "Model", ["gemini-1.5-flash", "mixtral-8x7b-32768"]
    )
    st.session_state.model = model

    db_name = st.text_input("Database", value="mydatabase.db", key="Database")

    # Connect/Disconnect button
    if st.session_state.db_connected:
        button_text = "Disconnect"
    else:
        button_text = "Connect"

    if st.button(button_text):
        if st.session_state.db_connected:
            # Disconnect
            st.session_state.db_connected = False
            st.session_state.table_info = {}
            st.session_state.db = None
            st.success("Disconnected from the database.")
        else:
            # Connect
            with st.spinner("Connecting to the database..."):
                try:
                    db = init_db(db_name)
                    st.session_state.db = db
                    st.session_state.db_connected = True  # Set the flag when connected
                    st.session_state.table_info = fetch_table_info(db_name)  # Store table info in session state
                    st.success("Connected to the database!")
                except Exception as e:
                    st.session_state.db_connected = False  # Reset the flag on failure
                    st.error(f"Failed to connect to the database: {e}")

    # Display table info in sidebar if connected
    if st.session_state.db_connected:
        st.subheader("Tables and Columns")
        table_info = st.session_state.table_info

        for table, columns in table_info.items():
            with st.expander(f"**Table:** {table}"):
                for column in columns:
                    st.write(f"🏷️ {column}")

# Display chat history
for message in st.session_state.chat_history:
    if isinstance(message, AIMessage):
        with st.chat_message("AI"):
            st.markdown(message.content)
    elif isinstance(message, HumanMessage):
        with st.chat_message("Human"):
            st.markdown(message.content)

# Disable chat input box until the database is connected
if st.session_state.get("db_connected", False):
    user_query = st.chat_input("Type a message...")
    if user_query is not None and user_query.strip() != "":
        st.session_state.chat_history.append(HumanMessage(content=user_query))

        with st.chat_message("Human"):
            st.markdown(user_query)

        with st.chat_message("AI"):
            model = st.session_state.model  # Get the selected model from the session state
            response = get_response(user_query, st.session_state.db, st.session_state.chat_history, model)
            st.markdown(response)

        st.session_state.chat_history.append(AIMessage(content=response))
else:
    st.info("Connect to the database to chat.")