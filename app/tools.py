import os
import subprocess
import time
from typing import Dict, Any, List

def open_vscode(path: str = None) -> str:
    if path:
        expanded_path = os.path.expanduser(path)
        subprocess.run(["open", "-a", "Visual Studio Code", expanded_path], check=True)
        return f"Opened '{path}' in Visual Studio Code."
    else:
        subprocess.run(["open", "-a", "Visual Studio Code"], check=True)
        return "Visual Studio Code has been opened."

def open_chrome(url: str = None) -> str:
    if url:
        subprocess.run(["open", "-a", "Google Chrome", url], check=True)
        if "mail.google.com" in url:
            return "Gmail compose window has been opened in Google Chrome."
        return "Google Chrome has been opened."
    else:
        subprocess.run(["open", "-a", "Google Chrome"], check=True)
        return "Google Chrome has been opened."

def open_terminal() -> str:
    subprocess.run(["open", "-a", "Terminal"], check=True)
    return "Terminal has been opened."

def open_finder() -> str:
    subprocess.run(["open", os.path.expanduser("~")], check=True)
    return "Finder has been opened at your home directory."

def open_folder(path: str) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return f"Error: The path '{path}' does not exist."
    subprocess.run(["open", expanded_path], check=True)
    return f"Opened folder '{path}'."

def take_screenshot(path: str = None) -> str:
    timestamp = int(time.time())
    
    if path:
        # Clean up path issues (e.g., if LLM put a space instead of a slash: 'Downloads screenshot.png')
        cleaned_path = path.strip()
        if "Downloads screenshot.png" in cleaned_path:
            cleaned_path = cleaned_path.replace("Downloads screenshot.png", "Downloads/screenshot.png")
            
        expanded_path = os.path.expanduser(cleaned_path)
        # If it is a directory, save with timestamp filename
        if os.path.isdir(expanded_path) or not os.path.splitext(expanded_path)[1]:
            os.makedirs(expanded_path, exist_ok=True)
            filename = os.path.join(expanded_path, f"screenshot_{timestamp}.png")
            display_path = os.path.join(os.path.basename(expanded_path.rstrip("/")), f"screenshot_{timestamp}.png")
        else:
            # It's a full file path, make sure parent dir exists
            parent_dir = os.path.dirname(expanded_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            filename = expanded_path
            display_path = os.path.join(os.path.basename(parent_dir), os.path.basename(expanded_path)) if parent_dir else os.path.basename(expanded_path)
    else:
        # Default save to Desktop
        desktop_dir = os.path.expanduser("~/Desktop")
        os.makedirs(desktop_dir, exist_ok=True)
        filename = os.path.join(desktop_dir, f"screenshot_{timestamp}.png")
        display_path = f"Desktop/screenshot_{timestamp}.png"
        
    # -x flag plays no sound
    subprocess.run(["screencapture", "-x", filename], check=True)
    return f"Screenshot taken and saved to {display_path}."

def list_downloads() -> List[str]:
    downloads_dir = os.path.expanduser("~/Downloads")
    if not os.path.exists(downloads_dir):
        return []
    
    files = os.listdir(downloads_dir)
    # Filter out hidden files
    visible_files = [f for f in files if not f.startswith(".")]
    # Sort by modification time (most recent first)
    visible_files.sort(key=lambda x: os.path.getmtime(os.path.join(downloads_dir, x)), reverse=True)
    return visible_files[:10]  # Return top 10

def lock_screen() -> str:
    # Try pmset displaysleepnow first as it is highly reliable and doesn't require UI access permission
    try:
        subprocess.run(["pmset", "displaysleepnow"], check=True)
        return "Screen locked (display put to sleep)."
    except Exception as e:
        # Fallback to AppleScript keyboard shortcut for locking
        subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "q" using {control down, command down}'], check=True)
        return "Screen lock command sent."

def shutdown() -> str:
    # Uses AppleScript to request system shutdown. This usually brings up the prompt
    # or shuts down directly depending on macOS configuration.
    subprocess.run(["osascript", "-e", 'tell application "System Events" to shut down'], check=True)
    return "Shutdown command initiated."

def restart() -> str:
    subprocess.run(["osascript", "-e", 'tell application "System Events" to restart'], check=True)
    return "Restart command initiated."

def run_command(command: str, timeout: int = 60) -> Dict[str, Any]:
    # Runs an arbitrary shell command safely (with a timeout)
    try:
        # Run in user shell environment with npx auto-yes configuration
        env = os.environ.copy()
        env["npm_config_yes"] = "true"
        res = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.expanduser("~"),
            env=env
        )
        return {
            "stdout": res.stdout,
            "stderr": res.stderr,
            "exit_code": res.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds.",
            "exit_code": -1
        }

def write_file(path: str, content: str) -> str:
    # Safely write content to a file at the specified path
    try:
        expanded_path = os.path.expanduser(path)
        parent_dir = os.path.dirname(expanded_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(expanded_path, "w", encoding="utf-8") as f:
            f.write(content)
        # Return a clean relative display path
        display_path = os.path.join(os.path.basename(parent_dir), os.path.basename(expanded_path)) if parent_dir else os.path.basename(expanded_path)
        return f"File written successfully to {display_path}."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def send_email(to_email: str, subject: str, body: str) -> str:
    # Composes and sends an email natively via macOS Mail application using AppleScript
    # Clean and check for empty subject to prevent macOS from blocking on warning dialogs
    clean_subject = subject.strip() if subject else ""
    if not clean_subject:
        clean_subject = "Sent from PocketDev AI"
        
    clean_body = body.strip() if body else ""
    if not clean_body:
        clean_body = "PocketDev AI message."
        
    # Escape quotes in subject and body for AppleScript compatibility
    escaped_subject = clean_subject.replace('"', '\\"')
    escaped_body = clean_body.replace('"', '\\"').replace('\n', '\\n')
    
    applescript = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{escaped_subject}", content:"{escaped_body}", visible:true}}
        tell newMessage
            make new to recipient with properties {{address:"{to_email}"}}
            send
        end tell
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", applescript], check=True)
        return f"Email draft composed and sent to {to_email}."
    except Exception as e:
        return f"Failed to send email: {str(e)}"

from playwright.sync_api import sync_playwright

def automate_browser(url: str, action: str = "screenshot", click_selector: str = None, fill_selector: str = None, fill_text: str = None) -> str:
    """
    Automates Chrome actions: navigate, click, fill inputs, and take screenshots for verification.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        
        if fill_selector and fill_text:
            page.fill(fill_selector, fill_text)
        if click_selector:
            page.click(click_selector)
            page.wait_for_load_state("networkidle")
            
        if action == "screenshot":
            screenshot_path = os.path.expanduser("~/Desktop/browser_screenshot.png")
            page.screenshot(path=screenshot_path)
            browser.close()
            return f"Navigated to {url}. Captured screenshot to Desktop/browser_screenshot.png"
            
        elif action == "content":
            text_content = page.content()[:1000] # return first 1000 chars of HTML
            browser.close()
            return text_content


def modify_file(path: str, target_text: str, replacement_text: str) -> str:
    """
    Finds specific code in a file and replaces it with new code.
    """
    expanded_path = os.path.expanduser(path)
    if not os.path.exists(expanded_path):
        return f"Error: File '{path}' not found."
        
    with open(expanded_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if target_text not in content:
        return f"Error: Target text to replace not found in the file."
        
    new_content = content.replace(target_text, replacement_text, 1)
    with open(expanded_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    return f"Successfully modified '{path}'."


def play_media(query: str, platform: str = "youtube") -> str:
    """
    Searches for a video or song on YouTube or YouTube Music, finds the direct link, and opens it in Chrome to play automatically.
    """
    import urllib.parse
    from playwright.sync_api import sync_playwright
    
    query_encoded = urllib.parse.quote(query)
    
    # We always search on regular YouTube in the background because it is fast and does not have cookie consent walls.
    search_url = f"https://www.youtube.com/results?search_query={query_encoded}"
    
    if "music" in platform.lower():
        platform_name = "YouTube Music"
        fallback_url = f"https://music.youtube.com/search?q={query_encoded}"
    else:
        platform_name = "YouTube"
        fallback_url = search_url
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Add user agent to avoid bot-detection blocking
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(search_url, timeout=10000)
            
            # Wait for video link
            page.wait_for_selector("a#video-title", timeout=6000)
            first_link = page.locator("a#video-title").first.get_attribute("href")
            
            if first_link:
                # If they wanted YouTube Music, we rewrite the domain
                if platform_name == "YouTube Music":
                    if "watch?v=" in first_link:
                        # Clean and append watch link
                        direct_url = f"https://music.youtube.com{first_link}"
                    else:
                        direct_url = fallback_url
                else:
                    direct_url = f"https://www.youtube.com{first_link}"
            else:
                direct_url = fallback_url
                
            browser.close()
            
        # Open the direct URL in Chrome (which autoplays)
        open_chrome(direct_url)
        return f"Successfully found and playing '{query}' on {platform_name}."
    except Exception as e:
        # Fallback: just open the search page if automation fails
        open_chrome(fallback_url)
        return f"Opened search for '{query}' on {platform_name} (direct playback failed: {str(e)})."


# Dictionary mapping tool names to python functions
TOOLS_MAP = {
    "open_vscode": open_vscode,
    "open_chrome": open_chrome,
    "open_terminal": open_terminal,
    "open_finder": open_finder,
    "open_folder": open_folder,
    "take_screenshot": take_screenshot,
    "list_downloads": list_downloads,
    "lock_screen": lock_screen,
    "shutdown": shutdown,
    "restart": restart,
    "run_command": run_command,
    "write_file": write_file,
    "send_email": send_email,
    "automate_browser": automate_browser,
    "modify_file": modify_file,
    "play_media": play_media,
}
