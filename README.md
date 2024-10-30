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
- `yt-dlp` library
- `youtubesearchpython` library

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/Brutarul/MusicBot.py.git
    cd MusicBot.py
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
/play Never Gonna Give You Up

The bot will join your voice channel and start playing the song. You can queue more songs using the same command.

## Project Structure

- **`bot.py`**: Main entry point for the bot.
- **`cogs/music_cog.py`**: Contains the `MusicCog` class with music commands and functionality.
- **`config.py`**: Contains your bot token. (Do not forget to add this file and update it with your own token.)
- **`requirements.txt`**: Lists required Python packages.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests. For major changes, please open an issue to discuss your proposed changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Support

If you encounter any issues or have questions, please open an issue on the [GitHub repository](https://github.com/Brutarul/MusicBot.py/issues).
