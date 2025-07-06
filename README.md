# Moonitor 🚀

A real-time Telegram memecoin signal monitoring application with AI-powered analysis.

## Features

- **Telegram Monitoring**: Listens to specified Telegram channels for messages
- **AI Analysis**: Uses OpenAI GPT to analyze messages for trading signals
- **Web Dashboard**: Modern, responsive web interface to view processed messages
- **Signal Detection**: Identifies "buy" or "hold" signals with confidence scores
- **Token Tracking**: Extracts and displays Solana token addresses
- **Real-time Updates**: Dashboard updates every 30 seconds automatically

## Quick Start

### 1. Setup Environment
```bash
pip install -r requirements.txt
```

Create a `.env` file with your configuration:
```env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_NAME=your_session_name
TELEGRAM_TARGET_CHAT_IDS=chat_id1,chat_id2
TELEGRAM_HISTORY_LIMIT=5
OPENAI_API_KEY=your_openai_api_key
DATABASE_FILE=activity_logger.db
```

### 2. Run the Application

**Start Telegram Monitoring:**
```bash
python src/main.py
```

**Launch Web Dashboard:**
```bash
python web_launcher.py
```

Then open http://localhost:5000 in your browser.

## Web Dashboard

The web dashboard provides:

- **Statistics Overview**: Total messages, buy/hold signals, recent activity
- **High-Confidence Signals**: Recent buy signals with confidence > 70%
- **Message Browser**: Filterable table of all processed messages
- **Advanced Filtering**: Filter by decision type, channel, confidence level
- **Channel Analytics**: Visual breakdown of message activity by channel
- **Real-time Updates**: Automatic refresh every 30 seconds

### Dashboard Features

- 📊 **Statistics Cards**: Quick overview of signal activity
- 🔥 **Hot Signals**: Recent high-confidence buy recommendations  
- 🔍 **Smart Filtering**: Filter messages by various criteria
- 📈 **Visual Analytics**: Charts showing channel activity
- 📱 **Responsive Design**: Works on desktop, tablet, and mobile
- 🎨 **Modern UI**: Clean, professional interface with dark mode support

## Project Structure

```
Moonitor/
├── src/
│   ├── main.py              # Main application entry point
│   ├── database/
│   │   └── database.py      # Database models and operations
│   ├── listeners/
│   │   └── telegram_listener.py  # Telegram message processing
│   ├── llm/
│   │   └── openai_analyzer.py    # AI analysis logic
│   └── web/
│       └── api.py           # Web API endpoints
├── frontend/
│   ├── templates/
│   │   └── index.html       # Main dashboard template
│   └── static/
│       ├── style.css        # Dashboard styling
│       └── app.js          # Frontend JavaScript
├── web_launcher.py          # Web dashboard launcher
└── requirements.txt         # Python dependencies
```

## Technologies Used

- **Backend**: Python, SQLAlchemy, Flask, Telethon, OpenAI API
- **Frontend**: HTML5, CSS3, JavaScript, Chart.js
- **Database**: SQLite
- **AI**: OpenAI GPT-4o-mini for message analysis