import random
import re
import requests
from flask import Flask, render_template_string, redirect, request

app = Flask(__name__)

PHOTOPRISM_URL = "http://beckimemory.jackson.terf/api/v1"
USERNAME = "admin"
APP_PASSWORD = "SOth134!#$"

ROUND_SUFFIX_RE = re.compile(r"\s+-\s+Round\s+\d+\s+Winners$")


def base_album_title(title: str) -> str:
    return ROUND_SUFFIX_RE.sub("", title)


# -------------------------------------------------
# PhotoPrism Helpers
# -------------------------------------------------

def get_session():
    resp = requests.post(
        f"{PHOTOPRISM_URL}/session",
        json={"username": USERNAME, "password": APP_PASSWORD},
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["config"]["downloadToken"]


def list_albums():
    token, _ = get_session()
    r = requests.get(
        f"{PHOTOPRISM_URL}/albums",
        headers={"X-Auth-Token": token},
        params={"count": 200, "order": "name", "include": "metadata", "type": "album"},
    )
    r.raise_for_status()
    return sorted(r.json(), key=lambda a: a["Title"])


def get_photos(album_uid):
    token, _ = get_session()
    r = requests.get(
        f"{PHOTOPRISM_URL}/photos",
        headers={"X-Auth-Token": token},
        params={"count": 5000, "s": album_uid},
    )
    r.raise_for_status()
    return r.json()


def create_album(title, thumb_uid=None):
    token, _ = get_session()
    payload = {"Title": title}
    if thumb_uid:
        payload["Thumb"] = thumb_uid
        
    r = requests.post(
        f"{PHOTOPRISM_URL}/albums",
        headers={"X-Auth-Token": token},
        json=payload,
    )
    r.raise_for_status()
    return r.json()["UID"]


def add_photos_to_album(album_uid, photo_uids):
    token, _ = get_session()
    for uid in photo_uids:
        r = requests.post(
            f"{PHOTOPRISM_URL}/albums/{album_uid}/photos",
            headers={"X-Auth-Token": token},
            json={"photos": [uid]},
        )
        r.raise_for_status()

def bulk_create_albums_logic(titles_string):
    token, _ = get_session()
    titles = [t.strip() for t in titles_string.split('\n') if t.strip()]
    results = []
    for title in titles:
        try:
            r = requests.post(
                f"{PHOTOPRISM_URL}/albums",
                headers={"X-Auth-Token": token},
                json={"Title": title},
            )
            r.raise_for_status()
            results.append(f"Created: {title}")
        except Exception as e:
            results.append(f"Error creating '{title}': {str(e)}")
    return results


# -------------------------------------------------
# Routes
# -------------------------------------------------

@app.route("/")
def index():
    albums = list_albums()
    return render_template_string("""
<nav style="margin-bottom: 20px; padding: 10px; background: #eee;">
    <strong>Navigation:</strong> 
    <a href="/bulk-albums">Bulk Album Creator</a>
</nav>
<h1>PhotoPrism Image Tournament</h1>
<ul>
{% for a in albums %}
  <li>
    {{ a.Title }}
    <a href="/tourney/{{ a.UID }}"><button>Image Tournament</button></a>
  </li>
{% endfor %}
</ul>
""", albums=albums)


@app.route("/bulk-albums", methods=["GET", "POST"])
def bulk_albums():
    logs = []
    if request.method == "POST":
        album_blob = request.form.get("album_list", "")
        if album_blob:
            logs = bulk_create_albums_logic(album_blob)

    return render_template_string("""
<nav style="margin-bottom: 20px; padding: 10px; background: #eee;">
    <strong>Navigation:</strong> 
    <a href="/">Back to Tournament List</a>
</nav>
<h1>Bulk Create Albums</h1>
<p>Paste album names (one per line):</p>
<form method="post">
    <textarea name="album_list" style="width:100%; height:300px;" placeholder="Album Name 1&#10;Album Name 2"></textarea>
    <br><br>
    <button type="submit" style="padding:10px 20px; cursor:pointer;">Create All Albums</button>
</form>

{% if logs %}
<div style="margin-top:20px; border:1px solid #ccc; padding:10px; font-family:monospace;">
    <h3>Results:</h3>
    {% for log in logs %}
        <div style="color: {{ 'red' if 'Error' in log else 'green' }}">{{ log }}</div>
    {% endfor %}
</div>
{% endif %}
""", logs=logs)


@app.route("/tourney/<album_uid>", methods=["GET", "POST"])
def tourney(album_uid):
    access_token, download_token = get_session()

    # Album info
    r = requests.get(
        f"{PHOTOPRISM_URL}/albums/{album_uid}",
        headers={"X-Auth-Token": access_token},
    )
    r.raise_for_status()
    album = r.json()
    album_title = album["Title"]

    round_num = int(request.args.get("round", 1))

    if request.method == "GET":
        photos = get_photos(album_uid)
        photos_by_uid = {p["UID"]: p for p in photos}
        remaining = list(photos_by_uid.keys())
        random.shuffle(remaining)
        if len(remaining) % 2 == 1:
            remaining = remaining[:-1]
        if len(remaining) < 2:
            return "<h1>Not enough images.</h1><a href='/'>Back</a>"
        winners = []
    else:
        remaining = request.form.getlist("remaining")
        winners = request.form.getlist("winners")

        if request.form.get("stop") == "1":
            if winners:
                base_title = base_album_title(album_title)
                new_title = f"{base_title} - Round {round_num} Winners"
                
                # Get the thumb from the original album
                original_thumb = album.get("Thumb") 
                new_album_uid = create_album(new_title, thumb_uid=original_thumb)
                
                add_photos_to_album(new_album_uid, winners)
            return redirect("/")

        winner = request.form.get("winner")
        left = request.form.get("left")
        right = request.form.get("right")
        winners.append(winner)
        remaining = [r for r in remaining if r not in (left, right)]

        if not remaining:
            base_title = base_album_title(album_title)
            new_title = f"{base_title} - Round {round_num} Winners"
            
            # Get the thumb from the original album
            original_thumb = album.get("Thumb")
            new_album_uid = create_album(new_title, thumb_uid=original_thumb)
            
            add_photos_to_album(new_album_uid, winners)
            return redirect(f"/tourney/{new_album_uid}?round={round_num + 1}")

    left_uid, right_uid = remaining[0], remaining[1]
    photos = get_photos(album_uid)
    photo_map = {p["UID"]: p for p in photos}
    left = photo_map[left_uid]
    right = photo_map[right_uid]

    match_num = (len(winners) + 1)
    total_matches = (len(remaining) + len(winners) * 2) // 2

    left_url = f"{PHOTOPRISM_URL}/dl/{left['Hash']}?t={download_token}"
    right_url = f"{PHOTOPRISM_URL}/dl/{right['Hash']}?t={download_token}"

    return render_template_string("""
<style>
.matchup { display: flex; gap: 20px; justify-content: center; align-items: center; height: 85vh; }
.matchup a { flex: 1; display: flex; justify-content: center; align-items: center; }
.matchup img { max-width: 100%; max-height: 85vh; object-fit: contain; cursor: pointer; }
</style>
<nav style="padding: 10px; background: #eee;">
    <a href="/">← Exit Tournament</a> | <a href="/bulk-albums">Bulk Album Creator</a>
</nav>

<h1>{{ album_title }}</h1>
<h3>Round {{ round_num }} — Match {{ match_num }} of {{ total_matches }}</h3>

<form method="post" style="margin-bottom:20px;">
  <input type="hidden" name="stop" value="1">
  {% for r in remaining %}<input type="hidden" name="remaining" value="{{ r }}">{% endfor %}
  {% for w in winners %}<input type="hidden" name="winners" value="{{ w }}">{% endfor %}
  <button style="background:#c33;color:white;padding:10px 20px;font-size:16px;">Stop & Save Round</button>
</form>

<form method="post">
  {% for r in remaining %}<input type="hidden" name="remaining" value="{{ r }}">{% endfor %}
  {% for w in winners %}<input type="hidden" name="winners" value="{{ w }}">{% endfor %}
  <input type="hidden" name="left" value="{{ left.UID }}">
  <input type="hidden" name="right" value="{{ right.UID }}">
  <input type="hidden" name="winner" value="">
  <div class="matchup">
    <a href="#" onclick="this.closest('form').winner.value='{{ left.UID }}'; this.closest('form').submit(); return false;">
      <img src="{{ left_url }}">
    </a>
    <a href="#" onclick="this.closest('form').winner.value='{{ right.UID }}'; this.closest('form').submit(); return false;">
      <img src="{{ right_url }}">
    </a>
  </div>
</form>
""",
        album_title=album_title,
        round_num=round_num,
        match_num=match_num,
        total_matches=total_matches,
        remaining=remaining,
        winners=winners,
        left=left,
        right=right,
        left_url=left_url,
        right_url=right_url,
    )

if __name__ == "__main__":
    app.run(debug=True)
