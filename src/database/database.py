import os
import logging
from dotenv import load_dotenv
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship


load_dotenv()
DATABASE_FILE = os.getenv("DATABASE_FILE", "activity_logger.db")

# Sets up a "pool" of connections to our SQLite database.
# `echo=False` means it won't log every single SQL statement.
engine = create_engine(f"sqlite:///{DATABASE_FILE}", echo=False)

# sessionmaker creates a factory for producing new Session objects.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# declarative_base() returns a base class that our table model will inherit from.
Base = declarative_base()

class ProcessedMessage(Base):
    """
    This class defines the structure of the 'processed_messages' table in our database.
    SQLAlchemy will automatically map this class to the table.
    """
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, index=True)

    # Identifying information
    telegram_message_id = Column(Integer, nullable=False, index=True)
    channel_id = Column(Integer, nullable=False)
    channel_name = Column(String)
    sender_id = Column(Integer)
    sender_name = Column(String)
    message_text = Column(Text, nullable=True)
    processed_at = Column(DateTime, default=datetime.now(timezone.utc))

    # LLM output
    llm_decision = Column(String, nullable=True)
    llm_confidence = Column(Float, nullable=True)
    llm_rationale = Column(Text, nullable=True)
    token_address = Column(String, nullable=True)

    # Relationship to the Trade object, which will be created when a 'buy' decision is made.
    trade = relationship("Trade", back_populates="processed_message", uselist=False)

    def __repr__(self):
        return (
            f"<ProcessedMessage(id={self.id}, "
            f"channel='{self.channel_name}', "
            f"sender='{self.sender_name}', "
            f"decision='{self.llm_decision}')>"
        )

class Trade(Base):
    """
    This new class defines the 'trades' table.
    It will only store entries for messages that result in a 'buy' decision.
    """
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Key to link this trade back to the message that triggered it
    processed_message_id = Column(Integer, ForeignKey('processed_messages.id'), nullable=False, unique=True)
    token_address = Column(String, nullable=False, index=True)
    status = Column(String, default="open", nullable=False)  # e.g., "open", "closed_profit", "closed_loss"

    # Buy-side information
    buy_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    buy_transaction_sig = Column(String, nullable=True)
    amount_spent_sol = Column(Float, nullable=True)
    amount_received_token = Column(Float, nullable=True)

    # Price targets
    take_profit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)

    # ----- Limit order transaction signatures -----
    tp_order_sig = Column(String, nullable=True)
    sl_order_sig = Column(String, nullable=True)

    # Sell-side information (will be filled in when the position is closed)
    sell_timestamp = Column(DateTime, nullable=True)
    sell_transaction_sig = Column(String, nullable=True)

    # Relationship back to the ProcessedMessage
    processed_message = relationship("ProcessedMessage", back_populates="trade")

    def __repr__(self):
        return (
            f"<Trade(id={self.id}, "
            f"token='{self.token_address}', "
            f"status='{self.status}')>"
        )

def create_db_and_tables():
    """
    Creates the database file and all tables defined in our models.
    This function should be called once when the main application starts.
    """
    logging.info("Initializing database...")
    try:
        Base.metadata.create_all(bind=engine)
        logging.info("Database and tables created successfully (if they didn't exist).")
    except Exception as e:
        logging.error(f"Error creating database tables: {e}", exc_info=True)
        raise


def get_session():
    """
    Provides a new database session for performing transactions.
    This should be called whenever we need to interact with the database.
    """
    return SessionLocal()
