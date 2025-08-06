import datetime
import logging
import asyncio
from ai.agents.live import MessageType
from db.service import DatabaseService, MessageDirection

logger = logging.getLogger(__name__)


class MessageAccumulator:
    def __init__(self):
        self.text_pieces = []
        self.audio_pieces = []
        self.transcription_pieces = []
        self.is_collecting = False
        self.message_start_time = None

    def start_collecting(self):
        self.is_collecting = True
        self.message_start_time = datetime.datetime.now()
        self.text_pieces.clear()
        self.audio_pieces.clear()
        self.transcription_pieces.clear()

    def add_piece(self, message_type: MessageType, data):
        if not self.is_collecting:
            self.start_collecting()

        if message_type == MessageType.TEXT:
            self.text_pieces.append(str(data))
        elif message_type == MessageType.AUDIO:
            # Ensure audio data is bytes
            if isinstance(data, str):
                # logger.warning("Received audio as string, skipping...")
                return
            elif isinstance(data, bytes):
                self.audio_pieces.append(data)
            else:
                # logger.warning(f"Unexpected audio data type: {type(data)}")
                pass
        elif message_type == MessageType.OUTPUT_TRANSCRIPTION:
            self.transcription_pieces.append(str(data))

    async def save_accumulated_message(self, db, chat_id):
        """Save the complete accumulated message to database with retry logic"""
        if not self.is_collecting:
            return

        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Save accumulated text if any
                if self.text_pieces:
                    complete_text = "".join(self.text_pieces)
                    await asyncio.wait_for(
                        DatabaseService.save_message(
                            db=db,
                            chat_id=chat_id,
                            direction=MessageDirection.OUTGOING,
                            content_type=MessageType.TEXT,
                            text_content=complete_text,
                        ),
                        timeout=10.0
                    )
                    logger.info(f"Saved complete text message: {len(complete_text)} chars")

                # Save accumulated transcription if any
                if self.transcription_pieces:
                    complete_transcription = "".join(self.transcription_pieces)
                    await asyncio.wait_for(
                        DatabaseService.save_message(
                            db=db,
                            chat_id=chat_id,
                            direction=MessageDirection.OUTGOING,
                            content_type=MessageType.OUTPUT_TRANSCRIPTION,
                            text_content=complete_transcription,
                        ),
                        timeout=10.0
                    )
                    logger.info(f"Saved complete transcription: {len(complete_transcription)} chars")
                
                # break if all pieces are saved successfully
                break
                
            except asyncio.TimeoutError:
                retry_count += 1
                logger.warning(f"Database save timeout, retry {retry_count}/{max_retries}")
                if retry_count >= max_retries:
                    logger.error("Failed to save message after all retries")
                    break
                await asyncio.sleep(1) # wait before retrying
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Failed to save accumulated message (attempt {retry_count}): {e}")
                if retry_count >= max_retries:
                    logger.error("Failed to save message after all retries")
                    break
                await asyncio.sleep(1)
                
            finally:
                if retry_count >= max_retries or retry_count == 0:
                    self.reset()

    def reset(self):
        self.is_collecting = False
        self.text_pieces.clear()
        self.audio_pieces.clear()
        self.transcription_pieces.clear()
        self.message_start_time = None
