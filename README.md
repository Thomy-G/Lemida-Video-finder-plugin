# 🎓 Lemida Video Finder (BIU Moodle)

A Chrome Extension and powerful Python CLI (managed with `uv`) to authenticate and extract all video links from Bar-Ilan University **Lemida** (Moodle) courses.

---

## 🌟 Features

- **Exact & Robust XPath Support**: Targets the full section XPath:
  ```xpath
  /html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source
  ```
  as well as generalized section-wide selectors (`//section//video/source`, HTML5 `<video>`, and embedded players like Kaltura & Panopto).
- **Chrome Extension (Manifest V3)**:
  - Detects videos automatically on any Lemida course page.
  - Extension icon badge displays detected video count in real-time.
  - Copy all video links with 1 click.
  - **Deep Scan**: Crawls linked activity pages (`mod/page`, `mod/kalvidres`, `mod/resource`) to discover videos inside subpages.
  - Export to **Text (.txt)**, **JSON (.json)**, **VLC Playlist (.m3u)**, and **yt-dlp download commands**.
  - **Export Session for CLI**: 1-click export of your active Bar-Ilan SSO session cookie to use directly in the CLI.
- **Python CLI (with `uv`)**:
  - Interactive Microsoft SSO login via Playwright (`uv run lemida-cli login`) with session persistence in `~/.lemida_session.json`.
  - Rich formatted tables in terminal with direct links, section names, and video titles.
  - Supports course ID (e.g. `108883`) or full URL (`https://lemida.biu.ac.il/course/view.php?id=108883`).
  - Output flags: `--links-only`, `--json`, `--ytdlp`, and `--output <filename>`.

---

## 🚀 1. Chrome Extension Setup

1. Open Google Chrome (or Edge/Brave) and navigate to:
   ```text
   chrome://extensions
   ```
2. Enable **Developer mode** toggle in the top-right corner.
3. Click **Load unpacked** (טען תוסף לא ארוז).
4. Select the `extension/` folder in this repository:
   ```text
   c:\Users\thomy\Projects\Lemida-Video-finder-plugin\extension
   ```
5. Navigate to any Lemida course, for example:
   ```text
   https://lemida.biu.ac.il/course/view.php?id=108883
   ```
6. Click the **Lemida Video Finder** extension icon in your browser toolbar to view all videos, preview them, or copy/download links!

---

## 💻 2. CLI Usage (Powered by `uv`)

### Prerequisites
Make sure `uv` is installed (already configured in this project).

### Step A: Authenticate (Microsoft SSO / 2FA)
Run the interactive login command:
```bash
uv run lemida-cli login
```
A browser window opens to the Bar-Ilan SSO login page (`login.microsoftonline.com`). Enter your BIU credentials and complete 2FA if prompted. Once redirected back to Lemida, your session cookies are automatically saved to `~/.lemida_session.json`.

You can verify your login status anytime:
```bash
uv run lemida-cli status
```

*(Note: You can also skip browser login and supply the `MoodleSession` cookie directly via `--cookie`)*

---

### Step B: Fetch Course Videos

#### 1. Standard Fetch (Formatted Table)
```bash
uv run lemida-cli fetch 108883
```
or with full URL:
```bash
uv run lemida-cli fetch https://lemida.biu.ac.il/course/view.php?id=108883
```

#### 2. Deep Scan Subpages
If videos are placed inside individual activity pages (e.g., Kaltura resources or subpages):
```bash
uv run lemida-cli fetch 108883 --deep
```

#### 3. Output Only Links (Great for piping or scripting)
```bash
uv run lemida-cli fetch 108883 --links-only
```

#### 4. Export to File
- As plain text:
  ```bash
  uv run lemida-cli fetch 108883 -o videos.txt
  ```
- As JSON:
  ```bash
  uv run lemida-cli fetch 108883 --json -o videos.json
  ```
- As VLC / Media Player Playlist:
  ```bash
  uv run lemida-cli fetch 108883 -o playlist.m3u
  ```

#### 5. Generate yt-dlp Download Commands
```bash
uv run lemida-cli fetch 108883 --ytdlp
```

#### 6. Using a Custom XPath
```bash
uv run lemida-cli fetch 108883 --xpath "/html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source"
```

#### 7. Pass Cookie Directly (without running `login`)
```bash
uv run lemida-cli fetch 108883 --cookie "MoodleSession=your_session_token_here"
```

---

## 📁 Project Structure

```text
Lemida-Video-finder-plugin/
├── extension/                       # Chrome Extension (Manifest V3)
│   ├── manifest.json                # Extension manifest
│   ├── background.js                # Service worker (badge & cookies)
│   ├── content.js                   # Injected scanner with XPath logic
│   ├── popup.html                   # Modern popup interface
│   ├── popup.css                    # Modern UI styles
│   ├── popup.js                     # Extension popup controller
│   └── icons/                       # High-res extension icons
│       ├── icon16.png
│       ├── icon48.png
│       └── icon128.png
├── cli/                             # Python CLI Package
│   ├── main.py                      # Typer CLI entrypoint
│   ├── parser.py                    # XPath & DOM parsing logic
│   ├── auth.py                      # SSO login & cookie management
│   └── exporter.py                  # Table, JSON, M3U & yt-dlp formatters
├── tests/                           # Unit tests
│   └── test_parser.py               # Parser & XPath test suite
├── pyproject.toml                   # uv project definition
└── README.md                        # Documentation
```

---

## 🧪 Running Tests

To run the unit test suite:
```bash
uv run python -m unittest discover tests
```
