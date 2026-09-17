import os
import json
import requests
from datetime import datetime

# TOOL 1: Read the Link
def get_issue_title(github_url):
    print(f"Contacting GitHub for: {github_url}")
    response = requests.get(github_url)
    data = response.json()
    return data.get("title").lower()

# TOOL 2: Find the Files (Now returns the name of the file it found!)
def scan_local_folder(folder_path, target_word):
    print(f"\nScanning the '{folder_path}' folder...")
    
    for filename in os.listdir(folder_path):
        file_path = f"{folder_path}/{filename}"
        with open(file_path, "r") as file:
            file_text = file.read().lower()

        if target_word in file_text:
            print(f" BINGO! The bug is hiding inside: {filename}")
            return filename # Hand the answer back!
            
    return "No bug found"

# TOOL 3: Save a Receipt
def save_receipt(issue_url, found_file):
    print("\nSaving receipt...")
    
    # Package our data into a neat dictionary
    receipt_data = {
        "searched_link": issue_url,
        "found_bug_in": found_file,
        "time_scanned": str(datetime.now())
    }
    
    # Create a unique file name using the current time
    timestamp = datetime.now().strftime('%H%M%S')
    file_name = f"receipts/scan_{timestamp}.json"
    
    # Save the dictionary into a real file
    with open(file_name, "w") as file:
        json.dump(receipt_data, file, indent=4)
        
    print(f" Receipt saved as: {file_name}")

# --- HOW TO USE YOUR TOOLS ---
my_link = "https://api.github.com/repos/pallets/flask/issues/5000"
my_folder = "demo"

# 1. Get the title
bug_title = get_issue_title(my_link)

# 2. Find the file AND save the answer in a variable
guilty_file = scan_local_folder(my_folder, bug_title)

# 3. Save the receipt!
save_receipt(my_link, guilty_file)