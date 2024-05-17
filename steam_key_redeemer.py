import requests
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from fuzzywuzzy import fuzz
import steam.webauth as wa
import time
import pickle
from pwinput import pwinput
import os
import json
import sys
import webbrowser
from base64 import b64encode
import atexit
import signal
from http.client import responses
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from flask import Flask, request
import threading
import re

# Patch steam webauth for password feedback
wa.getpass = pwinput

# Flask app for handling OAuth redirect
app = Flask(__name__)
auth_code = None

# Google OAuth 2.0 setup
SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
CLIENT_SECRETS_FILE = "client_secret.json"  # Prefill this value
GOOGLE_CREDENTIALS_FILE = ".google_credentials.json"
STEAM_COOKIES_FILE = ".steamcookies"

# Steam endpoints
STEAM_KEYS_PAGE = "https://store.steampowered.com/account/registerkey"
STEAM_USERDATA_API = "https://store.steampowered.com/dynamicstore/userdata/"
STEAM_REDEEM_API = "https://store.steampowered.com/account/ajaxregisterkey/"
STEAM_APP_LIST_API = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"

# Global variable for tracking files
files = {}

def process_quit(driver):
    def quit_on_exit(*args):
        driver.quit()

    atexit.register(quit_on_exit)
    signal.signal(signal.SIGTERM, quit_on_exit)
    signal.signal(signal.SIGINT, quit_on_exit)

def try_recover_cookies(cookie_file, session):
    try:
        cookies = pickle.load(open(cookie_file, "rb"))
        if type(session) is requests.Session:
            # handle Steam session
            session.cookies.update(cookies)
        else:
            # handle WebDriver
            for cookie in cookies:
                session.add_cookie(cookie)
        return True
    except Exception as e:
        return False

def find_dict_keys(node, kv, parent=False):
    if isinstance(node, list):
        for i in node:
            for x in find_dict_keys(i, kv, parent):
                yield x
    elif isinstance(node, dict):
        if kv in node:
            if parent:
                yield node
            else:
                yield node[kv]
        for j in node.values():
            for x in find_dict_keys(j, kv, parent):
                yield x

def verify_logins_session(session):
    # Returns steam_status
    if type(session) is requests.Session:
        loggedin = session.get(STEAM_KEYS_PAGE, allow_redirects=False).status_code not in (301, 302)
        return loggedin
    else:
        return False

def export_cookies(cookie_file, session):
    try:
        cookies = None
        if type(session) is requests.Session:
            # handle Steam session
            cookies = session.cookies
        else:
            # handle WebDriver
            cookies = session.get_cookies()
        pickle.dump(cookies, open(cookie_file, "wb"))
        return True
    except:
        return False

def get_headless_driver():
    possibleDrivers = [(webdriver.Firefox, webdriver.FirefoxOptions), (webdriver.Chrome, webdriver.ChromeOptions)]
    driver = None

    exceptions = []
    for d, opt in possibleDrivers:
        try:
            options = opt()
            if d == webdriver.Chrome:
                options.add_argument("--headless=new")
            else:
                options.add_argument("-headless")
            driver = d(options=options)
            process_quit(driver)  # make sure driver closes when we close
            return driver
        except WebDriverException as e:
            exceptions.append(('chrome:' if d == webdriver.Chrome else 'firefox:', e))
            continue
    cls()
    print("This script needs either Chrome or Firefox to be installed and the respective Web Driver for it to be configured (usually simplest is by placing it in the folder with the script)")
    print("")
    print("https://www.browserstack.com/guide/geckodriver-selenium-python")
    print("")
    print("Potential configuration hints:")
    for browser, exception in exceptions:
        print("")
        print(browser, exception.msg)

    time.sleep(30)
    sys.exit()

def steam_login():
    # Sign into Steam web

    # Attempt to use saved session
    r = requests.Session()
    if try_recover_cookies(STEAM_COOKIES_FILE, r) and verify_logins_session(r):
        return r

    # Saved state doesn't work, prompt user to sign in.
    s_username = input("Steam Username: ")
    user = wa.WebAuth(s_username)
    session = user.cli_login()
    export_cookies(STEAM_COOKIES_FILE, session)
    return session

def valid_steam_key(key):
    # Steam keys are in the format of AAAAA-BBBBB-CCCCC
    if not isinstance(key, str):
        return False
    key_parts = key.split("-")
    return (
        len(key) == 17
        and len(key_parts) == 3
        and all(len(part) == 5 for part in key_parts)
    )

def _redeem_steam(session, key, quiet=False):
    if key == "":
        return 0
    session_id = session.cookies.get_dict()["sessionid"]
    r = session.post(STEAM_REDEEM_API, data={"product_key": key, "sessionid": session_id})
    blob = r.json()

    if blob["success"] == 1:
        for item in blob["purchase_receipt_info"]["line_items"]:
            print("Redeemed " + item["line_item_description"])
        return 0
    else:
        error_code = blob.get("purchase_result_details")
        if error_code == None:
            # Sometimes purchase_result_details isn't there for some reason, try alt method
            error_code = blob.get("purchase_receipt_info")
            if error_code != None:
                error_code = error_code.get("result_detail")
        error_code = error_code or 53

        if error_code == 14:
            error_message = (
                "The product code you've entered is not valid. Please double check to see if you've "
                "mistyped your key. I, L, and 1 can look alike, as can V and Y, and 0 and O. "
            )
        elif error_code == 15:
            error_message = (
                "The product code you've entered has already been activated by a different Steam account. "
                "This code cannot be used again. Please contact the retailer or online seller where the "
                "code was purchased for assistance. "
            )
        elif error_code == 53:
            error_message = (
                "There have been too many recent activation attempts from this account or Internet "
                "address. Please wait and try your product code again later. "
            )
        elif error_code == 13:
            error_message = (
                "Sorry, but this product is not available for purchase in this country. Your product key "
                "has not been redeemed. "
            )
        elif error_code == 9:
            error_message = (
                "This Steam account already owns the product(s) contained in this offer. To access them, "
                "visit your library in the Steam client. "
            )
        elif error_code == 24:
            error_message = (
                "The product code you've entered requires ownership of another product before "
                "activation.\n\nIf you are trying to activate an expansion pack or downloadable content, "
                "please first activate the original game, then activate this additional content. "
            )
        elif error_code == 36:
            error_message = (
                "The product code you have entered requires that you first play this game on the "
                "PlayStation®3 system before it can be registered.\n\nPlease:\n\n- Start this game on "
                "your PlayStation®3 system\n\n- Link your Steam account to your PlayStation®3 Network "
                "account\n\n- Connect to Steam while playing this game on the PlayStation®3 system\n\n- "
                "Register this product code through Steam. "
            )
        elif error_code == 50:
            error_message = (
                "The code you have entered is from a Steam Gift Card or Steam Wallet Code. Browse here: "
                "https://store.steampowered.com/account/redeemwalletcode to redeem it. "
            )
        else:
            error_message = (
                "An unexpected error has occurred.  Your product code has not been redeemed.  Please wait "
                "30 minutes and try redeeming the code again.  If the problem persists, please contact <a "
                'href="https://help.steampowered.com/en/wizard/HelpWithCDKey">Steam Support</a> for '
                "further assistance. "
            )
        if error_code != 53 or not quiet:
            print(error_message)
        return error_code

def write_key(code, key):
    global files

    filename = "redeemed.csv"
    if code == 15 or code == 9:
        filename = "already_owned.csv"
    elif code != 0:
        filename = "errored.csv"

    if filename not in files:
        files[filename] = open(filename, "a", encoding="utf-8-sig")
    key["human_name"] = key["human_name"].replace(",", ".")
    gamekey = key.get('gamekey')
    human_name = key.get("human_name")
    redeemed_key_val = key.get("redeemed_key_val")
    output = f"{gamekey},{human_name},{redeemed_key_val}\n"
    files[filename].write(output)
    files[filename].flush()

def cls():
    os.system('cls' if os.name == 'nt' else 'clear')
    print_main_header()

def print_main_header():
    print("===Steam Key Manager===")
    print("----------------------")

def start_flask():
    app.run(port=3000)

@app.route('/oauth2callback')
def oauth2callback():
    global auth_code
    auth_code = request.args.get('code')
    return "Authentication successful! You can close this window."

@app.route('/shutdown', methods=['POST'])
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'

def authenticate_google_docs():
    global auth_code

    # Try to load saved credentials
    if os.path.exists(GOOGLE_CREDENTIALS_FILE):
        creds = Credentials.from_authorized_user_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
    else:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            auth_url, _ = flow.authorization_url(prompt='consent')

            webbrowser.open(auth_url)

            # Start Flask server to handle OAuth2 callback
            flask_thread = threading.Thread(target=start_flask)
            flask_thread.start()

            while auth_code is None:
                time.sleep(1)

            flask_thread.join()

            flow.fetch_token(code=auth_code)
            creds = flow.credentials

            # Save the credentials for the next run
            with open(GOOGLE_CREDENTIALS_FILE, 'w') as token:
                token.write(creds.to_json())

    service = build('docs', 'v1', credentials=creds)
    return service

def get_google_doc_content(service, document_id):
    doc = service.documents().get(documentId=document_id).execute()
    content = doc.get('body').get('content')
    return content

def extract_steam_keys(doc_content):
    steam_keys = []
    current_title = None

    for element in doc_content:
        if 'paragraph' in element:
            for run in element.get('paragraph').get('elements'):
                run_text = run.get('textRun', {}).get('content', '').strip()

                if valid_steam_key(run_text):
                    if current_title:
                        steam_keys.append((current_title, run_text))
                        current_title = None
                else:
                    if not re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', run_text):  # Ignore dates
                        current_title = run_text
                    else:
                        current_title = None
    return steam_keys

def get_owned_apps(steam_session):
    owned_content = steam_session.get(STEAM_USERDATA_API).json()
    owned_app_ids = owned_content["rgOwnedPackages"] + owned_content["rgOwnedApps"]
    owned_app_details = {
        app["appid"]: app["name"]
        for app in steam_session.get(STEAM_APP_LIST_API).json()["applist"]["apps"]
        if app["appid"] in owned_app_ids
    }
    return owned_app_details

def match_ownership(owned_app_details, game):
    threshold = 70
    best_match = (0, None)
    # Do a string search based on product names.
    matches = [
        (fuzz.token_set_ratio(appname, game), appid)
        for appid, appname in owned_app_details.items()
    ]
    refined_matches = [
        (fuzz.token_sort_ratio(owned_app_details[appid], game), appid)
        for score, appid in matches
        if score > threshold
    ]

    if len(refined_matches) > 0:
        best_match = max(refined_matches, key=lambda item: item[0])
    elif len(refined_matches) == 1:
        best_match = refined_matches[0]
    if best_match[0] < 35:
        best_match = (0, None)
    return best_match

def prompt_mode():
    print("Choose your mode:")
    print("[1] Auto-Redeem all unowned games")
    print("[2] Choose games to redeem one by one")
    print("[3] Export Mode")
    print("[4] Help")
    print("[5] Exit")
    mode = input("Enter 1, 2, 3, 4, or 5: ").strip()
    return mode

def help_documentation():
    print("Help Documentation:")
    print("1. Google Authentication:")
    print("   - You will need to provide the path to your client_secret.json file.")
    print("   - If you have not already done so, you will need to create a Google Cloud project and enable the Docs API.")
    print("   - Login to your Google account and navigate to the Google Cloud Console.")
    print("   - Enter a name for your application and click create.")
    print("   - Go to API & Services > Credentials > Create Credentials > OAuth Client ID.")
    print("   - Inside the Application Type dropdown, select Web Application")
    print("   - Add URI: http://localhost:3000/oauth2callback")
    print("   - Go to API & Services > Library and select Docs API.")
    print("   - Enable Document:read_only and (Optionally) Document:create permissions.")
    print("   - Back at APIs & Services > OAuth consent screen, Add Test Users yourself or share your Google account with the test users.")
    print("   - Click Save and Continue.")
    print("   - Download the client_secret.json file and place it in the same directory as this script.")
    print("   - Follow the instructions to authenticate your Google account.")
    print("   - This will allow the script to access your Google Docs and retrieve Steam keys.")
    print("2. Steam Login:")
    print("   - Enter your Steam username and password when prompted.")
    print("   - This will allow the script to access your Steam account and retrieve your game library.")
    print("3. Modes of Operation:")
    print("   - Auto-Redeem: Automatically redeem all Steam keys that are not already in your library.")
    print("   - Choose Games: Manually choose which games to redeem one by one.")
    print("   - Export Mode: Export all Steam keys to a CSV for manual review.")
    print("4. CSV Export:")
    print("   - All redeemed keys will be exported to a CSV file.")
    print("   - Files: redeemed.csv, already_owned.csv, errored.csv")
    print("5. Troubleshooting:")
    print("   - If you encounter any issues, please refer to the error.csv file for details.")
    input("Press Enter to go back to Choose your mode...")

def export_to_csv(google_steam_keys, owned_app_details):
    with open("exported_keys.csv", "w", encoding="utf-8-sig") as f:
        f.write("Game Title,Steam Key,Owned\n")
        for title, key in google_steam_keys:
            owned = "Yes" if match_ownership(owned_app_details, title)[1] is not None else "No"
            f.write(f"{title},{key},{owned}\n")
    print("Export completed. Check exported_keys.csv for details.")

if __name__ == "__main__":
    cls()

    while True:
        mode = prompt_mode()

        if mode == "5":
            print("Exiting...")
            break

        if mode == "4":
            help_documentation()
            continue

        document_id = input("Enter the Google Document ID: ").strip()
        CLIENT_SECRETS_FILE = input("Enter the path to your client_secret.json (press Enter to use default): ").strip() or "client_secret.json"
        service = authenticate_google_docs()
        doc_content = get_google_doc_content(service, document_id)
        google_steam_keys = extract_steam_keys(doc_content)

        # Log in to Steam
        steam_session = steam_login()
        print("Successfully signed in on Steam.")
        print("Getting your owned content to avoid attempting to register keys already owned...")

        # Query owned App IDs according to Steam
        owned_app_details = get_owned_apps(steam_session)

        # Filter out keys that the user already owns
        unowned_keys = [(title, key) for title, key in google_steam_keys if match_ownership(owned_app_details, title)[1] is None]

        print(f"Filtered out game keys that you already own on Steam; {len(unowned_keys)} keys unowned.")

        if mode == "1":
            # Auto-Redeem mode
            for title, key in unowned_keys:
                code = _redeem_steam(steam_session, key)
                write_key(code, {"gamekey": key, "human_name": title, "redeemed_key_val": key})
            print("Process completed.")
        elif mode == "2":
            # Choose games to redeem one by one
            for title, key in unowned_keys:
                redeem = input(f"Do you want to redeem the key for {title}? (y/n): ").strip().lower()
                if redeem == "y":
                    code = _redeem_steam(steam_session, key)
                    write_key(code, {"gamekey": key, "human_name": title, "redeemed_key_val": key})
            print("Process completed.")
        elif mode == "3":
            # Export to CSV
            export_to_csv(google_steam_keys, owned_app_details)

    # Cleanup
    for f in files:
        files[f].close()
