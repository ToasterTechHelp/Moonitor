import os
import logging
from dotenv import load_dotenv
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base


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

    def __repr__(self):
        return (
            f"<ProcessedMessage(id={self.id}, "
            f"channel='{self.channel_name}', "
            f"sender='{self.sender_name}', "
            f"decision='{self.llm_decision}')>"
        )

def create_db_and_tables():
    """
    Creates the database file and all tables defined in our models.
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
