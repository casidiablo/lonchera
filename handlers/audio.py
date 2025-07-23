import logging
import os
import time
from tempfile import NamedTemporaryFile

import requests
from telegram_extensions import Update
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

from handlers.lunch_money_agent import get_agent_response, handle_ai_response
from persistence import get_db

logger = logging.getLogger("handlers.audio")

# Constants
HTTP_OK = 200


async def handle_audio_transcription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle audio file uploads and transcribe them using DeepInfra's Whisper API.

    Args:
        update: The update containing the audio file
        context: The context

    Returns:
        True if the audio was successfully handled, False otherwise
    """
    message = update.message
    if message is None or update.effective_chat is None:
        logger.info("No message or chat found")
        return False

    chat_id = update.chat_id

    # Check if AI agent is enabled for this chat
    settings = get_db().get_current_settings(chat_id)
    ai_agent = settings.ai_agent if settings else False

    if not ai_agent:
        await context.bot.send_message(
            chat_id=chat_id,
            text="AI Agent is not enabled. Please enable AI Agent in settings to process audio messages.",
            reply_to_message_id=message.message_id,
        )
        return False

    # Check if there's an audio file in the message
    audio_file = None
    if message.voice:
        audio_file = message.voice
    elif message.audio:
        audio_file = message.audio

    if not audio_file:
        logger.info("No audio file found in message")
        return False

    # React to the audio message to indicate processing
    await context.bot.set_message_reaction(
        chat_id=chat_id, message_id=message.message_id, reaction=ReactionEmoji.HIGH_VOLTAGE_SIGN
    )

    get_db().inc_metric("audio_processing_requests")

    try:
        # Process audio transcription
        transcription = await _process_audio_transcription(update, context, audio_file, settings)

        if not transcription:
            get_db().inc_metric("audio_processing_failed")
            await context.bot.send_message(chat_id=chat_id, text="Failed to transcribe audio")
            return False

        # Track transcription metrics
        get_db().inc_metric("audio_transcription_successful")
        get_db().inc_metric("audio_transcription_chars", len(transcription))

        # try to see if the message is a reply to a transaction message
        tx_id = None
        replying_to_msg_id = None
        if message.reply_to_message:
            replying_to_msg_id = message.reply_to_message.message_id
            tx_id = get_db().get_tx_associated_with(replying_to_msg_id, message.chat_id)

        # Process the transcription with AI
        ai_response = get_agent_response(transcription, chat_id, tx_id, replying_to_msg_id, verbose=True)
        await handle_ai_response(update, context, ai_response)

    except Exception as e:
        logger.exception("Error processing audio file")
        get_db().inc_metric("audio_processing_failed")
        await context.bot.send_message(chat_id=chat_id, text=f"Error processing audio: {e!s}")

        return False
    else:
        # Track successful end-to-end processing
        get_db().inc_metric("audio_processing_successful")
        return True


async def _process_audio_transcription(
    update: Update, context: ContextTypes.DEFAULT_TYPE, audio_file, settings
) -> str | None:
    """
    Download and transcribe audio file.

    Args:
        update: The update containing the audio file
        context: The context
        audio_file: The audio file object
        settings: User settings

    Returns:
        The transcribed text
    """
    try:
        chat_id = update.chat_id
    except ValueError:
        return None

    # Download the audio file
    audio_data = await context.bot.get_file(audio_file.file_id)

    # Track audio file size
    file_size = getattr(audio_file, "file_size", 0) or 0
    get_db().inc_metric("audio_file_size_bytes", file_size)

    # Save to a temporary file
    with NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
        await audio_data.download_to_drive(temp_file.name)
        temp_path = temp_file.name

    # Transcribe the audio
    transcription_start = time.time()
    transcription, language = transcribe_audio(temp_path)
    transcription_time = time.time() - transcription_start
    get_db().inc_metric("audio_transcription_time_seconds", transcription_time)

    # Send the transcription to the user if enabled in settings
    if settings.show_transcription:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"I will process now the following transcription:\n> {transcription.replace('.', '\\.')}",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as se:
            if "Can't parse entities" in str(se):
                # try to send without markdown
                await context.bot.send_message(
                    chat_id=chat_id, text=f"I will process now the following transcription:\n{transcription}"
                )

    # Delete the temporary file
    os.unlink(temp_path)

    return transcription


def transcribe_audio(file_path: str) -> tuple[str, str]:
    """
    Transcribe an audio file using DeepInfra's Whisper API.

    Args:
        file_path: Path to the audio file

    Returns:
        A tuple containing the transcription text and detected language
    """
    url = "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3"
    api_key = os.getenv("DEEPINFRA_API_KEY")

    if not api_key:
        raise ValueError("DEEPINFRA_API_KEY not set")

    headers = {"Authorization": f"Bearer {api_key}"}

    logger.info(f"Sending audio file {file_path} to DeepInfra for transcription")

    try:
        with open(file_path, "rb") as audio_file:
            files = {"audio": audio_file}
            response = requests.post(url, headers=headers, files=files)

        # Track DeepInfra usage metrics
        get_db().inc_metric("deepinfra_whisper_requests")

        if response.status_code == HTTP_OK:
            response_json = response.json()

            # Extract the transcription text and language from the response
            transcription = response_json.get("text", "")
            language = response_json.get("language", "")

            # Track cost if available
            if "inference_status" in response_json and "cost" in response_json["inference_status"]:
                cost = response_json["inference_status"]["cost"]
                get_db().inc_metric("deepinfra_whisper_estimated_cost", cost)

            # Track language detection
            if language:
                get_db().inc_metric(f"audio_language_{language.lower()}")

            logger.info(f"Transcription successful: {transcription}")
            logger.info(f"Detected language: {language}")

            return transcription, language
        else:
            get_db().inc_metric("deepinfra_whisper_requests_failed")
            logger.exception(f"Transcription failed with status code: {response.status_code}")
            response.raise_for_status()
            return "", ""
    except Exception:
        get_db().inc_metric("deepinfra_whisper_requests_failed")
        logger.exception("Error during transcription")
        raise
