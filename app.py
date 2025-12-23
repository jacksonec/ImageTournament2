import os, json, random, math, io, zipfile, shutil
from flask import (
    Flask, render_template_string, request, redirect,
    send_from_directory, send_file
)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BRACKETS_DIR = os.path.join(BASE_DIR, "brackets")
os.makedirs(BRACKETS_DIR, exist_ok=True)

app = Flask(__name__)

# -------------------------------------------------
# Helpers
# -------------------------------------------------

def bracket_path(name):
    return os.path.join(BRACKETS_DIR, name)

def images_path(name):
    return os.path.join(bracket_path(name), "images")

def state_path(name):
    return os.path.join(bracket_path(name), "state.json")

def init_state(image_dir):
    images = [
        f for f in os.listdir(image_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
    ]
    random.shuffle(images)
    n = len(images)
    return {
        "round": 1,
        "total_rounds": math.ceil(math.log2(n)) if n > 1 else 1,
        "queue": images,
        "winners": [],
        "current": [],
        "ranking": [],
        "round_history": [],
        "stopped": False
    }

def load_state(name):
    with open(state_path(name)) as f:
        return json.load(f)

def save_state(name, state):
    with open(state_path(name), "w") as f:
        json.dump(state, f, indent=2)

# -------------------------------------------------
# Main Menu
# -------------------------------------------------

@app.route("/")
def menu():
    brackets = sorted(
        d for d in os.listdir(BRACKETS_DIR)
        if os.path.isdir(bracket_path(d))
    )
    return render_template_string("""
<h1>Image Tournament</h1>

<a href="/new"><button>New Bracket</button></a>

<h2>Completed Brackets</h2>
<ul>
{% for b in brackets %}
  <li>
    <a href="/results/{{b}}">{{b}}</a>
    <form action="/delete/{{b}}" method="post" style="display:inline;">
      <button onclick="return confirm('Delete {{b}}?')">Delete</button>
    </form>
  </li>
{% endfor %}
</ul>
""", brackets=brackets)

# -------------------------------------------------
# New Bracket
# -------------------------------------------------

@app.route("/new")
def new_bracket():
    return render_template_string("""
<h1>New Bracket</h1>

<form action="/create" method="post" enctype="multipart/form-data">
  <label>Bracket name:</label><br>
  <input name="name" required><br><br>

  <label>Add images:</label><br>
  <input type="file" name="files" multiple accept="image/*"><br><br>

  <button type="submit">Go</button>
</form>

<a href="/">Cancel</a>
""")

@app.route("/create", methods=["POST"])
def create():
    name = secure_filename(request.form["name"])
    path = bracket_path(name)

    if os.path.exists(path):
        return "Bracket already exists", 400

    os.makedirs(images_path(name), exist_ok=True)

    for f in request.files.getlist("files"):
        if f.filename:
            f.save(os.path.join(images_path(name), secure_filename(f.filename)))

    state = init_state(images_path(name))
    save_state(name, state)

    return redirect(f"/play/{name}")

# -------------------------------------------------
# Tournament Play (FULL SCREEN PICKER)
# -------------------------------------------------

@app.route("/play/<name>")
def play(name):
    state = load_state(name)

    # Tournament finished naturally
    if not state["stopped"] and not state["current"]:
        total_remaining = len(state["queue"]) + len(state["winners"])
        if total_remaining == 1:
            # Commit final round if missing
            if not state["round_history"] or state["round_history"][-1]["round"] != state["round"]:
                final_winner = state["queue"] or state["winners"]
                state["round_history"].append({
                    "round": state["round"],
                    "winners": final_winner[:]
                })
            save_state(name, state)
            return redirect(f"/results/{name}")

    # Manual stop
    if state["stopped"]:
        save_state(name, state)
        return redirect(f"/results/{name}")


    if not state["current"]:
        if len(state["queue"]) >= 2:
            state["current"] = state["queue"][:2]
            state["queue"] = state["queue"][2:]
        elif len(state["queue"]) == 1:
            state["winners"].append(state["queue"].pop())
        else:
            if len(state["winners"]) > 1:
                state["round_history"].append({
                    "round": state["round"],
                    "winners": state["winners"][:]
                })
                state["queue"] = state["winners"]
                random.shuffle(state["queue"])
                state["winners"] = []
                state["round"] += 1
            else:
                state["queue"] = state["winners"]
                state["winners"] = []

        save_state(name, state)
        return redirect(f"/play/{name}")

    left, right = state["current"]
    remaining = len(state["queue"]) + len(state["winners"]) + 2

    return render_template_string("""
<!doctype html>
<html>
<head>
<title>Image Tournament</title>
<style>
body {
  margin: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #111;
  color: white;
}

form.images {
  flex: 1;
  display: flex;
}

button.pick {
  flex: 1;
  border: none;
  background: black;
  padding: 0;
}

button.pick img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
</style>
</head>
<body>

<header>
  <div>Round {{r}} of {{tr}} — {{rem}} remaining</div>
  <form action="/stop/{{name}}" method="post">
    <button>Stop</button>
  </form>
</header>

<form class="images" method="post">
  <button class="pick" name="winner" value="{{left}}">
    <img src="/image/{{name}}/{{left}}">
  </button>
  <button class="pick" name="winner" value="{{right}}">
    <img src="/image/{{name}}/{{right}}">
  </button>
</form>

</body>
</html>
""", left=left, right=right, r=state["round"],
   tr=state["total_rounds"], rem=remaining, name=name)

@app.route("/play/<name>", methods=["POST"])
def vote(name):
    state = load_state(name)
    left, right = state["current"]
    winner = request.form["winner"]
    loser = right if winner == left else left
    state["winners"].append(winner)
    state["ranking"].insert(0, loser)
    state["current"] = []
    save_state(name, state)
    return redirect(f"/play/{name}")

@app.route("/stop/<name>", methods=["POST"])
def stop(name):
    state = load_state(name)
    state["stopped"] = True
    save_state(name, state)
    return redirect(f"/results/{name}")

# -------------------------------------------------
# Results
# -------------------------------------------------

@app.route("/results/<name>")
def results(name):
    state = load_state(name)
    return render_template_string("""
<h1>Results: {{name}}</h1>

<div style="display:flex; flex-wrap:wrap;">
{% for r in state.round_history %}
  <div style="margin:10px; width:100%;">
    <h3>Round {{r.round}}</h3>
    {% for img in r.winners %}
      <a href="/image/{{name}}/{{img}}" target="_blank">
        <img src="/image/{{name}}/{{img}}" width="120">
      </a>
    {% endfor %}
    <form action="/download/{{name}}/{{r.round}}">
      <button>Download</button>
    </form>
  </div>
{% endfor %}
</div>

<a href="/"><button>Exit</button></a>
""", state=state, name=name)

# -------------------------------------------------
# Downloads / Images / Delete
# -------------------------------------------------

@app.route("/download/<name>/<int:round>")
def download(name, round):
    state = load_state(name)
    winners = state["round_history"][round - 1]["winners"]

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for f in winners:
            root, ext = os.path.splitext(f)
            renamed = f"{root}-round{round}{ext}"
            z.write(os.path.join(images_path(name), f), renamed)

    mem.seek(0)
    return send_file(
        mem,
        download_name=f"{name}_round_{round}.zip",
        as_attachment=True
    )

@app.route("/image/<name>/<file>")
def image(name, file):
    return send_from_directory(images_path(name), file)

@app.route("/delete/<name>", methods=["POST"])
def delete(name):
    shutil.rmtree(bracket_path(name), ignore_errors=True)
    return redirect("/")

# -------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
