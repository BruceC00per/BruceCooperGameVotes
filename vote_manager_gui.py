import tkinter as tk
from tkinter import messagebox
import json
import subprocess
import os
from datetime import datetime
from twitch_vote_bot import write_vote_file  # ✅ uses original HTML template

VOTES_JSON = "votes.json"
REFRESH_INTERVAL = 5000  # ms

def load_votes():
    if not os.path.exists(VOTES_JSON):
        return {}
    try:
        with open(VOTES_JSON, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return {v["name"].lower(): v for v in raw}
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load votes: {e}")
        return {}

def save_votes(votes):
    arr = sorted(votes.values(), key=lambda v: v["votes"], reverse=True)
    with open(VOTES_JSON, "w", encoding="utf-8") as f:
        json.dump(arr, f, indent=2)

class VoteManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Game Vote Manager")
        self.root.geometry("740x600")

        # Add Game Section
        self.add_frame = tk.Frame(root)
        self.add_frame.pack(pady=10)

        tk.Label(self.add_frame, text="Game Name:").pack(side=tk.LEFT)
        self.game_entry = tk.Entry(self.add_frame, width=30)
        self.game_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(self.add_frame, text="Store Link (optional):").pack(side=tk.LEFT)
        self.link_entry = tk.Entry(self.add_frame, width=30)
        self.link_entry.pack(side=tk.LEFT, padx=5)

        tk.Button(self.add_frame, text="➕ Add Game", command=self.add_game).pack(side=tk.LEFT, padx=5)

        # Vote List
        self.games_frame = tk.Frame(root)
        self.games_frame.pack(fill=tk.BOTH, expand=True)

        # Buttons
        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=10)

        tk.Button(self.button_frame, text="🔄 Refresh", command=self.refresh_list).pack(side=tk.LEFT, padx=5)
        tk.Button(self.button_frame, text="💾 Save & Push", command=self.save_and_push).pack(side=tk.LEFT, padx=5)

        self.refresh_list()
        self.auto_refresh()

    def refresh_list(self):
        self.game_suggestions = load_votes()

        for w in self.games_frame.winfo_children():
            w.destroy()

        headers = [("Game", 30), ("Votes", 10), ("Action", 15)]
        for idx, (txt, width) in enumerate(headers):
            tk.Label(self.games_frame, text=txt, width=width, anchor="w", font=("Helvetica", 12, "bold")).grid(row=0, column=idx, padx=10, pady=5)

        for row, (key, info) in enumerate(sorted(self.game_suggestions.items(), key=lambda kv: kv[1]["votes"], reverse=True), start=1):
            tk.Label(self.games_frame, text=info["name"], width=30, anchor="w").grid(row=row, column=0, padx=10, pady=3)
            tk.Label(self.games_frame, text=str(info["votes"]), width=10).grid(row=row, column=1)
            tk.Button(self.games_frame, text="❌ Remove", command=lambda k=key: self.remove_vote(k)).grid(row=row, column=2, padx=5)

    def remove_vote(self, key):
        votes = load_votes()
        if key in votes:
            votes[key]["votes"] -= 1
            if votes[key]["votes"] <= 0:
                del votes[key]
            save_votes(votes)
        self.refresh_list()

    def add_game(self):
        name = self.game_entry.get().strip()
        link = self.link_entry.get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Please enter a game name.")
            return

        votes = load_votes()
        key = name.lower()
        now_str = datetime.now().strftime("%I:%M %p, %b %d")

        if key in votes:
            votes[key]["votes"] += 1
        else:
            votes[key] = {
                "name": name,
                "votes": 1,
                "url": link if link else None,
                "user": "Manual",
                "time": now_str
            }

        save_votes(votes)
        self.game_entry.delete(0, tk.END)
        self.link_entry.delete(0, tk.END)
        self.refresh_list()

    def save_and_push(self):
        try:
            write_vote_file()  # ✅ uses original template!
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "Vote update from GUI"], check=True)
            subprocess.run(["git", "push"], check=True)
            messagebox.showinfo("Success", "Changes saved and pushed.")
        except subprocess.CalledProcessError:
            messagebox.showwarning("Warning", "Nothing to commit or push failed.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def auto_refresh(self):
        self.refresh_list()
        self.root.after(REFRESH_INTERVAL, self.auto_refresh)

if __name__ == "__main__":
    root = tk.Tk()
    app = VoteManagerApp(root)
    root.mainloop()
