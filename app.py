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


def create_album(title):
    token, _ = get_session()
    r = requests.post(
        f"{PHOTOPRISM_URL}/albums",
        headers={"X-Auth-Token": token},
        json={"Title": title},
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


# -------------------------------------------------
# Main Menu
# -------------------------------------------------

@app.route("/")
def index():
    albums = list_albums()
    return render_template_string("""
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


# -------------------------------------------------
# Tournament Route
# -------------------------------------------------

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

    # -------------------------------------------------
    # INITIAL ROUND SETUP (GET only)
    # -------------------------------------------------
    if request.method == "GET":
        photos = get_photos(album_uid)
        photos_by_uid = {p["UID"]: p for p in photos}
        remaining = list(photos_by_uid.keys())

        random.shuffle(remaining)

        # No byes
        if len(remaining) % 2 == 1:
            remaining = remaining[:-1]

        if len(remaining) < 2:
            return "<h1>Not enough images.</h1><a href='/'>Back</a>"

        winners = []

    # -------------------------------------------------
    # POST — state carried forward
    # -------------------------------------------------
    else:
        remaining = request.form.getlist("remaining")
        winners = request.form.getlist("winners")

        # STOP BUTTON
        if request.form.get("stop") == "1":
            if winners:
                base_title = base_album_title(album_title)
                new_title = f"{base_title} - Round {round_num} Winners"
                new_album_uid = create_album(new_title)
                add_photos_to_album(new_album_uid, winners)
            return redirect("/")

        # Winner chosen
        winner = request.form.get("winner")
        left = request.form.get("left")
        right = request.form.get("right")

        winners.append(winner)

        # Remove both competitors
        remaining = [r for r in remaining if r not in (left, right)]

        # Round complete
        if not remaining:
            base_title = base_album_title(album_title)
            new_title = f"{base_title} - Round {round_num} Winners"
            new_album_uid = create_album(new_title)
            add_photos_to_album(new_album_uid, winners)
            return redirect(f"/tourney/{new_album_uid}?round={round_num + 1}")

    # -------------------------------------------------
    # Current matchup
    # -------------------------------------------------
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
.matchup {
  display: flex;
  gap: 20px;
  justify-content: center;
  align-items: center;
  height: 85vh;
}
.matchup a {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
}
.matchup img {
  max-width: 100%;
  max-height: 85vh;
  object-fit: contain;
  cursor: pointer;
}
</style>

<h1>{{ album_title }}</h1>
<h3>Round {{ round_num }} — Match {{ match_num }} of {{ total_matches }}</h3>

<form method="post" style="margin-bottom:20px;">
  <input type="hidden" name="stop" value="1">
  {% for r in remaining %}
    <input type="hidden" name="remaining" value="{{ r }}">
  {% endfor %}
  {% for w in winners %}
    <input type="hidden" name="winners" value="{{ w }}">
  {% endfor %}
  <button style="background:#c33;color:white;padding:10px 20px;font-size:16px;">
    Stop & Save Round
  </button>
</form>

<form method="post">
  {% for r in remaining %}
    <input type="hidden" name="remaining" value="{{ r }}">
  {% endfor %}
  {% for w in winners %}
    <input type="hidden" name="winners" value="{{ w }}">
  {% endfor %}

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


# -------------------------------------------------
# Run App
# -------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
