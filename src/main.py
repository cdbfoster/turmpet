import json
import random
import sqlite3
import time

from flask import abort, escape, Flask, render_template, request, session


app = Flask(__name__, static_folder="")
app.secret_key = b'\x1d2\x8b\x87\r\xa2l\xb3\xc2y\xad+\n/\x03\xed'


class State:
    def __init__(self):
        self.next_id = 0
        self.cards = []
        self.used_cards = []
        self.current_pot = set()
        self.current_draw = None
        self.session = {}

    def __enter__(self):
        self.connection = sqlite3.connect("main.db")
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

        while True:
            try:
                self.cursor.execute('BEGIN EXCLUSIVE')
            except:
                time.sleep(0.1)
                continue
            break

        self.cursor.execute('create table if not exists objects (id integer primary key, name text not null default "", value text not null default "")')

        self.cursor.execute('select name, value from objects')
        objects = self.cursor.fetchall()
        if len(objects) == 0:
            self.cursor.execute('insert into objects (name, value) values ("next_id", "0")')
            self.cursor.execute('insert into objects (name, value) values ("cards", "[]")')
            self.cursor.execute('insert into objects (name, value) values ("used_cards", "[]")')
            self.cursor.execute('insert into objects (name, value) values ("current_pot", "[]")')
            self.cursor.execute('insert into objects (name, value) values ("current_draw", "null")')
            self.cursor.execute('select name, value from objects')
            objects = self.cursor.fetchall()

        def get_object(objects, name):
            for o in objects:
                if o["name"] == name:
                    return o

        session_name = "session_{}".format(session["user_id"])
        if get_object(objects, session_name) is None:
            self.cursor.execute('insert into objects (name, value) values (?, "{}")', [session_name])
            self.cursor.execute('select name, value from objects')
            objects = self.cursor.fetchall()

        self.next_id = json.loads(get_object(objects, "next_id")["value"])
        self.cards = json.loads(get_object(objects, "cards")["value"])
        self.used_cards = json.loads(get_object(objects, "used_cards")["value"])
        self.current_pot = set(json.loads(get_object(objects, "current_pot")["value"]))
        self.current_draw = json.loads(get_object(objects, "current_draw")["value"])
        self.session = json.loads(get_object(objects, session_name)["value"])

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.execute('update objects set value = ? where name = ?', [json.dumps(self.next_id), "next_id"])
        self.cursor.execute('update objects set value = ? where name = ?', [json.dumps(self.cards), "cards"])
        self.cursor.execute('update objects set value = ? where name = ?', [json.dumps(self.used_cards), "used_cards"])
        self.cursor.execute('update objects set value = ? where name = ?', [json.dumps(list(self.current_pot)), "current_pot"])
        self.cursor.execute('update objects set value = ? where name = ?', [json.dumps(self.current_draw), "current_draw"])
        self.cursor.execute('update objects set value = ? where name = ?', [json.dumps(self.session), "session_{}".format(session["user_id"])])

        self.connection.commit()
        self.connection.close()


@app.route("/", methods=["GET", "POST"])
def main():
    if "user_id" not in session and request.method == "POST":
        if request.form["password"].strip().lower() == "turmpet":
            session["user_id"] = int(1000000000 * random.random())

    return render_template("index.html", allowed="user_id" in session)


@app.route("/new_card", methods=["POST"])
def new():
    authenticate()

    with State() as state:
        text = request.json["text"].strip()
        if text != "":
            card = {
                "id": state.next_id,
                "text": escape(text)
            }

            state.next_id += 1;
            state.cards.append(card)
            state.current_pot.add(card["id"])

            user_submitted = state.session.get("submitted", [])
            user_submitted.append(card)
            state.session["submitted"] = user_submitted

        return render_state(state)


@app.route("/delete_card", methods=["POST"])
def delete():
    authenticate()

    with State() as state:
        card_id = request.json["id"]

        state.cards = [c for c in state.cards if c["id"] != card_id]
        state.used_cards = [c for c in state.used_cards if c["id"] != card_id]

        state.current_pot.discard(card_id)

        if state.current_draw is not None and state.current_draw["id"] == card_id:
            state.current_draw = None

        user_submitted = state.session.get("submitted", [])
        user_submitted = [s for s in user_submitted if s["id"] != card_id]
        state.session["submitted"] = user_submitted

        return render_state(state)


@app.route("/delete_all", methods=["POST"])
def delete_all():
    authenticate()

    with State() as state:
        state.cards = []
        state.used_cards = []
        state.current_pot = set()
        state.current_draw = None

        return render_state(state)


@app.route("/readd_card", methods=["POST"])
def readd():
    authenticate()

    with State() as state:
        card_id = request.json["id"]

        if card_id is not None:
            state.used_cards = [c for c in state.used_cards if c["id"] != card_id]
            state.current_pot.add(card_id)

            if state.current_draw is not None and state.current_draw["id"] == card_id:
                state.current_draw = None
        else:
            state.current_draw = None
            if state.session.get("draw", None) is not None:
                state.session["draw"] = None

        return render_state(state)


@app.route("/readd_all", methods=["POST"])
def readd_all():
    authenticate()

    with State() as state:
        state.used_cards = []
        state.current_pot = set([c["id"] for c in state.cards])
        state.current_draw = None

        return render_state(state)


@app.route("/draw_card", methods=["GET"])
def draw():
    authenticate()

    with State() as state:
        if state.current_draw is not None:
            state.used_cards.append(state.current_draw)
            state.current_pot.discard(state.current_draw["id"])
            state.session["turn_score"] = state.session.get("turn_score", 0) + 1
        else:
            state.session["turn_score"] = 0

        if len(state.current_pot) > 0:
            state.current_draw = random.choice([c for c in state.cards if c["id"] in state.current_pot])
            state.session["draw"] = state.current_draw
        else:
            state.current_draw = None
            state.session["draw"] = None

        return render_state(state)


@app.route("/current_state", methods=["GET"])
def current_state():
    authenticate()

    with State() as state:
        user_submitted = state.session.get("submitted", [])
        user_submitted = [s for s in user_submitted if any(True for c in state.cards if s["id"] == c["id"] and s["text"] == c["text"])]
        state.session["submitted"] = user_submitted

        if state.session.get("draw", None) is not None:
            if state.current_draw is None or state.session["draw"]["id"] != state.current_draw["id"] or state.session["draw"]["text"] != state.current_draw["text"]:
                state.session["draw"] = None

        return render_state(state)


def render_state(state):
    if state.session.get("draw", None) is not None:
        draw = state.session["draw"]
    elif state.current_draw is not None:
        draw = False
    else:
        draw = None

    return json.dumps({
        "remaining": len(state.current_pot),
        "total": len(state.cards),
        "draw": draw,
        "turn_score": state.session.get("turn_score", 0),
        "submitted": state.session.get("submitted", []),
        "used": state.used_cards,
    })


def authenticate():
    if "user_id" not in session:
        abort(403)