# Steam Key Redeemer from Google Docs

This Python utility script extracts Steam keys from Google Docs and redeems them on Steam by detecting when a game is already owned on Steam.

It is designed to be a set-it-and-forget-it tool that maximizes the successful entry of keys into Steam, ensuring that no Steam game goes unredeemed.

The script automates the login process to Steam, making the entire process seamless. Feel free to submit an issue if you encounter any problems.

Any keys redeemed by the script are recorded in spreadsheet files, allowing you to review which actions were taken, and whether keys were redeemed, skipped, or failed.


## Supported Google Doc formats 
Examples of types document formats it can parse and extract from. Excludes dates by default. (There may be more it can handle, I just don't have examples)

**5/17/2024**
1) The Escapists 2
   1) XXXX-XXXX-XXXX
2) Golf With Your Friends
   1) XXXX-XXXX-XXXX
3) Moving Out
   1) XXXX-XXXX-XXXX

**5/16/2024**
1) 9 Years of Shadows XXXX-XXXX-XXXX
2) Axiom Verge 2 XXXX-XXXX-XXXX
3) Cookie Cutter XXXX-XXXX-XXXX

## To Run the Program
### Dependencies
- Requires Python version 3.8 or above.

### Optionally
```sh
run_steam_key_redeemer.bat
```

### Manual Installation
```sh 
pip install -r requirements.txt
```

```sh
py steam_key_redeemer.py
```

## Modes

### Auto-Redeem Mode (Steam)
Find Steam games from a Google Doc that are unowned by your Steam account, and **ONLY** redeem those that are unowned.

### Choose Games to Redeem One by One
Manually choose which games to redeem one by one.

### Export Mode
Find all games from the Google Doc, reveal all Steam keys and game titles, and output them to a CSV (including a Steam ownership column). This is great if you want a manual review of what games are in your keys list that you may have missed.

## Notes
To remove an already added account, delete the associated `.steamcookies` file.

### Thank You
Thanks to FailSpy for their work on [Humble Steam Key Redeemer](https://github.com/FailSpy/humble-steam-key-redeemer), as some of the code was leveraged and inspired additional functionality.