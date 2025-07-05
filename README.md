# SQL AI Assistant Pro+

## Description

SQL AI Assistant Pro+ is an advanced, AI-powered Streamlit application designed to simplify SQL database interactions. It allows users to query databases using natural language, receive AI-generated SQL, perform simulated data manipulation operations (Add, Update, Delete) with guidance, and even ask general knowledge questions. The assistant is schema-aware and provides an interactive chat interface for a seamless user experience.

## Features

*   **Natural Language to SQL:** Translates user questions in plain English into SQL SELECT queries.
*   **Guided DML Operations:** Assists users in Adding, Updating, and Deleting data with step-by-step guidance.
    *   All DML operations are **simulated** and do not modify the actual database.
*   **User Review and Editing of DML:** Allows users to inspect and modify AI-generated DML (INSERT, UPDATE, DELETE) statements before simulated execution.
*   **Database Schema-Aware:** Utilizes the database schema to generate more accurate and relevant SQL queries.
*   **Database Summarization:** Provides a concise summary of the connected database's purpose and main tables.
*   **General Knowledge Q&A:** Capable of answering general knowledge questions unrelated to the database.
*   **Conversational Follow-ups:** Suggests relevant follow-up questions or actions to enhance the interactive experience.
*   **Interactive Chat Interface:** User-friendly chat interface built with Streamlit.
*   **Customizable Configuration:** Easily configured using Streamlit secrets for API keys and database credentials.

## Tech Stack

*   **Programming Language:** Python
*   **Web Framework:** Streamlit
*   **LLM Orchestration:** Langchain
*   **AI Model:** Google Gemini API (specifically `gemini-1.5-flash`)
*   **Database:** MySQL (example implementation, adaptable to other SQL databases supported by SQLAlchemy)
*   **Supporting Libraries:** `google-generativeai`, `langchain-google-genai`, `langchain-community`, `pymysql`, `mysql-connector-python`, `pandas`

## Setup Instructions

### Prerequisites

*   Python 3.8 or newer.
*   Access to a MySQL database. If you intend to use a different SQL database, you will need to adjust the `mysql_uri` in `app.py` and potentially install a different database driver.
*   Google API Key with access to the Gemini API.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://your-repository-url-here.com/sql-ai-assistant-pro.git
    # Replace with the actual repository URL when available
    ```

2.  **Navigate to the project directory:**
    ```bash
    cd sql-ai-assistant-pro
    # Replace with your actual project directory name
    ```

3.  **Create a Python virtual environment:**
    ```bash
    python -m venv .venv
    ```

4.  **Activate the virtual environment:**
    *   On Windows:
        ```bash
        .venv\Scripts\activate
        ```
    *   On macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```

5.  **Install required Python packages:**
    It's recommended to create a `requirements.txt` file based on the imports in `app.py`. For a quick start, you can install the primary dependencies:
    ```bash
    pip install streamlit langchain langchain-google-genai google-generativeai langchain-community pymysql mysql-connector-python pandas
    ```
    For a complete list, review the `import` statements in `app.py` and install accordingly.

### Configuration (`.streamlit/secrets.toml`)

Create a file named `secrets.toml` inside a `.streamlit` directory in the root of your project (`<project_directory>/.streamlit/secrets.toml`).

Add your Google API key and database connection details to this file. Here's a template:

```toml
GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY_HERE"

# MySQL Connection Details
# These are examples; update them with your actual database credentials.
MYSQL_USER = "adit"
MYSQL_PASSWORD = "yourpassword"
MYSQL_HOST = "localhost"
MYSQL_PORT = "3306" # Streamlit's st.secrets.get() retrieves this as a string.
MYSQL_DATABASE = "mychinook" # Example database name
```

**Note on `MYSQL_PORT`**: The `app.py` script uses `st.secrets.get("MYSQL_PORT", "3306")`, so providing it as a string in the `secrets.toml` file is appropriate.

## How to Run

1.  **Ensure your MySQL server is running** and accessible with the credentials you provided in `secrets.toml`.
2.  **Verify that the database specified (`MYSQL_DATABASE`) exists** on your MySQL server. The "mychinook" database is a common sample database for SQL tutorials. If you don't have it, you can use any other database you have access to, but the AI's schema awareness will be based on that database.
3.  **Activate your virtual environment** if you haven't already:
    *   Windows: `.venv\Scripts\activate`
    *   macOS/Linux: `source .venv/bin/activate`
4.  **Run the Streamlit application** from the project's root directory:
    ```bash
    streamlit run app.py
    ```
    The application should open in your web browser.

## Usage

*   **Chat Interface:** Type your questions directly into the chat input at the bottom of the page.
    *   Ask for data (e.g., "Show me all artists from Canada").
    *   Ask general knowledge questions (e.g., "What is a relational database?").
*   **Quick Actions:** Use the buttons for specific tasks:
    *   **➕ Add Data:** Initiate a guided process to add new records to a table.
    *   **🔄 Update Data:** Start a guided process to modify existing records in a table.
    *   **➖ Delete Data:** Begin a guided process to delete records from a table.
    *   **📊 Summarize Database:** Get an AI-generated overview of the connected database.
*   **DML Operations:**
    *   When performing Add, Update, or Delete operations, the AI will guide you.
    *   You'll be asked for an initial description, then presented with options to provide details (via form or text).
    *   Before any (simulated) execution, you can review and **edit** the AI-generated SQL command in a text area.
*   **Important Note:** All Add, Update, and Delete operations are **simulated** by default. This means the AI will generate the SQL and show you what would happen, but **no actual changes will be made to your database.**

## Code Structure (High-Level)

*   `app.py`: This is the main file containing all the Streamlit UI elements, application logic, and the definitions for Langchain chains and prompts used to interact with the Google Gemini LLM.
    *   **Page Configuration & Secrets:** Sets up the Streamlit page and loads API keys/database credentials.
    *   **LLM & Database Connection:** Initializes the Gemini LLM and the SQLDatabase connection.
    *   **Helper Functions & Prompts:** Contains functions for schema retrieval, query execution (simulated for DML), and various prompt templates (`sql_intent_prompt_template_str`, `dml_guidance_prompt_template_str`, `dml_generation_prompt_template_str`, `nl_response_prompt_template_str`, etc.) that define how the AI behaves for different tasks.
    *   **Langchain Chains:** Defines the sequences of operations (e.g., `initial_processing_chain`, `select_answer_chain`) that combine prompts, the LLM, and output parsers.
    *   **Streamlit UI Section:** Builds the interactive user interface, including quick action buttons, chat history, input areas, and DML operation stages.
    *   **Logic for Processing Actions:** Manages the application's state and orchestrates the calls to different chains based on user input and current action.
    *   **Sidebar:** Contains the user guide and application information.

This structure centralizes the application's functionality within a single script, leveraging Streamlit's capabilities for building interactive web UIs and Langchain for LLM interactions.
