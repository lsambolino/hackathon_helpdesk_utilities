import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CHATBOT_ENDPOINT = os.environ.get("CHATBOT_ENDPOINT", "http://localhost:8080/chat")
MODEL = os.environ.get("EVALUATOR_MODEL", "claude-sonnet-4-6")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "8"))
NUM_SCENARIOS = int(os.environ.get("NUM_SCENARIOS", "5"))
DATASET_URL = "https://raw.githubusercontent.com/lsambolino/hackathon_helpdesk_utilities/main/hydric_complaints_backlog.json"
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./results")

# Timing thresholds (seconds) → score 1-5
TIMING_THRESHOLDS = [1.0, 2.5, 5.0, 9.0]  # <1s=5, 1-2.5=4, 2.5-5=3, 5-9=2, >9=1
