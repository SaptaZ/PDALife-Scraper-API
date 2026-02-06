# PDALife Scraper API

A high-performance, asynchronous REST API built with FastAPI to search and extract application data from PDALife.com. This tool automates the retrieval of download links, handling complex redirects, CDN (MobDisc) traversals, and magnet link extraction.

## Table of Contents

* [Overview](#overview)
* [Key Features](#key-features)
* [Technology Stack](#technology-stack)
* [Prerequisites](#prerequisites)
* [Installation](#installation)
* [Usage](#usage)
* [API Endpoints](#api-endpoints)
* [Legal Disclaimer](#legal-disclaimer)
* [License](#license)

## Overview

This project provides a programmatic interface to PDALife.com. It allows users to search for applications and retrieve direct download links that are often hidden behind multiple redirect layers or proprietary CDN pages (MobDisc). The system uses asynchronous request handling to ensure speed and efficiency, even when processing multiple search results simultaneously.

## Key Features

* **Asynchronous Processing**: Built on `httpx` and `asyncio` to handle concurrent network requests efficiently.
* **Deep Link Extraction**: Automatically resolves `MobDisc` CDN redirects to find the actual file or magnet link.
* **Google Translate Unwrap**: Detects and cleans URLs wrapped in Google Translate proxies.
* **Pagination Support**: Automatically navigates through search result pages to fulfill the requested limit.
* **Robust Error Handling**: Includes retry logic for 429 (Rate Limit) and 5xx errors, with fallback mechanisms for different HTML structures.
* **Magnet Link Support**: Native detection and extraction of BitTorrent magnet links.

## Technology Stack

* **Python 3.8+**
* **FastAPI**: Modern, fast web framework for building APIs.
* **Uvicorn**: Lightning-fast ASGI server implementation.
* **HTTPX**: A next-generation HTTP client for Python with async support.
* **BeautifulSoup4**: Library for parsing HTML and XML documents.

## Prerequisites

Ensure you have Python 3.8 or higher installed on your system.

## Installation

1. **Clone the repository:**

```bash
git clone [https://github.com/SaptaZ/pdalife-scraper.git](https://github.com/SaptaZ/pdalife-scraper.git)
cd pdalife-scraper

```

2. **Create a virtual environment (optional but recommended):**

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

```

3. **Install dependencies:**

```bash
pip install fastapi uvicorn httpx beautifulsoup4

```

## Usage

You can run the application directly using the built-in entry point or via Uvicorn CLI.

### Option 1: Direct Execution

```bash
python main.py

```

### Option 2: Using Uvicorn

```bash
uvicorn main:app --host 0.0.0.0 --port 7860 --reload

```

The server will start on port `7860` (or the port defined in your environment variables).

## API Endpoints

### 1. Health Check

Verifies that the API is running.

* **URL**: `/`
* **Method**: `GET`
* **Response**:

```json
{
  "message": "Search API for PDALife.com by Bowo",
  "github": "[https://github.com/SaptaZ](https://github.com/SaptaZ)",
  "example_usage": "/search?query=minecraft&limit=5"
}
```

### 2. Search Applications

Searches for an application and scrapes download details.

* **URL**: `/search`

* **Method**: `GET`

* **Query Parameters**:

* `query` (string, required): The name of the application to search for.

* `limit` (integer, optional): Maximum number of results to retrieve. Default is `5`.

* **Example Request**:

```http
GET /search?query=minecraft&limit=5

```

* **Example Response**:

```json
{
  "success": true,
  "query": "minecraft",
  "limit": 5,
  "count": 5,
  "results": [
    {
      "name": "Minecraft - Pocket Edition  APK mod full",
      "link": "https://pdalife.com/minecraft-pocket-edition-android-a1552.html",
      "image": "https://pdacdn.com/app/59522ace02abb/minecraft-play-with-friends.png",
      "download": "https://mobdisc.com/download/Minecraft-v1-21-132-1-patched.apk, https://mobdisc.com/download/Minecraft-v1-21-131-1.apk, https://mobdisc.com/download/Minecraft-v1-21-130-3-patched.apk, https://mobdisc.com/download/Minecraft-v1-26-0-23-patched.apk",
      "size": "699.25 Mb"
    }
  ]
}
```

## Legal Disclaimer

This repository is for educational purposes only. The code demonstrates how to use Python for web scraping and data extraction. The author is not responsible for any misuse of this software or for any copyright infringements caused by downloading content from third-party sources. Users should comply with the Terms of Service of the target websites.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
