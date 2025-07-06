#!/usr/bin/env python3
"""
Web interface launcher for Moonitor.
This script starts the web dashboard for viewing processed Telegram messages.
"""

import sys
import os
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.web.api import app

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🚀 Starting Moonitor Web Dashboard...")
    print("📊 Dashboard will be available at: http://localhost:5000")
    print("🔄 Press Ctrl+C to stop the server")
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Moonitor Web Dashboard stopped.")