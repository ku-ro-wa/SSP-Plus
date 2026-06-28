import sys
import os

# Make SSP/ importable so tests can import managers and database modules directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'SSP')))
