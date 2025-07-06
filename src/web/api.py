import logging
from datetime import datetime, timezone
from typing import List, Optional
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from sqlalchemy import desc, func
from sqlalchemy.orm import sessionmaker

from src.database.database import engine, ProcessedMessage, get_session


app = Flask(__name__, template_folder='../../frontend/templates', static_folder='../../frontend/static')
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


@app.route('/api/messages')
def get_messages():
    """Get processed messages with optional filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    decision = request.args.get('decision')
    channel_name = request.args.get('channel')
    min_confidence = request.args.get('min_confidence', type=float)
    
    session = get_session()
    try:
        query = session.query(ProcessedMessage)
        
        # Apply filters
        if decision:
            query = query.filter(ProcessedMessage.llm_decision == decision)
        if channel_name:
            query = query.filter(ProcessedMessage.channel_name.ilike(f'%{channel_name}%'))
        if min_confidence is not None:
            query = query.filter(ProcessedMessage.llm_confidence >= min_confidence)
        
        # Order by processed time (newest first)
        query = query.order_by(desc(ProcessedMessage.processed_at))
        
        # Paginate
        offset = (page - 1) * per_page
        total = query.count()
        messages = query.offset(offset).limit(per_page).all()
        
        # Convert to dict
        result = {
            'messages': [
                {
                    'id': msg.id,
                    'telegram_message_id': msg.telegram_message_id,
                    'channel_id': msg.channel_id,
                    'channel_name': msg.channel_name,
                    'sender_id': msg.sender_id,
                    'sender_name': msg.sender_name,
                    'message_text': msg.message_text,
                    'processed_at': msg.processed_at.isoformat() if msg.processed_at else None,
                    'llm_decision': msg.llm_decision,
                    'llm_confidence': msg.llm_confidence,
                    'llm_rationale': msg.llm_rationale,
                    'token_address': msg.token_address
                }
                for msg in messages
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({'error': 'Failed to fetch messages'}), 500
    finally:
        session.close()


@app.route('/api/stats')
def get_stats():
    """Get dashboard statistics."""
    session = get_session()
    try:
        # Basic counts
        total_messages = session.query(ProcessedMessage).count()
        buy_decisions = session.query(ProcessedMessage).filter(ProcessedMessage.llm_decision == 'buy').count()
        hold_decisions = session.query(ProcessedMessage).filter(ProcessedMessage.llm_decision == 'hold').count()
        
        # Recent activity (last 24 hours)
        recent_cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        recent_messages = session.query(ProcessedMessage).filter(
            ProcessedMessage.processed_at >= recent_cutoff
        ).count()
        
        # Average confidence scores
        avg_confidence = session.query(func.avg(ProcessedMessage.llm_confidence)).filter(
            ProcessedMessage.llm_confidence.isnot(None)
        ).scalar()
        
        # Top channels by message count
        channel_stats = session.query(
            ProcessedMessage.channel_name,
            func.count(ProcessedMessage.id).label('message_count')
        ).filter(
            ProcessedMessage.channel_name.isnot(None)
        ).group_by(
            ProcessedMessage.channel_name
        ).order_by(
            desc('message_count')
        ).limit(5).all()
        
        # Recent buy signals with high confidence
        recent_buy_signals = session.query(ProcessedMessage).filter(
            ProcessedMessage.llm_decision == 'buy',
            ProcessedMessage.llm_confidence >= 0.7,
            ProcessedMessage.processed_at >= recent_cutoff
        ).order_by(desc(ProcessedMessage.processed_at)).limit(5).all()
        
        result = {
            'total_messages': total_messages,
            'buy_decisions': buy_decisions,
            'hold_decisions': hold_decisions,
            'recent_messages_24h': recent_messages,
            'avg_confidence': round(avg_confidence, 3) if avg_confidence else 0,
            'top_channels': [
                {'name': name, 'count': count} for name, count in channel_stats
            ],
            'recent_buy_signals': [
                {
                    'id': msg.id,
                    'channel_name': msg.channel_name,
                    'sender_name': msg.sender_name,
                    'message_text': msg.message_text[:100] + '...' if len(msg.message_text or '') > 100 else msg.message_text,
                    'confidence': msg.llm_confidence,
                    'token_address': msg.token_address,
                    'processed_at': msg.processed_at.isoformat() if msg.processed_at else None
                }
                for msg in recent_buy_signals
            ]
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500
    finally:
        session.close()


@app.route('/api/channels')
def get_channels():
    """Get list of unique channels."""
    session = get_session()
    try:
        channels = session.query(ProcessedMessage.channel_name).filter(
            ProcessedMessage.channel_name.isnot(None)
        ).distinct().all()
        
        result = [channel[0] for channel in channels]
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error fetching channels: {e}")
        return jsonify({'error': 'Failed to fetch channels'}), 500
    finally:
        session.close()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)