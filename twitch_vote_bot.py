import socket
import datetime
import pytz
import os
import json
import requests
import subprocess
import random
import time
import sys
from dotenv import load_dotenv
load_dotenv()
from collections import defaultdict
from urllib.parse import quote_plus
import difflib
from bs4 import BeautifulSoup

# ====== CONFIG ======
CLIENT_ID    = os.getenv("CLIENT_ID")
OAUTH_TOKEN  = os.getenv("OAUTH_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
CHANNEL_NAME = os.getenv("CHANNEL_NAME")
CHANNEL      = "#" + CHANNEL_NAME.lower()
VOTE_FILE         = "index.html"
VOTES_JSON        = "votes.json"
ARCHIVE_DIR       = "archives"
METADATA_FILE     = os.path.join(ARCHIVE_DIR, "archives.json")
TWITCH_URL        = "https://twitch.tv/brucecooper"

# ====== STATE ======
PST                   = pytz.timezone("America/Los_Angeles")
game_suggestions      = {}                   # key -> {"name","votes","url","user","time"}
user_votes            = defaultdict(dict)    # user_votes[user][key] = week_id
user_daily_counts     = defaultdict(lambda: defaultdict(int))
vote_history          = []                   # [(key, user), …]
last_message_time     = 0
MESSAGE_COOLDOWN      = 0.3
last_archive_date     = None
pending_clear         = False                # for !voteremove all
pending_delete_fname  = None                 # for specific archive deletion
pending_delete_all    = False                # for delete all archives

# ====== HELPERS ======
def fetch_meme_urls():
    try:
        token = OAUTH_TOKEN.split("oauth:")[-1]
        headers = {"Client-ID": CLIENT_ID, "Authorization": f"Bearer {token}"}
        r = requests.get("https://api.twitch.tv/helix/chat/emotes/global", headers=headers, timeout=5)
        r.raise_for_status()
        return [e["images"]["url_4x"] for e in r.json().get("data", []) if e.get("images",{}).get("url_4x")] \
               or ["https://i.imgur.com/0rR9O4N.jpeg"]
    except:
        return ["https://i.imgur.com/0rR9O4N.jpeg"]

MEME_URLS = fetch_meme_urls()
ACCENTS   = ["#ff0044", "#00ff88", "#ffaa00", "#00ccff", "#ff00cc"]

def send_chat(sock, message):
    global last_message_time
    now = time.time()
    if now - last_message_time < MESSAGE_COOLDOWN:
        time.sleep(MESSAGE_COOLDOWN)
    sock.send(f"PRIVMSG {CHANNEL} :{message}\r\n".encode())
    last_message_time = now

def get_current_pst_datetime():
    return datetime.datetime.now(PST)

def get_current_vote_week():
    return get_current_pst_datetime().strftime("%Y-W%U")

def find_steam_link(name):
    try:
        url = "https://store.steampowered.com/search/?term=" + quote_plus(name)
        r = requests.get(url, headers={"User-Agent":"Mozilla"}, timeout=5)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        row = soup.select_one("a.search_result_row")
        if row:
            title = row.select_one("span.title").text.strip()
            if difflib.SequenceMatcher(None, name.lower(), title.lower()).ratio() > 0.7:
                return title, row["href"].split("?")[0]
    except:
        pass
    return None

# ====== PERSISTENCE ======
def write_votes_json():
    arr = []
    for _, info in sorted(game_suggestions.items(), key=lambda kv: kv[1]["votes"], reverse=True):
        arr.append({
            "name":  info["name"],
            "votes": info["votes"],
            "url":   info["url"],
            "user":  info["user"],
            "time":  info["time"]
        })
    with open(VOTES_JSON, "w", encoding="utf-8") as vf:
        json.dump(arr, vf, indent=2)

def write_vote_file():
    write_votes_json()

    # build games list HTML
    games_html = ""
    for _, info in sorted(game_suggestions.items(), key=lambda kv: kv[1]["votes"], reverse=True):
        lbl = "vote" if info["votes"] == 1 else "votes"
        link_html = (f'<div class="store-link"><a href="{info["url"]}" target="_blank">'
                     f'View on Store</a></div>' if info["url"] else "")
        games_html += f"""
      <div class="game">
        <div class="votes">{info['votes']} {lbl}</div>
        <div class="game-name">{info['name']}</div>
        <div class="suggester">Suggested by: {info['user']} at {info['time']}</div>
        {link_html}
      </div>"""

    mem0     = MEME_URLS[0]
    memes    = json.dumps(MEME_URLS)
    accents  = json.dumps(ACCENTS)
    vjson    = VOTES_JSON

    # use relative path here so link works on both main and archive pages:
    archlink = f"{ARCHIVE_DIR}/index.html"

    twitch   = TWITCH_URL

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8"/>
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>
  <meta http-equiv="Pragma" content="no-cache"/>
  <meta http-equiv="Expires" content="0"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>🎮 Game Suggestions</title>
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500&family=Roboto+Mono&display=swap" rel="stylesheet"/>
  <style>
    :root {{
      --accent-color: #00eaff;
      --game-color:   #00ff88;
      --bgurl:        url('{mem0}');
      --card-bg:      rgba(17,17,17,0.85);
      --card-border:  rgba(0,234,255,0.6);
      --vote-bg:      rgba(0,234,255,0.15);
    }}
    body {{margin:0;font-family:'Roboto Mono',monospace;color:#e0e0e0;background:#0a0a0a;position:relative}}
    body::before {{content:"";background:var(--bgurl) repeat center;background-size:100px 100px;
                   position:fixed;inset:0;opacity:0.25;filter:blur(4px);z-index:-1}}
    .container {{max-width:900px;margin:2rem auto;padding:2rem;
                 background:rgba(0,0,0,0.8);border-radius:16px;box-shadow:0 0 30px rgba(0,0,0,0.8)}}
    h1 {{font-family:'Orbitron',sans-serif;text-align:center;color:var(--accent-color);
         margin-bottom:0.5rem;text-shadow:0 0 8px rgba(0,234,255,0.7)}}
    h1 a {{ color: inherit; text-decoration: none; }}
    .links {{text-align:center;margin-bottom:1rem;}}
    .links a {{color:var(--accent-color);text-decoration:none;margin:0 0.5rem;font-size:1em;}}
    .links a:hover {{text-decoration:underline;}}
    .game {{background:var(--card-bg);border:2px solid var(--card-border);
            border-radius:12px;padding:1rem 1.5rem;margin:1rem 0;
            box-shadow:0 4px 12px rgba(0,0,0,0.7);transition:0.2s}}
    .game:hover {{transform:translateY(-4px);box-shadow:0 8px 20px rgba(0,0,0,0.8)}}
    .votes {{display:inline-block;background:var(--vote-bg);color:var(--accent-color);
             font-size:1.3em;font-weight:bold;padding:0.4em 0.8em;border-radius:0.4em;
             margin-bottom:0.5em;text-shadow:0 0 4px rgba(0,234,255,0.5)}}
    .game-name {{font-size:1.5em;font-weight:bold;margin:0.3em 0;color:var(--game-color)}}
    .suggester {{opacity:0.75;font-style:italic;font-size:0.9em}}
    .store-link a {{color:#888;font-size:0.8em;text-decoration:none}}
    .store-link a:hover {{color:var(--accent-color);text-shadow:0 0 6px var(--accent-color)}}
    .archive-link {{margin-top:1rem;text-align:center}}
    .archive-link .link {{font-size:0.85em;color:#888;text-decoration:none;
                          padding:0.3em 0.6em;border:1px solid #555;
                          border-radius:6px;background:rgba(0,0,0,0.3)}}
    .archive-link .link:hover {{background:rgba(255,255,255,0.1);color:#aaa}}
    .howto-section {{margin-top:2rem;padding:1rem;background:rgba(0,0,0,0.5);
                     border-left:4px solid var(--accent-color);border-radius:6px;
                     font-size:0.9em;line-height:1.4}}
    @media(max-width:600px) {{
      .container{{margin:1rem;padding:1rem}}
      h1{{font-size:2rem}}
      .links a{{font-size:0.9em}}
      .game{{padding:0.8rem 1rem}}
      .votes{{font-size:1.1em;padding:0.3em 0.6em}}
    }}
  </style>
  <script>
    var EMOTES  = {memes};
    var ACCENTS = {accents};
    document.addEventListener('DOMContentLoaded', function() {{
      var bg = EMOTES[Math.floor(Math.random()*EMOTES.length)];
      var accent = ACCENTS[Math.floor(Math.random()*ACCENTS.length)];
      var gameColor = ACCENTS[Math.floor(Math.random()*ACCENTS.length)];
      document.documentElement.style.setProperty('--bgurl','url('+bg+')');
      document.documentElement.style.setProperty('--accent-color',accent);
      document.documentElement.style.setProperty('--game-color',gameColor);
      updateVotes(); setInterval(updateVotes,2000);
    }});
    async function updateVotes() {{
      try {{
        var res = await fetch('{vjson}?cb=' + Date.now());
        var games = await res.json();
        document.getElementById('games-list').innerHTML = games.map(function(g) {{
          var lbl = g.votes===1 ? 'vote' : 'votes';
          var link = g.url
            ? '<div class="store-link"><a href="'+g.url+'" target="_blank">View on Store</a></div>'
            : '';
          return '<div class="game">'
               +  '<div class="votes">'+g.votes+' '+lbl+'</div>'
               +  '<div class="game-name">'+g.name+'</div>'
               +  '<div class="suggester">Suggested by: '+g.user+' at '+g.time+'</div>'
               +  link
               + '</div>';
        }}).join('');  
      }} catch(e) {{ console.error(e); }}
    }}
  </script>
</head><body>
  <div class="container">
    <h1><a href="index.html">🎮 Game Suggestions</a></h1>
    <div class="links">
        <a href="{twitch}" target="_blank">🎥 Watch Live on Twitch</a>
        <a class="link" href="{archlink}">📂 View Archives</a>
        <a class="link" href="commands.html">📜 View Commands</a>
    </div>
    <div id="games-list">
      {games_html}
    </div>
    <script>
      var host = window.location.hostname;
      var iframe = document.createElement('iframe');
      iframe.src  = 'https://player.twitch.tv/?channel=brucecooper&parent=' + host;
      iframe.style.width  = '100%';
      iframe.style.height = '300px';
      iframe.style.border = 'none';
      document.body.appendChild(iframe);
    </script>
    <div id="howto" class="howto-section">
      <h2>How to Vote</h2>
      <p>You may vote for up to <strong>5 different games per day</strong>, but only the same game <strong>once per week</strong>.</p>
      <p>In chat, type <code>!vote Game&nbsp;Name</code>. Votes reset every Saturday at midnight&nbsp;PST.</p>
    </div>
  </div>
</body></html>"""

    with open(VOTE_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    push_to_github()

# ====== ARCHIVE & GITHUB UTILS ======
def archive_votes():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    now     = get_current_pst_datetime()
    week_id = now.strftime("%Y-W%U")
    start   = (now - datetime.timedelta(days=6)).strftime("%B %d, %Y")
    end     = now.strftime("%B %d, %Y")
    fn      = f"archive_{week_id}.html"
    path    = os.path.join(ARCHIVE_DIR, fn)
    if os.path.exists(VOTE_FILE):
        with open(VOTE_FILE,'r',encoding="utf-8") as src, open(path,'w',encoding="utf-8") as dst:
            dst.write(src.read())
    meta = []
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE,'r',encoding="utf-8") as m:
            meta = json.load(m)
    total = sum(info["votes"] for info in game_suggestions.values())
    if not any(e["week_id"]==week_id for e in meta):
        meta.append({"week_id":week_id,"start":start,"end":end,"total_votes":total,"file":fn})
        with open(METADATA_FILE,'w',encoding="utf-8") as m:
            json.dump(meta,m,indent=2)
    generate_archive_index()
    push_to_github()

def generate_archive_index():
    if not os.path.exists(METADATA_FILE): return
    with open(METADATA_FILE,'r',encoding="utf-8") as m:
        meta = sorted(json.load(m), key=lambda e:e["week_id"], reverse=True)
    back_main = "../index.html"
    html2 = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>📂 Vote Archives</title>
  <style>
    body{background:#0a0a0a;color:#c9d1d9;font-family:sans-serif;padding:20px}
    .links{margin-bottom:1rem}.links a{color:#888;text-decoration:none;margin-right:1rem}
    .links a:hover{text-decoration:underline;font-weight:bold}
    .week{margin-bottom:1rem;padding:0.5rem 0;border-bottom:1px solid #333}
    a{color:#888;text-decoration:none}a:hover{text-decoration:underline}
  </style></head><body>"""
    html2 += f"<div class='links'><a href='{back_main}'>← Back to Suggestions</a><a href='{TWITCH_URL}' target='_blank'>🎥 Watch on Twitch</a></div>"
    html2 += "<h1>📂 Vote Archives</h1>"
    for e in meta:
        html2 += (
            "<div class='week'>"
            f"<strong>Week {e['week_id']}</strong><br>"
            f"{e['start']} – {e['end']}<br>"
            f"Total Votes: {e['total_votes']}<br>"
            f"<a href='{e['file']}'>View Details</a>"
            "</div>"
        )
    html2 += "</body></html>"
    with open(os.path.join(ARCHIVE_DIR, "index.html"), 'w', encoding="utf-8") as out:
        out.write(html2)
    push_to_github()

def push_to_github():
    to_add = [VOTES_JSON, VOTE_FILE]
    if os.path.isdir(ARCHIVE_DIR):
        for fn in os.listdir(ARCHIVE_DIR):
            if fn.endswith(".html") or fn.endswith(".json"):
                to_add.append(os.path.join(ARCHIVE_DIR, fn))
    try:
        subprocess.run(["git","add"] + to_add, check=True)
        if subprocess.run(["git","diff-index","--quiet","HEAD"], check=False).returncode != 0:
            subprocess.run(["git","commit","-m","Auto update vote page"], check=True)
            subprocess.run(["git","push"], check=True)
    except subprocess.CalledProcessError:
        pass

def main():
    global last_message_time, last_archive_date, pending_clear, pending_delete_fname, pending_delete_all
    sock = socket.socket()
    try:
        sock.connect(("irc.chat.twitch.tv", 6667))
    except Exception as e:
        print("Connection error:", e)
        return
    sock.send(f"PASS {OAUTH_TOKEN}\r\n".encode())
    sock.send(f"NICK {BOT_USERNAME}\r\n".encode())
    sock.send(f"JOIN {CHANNEL}\r\n".encode())
    print(f"✅ Connected to {CHANNEL}")

    while True:
        now   = get_current_pst_datetime()
        today = now.strftime("%Y-%m-%d")

        if now.weekday()==5 and now.strftime("%H:%M")=="00:00" and last_archive_date!=now.date():
            archive_votes()
            game_suggestions.clear(); user_votes.clear()
            user_daily_counts.clear(); vote_history.clear()
            write_vote_file()
            last_archive_date = now.date()

        try:
            resp = sock.recv(2048).decode("utf-8", errors="ignore")
        except:
            break
        if resp.startswith("PING"):
            sock.send("PONG :tmi.twitch.tv\r\n".encode()); continue

        for line in resp.split("\r\n"):
            if f"PRIVMSG {CHANNEL}" not in line: continue
            user = line.split("!",1)[0][1:]; msg = line.split(":",2)[2].strip()

            # !archive
            if msg.lower()=="!archive" and user.lower()==BOT_USERNAME.lower():
                send_chat(sock, f"@{user} ⚠️ Archiving now... confirm with !confirmarchive")
                continue
            if msg.lower()=="!confirmarchive" and user.lower()==BOT_USERNAME.lower():
                archive_votes()
                game_suggestions.clear(); user_votes.clear()
                user_daily_counts.clear(); vote_history.clear()
                write_vote_file()
                last_archive_date = now.date()
                send_chat(sock, f"@{user} ✅ Archive complete, votes cleared.")
                continue

            # !archivedelete ...
            if msg.lower().startswith("!archivedelete ") and user.lower()==BOT_USERNAME.lower():
                arg = msg[len("!archivedelete "):].strip()
                if arg.lower()=="all":
                    pending_delete_all = True
                    send_chat(sock, f"@{user} ⚠️ Confirm delete ALL archives with !confirmdeleteall")
                else:
                    pending_delete_fname = arg
                    send_chat(sock, f"@{user} ⚠️ Confirm delete archive '{pending_delete_fname}' with !confirmdelete")
                continue

            if msg.lower()=="!confirmdelete" and user.lower()==BOT_USERNAME.lower() and pending_delete_fname:
                fn = pending_delete_fname
                path = os.path.join(ARCHIVE_DIR, fn)
                if os.path.exists(path):
                    os.remove(path)
                    meta = []
                    if os.path.exists(METADATA_FILE):
                        with open(METADATA_FILE,"r",encoding="utf-8") as m:
                            meta = json.load(m)
                    meta = [e for e in meta if e.get("file")!=fn]
                    with open(METADATA_FILE,"w",encoding="utf-8") as m:
                        json.dump(meta,m,indent=2)
                    generate_archive_index(); push_to_github()
                    send_chat(sock, f"@{user} ✅ Archive '{fn}' deleted.")
                else:
                    send_chat(sock, f"@{user} ❌ Archive '{fn}' not found.")
                pending_delete_fname = None
                continue

            if msg.lower()=="!confirmdeleteall" and user.lower()==BOT_USERNAME.lower() and pending_delete_all:
                for fn in os.listdir(ARCHIVE_DIR):
                    if fn.endswith(".html") or fn.endswith(".json"):
                        os.remove(os.path.join(ARCHIVE_DIR, fn))
                with open(METADATA_FILE,"w",encoding="utf-8") as m:
                    json.dump([],m,indent=2)
                generate_archive_index(); push_to_github()
                send_chat(sock, f"@{user} ✅ All archives deleted.")
                pending_delete_all = False
                continue

            # !voteremove all
            if msg.lower()=="!voteremove all" and user.lower()==BOT_USERNAME.lower():
                pending_clear=True
                send_chat(sock, f"@{user} ⚠️ Confirm delete ALL votes with !confirm")
                continue
            if msg.lower()=="!confirm" and user.lower()==BOT_USERNAME.lower() and pending_clear:
                game_suggestions.clear(); user_votes.clear()
                user_daily_counts.clear(); vote_history.clear()
                write_vote_file()
                pending_clear=False
                send_chat(sock, f"@{user} ✅ All votes removed.")
                continue

            # !voteremove last
            if msg.lower()=="!voteremove last" and user.lower()==BOT_USERNAME.lower():
                if vote_history:
                    k,u = vote_history.pop()
                    game_suggestions[k]["votes"]-=1
                    user_votes[u].pop(k,None)
                    if game_suggestions[k]["votes"]<=0:
                        del game_suggestions[k]
                    write_vote_file(); send_chat(sock, f"@{user} 🗑️ Removed last vote '{k}'.")
                else:
                    send_chat(sock, f"@{user} 🤷 No vote history.")
                continue

            # !voteremove (own last vote)
            if msg.lower() == "!voteremove":
                for i in range(len(vote_history)-1, -1, -1):
                    key, u = vote_history[i]
                    if u == user:
                        vote_history.pop(i)
                        game_suggestions[key]["votes"] -= 1
                        user_votes[user].pop(key, None)
                        if game_suggestions[key]["votes"] <= 0:
                            del game_suggestions[key]
                        write_vote_file()
                        send_chat(sock, f"@{user} 🗑️ Your last vote for '{key}' was removed.")
                        break
                else:
                    send_chat(sock, f"@{user} 🤷 You have no recent vote to remove.")
                continue

            # !voteremove <game>
            if msg.lower().startswith("!voteremove ") and user.lower()==BOT_USERNAME.lower():
                name = msg[len("!voteremove "):].strip()
                key = (difflib.get_close_matches(name.lower(), game_suggestions.keys(), n=1, cutoff=0.7)
                       or [name.lower()])[0]
                if key in game_suggestions and game_suggestions[key]["votes"]>0:
                    game_suggestions[key]["votes"]-=1
                    for i in range(len(vote_history)-1,-1,-1):
                        if vote_history[i][0]==key:
                            vote_history.pop(i)
                            break
                    if game_suggestions[key]["votes"]<=0:
                        del game_suggestions[key]
                    write_vote_file(); send_chat(sock, f"@{user} 🗑️ Removed one vote from '{key}'.")
                else:
                    send_chat(sock, f"@{user} 🤷 No votes for '{name}'.")
                continue

                

            # !vote <game>
            if msg.lower().startswith("!vote "):
                raw = msg[len("!vote "):].strip()
                week = get_current_vote_week()
                if user_daily_counts[user][today]>=5:
                    send_chat(sock, f"@{user} ❌ You've reached 5 votes today.")
                    continue
                existing = difflib.get_close_matches(raw.lower(), game_suggestions.keys(), n=1, cutoff=0.7)
                if existing:
                    key = existing[0]
                else:
                    steam = find_steam_link(raw)
                    if steam:
                        name, link = steam
                    else:
                        name, link = raw, None
                    key = name.lower()
                    if key not in game_suggestions:
                        game_suggestions[key] = {"name":name,"votes":0,"url":link,"user":user,"time":""}
                if user_votes[user].get(key)==week:
                    send_chat(sock, f"@{user} ❌ Already voted '{game_suggestions[key]['name']}' this week.")
                    continue
                game_suggestions[key]["votes"]+=1
                now_ts = get_current_pst_datetime().strftime("%I:%M %p, %b %d")
                game_suggestions[key]["user"]=user; game_suggestions[key]["time"]=now_ts
                user_votes[user][key]=week; user_daily_counts[user][today]+=1
                vote_history.append((key,user))
                write_vote_file()
                send_chat(sock, f"@{user} ✅ Vote for '{game_suggestions[key]['name']}' counted!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("💥 Unhandled error:", e)
        input("Press Enter to exit…")
