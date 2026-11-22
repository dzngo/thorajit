import streamlit as st
from dotenv import load_dotenv
from pathlib import Path


from ui import routing
from storage.question_events import QuestionEvents
from services.question_bank import load_questions

load_dotenv()


@st.cache_resource(show_spinner=False)
def initialize_question_counters(environment: str, questions: tuple[tuple[str, str], ...]) -> bool:
    QuestionEvents(environment=environment).initialize(questions)
    return True


@st.cache_data(ttl=60, show_spinner=False)
def question_catalog_for_counters(environment: str, database_url: str) -> tuple[tuple[str, str], ...]:
    """Refresh the counter catalog periodically instead of querying on every UI rerun."""
    return tuple((question["id"], question["text"]) for question in load_questions())


def main() -> None:
    st.set_page_config(
        page_title="Thorajit",
        page_icon=str(Path(__file__).parent / "design" / "thorajit" / "assets" / "icon.png"),
        layout="centered",
    )
    import os

    try:
        environment = os.getenv("WGY_ENV", "development")
        database_url = os.getenv("QUESTION_DB_NEO_URL") or os.getenv("QUESTION_STATS_DATABASE_URL", "")
        initialize_question_counters(environment, question_catalog_for_counters(environment, database_url))
    except Exception:
        st.warning("Question statistics are unavailable. They will be retried when the database is available.")
    routing.run()


if __name__ == "__main__":
    main()
