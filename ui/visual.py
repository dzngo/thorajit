"""Shared visual styling for the Thorajit Streamlit interface."""

import base64
import html
from pathlib import Path
from functools import lru_cache

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "design" / "thorajit" / "assets"
BACKGROUND = ASSETS / "background.webp"
LOGO = ASSETS / "logo-transparent.webp"


@lru_cache(maxsize=None)
def _asset_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def apply_style() -> None:
    background = _asset_base64(BACKGROUND)
    vietnamese = _asset_base64(ASSETS / "nunito-vietnamese-wght-normal.woff2")
    latin_ext = _asset_base64(ASSETS / "nunito-latin-ext-wght-normal.woff2")
    latin = _asset_base64(ASSETS / "nunito-latin-wght-normal.woff2")
    st.html(f"""
    <style>
    @font-face {{ font-family: 'Nunito'; font-style: normal; font-weight: 200 1000; font-display: swap;
      src: url('data:font/woff2;base64,{vietnamese}') format('woff2');
      unicode-range: U+0102-0103,U+0110-0111,U+0128-0129,U+0168-0169,U+01A0-01A1,U+01AF-01B0,U+0300-0301,U+0303-0304,U+0308-0309,U+0323,U+0329,U+1EA0-1EF9,U+20AB; }}
    @font-face {{ font-family: 'Nunito'; font-style: normal; font-weight: 200 1000; font-display: swap;
      src: url('data:font/woff2;base64,{latin_ext}') format('woff2');
      unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF; }}
    @font-face {{ font-family: 'Nunito'; font-style: normal; font-weight: 200 1000; font-display: swap;
      src: url('data:font/woff2;base64,{latin}') format('woff2');
      unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD; }}
    .stApp {{ background: #dfebce url('data:image/webp;base64,{background}') center top / cover fixed no-repeat; color: #603112; }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stAppViewContainer"] > .main {{ background: transparent; }}
    [data-testid="stMainBlockContainer"] {{ max-width: 520px; padding: 1rem 1.2rem 4rem; }}
    .stApp, .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea {{ font-family: 'Nunito', sans-serif; color: #603112; }}
    .stApp h1, .stApp h2, .stApp h3 {{ font-family: 'Nunito', sans-serif; color: #603112; font-weight: 900; }}
    .stApp h2 {{ background: #ffedcf; border-radius: 3rem; text-align: center; padding: .65rem 1rem;
      margin-bottom: .65rem; font-size: 2rem; line-height: 1.15; }}
    .stApp h3 {{ font-size: 1.35rem; }}
    [data-testid="stImage"] {{ margin: auto; }}
    [data-testid="stCaptionContainer"] p {{ color: #6b492d; }}
    [data-testid="stVerticalBlock"][class*="st-key-card_"] {{ background: #fff0d4; border: 2px solid #9b5c24; border-radius: 24px; padding: 1rem; box-shadow: 0 5px 0 #957a4b33; }}
    div.stButton button {{ min-height: 3.5rem; border-radius: 999px; font-weight: 900; font-size: 1.12rem; border: 2px solid #9d591e; background: #fff0d4; color: #603112; box-shadow: 0 4px 0 #84512c;
      transition: transform .1s ease, box-shadow .1s ease; }}
    div.stButton > button[kind="primary"] {{ background: #a45617; border-color: #8e4817; color: #fff1d8; box-shadow: 0 5px 0 #69350f; }}
    div.stButton button p {{ color: inherit; font-size: 1.15rem; font-weight: 900; }}
    div.stButton button:hover {{ border-color: #6e7b17; color: #603112; background: #f7dfad; }}
    div.stButton > button[kind="primary"]:hover {{ background: #8d4815; color: #fff8ed; }}
    .stApp div.stButton > button:active:not(:disabled) {{ transform: translateY(3px); box-shadow: 0 1px 0 #4c3218; }}
    @media (prefers-reduced-motion: reduce) {{ div.stButton > button {{ transition: none; }} }}
    div.stButton button:focus-visible, .stApp input:focus-visible, .stApp textarea:focus-visible {{ outline: 3px solid #4a6414; outline-offset: 3px; }}
    [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{ background: #fff0d9 !important; border: 2px solid #a05f26 !important; border-radius: 24px !important; }}
    [data-baseweb="input"] input, [data-baseweb="textarea"] textarea {{ color: #603112 !important; }}
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {{ background: #fff0d9 !important; border: 0 !important; border-radius: 22px !important; min-height: 3rem; padding: .7rem 1rem; }}
    [class*="st-key-card_answer_"] textarea:focus-visible {{ outline: none; }}
    [class*="st-key-card_answer_"] [data-testid="stTextAreaRootElement"] {{
      border: 2px solid #a05f26 !important; border-radius: 24px; }}
    [class*="st-key-card_answer_"] [data-testid="stTextAreaRootElement"]:focus-within {{
      border-color: #78451f !important; box-shadow: 0 0 0 2px #e0b878; }}
    [data-testid="stAlert"] {{ border-radius: 22px; background: #fff0d4; color: #603112; }}
    [data-testid="stExpander"] {{ background: #fff0d4aa; border: 1px solid #a36b32; border-radius: 20px; }}
    /* The welcome screen is a game cover: larger actions and a softer title panel. */
    .st-key-welcome {{ gap: 1.4rem !important; }}
    .st-key-welcome h2 {{ padding: 1.45rem 1.25rem; border-radius: 42% 46% 40% 44% / 48% 44% 52% 46%;
      background: #ffedcf; font-size: clamp(1.65rem, 7vw, 2.1rem); }}
    .st-key-welcome .stButton > button {{ min-height: 5rem; border-width: 3px; }}
    .st-key-welcome .stButton > button p {{ font-size: 1.6rem; }}
    .st-key-welcome .st-key-entry_join button {{ border-color: #83951b; box-shadow: 0 5px 0 #586711;
      background: linear-gradient(165deg, #fff1d8 75%, #dae5a0 75%); }}
    .st-key-welcome [data-testid="stExpander"] {{ margin: .5rem auto 0; width: min(100%, 24rem); }}
    [data-testid="stPills"] button, [data-testid="stSegmentedControl"] button {{ background: #fff0d4; color: #603112; border: 1px solid #aa773d; border-radius: 20px; font-weight: 800; }}
    [data-testid="stPills"] button[aria-pressed="true"], [data-testid="stSegmentedControl"] button[aria-pressed="true"] {{ background: #e0e8a3; border: 2px solid #718615; color: #354300; }}
    [class*="_theme_select"] [role="radiogroup"] {{ display: grid; grid-auto-flow: column;
      grid-template-rows: repeat(5, auto); grid-auto-columns: minmax(8rem, 1fr); gap: .5rem; overflow-x: auto; }}
    [class*="_theme_select"] [role="radio"], [class*="_level_select"] [role="radio"] {{
      min-height: 3rem; background: #fff0d4; color: #603112; border: 2px solid #a56b32;
      border-radius: 18px; font-weight: 800; }}
    [class*="_theme_select"] [role="radio"][aria-checked="true"],
    [class*="_level_select"] [role="radio"][aria-checked="true"] {{ background: #dce8a5; border-color: #718615; }}
    [class*="_theme_select"] [role="radio"][aria-checked="true"]::after,
    [class*="_level_select"] [role="radio"][aria-checked="true"]::after {{ content: "✓"; color: #4a6414;
      font-size: 1.1rem; font-weight: 900; margin-left: .35rem; }}
    [class*="_vibe_confirm"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_vibe_confirm"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    .room-card-title {{ margin: 0 0 .5rem; overflow-wrap: anywhere; color: #603112; font-size: 1.45rem; font-weight: 900; }}
    .room-details {{ margin: 0; }}
    .room-detail {{ display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
      padding: .55rem 0; border-top: 1px solid #d9bd8d; overflow-wrap: anywhere; }}
    .room-detail dt {{ color: #795538; font-weight: 700; }}
    .room-detail dd {{ margin: 0; text-align: right; min-width: 0; font-weight: 800; }}
    .round-context {{ display: flex; flex-direction: column; align-items: center; gap: .45rem; margin: .4rem 0 1rem; }}
    .round-pill, .role-pill {{ padding: .35rem 1rem; border-radius: 999px; font-weight: 900; text-align: center;
      max-width: 100%; overflow-wrap: anywhere; }}
    .round-pill {{ background: #986137; color: #fff0d4; }}
    .role-pill {{ background: #f7dfad; color: #603112; }}
    .waiting-card {{ text-align: center; color: #603112; }}
    .waiting-title {{ background: #fff0d4; border-radius: 28px; padding: 2rem 1.4rem;
      font-size: clamp(1.45rem, 5vw, 2rem); line-height: 1.2; font-weight: 900; overflow-wrap: anywhere;
      box-shadow: 0 5px 0 #957a4b33; }}
    .waiting-detail {{ padding: 1.5rem .5rem .8rem; font-size: 1.1rem; }}
    .waiting-dots {{ display: flex; justify-content: center; gap: .8rem; padding: .5rem; }}
    .waiting-dots span {{ width: .8rem; height: .8rem; border-radius: 50%; background: #e9ad45;
      animation: waiting-bounce 1.2s ease-in-out infinite; }}
    .waiting-dots span:first-child {{ background: #f3d28a; }}
    .waiting-dots span:nth-child(2) {{ animation-delay: .15s; }}
    .waiting-dots span:last-child {{ background: #c67817; animation-delay: .3s; }}
    @keyframes waiting-bounce {{ 0%, 60%, 100% {{ transform: translateY(0); }} 30% {{ transform: translateY(-.3rem); }} }}
    @media (prefers-reduced-motion: reduce) {{ .waiting-dots span {{ animation: none; }} }}
    .waiting-card.compact {{ background: #fff0d4; border-radius: 28px; padding: .5rem 1rem; box-shadow: 0 5px 0 #957a4b33; }}
    .waiting-card.compact .waiting-title {{ background: transparent; box-shadow: none; padding: 1rem .3rem .4rem; }}
    .answer-summary {{ background: #fff0d4; border: 2px solid #e3c99c; border-radius: 24px;
      padding: 1rem 1.2rem; margin: .5rem 0 1rem; overflow-wrap: anywhere; }}
    .answer-summary-label {{ font-weight: 900; margin-bottom: .35rem; }}
    .answer-summary-value {{ font-size: 1.2rem; font-weight: 800; }}
    .question-card {{ background: #fff0d4; border: 2px solid #f6e2bd; border-radius: 28px;
      padding: 2rem 1.4rem; margin: .5rem 0 1rem; text-align: center; overflow-wrap: anywhere;
      color: #603112; font-size: clamp(1.45rem, 5vw, 2rem); line-height: 1.2; font-weight: 900;
      box-shadow: 0 5px 0 #957a4b33; }}
    .st-key-question_setup {{ background: #fff0d4; border: 2px solid #f6e2bd; border-radius: 999px;
      padding: .45rem .55rem .45rem 1rem; box-shadow: 0 5px 0 #957a4b33; }}
    .st-key-question_setup [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; }}
    .st-key-question_setup [data-testid="stColumn"] {{ min-width: 0 !important; }}
    .st-key-question_setup [data-testid="stColumn"]:last-child {{ min-width: 5.5rem !important; }}
    .question-setup-text {{ display: flex; align-items: center; gap: .65rem; min-width: 0;
      color: #603112; font-size: clamp(1rem, 3.6vw, 1.2rem); font-weight: 900; line-height: 1.2;
      overflow-wrap: anywhere; }}
    .st-key-question_setup div.stButton button {{ min-height: 2.6rem; padding: .4rem .65rem;
      background: #dce5a6; border: 0; color: #354300; box-shadow: none; }}
    .st-key-question_setup div.stButton button p {{ font-size: 1rem; }}
    .st-key-question_setup div.stButton button:hover {{ background: #cbd889; color: #354300; }}
    .st-key-saved_question_grid [data-testid="stHorizontalBlock"] {{ overflow-x: auto; flex-wrap: nowrap; }}
    .st-key-saved_question_grid [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ min-width: min(17rem, 85vw); }}
    [class*="_saved_use_"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_saved_use_"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    [class*="_question_confirm"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_question_confirm"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    .judgment-card {{ background: #fff0d4; border: 2px solid #9b5c24; border-radius: 22px;
      padding: .8rem 1rem 1rem; margin: .65rem 0; overflow-wrap: anywhere; }}
    .judgment-card.storyteller {{ background: #f1f4cb; border-color: #78891b; }}
    .judgment-author {{ display: inline-block; background: #98501c; color: #fff0d4;
      border-radius: 999px; padding: .2rem .75rem; font-weight: 800; }}
    .judgment-card.storyteller .judgment-author {{ background: #63750c; }}
    .judgment-answer {{ margin-top: .5rem; font-size: 1.2rem; font-weight: 900; }}
    .decision-prompt {{ background: #fff0d4; border-radius: 24px; padding: 1rem; text-align: center;
      color: #603112; font-size: 1.15rem; font-weight: 900; overflow-wrap: anywhere;
      box-shadow: 0 4px 0 #957a4b33; }}
    .decision-status {{ border: 2px solid #98501c; border-radius: 24px; padding: .85rem 1rem;
      background: #f8e2b5; color: #603112; font-size: 1.3rem; font-weight: 900; text-align: center; }}
    .decision-status.correct {{ border-color: #63750c; background: #e0e9b0; color: #354300; }}
    [class*="_modify_answer_"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_modify_answer_"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    [class*="_submit_answer_"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_submit_answer_"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    [class*="_judgment_correct"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_judgment_correct"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    [class*="_next_turn_action"] div.stButton > button[kind="primary"],
    [class*="_view_results"] div.stButton > button[kind="primary"],
    .st-key-results_return_lobby div.stButton > button[kind="primary"],
    .st-key-results_back_entry div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_next_turn_action"] div.stButton > button[kind="primary"]:hover,
    [class*="_view_results"] div.stButton > button[kind="primary"]:hover,
    .st-key-results_return_lobby div.stButton > button[kind="primary"]:hover,
    .st-key-results_back_entry div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    .player-columns {{ display: flex; gap: .75rem; overflow-x: auto; padding: .2rem; }}
    .player-columns:focus-visible {{ outline: 3px solid #4a6414; outline-offset: 3px; }}
    .player-column {{ flex: 1 0 100%; min-width: 0; }}
    .player-columns.multiple .player-column {{ flex-basis: calc(50% - .375rem); min-width: 9rem; }}
    .player-row {{ display: flex; justify-content: space-between; gap: .5rem; padding: .4rem 0;
      border-bottom: 1px solid #dec49a; overflow-wrap: anywhere; }}
    .player-row span {{ min-width: 0; }}
    .player-row strong {{ white-space: nowrap; }}
    .vote-card {{ position: relative; display: flex; flex-direction: column; border: 2px solid #98501c; border-radius: 22px; margin: .8rem 0 1.1rem; background: #fff0d5; min-height: 3.75rem; overflow: visible; }}
    .vote-card.correct {{ border-color: #718615; }}
    .vote-background {{ position: absolute; inset: 0; border-radius: 19px; overflow: hidden; }}
    .vote-fill {{ position: absolute; inset: 0 auto 0 0; width: var(--share); background: #eec88b; opacity: .7; }}
    .vote-card.correct .vote-fill {{ background: #cbdc88; }}
    .vote-content {{ position: relative; flex: 1; padding: .65rem 1rem .8rem; display: flex; justify-content: space-between; align-items: center; gap: .5rem; font-size: 1.1rem; font-weight: 900; }}
    .vote-author, .vote-correct {{ position: absolute; color: white; border: 2px solid #fff0d5; border-radius: 999px; background: #94501d; padding: .1rem .65rem; font-weight: 800; font-size: .8rem; }}
    .vote-author {{ position: relative; align-self: flex-start; max-width: calc(100% - 1.4rem);
      margin: 0 .7rem -.8rem; overflow-wrap: anywhere; }}
    .correct .vote-author, .vote-correct {{ background: #63750c; }}
    .vote-correct {{ right: .5rem; top: -.8rem; }}
    .thor-moment-shape {{ position: absolute; z-index: 1; top: -1.7rem; width: 2.2rem; height: 2.2rem;
      border-radius: 38% 55% 43% 55%; opacity: 0; pointer-events: none; }}
    .thor-moment-shape.green {{ left: calc(50% - 2rem); background: #a0ac59; }}
    .thor-moment-shape.gold {{ left: 50%; background: #e7a444; mix-blend-mode: multiply; }}
    .thor-moment-spark {{ position: absolute; z-index: 1; top: -.7rem; color: #b7883e;
      font-size: .8rem; opacity: 0; pointer-events: none; }}
    .thor-moment-spark.left {{ left: calc(50% - 2.7rem); }}
    .thor-moment-spark.right {{ left: calc(50% + 2.1rem); }}
    .thor-moment .thor-moment-shape {{ animation: thor-shape 1.5s ease-out both; }}
    .thor-moment .thor-moment-spark {{ animation: thor-spark 1.5s ease-out both; }}
    .thor-moment-shape.green {{ --thor-start: -1rem; --thor-end: .35rem; }}
    .thor-moment-shape.gold {{ --thor-start: 1rem; --thor-end: -.35rem; }}
    @keyframes thor-shape {{ 0% {{ opacity: 0; transform: translateX(var(--thor-start)) scale(.7) rotate(-10deg); }}
      35% {{ opacity: .75; }} 65% {{ opacity: .75; transform: translateX(var(--thor-end)) scale(1) rotate(8deg); }}
      100% {{ opacity: 0; transform: translateX(var(--thor-end)) scale(.85) rotate(8deg); }} }}
    @keyframes thor-spark {{ 0%, 25% {{ opacity: 0; transform: scale(.5); }}
      50% {{ opacity: .85; }} 100% {{ opacity: 0; transform: translateY(-.8rem) scale(1.1); }} }}
    @media (prefers-reduced-motion: reduce) {{ .thor-moment .thor-moment-shape,
      .thor-moment .thor-moment-spark {{ animation: none; opacity: 0; }} }}
    .vote-columns {{ display: flex; gap: 1rem; overflow-x: auto; padding: .5rem .1rem 1rem; }}
    .vote-columns:has(.thor-moment) {{ padding-top: 1.8rem; }}
    .vote-columns:focus-visible, .results-rank-columns:focus-visible {{ outline: 3px solid #4a6414; outline-offset: 3px; }}
    .vote-column {{ flex: 1 0 100%; min-width: 0; }}
    .vote-columns.multiple .vote-column {{ flex-basis: calc(50% - .5rem); min-width: 13rem; }}
    .vote-content {{ overflow-wrap: anywhere; }}
    .vote-voters {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .25rem; }}
    .vote-voter {{ position: relative; font-size: 1.5rem; font-weight: 700; }}
    .vote-voter summary {{ cursor: pointer; list-style: none; border-radius: .4rem; }}
    .vote-voter summary::-webkit-details-marker {{ display: none; }}
    .vote-voter summary:focus-visible {{ outline: 3px solid #4a6414; outline-offset: 2px; }}
    .vote-voter-name {{ position: absolute; right: 0; top: 100%; z-index: 2; width: max-content; max-width: min(12rem, 60vw);
      padding: .3rem .6rem; border-radius: .6rem; background: #603112; color: #fff1d8;
      font-size: .85rem; overflow-wrap: anywhere; box-shadow: 0 2px 5px #60311255; }}
    .guess-instruction {{ text-align: center; overflow-wrap: anywhere; }}
    .story-answer-columns {{ display: flex; gap: .75rem; overflow-x: auto; padding: .2rem; }}
    .story-answer-columns:focus-visible {{ outline: 3px solid #4a6414; outline-offset: 3px; }}
    .story-answer-column {{ flex: 1 0 100%; min-width: 0; }}
    .story-answer-columns.multiple .story-answer-column {{ flex-basis: calc(50% - .375rem); min-width: 13rem; }}
    .story-answer {{ display: flex; flex-direction: column; gap: .3rem;
      margin-bottom: .5rem; padding: .75rem 1rem; border: 2px solid #a56b32; border-radius: 18px;
      background: #fff0d4; color: #603112; font-weight: 800; overflow-wrap: anywhere; }}
    .story-answer.own {{ border-color: #718615; background: #e1e9a9; }}
    .story-answer-label {{ color: #354300; font-size: .85rem; font-weight: 900; }}
    .stRadio [role="radiogroup"] {{ display: grid; grid-auto-flow: column; grid-template-rows: repeat(5, auto); grid-auto-columns: minmax(14rem, 1fr); overflow-x: auto; gap: .5rem; }}
    .stRadio [role="radiogroup"] label {{ background: #fff0d4; border: 2px solid #a56b32; border-radius: 18px; padding: .65rem; min-height: 3.5rem; }}
    .stRadio [role="radiogroup"] label p {{ font-size: 1rem; font-weight: 800; overflow-wrap: anywhere; }}
    [class*="_submit_guess_"] div.stButton > button[kind="primary"] {{ background: #63750c; border-color: #4e5f08; box-shadow: 0 5px 0 #4d5c09; }}
    [class*="_submit_guess_"] div.stButton > button[kind="primary"]:hover {{ background: #53640a; }}
    .stRadio [role="radiogroup"] label:has(input:checked) {{ background: #e1e9a9; border-color: #718615; }}
    .results-panels {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: .8rem; align-items: start; }}
    .results-ranking, .wg-results-panel {{ background: #fff0d4; border: 2px solid #9b5c24; border-radius: 22px; padding: 1rem; margin-bottom: .8rem; overflow-wrap: anywhere; }}
    .results-ranking h3, .wg-results-section-title {{ font-size: 1.15rem; font-weight: 900; margin: 0 0 .7rem; }}
    .results-rank-columns {{ display: flex; overflow-x: auto; gap: .7rem; }}
    .results-rank-column {{ flex: 1 0 100%; min-width: 10rem; }}
    .results-rank-columns.multiple .results-rank-column {{ flex-basis: calc(50% - .35rem); }}
    .results-row {{ display: flex; gap: .4rem; align-items: baseline; padding: .5rem 0; border-bottom: 1px solid #d8bb87; }}
    .results-row span {{ flex: 1; min-width: 0; }}
    .results-row b:last-child {{ white-space: nowrap; }}
    .wg-results-stat-grid {{ display: grid; gap: .55rem; }}
    .wg-results-panel > summary {{ cursor: pointer; }}
    .wg-results-panel > summary:focus-visible, .wg-results-bestie-columns:focus-visible {{ outline: 3px solid #4a6414; outline-offset: 3px; }}
    .wg-results-bestie-columns {{ display: flex; gap: .7rem; overflow-x: auto; padding: .4rem .1rem; }}
    .wg-results-bestie-column {{ display: grid; align-content: start; gap: .55rem; flex: 1 0 100%; min-width: 12rem; }}
    .wg-results-bestie-columns.multiple .wg-results-bestie-column {{ flex-basis: calc(50% - .35rem); }}
    .wg-results-stat-card, .wg-results-bestie-card {{ background: #f8e2b5; border-radius: 14px; padding: .6rem; }}
    .wg-results-stat-title, .wg-results-bestie-owner {{ font-weight: 900; }}
    .wg-results-stat-subtitle {{ color: #795538; font-size: .85rem; }}
    .wg-results-stat-value, .wg-results-bestie-value {{ font-weight: 700; }}
    .stApp div.stButton > button[kind="primary"] {{ background-image: linear-gradient(155deg,
      rgba(55, 35, 12, .08) 0 22%, transparent 22% 78%, rgba(55, 35, 12, .1) 78%); }}
    @media (min-width: 900px) {{
      .stApp:has(.results-panels) [data-testid="stMainBlockContainer"],
      .stApp:has(.vote-columns.multiple) [data-testid="stMainBlockContainer"] {{ max-width: 960px; }}
    }}
    @media (max-width: 600px) {{
      .results-panels {{ grid-template-columns: minmax(0, 1fr); }}
      .results-rank-columns.multiple .results-rank-column,
      .wg-results-bestie-columns.multiple .wg-results-bestie-column {{ flex-basis: 100%; }}
      .stRadio [role="radiogroup"]:has(> div:nth-child(6)) {{ grid-auto-columns: max(14rem, 72vw); }}
    }}
    </style>
    """)


def render_brand() -> None:
    with st.container(horizontal_alignment="center"):
        st.image(str(LOGO), width=260, alt="Thorajit")


def question_card(question: str) -> None:
    """Display the current prompt consistently across the round."""
    st.html(f'<div class="question-card" role="group" aria-label="Question">{html.escape(str(question))}</div>')


def waiting_card(title: str, detail: str) -> None:
    """Show a non-interactive waiting status with an accessible text equivalent."""
    detail_html = f'<div class="waiting-detail">{html.escape(detail)}</div>' if detail else ""
    card_class = "waiting-card" if detail else "waiting-card compact"
    st.html(f'<div class="{card_class}" role="status"><div class="waiting-title">{html.escape(title)}</div>'
            f'{detail_html}<div class="waiting-dots" aria-hidden="true"><span></span><span></span><span></span></div></div>')


def answer_card(label: str, answer: str) -> None:
    """Display a player's own submitted answer or guess as non-interactive content."""
    st.html(f'<div class="answer-summary"><div class="answer-summary-label">{html.escape(label)}</div>'
            f'<div class="answer-summary-value">{html.escape(str(answer))}</div></div>')


def thorajit_decoration() -> str:
    """Decorative shapes for the special single-correct-guess reveal."""
    return ('<span class="thor-moment-shape green" aria-hidden="true"></span>'
            '<span class="thor-moment-shape gold" aria-hidden="true"></span>'
            '<span class="thor-moment-spark left" aria-hidden="true">✦</span>'
            '<span class="thor-moment-spark right" aria-hidden="true">✦</span>')


def decision_status(correct: bool) -> None:
    """Show the Storyteller's decision as a status rather than an action."""
    label = "✓ Correct!" if correct else "Not quite"
    style = "decision-status correct" if correct else "decision-status"
    st.html(f'<div class="{style}" role="status">{label}</div>')
