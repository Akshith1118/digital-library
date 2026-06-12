import subprocess
import sys
import threading
import time
import re

def run_flask():
    # Start Flask server locally
    subprocess.run([sys.executable, "app.py"])

def run_tunnel():
    print("Starting secure public internet tunnel via localhost.run...")
    # Launch SSH reverse tunnel
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-R", "80:localhost:5000", "nokey@localhost.run"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    url_pattern = re.compile(r"https://[a-zA-Z0-9.-]+\.(?:localhost\.run|lhr\.life)")
    
    # Parse output to capture and highlight the public URL
    for line in iter(process.stdout.readline, ''):
        line_str = line.strip()
        print(line_str)
        match = url_pattern.search(line_str)
        if match:
            public_url = match.group(0)
            print("\n" + "="*70)
            print(" 🎉 YOUR WEBSITE IS PUBLIC ON THE INTERNET!")
            print(f" Public Link: {public_url}")
            print(" Open this link from anywhere in the world on any device.")
            print("="*70 + "\n")

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Wait for the Flask server to initialize
    time.sleep(2)
    
    try:
        run_tunnel()
    except KeyboardInterrupt:
        print("\nStopping application and tunnel...")
