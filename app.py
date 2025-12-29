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

    # Photos (deduplicated)
    photos = get_photos(album_uid)
    photos_by_uid = {p["UID"]: p for p in photos}
    photo_list = list(photos_by_uid.values())

    random.shuffle(photo_list)

    # Remove odd image (no byes)
    if len(photo_list) % 2 == 1:
        photo_list = photo_list[:-1]

    total = len(photo_list)

    if total < 2:
        return "<h1>Not enough images to run a tournament.</h1><a href='/'>Back</a>"

    # State
    index = int(request.form.get("index", 0))
    winners = request.form.getlist("winners")
    round_num = int(request.args.get("round", 1))

    # STOP BUTTON HANDLER
    if request.method == "POST" and request.form.get("stop") == "1":
        if winners:
            base_title = base_album_title(album_title)
            new_title = f"{base_title} - Round {round_num} Winners"
            new_album_uid = create_album(new_title)
            add_photos_to_album(new_album_uid, winners)
        return redirect("/")

    # Winner submission
    if request.method == "POST" and "winner" in request.form:
        winners.append(request.form["winner"])
        index += 2

        if index >= total:
            # Round complete
            base_title = base_album_title(album_title)
            new_title = f"{base_title} - Round {round_num} Winners"
            new_album_uid = create_album(new_title)
            add_photos_to_album(new_album_uid, winners)

            return redirect(f"/tourney/{new_album_uid}?round={round_num + 1}")

    # Matchup
    left = photo_list[index]
    right = photo_list[index + 1]

    match_num = (index // 2) + 1
    total_matches = total // 2

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
      <input type="hidden" name="index" value="{{ index }}">
      {% for w in winners %}
        <input type="hidden" name="winners" value="{{ w }}">
      {% endfor %}
      <button style="background:#c33;color:white;padding:10px 20px;font-size:16px;">
        Stop & Save Round
      </button>
    </form>

    <form method="post">
      <input type="hidden" name="index" value="{{ index }}">
      {% for w in winners %}
        <input type="hidden" name="winners" value="{{ w }}">
      {% endfor %}

      <div class="matchup">
        <a href="#" onclick="this.closest('form').winner.value='{{ left.UID }}'; this.closest('form').submit(); return false;">
          <img src="{{ left_url }}">
        </a>

        <a href="#" onclick="this.closest('form').winner.value='{{ right.UID }}'; this.closest('form').submit(); return false;">
          <img src="{{ right_url }}">
        </a>
      </div>

      <input type="hidden" name="winner" value="">
    </form>
    """,
                                  album_title=album_title,
                                  round_num=round_num,
                                  match_num=match_num,
                                  total_matches=total_matches,
                                  index=index,
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
