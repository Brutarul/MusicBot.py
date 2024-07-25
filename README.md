# Discord Music Bot

This Discord bot plays music in voice channels using YouTube as a source. It includes commands to play, queue, skip, pause, and manage songs in a playlist.

## Features

- Play music from YouTube by URL or search term.
- Queue multiple songs.
- Pause, resume, and skip songs.
- Clear the music queue.
- Disconnect from the voice channel when idle.

## Prerequisites

- Python 3.8+
- `discord.py` library
- `youtube-dl` library
- `youtubesearchpython` library
- `ffmpeg` installed and added to your PATH

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/Brutarul/discord-music-bot.git
    cd discord-music-bot
    ```

2. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

3. Create a `config.py` file and add your bot token:
    ```python
    TOKEN = 'your-bot-token'
    ```

4. Run the bot:
    ```bash
    python bot.py
    ```

## Usage

Invite your bot to your server and use the following commands:

- **/play <song>**: Plays a song based on the URL or name provided.
- **/queue**: Displays the current songs in the queue.
- **/clear_queue**: Stops the music and clears the queue.
- **/stop**: Disconnects the bot from the voice channel.
- **/remove**: Removes the last song added to the queue.
- **/pause**: Pauses the current song being played.
- **/resume**: Resumes the paused song.
- **/skip**: Skips the current song.

### Example

To play a song, simply type:

