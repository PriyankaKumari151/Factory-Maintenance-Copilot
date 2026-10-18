"""Shared paths and configuration. No API key is embedded in source code."""
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DB = DATA / 'factory.db'
load_dotenv(ROOT / '.env')
