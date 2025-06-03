import streamlit as st
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.runnable import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser, BaseOutputParser, JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.utilities import SQLDatabase
import ast
import json # For parsing structured LLM responses

# --- 1. Page Configuration (MUST BE THE FIRST STREAMLIT COMMAND) ---
st.set_page_config(
    page_title="SQL AI Assistant Pro+",
    layout="centered",
    initial_sidebar_state="auto",
    menu_items={
        'About': "# SQL AI Assistant Pro+\nEnhanced AI for SQL database interaction and management."
    }
)

# --- 2. Configuration & Secrets ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    MYSQL_USER = st.secrets.get("MYSQL_USER", "adit")
    MYSQL_PASSWORD = st.secrets.get("MYSQL_PASSWORD", "yourpassword")
    MYSQL_HOST = st.secrets.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = st.secrets.get("MYSQL_PORT", "3306")
    MYSQL_DATABASE = st.secrets.get("MYSQL_DATABASE", "mychinook")
except (FileNotFoundError, KeyError):
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    MYSQL_USER = os.environ.get("MYSQL_USER", "adit")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "yourpassword")
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
    MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "mychinook")

if not GOOGLE_API_KEY:
    st.error("Google API Key not found! Please set it in Streamlit secrets (GOOGLE_API_KEY) or as an environment variable.")
    st.stop()

os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
mysql_uri = f'mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}'

# --- 3. LLM Definition ---
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.1,
    top_p=0.95,
    top_k=40,
    max_output_tokens=3072,
    candidate_count=1,
    convert_system_message_to_human=True,
)

# --- 4. Database Connection ---
@st.cache_resource
def get_database_connection():
    try:
        db_connection = SQLDatabase.from_uri(mysql_uri)
        return db_connection
    except Exception as e:
        st.error(f"Database Connection Failed!\nError: {e}")
        st.info("Please check your MySQL server status and credentials. Ensure the server is accessible.")
        return None
db = get_database_connection()

# --- 5. Custom Output Parsers ---
class SimpleStrParser(BaseOutputParser):
    def parse(self, text: str) -> str:
        cleaned_text = text.strip()
        if cleaned_text.startswith("```sql"):
            cleaned_text = cleaned_text[len("```sql"):].strip()
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-len("```")].strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[len("```json"):].strip()
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-len("```")].strip()
        return cleaned_text

# --- 6. Helper Functions & Prompts ---
def get_schema(_=None):
    if db:
        try: return db.get_table_info()
        except Exception as e: return f"Error getting schema: {str(e)}"
    return "Error: Database connection not available."

def run_select_query(sql_query: str):
    if db:
        if not sql_query or \
           "Cannot answer" in sql_query or \
           "Error: SQL not generated" in sql_query or \
           not sql_query.strip().upper().startswith("SELECT"):
            return "Skipping execution: Query is not a valid SELECT statement or is unanswerable."
        try:
            return db.run(sql_query.strip())
        except Exception as e:
            return f"Error executing SELECT query: {str(e)}\nAttempted Query: {sql_query.strip()}"
    return "Error: Database connection not available for query execution."

def run_simulated_dml_query(dml_sql: str, action: str):
    if not dml_sql or "Error generating DML" in dml_sql or "Command too vague" in dml_sql:
        return f"Error: Could not simulate {action} due to issues with the DML command."
    if not (dml_sql.strip().upper().startswith("INSERT") or \
            dml_sql.strip().upper().startswith("DELETE") or \
            dml_sql.strip().upper().startswith("UPDATE")):
        return f"Error: The provided command for {action} does not appear to be valid DML."
    return f"Successfully (simulated) {action} data. No actual changes were made to the database in this demo."

sql_intent_prompt_template_str = """
You are an advanced AI assistant. Analyze the user's question and database schema. Respond in JSON.
JSON output must contain "response_type".

1.  If the question is a request for information (SELECT query):
    If the question is specific enough to generate a query, set "response_type": "SELECT_QUERY", "generated_sql": "YOUR_SQL_QUERY_HERE".
    If the question is too vague for a specific SELECT query, set "response_type": "CLARIFICATION_NEEDED_FOR_SELECT", "ai_response": "Your question is a bit vague for a precise query. Could you please provide more details or specific criteria?".
    If unanswerable by schema, set "response_type": "SELECT_QUERY", "generated_sql": "Cannot answer based on the schema."

2.  If the question suggests intent to ADD, DELETE, or UPDATE data:
    Set "response_type": "DML_INTENT_DETECTED".
    Set "dml_action": "add" / "delete" / "update" (based on user's words).
    Set "ai_response": "It looks like you want to [add/delete/update] data. Please use the dedicated buttons ('➕ Add Data', '➖ Delete Data') and provide an initial description of what you want to do in the input area that will appear."

3.  If the question is a general inquiry about the database itself (e.g., "what is this database about?", "what kind of data is stored here?"):
    Set "response_type": "DATABASE_OVERVIEW_REQUEST".
    Set "ai_response": "Let me provide an overview of this database."

4.  If general greeting or too ambiguous for any of the above:
    Set "response_type": "GENERAL_RESPONSE".
    Set "ai_response": "Your conversational reply or request for more clarity."

Database Schema:
{schema}
User Question:
{question}
Respond with a valid JSON object only:
"""
sql_intent_prompt = ChatPromptTemplate.from_template(sql_intent_prompt_template_str)

dml_guidance_prompt_template_str = """
You are an AI assistant helping a user {action_description}.
Based on their initial description: "{user_initial_description}"
And the Database Schema:
{schema}

Your task is to:
1.  Identify the most likely target table for the {action_type} operation. Let's call this `identified_table_name_value`.
2.  Identify key columns/fields for this `identified_table_name_value` that are typically involved in an {action_type} operation.
3.  Provide clear guidance and a template for the user.

Respond in JSON format with the following fields:
    "response_type": "DML_GUIDANCE_PROVIDED",
    "target_table": "`identified_table_name_value` (your best guess for the table name, or 'Unknown' if too vague)",
    "suggested_fields": ["field1_name", "field2_name", ...] (a list of key field names for `identified_table_name_value` relevant to the action; empty list if target_table is Unknown or no specific fields are obvious),
    "guidance_text": "A string like: 'To {action_type} data for table `identified_table_name_value`, please provide details for the following fields, or describe using a text template.' (Construct this string replacing `identified_table_name_value` with the actual table name you identified. If table is Unknown, provide a generic message.)",
    "fields_template_text": "For ADD: 'Column1=Value1, Column2=Value2, ...'. For DELETE: 'Specify conditions like Column1=Value1 AND Column2=Value2 to identify records.'",
    "example_text": "A string like: 'Example for {action_type} on `identified_table_name_value`: [Provide a short, concrete example...]' (Construct this string replacing `identified_table_name_value` with the actual table name you identified)"

If the initial description is too vague to identify a target table:
    Set "target_table": "Unknown".
    Set "suggested_fields": [].
    Set "guidance_text": "Your description is a bit too general. Could you please specify which table you're interested in and provide more details for the {action_type} operation?".
    Omit "fields_template_text" and "example_text".
"""
dml_guidance_prompt = ChatPromptTemplate.from_template(dml_guidance_prompt_template_str)

dml_generation_prompt_template_str = """
You are an expert SQL generation assistant for DML.
Based on the user's structured request, the action ({action_type}), and schema, generate a SQL {action_type} statement.

Action: {action_type_description}
User's Structured Details: {user_structured_details}
Database Schema: {schema}

Instructions:
1.  For DELETE: A WHERE clause is MANDATORY. If details are insufficient for a safe WHERE clause, respond: "Error generating DML: Deletion criteria are too vague or unsafe. Please provide specific identifiers."
2.  For INSERT: Ensure all necessary non-nullable columns (without defaults) are covered. If critical info is missing, respond: "Error generating DML: Missing critical information for insert: [list missing fields, e.g., 'ColumnName']."
3.  Output ONLY the SQL DML statement or an error message starting with "Error generating DML:".

SQL {action_type} Statement or Error:
"""
dml_generation_prompt = ChatPromptTemplate.from_template(dml_generation_prompt_template_str)

nl_response_prompt_template_str = """
User Question: {question}
Generated SQL Query: {generated_sql}
SQL Query Result: {sql_response}
Provide a concise natural language answer. If empty, state no data found. If error, mention it.
Answer:
"""
nl_response_prompt = ChatPromptTemplate.from_template(nl_response_prompt_template_str)

db_summary_prompt_template_str = """
Database Schema:
{schema}
1. Provide a 3-line summary of this database's purpose and content.
2. List up to 5-7 main tables. Briefly state their likely record count (e.g., "many records", "few records") if inferable.
Summary:
"""
db_summary_prompt = ChatPromptTemplate.from_template(db_summary_prompt_template_str)

# --- 7. Langchain Chains ---
initial_processing_chain = ( RunnablePassthrough.assign(schema=get_schema) | sql_intent_prompt | llm | SimpleStrParser() | JsonOutputParser() )
select_answer_chain = ( nl_response_prompt | llm | StrOutputParser() )
dml_guidance_chain = ( dml_guidance_prompt | llm | SimpleStrParser() | JsonOutputParser() )
dml_generation_chain = ( dml_generation_prompt | llm | SimpleStrParser() )
db_summary_chain = ( RunnablePassthrough.assign(schema=get_schema) | db_summary_prompt | llm | StrOutputParser() )

# --- 8. Streamlit UI Section ---
st.markdown("""
<style>
    /* General body and font */
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
    }

    /* Buttons */
    .stButton>button { 
        border-radius: 8px; 
        padding: 8px 18px; 
        font-weight: 500; 
        border: 1px solid #d1d1d1; /* Slightly more visible border */
        background-color: #ffffff; /* White background */
        color: #333333; /* Darker text */
        transition: background-color 0.2s ease-in-out, color 0.2s ease-in-out, border-color 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background-color: #f0f0f0; /* Light grey hover */
        border-color: #c1c1c1;
    }
    .stButton>button[kind="primary"] { /* Primary buttons */
        background-color: #007bff; /* Streamlit's primary blue, or your choice */
        color: white;
        border: 1px solid #007bff;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #0056b3;
        border-color: #0056b3;
    }

    /* Inputs */
    .stChatInput>div>div>input, 
    .stTextArea textarea,
    .stTextInput>div>div>input { 
        border-radius: 8px; 
        border: 1px solid #d1d1d1; /* Consistent border for inputs */
        padding: 10px; /* More padding inside inputs */
    }
    .stChatInput>div>div>input:focus,
    .stTextArea textarea:focus,
    .stTextInput>div>div>input:focus {
        border-color: #007bff; /* Highlight focus with primary color */
        box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25); /* Focus shadow */
    }
    
    /* Main app title */
    h1 { 
        font-size: 2.2em; 
        font-weight: 600;
        color: #2c3e50; 
        text-align: center;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    /* Section headers */
    h3 { 
        color: #34495e; 
        border-bottom: 1px solid #eaeaea;
        padding-bottom: 0.4rem;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
        font-size: 1.3em;
    }
    
    /* Main container padding */
    .main .block-container { 
        padding-top: 1.5rem; 
        padding-bottom: 1.5rem;
        padding-left: 1.5rem; 
        padding-right: 1.5rem;
    }

    /* Chat messages styling */
    .stChatMessage {
        border-radius: 10px;
        padding: 0.8rem 1.1rem; /* Slightly more padding */
        margin-bottom: 0.6rem;
        border: 1px solid transparent; /* Base border */
    }
    div[data-testid="stChatMessage"]:has(span[data-testid="chatAvatarIcon-assistant"]) {
        background-color: #f8f9fa; /* Very light grey for assistant messages */
        border-color: #e9ecef; /* Subtle border for assistant messages */
    }
    div[data-testid="stChatMessage"]:has(span[data-testid="chatAvatarIcon-user"]) {
        background-color: #e7f5ff; /* Light blue for user messages for distinction */
        border-color: #cce7ff;
    }

    /* Expander styling */
    [data-testid="stExpander"] {
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    [data-testid="stExpander"] summary {
        font-weight: 500;
    }

    /* Code block styling */
    [data-testid="stCodeBlock"] {
        border-radius: 8px;
    }

    /* Sidebar styling - let Streamlit handle its default for better theme consistency */
    /* [data-testid="stSidebar"] { background-color: #f0f2f6; } */
    [data-testid="stSidebar"] .stMarkdown h3 { /* Subheaders in sidebar */
        font-size: 1.1em;
        color: #495057;
    }
    [data-testid="stSidebar"] .stMarkdown p, 
    [data-testid="stSidebar"] .stMarkdown li {
        font-size: 0.95em;
    }

</style>
""", unsafe_allow_html=True)

st.title("SQL AI Assistant Pro+")

st.markdown("### Quick Actions")
cols = st.columns([1, 1, 1.5]) # Add, Delete, Summarize
if cols[0].button("➕ Add Data", use_container_width=True, key="add_data_button"):
    st.session_state.current_action = "add_data_initial_input"
    st.session_state.dml_initial_description = ""
    st.session_state.dml_form_inputs = {}
    st.session_state.dml_text_details = ""
    st.session_state.dml_guidance_message = None
    st.session_state.dml_input_method = None
    st.rerun()
if cols[1].button("➖ Delete Data", use_container_width=True, key="delete_data_button"):
    st.session_state.current_action = "delete_data_initial_input"
    st.session_state.dml_initial_description = ""
    st.session_state.dml_form_inputs = {}
    st.session_state.dml_text_details = ""
    st.session_state.dml_guidance_message = None
    st.session_state.dml_input_method = None
    st.rerun()
if cols[2].button("📊 Summarize Database", use_container_width=True, key="summarize_db_button"):
    st.session_state.current_action = "summarize_db"
    st.rerun()
st.markdown("---")

# Session State Init
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": {"ai_response": "Hello! Use the quick action buttons or ask a question below."}}]
# Initialize other session state variables if not present
for key, default_val in [
    ("current_action", None),
    ("dml_initial_description", ""),
    ("dml_form_inputs", {}),
    ("dml_text_details", ""),
    ("dml_guidance_message", None),
    ("dml_input_method", None),
    ("pending_dml_confirmation", None)
]:
    if key not in st.session_state:
        st.session_state[key] = default_val


# --- UI for DML Stages ---
# Stage 1: Get initial DML description
if st.session_state.current_action in ["add_data_initial_input", "delete_data_initial_input"]:
    action_verb = "Add" if "add" in st.session_state.current_action else "Delete"
    st.subheader(f"Describe Data to {action_verb}")
    st.session_state.dml_initial_description = st.text_area(
        f"Briefly describe what you want to {action_verb.lower()} (e.g., 'add a new rock album by Test Band', 'delete customer with ID 123')",
        value=st.session_state.dml_initial_description, height=80, key=f"dml_init_desc_{action_verb}"
    )
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button(f"Get Guidance for {action_verb}", type="primary", use_container_width=True):
            if st.session_state.dml_initial_description.strip():
                st.session_state.current_action = f"process_initial_dml_description_{action_verb.lower()}"
                st.rerun()
            else: st.warning("Please provide an initial description.")
    with col2:
        if st.button("Cancel", use_container_width=True): 
            st.session_state.current_action = None; st.rerun()

# Stage 2: Display guidance and offer input methods (Form or Text)
elif st.session_state.current_action in ["awaiting_dml_input_method_add", "awaiting_dml_input_method_delete"]:
    action_verb = "Add" if "add" in st.session_state.current_action else "Delete"
    guidance = st.session_state.dml_guidance_message
    if guidance:
        st.subheader(f"Provide Details for {action_verb} Operation")
        st.info(guidance.get("guidance_text", "Please provide specific details."))
        target_table = guidance.get("target_table", "Unknown")
        if target_table != "Unknown":
            st.markdown(f"The AI suggests the target table is: **`{target_table}`**")

        st.markdown("##### How would you like to provide the details?")
        col1, col2, col3 = st.columns([1,1,1])
        with col1:
            if st.button("📋 Fill Form", use_container_width=True, disabled=(target_table == "Unknown" or not guidance.get("suggested_fields"))):
                st.session_state.dml_input_method = "form"
                st.session_state.current_action = f"awaiting_structured_dml_details_{action_verb.lower()}"
                st.rerun()
        with col2:
            if st.button("✍️ Describe in Text", use_container_width=True):
                st.session_state.dml_input_method = "text"
                st.session_state.current_action = f"awaiting_structured_dml_details_{action_verb.lower()}"
                st.rerun()
        with col3:
            if st.button("❌ Cancel Operation", use_container_width=True):
                st.session_state.current_action = None; st.session_state.dml_guidance_message = None; st.rerun()

        if target_table == "Unknown" or not guidance.get("suggested_fields"):
            st.caption("Form input is disabled as the target table or fields could not be clearly identified. Please use 'Describe in Text'.")
    else:
        st.error("Guidance message not found. Please start the DML action again.")
        st.session_state.current_action = None

# Stage 2b: Input details (Form or Text)
elif st.session_state.current_action in ["awaiting_structured_dml_details_add", "awaiting_structured_dml_details_delete"]:
    action_verb = "Add" if "add" in st.session_state.current_action else "Delete"
    guidance = st.session_state.dml_guidance_message

    if not guidance:
        st.error("Error: DML guidance is missing. Please restart the Add/Delete action."); st.stop()

    st.subheader(f"Enter Details for {action_verb} on Table: `{guidance.get('target_table', 'Unknown')}`")

    if st.session_state.dml_input_method == "form":
        st.markdown("Please fill in the values for the suggested fields:")
        suggested_fields = guidance.get("suggested_fields", [])
        if not suggested_fields:
            st.warning("No specific fields were suggested by the AI. Please use the 'Describe in Text' option or ensure your initial description was clear.")
        else:
            with st.form(key=f"dml_form_{action_verb}"):
                for field in suggested_fields:
                    st.session_state.dml_form_inputs[field] = st.text_input(
                        f"{field}:",
                        value=st.session_state.dml_form_inputs.get(field, ""),
                        key=f"form_input_{action_verb}_{field.replace(' ','_')}"
                    )
                form_submit_button = st.form_submit_button(label=f"Generate {action_verb} Command from Form")
                if form_submit_button:
                    if any(st.session_state.dml_form_inputs.get(f) for f in suggested_fields if suggested_fields):
                        st.session_state.current_action = f"process_structured_dml_{action_verb.lower()}"
                        st.rerun()
                    elif not suggested_fields:
                         st.warning("Cannot proceed with form as no fields were suggested. Try 'Describe in Text'.")
                    else:
                        st.warning("Please fill in at least one field in the form.")


    elif st.session_state.dml_input_method == "text":
        st.info(guidance.get("guidance_text", "Please provide specific details."))
        if guidance.get("fields_template_text"): st.markdown(f"**Text Template Suggestion:** `{guidance.get('fields_template_text')}`")
        if guidance.get("example_text"): st.markdown(f"**Example:** `{guidance.get('example_text')}`")
        st.session_state.dml_text_details = st.text_area(
            "Enter structured details based on the guidance above:",
            value=st.session_state.dml_text_details, height=120, key=f"dml_text_details_{action_verb}"
        )
        if st.button(f"Generate {action_verb} Command from Text", type="primary"):
            if st.session_state.dml_text_details.strip():
                st.session_state.current_action = f"process_structured_dml_{action_verb.lower()}"
                st.rerun()
            else:
                st.warning("Please provide the structured details in text.")
    else:
        st.error("Input method not selected. Please restart the Add/Delete action.")

    if st.button("Go Back / Cancel Details Input"):
        st.session_state.current_action = f"awaiting_dml_input_method_{action_verb.lower()}" # Go back to method selection
        # Don't clear guidance_message here, it's needed if user goes back
        # st.session_state.dml_input_method = None # Will be re-selected
        st.session_state.dml_form_inputs = {}
        st.session_state.dml_text_details = ""
        st.rerun()


# Stage 3: DML Confirmation
elif st.session_state.pending_dml_confirmation:
    action_verb = st.session_state.pending_dml_confirmation["action"]
    dml_sql = st.session_state.pending_dml_confirmation["sql"]
    st.warning(f"⚠️ **Confirm Database Modification: {action_verb.capitalize()} Data**")
    st.markdown(f"The AI proposes the following SQL command:")
    st.code(dml_sql, language="sql")
    st.markdown("**Executing this will alter your database. This is a demonstration and will not actually execute changes.**")
    c1, c2, _ = st.columns([1,1,2])
    if c1.button(f"Proceed with {action_verb.capitalize()} (Simulated)", type="primary", use_container_width=True):
        simulated_result = run_simulated_dml_query(dml_sql, action_verb)
        st.session_state.messages.append({"role": "assistant", "content": {"ai_response": simulated_result}})
        st.session_state.pending_dml_confirmation = None
        st.session_state.current_action = None
        st.rerun()
    if c2.button("Cancel Operation", use_container_width=True):
        st.session_state.messages.append({"role": "assistant", "content": {"ai_response": f"{action_verb.capitalize()} operation cancelled."}})
        st.session_state.pending_dml_confirmation = None
        st.session_state.current_action = None
        st.rerun()

# --- Display Chat History ---
st.markdown("### Chat / Query Results")
chat_container_height = 450 if not (st.session_state.current_action and "dml" in st.session_state.current_action) else 250
chat_container = st.container(height=chat_container_height, border=True)
with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            content = message["content"]
            if isinstance(content, dict):
                if content.get("ai_response"): st.markdown(content["ai_response"])
                generated_sql_display = content.get("generated_sql_display")
                if generated_sql_display:
                    if "Cannot answer" in generated_sql_display or "Error:" in generated_sql_display or "CLARIFICATION_NEEDED" in generated_sql_display:
                        st.warning(generated_sql_display)
                    else:
                        with st.expander("View Generated SELECT SQL", expanded=False):
                            st.code(generated_sql_display, language="sql")
                sql_result_display = content.get("sql_query_result_display")
                if sql_result_display and not ("Skipping execution" in sql_result_display or "Error executing SELECT query" in sql_result_display):
                    with st.expander("View Raw SQL Output (SELECT)", expanded=False):
                        try:
                            if isinstance(sql_result_display, str) and sql_result_display.strip().startswith("["):
                                parsed = ast.literal_eval(sql_result_display)
                                if parsed: st.dataframe(parsed, hide_index=True)
                                else: st.info("Query returned no data.")
                            elif not sql_result_display: st.info("Query returned no data.")
                            else: st.text(str(sql_result_display))
                        except: st.text(str(sql_result_display))
                elif sql_result_display and "Error executing SELECT query" in sql_result_display:
                    st.error(sql_result_display)
                if content.get("error"): st.error(content["error"])
            else: st.markdown(str(content))

# --- Chat Input ---
# Disable chat input if a DML form/confirmation is active to guide user focus
chat_input_disabled = bool(st.session_state.current_action and ("dml" in st.session_state.current_action or st.session_state.pending_dml_confirmation))
chat_input_placeholder = "Complete or cancel the Add/Delete process above to chat." if chat_input_disabled else "Ask a question about your data..."

if user_input := st.chat_input(chat_input_placeholder, key="main_chat_input", disabled=chat_input_disabled):
    if not chat_input_disabled: # Should always be true if input is enabled, but good practice
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.current_action = "process_chat_input"
        st.rerun()

# --- Logic for Processing Actions ---
if 'current_action' in st.session_state and st.session_state.current_action:
    action_to_process = st.session_state.current_action
    # No assistant_response_content here, it's built within each block

    try:
        if action_to_process == "process_chat_input":
            with st.spinner("AI is processing your query..."):
                # ... (rest of process_chat_input logic - same as previous version)
                user_query = st.session_state.messages[-1]["content"]
                llm_response_json = initial_processing_chain.invoke({"question": user_query})
                response_type = llm_response_json.get("response_type")
                assistant_response_content = {}

                if response_type == "SELECT_QUERY":
                    generated_sql = llm_response_json.get("generated_sql")
                    assistant_response_content["generated_sql_display"] = generated_sql
                    if generated_sql and "Cannot answer" not in generated_sql:
                        sql_response_raw = run_select_query(generated_sql)
                        assistant_response_content["sql_query_result_display"] = sql_response_raw
                        nl_answer = select_answer_chain.invoke({"question": user_query, "generated_sql": generated_sql, "sql_response": sql_response_raw})
                        assistant_response_content["ai_response"] = nl_answer
                    else:
                        assistant_response_content["ai_response"] = generated_sql
                elif response_type == "CLARIFICATION_NEEDED_FOR_SELECT" or response_type == "DML_INTENT_DETECTED" or response_type == "GENERAL_RESPONSE":
                    assistant_response_content["ai_response"] = llm_response_json.get("ai_response")
                elif response_type == "DATABASE_OVERVIEW_REQUEST":
                    summary = db_summary_chain.invoke({})
                    assistant_response_content["ai_response"] = f"**Database Overview:**\n\n{summary}"
                else:
                    assistant_response_content["error"] = "Unexpected AI response type."
            st.session_state.messages.append({"role": "assistant", "content": assistant_response_content})
            st.session_state.current_action = None
            st.rerun()

        elif action_to_process.startswith("process_initial_dml_description_"):
            with st.spinner("AI is preparing guidance..."):
                action_verb = "add" if "add" in action_to_process else "delete"
                action_desc = "adding new data" if action_verb == "add" else "deleting existing data"
                initial_desc = st.session_state.dml_initial_description
                guidance_json = dml_guidance_chain.invoke({
                    "action_type": action_verb,
                    "action_description": action_desc,
                    "user_initial_description": initial_desc,
                    "schema": get_schema()
                })
                st.session_state.dml_guidance_message = guidance_json
                st.session_state.current_action = f"awaiting_dml_input_method_{action_verb}"
            st.rerun()

        elif action_to_process.startswith("process_structured_dml_"):
            with st.spinner("AI is generating DML command..."):
                action_verb = "add" if "add" in action_to_process else "delete"
                action_desc = "adding new data" if action_verb == "add" else "deleting existing data"
                
                user_structured_details_str = ""
                if st.session_state.dml_input_method == "form":
                    filled_fields = {k: v for k, v in st.session_state.dml_form_inputs.items() if v}
                    # Convert to a string format the LLM can understand, e.g., "Field1='Value1', Field2='Value2'"
                    # This formatting might need to be explicitly taught to the DML generation prompt.
                    user_structured_details_str = ", ".join([f"{k}='{str(v).replace('\'', '\'\'')}'" for k,v in filled_fields.items()]) # Basic SQL string escaping for values
                elif st.session_state.dml_input_method == "text":
                    user_structured_details_str = st.session_state.dml_text_details
                else:
                    st.error("DML Input method not determined."); st.stop()

                generated_dml_sql = dml_generation_chain.invoke({
                    "action_type": action_verb.upper(),
                    "action_type_description": action_desc,
                    "user_structured_details": user_structured_details_str,
                    "schema": get_schema()
                })
                if generated_dml_sql.startswith("Error generating DML:"):
                    st.session_state.messages.append({"role": "assistant", "content": {"ai_response": generated_dml_sql}})
                    # Go back to the input method selection or initial description if DML gen fails?
                    # For now, just reset current_action to allow user to try again or cancel.
                    st.session_state.current_action = None 
                else:
                    st.session_state.pending_dml_confirmation = {"action": action_verb, "sql": generated_dml_sql}
                    # current_action will be reset by the confirmation UI logic
            st.rerun()

        elif action_to_process == "summarize_db":
            with st.spinner("AI is summarizing the database..."):
                summary = db_summary_chain.invoke({})
                st.session_state.messages.append({"role": "assistant", "content": {"ai_response": f"**Database Summary:**\n\n{summary}"}})
            st.session_state.current_action = None
            st.rerun()

    except json.JSONDecodeError as e:
        err_msg = f"AI response format error (not valid JSON): {str(e)}. The LLM might have responded in plain text instead of JSON."
        st.session_state.messages.append({"role": "assistant", "content": {"error": err_msg}})
        st.session_state.current_action = None; st.rerun()
    except Exception as e:
        import traceback
        err_msg = f"An unexpected error occurred: {str(e)}\n{traceback.format_exc()}"
        st.session_state.messages.append({"role": "assistant", "content": {"error": err_msg}})
        st.session_state.current_action = None; st.rerun()


# Sidebar general information
st.sidebar.markdown("---")
st.sidebar.header("User Guide & Tips")
st.sidebar.markdown("""
**Querying Data:**
- Ask specific questions (e.g., "List all albums by 'AC/DC'").
- If your query is vague, the AI will ask for clarification.

**Adding Data:**
1. Click "➕ Add Data".
2. Briefly describe what you want to add (e.g., "add a new artist").
3. Click "Get Guidance". The AI will suggest a target table and fields.
4. Choose "📋 Fill Form" (recommended if fields are suggested) or "✍️ Describe in Text".
5. Provide the details as guided.
6. Review the generated SQL command and confirm (simulated execution).

**Deleting Data:**
1. Click "➖ Delete Data".
2. Briefly describe what you want to delete, including specific criteria (e.g., "delete track with ID 5").
3. Click "Get Guidance".
4. Choose input method and provide details. **Be very specific with deletion criteria.**
5. Review and confirm the SQL command (simulated execution).

**Summarize Database:**
- Click "📊 Summarize Database" for a high-level overview.

**General Questions:**
- You can ask general questions about the database like "What kind of data does this store?" directly in the chat.

**Important Note:** All Add/Delete operations are **simulated** in this demo and do **not** make actual changes to your database.
""")
st.sidebar.markdown("---")
st.sidebar.caption("Powered by Google Gemini & Langchain")
