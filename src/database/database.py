import os
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger(__name__)

DATABASE_FILE = os.getenv("DATABASE_FILE", "activity_logger.db")

# Simple SQLite configuration - no pooling needed
engine = create_engine(
    f"sqlite:///{DATABASE_FILE}",
    echo=False,
    connect_args={
        "check_same_thread": False,  # Allow SQLite to be used across threads
        "timeout": 20  # Wait up to 20 seconds for locks to clear
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)
    telegram_message_id = Column(Integer, nullable=False, index=True)
    channel_id = Column(Integer, nullable=False)
    channel_name = Column(String)
    sender_id = Column(Integer)
    sender_name = Column(String)
    message_text = Column(Text, nullable=True)
    processed_at = Column(DateTime, default=datetime.now(timezone.utc))
    llm_decision = Column(String, nullable=True)
    llm_confidence = Column(Float, nullable=True)
    llm_rationale = Column(Text, nullable=True)
    token_address = Column(String, nullable=True)
    trade = relationship("Trade", back_populates="processed_message", uselist=False)

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    processed_message_id = Column(Integer, ForeignKey('processed_messages.id'), nullable=False, unique=True)
    token_address = Column(String, nullable=False, index=True)
    status = Column(String, default="open", nullable=False)
    buy_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    buy_transaction_sig = Column(String, nullable=True)
    amount_spent_sol = Column(Float, nullable=True)
    amount_received_token = Column(Float, nullable=True)
    take_profit_percentage = Column(Float, nullable=True)
    stop_loss_percentage = Column(Float, nullable=True)
    tp_order_sig = Column(String, nullable=True)
    sl_order_sig = Column(String, nullable=True)
    sell_timestamp = Column(DateTime, nullable=True)
    sell_transaction_sig = Column(String, nullable=True)
    processed_message = relationship("ProcessedMessage", back_populates="trade")

def create_db_and_tables():
    """Creates the database file and all tables."""
    logger.info("Initializing database...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database and tables created successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Database error creating tables: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating database tables: {e}", exc_info=True)
        raise

@contextmanager
def get_db_session():
    """
    Context manager for database sessions with automatic cleanup.
    This is the main improvement - handles commit/rollback automatically.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error: {e}", exc_info=True)
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error in database session: {e}", exc_info=True)
        raise
    finally:
        session.close()