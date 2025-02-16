# Flask Chromecast Streamer

A simple web application that allows you to stream media to your Chromecast devices.

## Features

- Discover available Chromecast devices on your network
- Stream media to selected Chromecast device
- Basic media controls (play, pause, stop)
- Modern, responsive UI using Tailwind CSS

## Requirements

- Python 3.7+
- Flask
- pychromecast
- flask-cors

## Installation

1. Clone this repository
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the Flask application:
   ```bash
   python app.py
   ```
2. Open your web browser and navigate to `http://localhost:5000`
3. Select your Chromecast device from the dropdown menu
4. Enter a media URL (must be a direct link to a media file)
5. Click "Stream" to start streaming
6. Use the media controls to play, pause, or stop the stream

## Notes

- The media URL must be directly accessible by the Chromecast device
- Supported media formats depend on your Chromecast device's capabilities
- Make sure your computer and Chromecast device are on the same network
