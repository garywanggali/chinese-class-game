import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, url_for


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
QA_PATH = DATA_DIR / "qa.json"


def load_qa() -> List[Dict[str, str]]:
  raw = json.loads(QA_PATH.read_text(encoding="utf-8"))
  qa: List[Dict[str, str]] = []
  seen = set()
  for item in raw:
    if not isinstance(item, dict):
      continue
    q = str(item.get("q", "")).strip()
    a = str(item.get("a", "")).strip()
    if not q or not a:
      continue
    key = (q, a)
    if key in seen:
      continue
    seen.add(key)
    qa.append({"q": q, "a": a})
  return qa


def now_ms() -> int:
  return int(time.time() * 1000)


@dataclass
class RoundState:
  round_id: str
  q: str
  options: List[str]
  correct_index: int
  started_at_ms: int
  duration_s: int
  ended_at_ms: Optional[int] = None
  # team -> {token -> (choice_index, answered_at_ms)}
  answers: Dict[str, Dict[str, Tuple[int, int]]] = field(default_factory=lambda: {"A": {}, "B": {}})
  # team -> {token -> points_awarded}
  points: Dict[str, Dict[str, int]] = field(default_factory=lambda: {"A": {}, "B": {}})


@dataclass
class GameState:
  qa: List[Dict[str, str]]
  teacher_key: str
  active_round: Optional[RoundState] = None
  team_score: Dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0})
  team_correct: Dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0})
  team_total: Dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0})
  # team -> token -> {nickname, joined_at_ms, last_seen_ms}
  roster: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=lambda: {"A": {}, "B": {}})
  last_event_id: int = 0


class EventBus:
  def __init__(self) -> None:
    self._lock = threading.Lock()
    self._subscribers: List[Queue] = []

  def subscribe(self) -> Queue:
    q: Queue = Queue()
    with self._lock:
      self._subscribers.append(q)
    return q

  def unsubscribe(self, q: Queue) -> None:
    with self._lock:
      if q in self._subscribers:
        self._subscribers.remove(q)

  def publish(self, event: Dict[str, Any]) -> None:
    with self._lock:
      subs = list(self._subscribers)
    for q in subs:
      q.put(event)


def create_app() -> Flask:
  app = Flask(__name__, static_folder="static", template_folder="templates")

  qa = load_qa()
  teacher_key = secrets.token_urlsafe(16)
  state = GameState(qa=qa, teacher_key=teacher_key)
  bus = EventBus()
  lock = threading.Lock()

  def emit(event_type: str, payload: Dict[str, Any]) -> None:
    with lock:
      state.last_event_id += 1
      eid = state.last_event_id
    bus.publish({"id": eid, "type": event_type, "payload": payload, "ts": now_ms()})

  def require_teacher() -> None:
    key = request.headers.get("X-Teacher-Key") or request.args.get("key") or request.cookies.get("teacher_key")
    if key != state.teacher_key:
      abort(403)

  def build_options(correct: str, n: int = 4) -> Tuple[List[str], int]:
    pool = [x["a"] for x in state.qa if x["a"] != correct]
    secrets.SystemRandom().shuffle(pool)
    distractors = pool[: max(0, n - 1)]
    options = [correct] + distractors
    secrets.SystemRandom().shuffle(options)
    return options, options.index(correct)

  def public_snapshot() -> Dict[str, Any]:
    with lock:
      r = state.active_round
      active = None
      if r:
        ends_at = r.started_at_ms + r.duration_s * 1000
        active = {
          "round_id": r.round_id,
          "q": r.q,
          "options": r.options,
          "started_at_ms": r.started_at_ms,
          "duration_s": r.duration_s,
          "ends_at_ms": ends_at,
          "ended_at_ms": r.ended_at_ms,
        }
        if r.ended_at_ms is not None:
          active["correct_index"] = r.correct_index
      return {
        "active_round": active,
        "team_score": dict(state.team_score),
        "team_correct": dict(state.team_correct),
        "team_total": dict(state.team_total),
        "roster": {
          "A": [v.get("nickname") for v in state.roster["A"].values()],
          "B": [v.get("nickname") for v in state.roster["B"].values()],
        },
      }

  def teacher_snapshot() -> Dict[str, Any]:
    snap = public_snapshot()
    with lock:
      r = state.active_round
      if r:
        snap["answers"] = {
          "A": {k: {"choice": v[0], "at_ms": v[1]} for k, v in r.answers["A"].items()},
          "B": {k: {"choice": v[0], "at_ms": v[1]} for k, v in r.answers["B"].items()},
        }
        snap["correct_index"] = r.correct_index
      else:
        snap["answers"] = {"A": {}, "B": {}}
      snap["roster_full"] = state.roster
    return snap

  def close_round_if_needed() -> None:
    ended_payload: Optional[Dict[str, Any]] = None
    with lock:
      r = state.active_round
      if not r or r.ended_at_ms is not None:
        return
      if now_ms() < r.started_at_ms + r.duration_s * 1000:
        return

      r.ended_at_ms = now_ms()

      round_summary: Dict[str, Any] = {
        "round_id": r.round_id,
        "correct_index": r.correct_index,
        "correct_text": r.options[r.correct_index] if 0 <= r.correct_index < len(r.options) else "",
        "teams": {"A": {"correct": [], "wrong": []}, "B": {"correct": [], "wrong": []}},
      }

      for team in ("A", "B"):
        # Team totals = number of distinct answer tokens
        state.team_total[team] += len(r.answers[team])
        for token, (choice, at_ms) in r.answers[team].items():
          is_correct = choice == r.correct_index
          nickname = (state.roster.get(team, {}).get(token, {}) or {}).get("nickname") or "匿名"
          if is_correct:
            state.team_correct[team] += 1
            dt = max(0, at_ms - r.started_at_ms)
            pts = max(100, 1000 - int(dt / 10))
            state.team_score[team] += pts
            r.points[team][token] = pts
            round_summary["teams"][team]["correct"].append({"name": nickname, "pts": pts})
          else:
            r.points[team][token] = 0
            round_summary["teams"][team]["wrong"].append({"name": nickname, "pts": 0})

      ended_payload = {"state": public_snapshot(), "round_summary": round_summary}

    emit("round_ended", ended_payload)

  def _round_watcher() -> None:
    while True:
      try:
        close_round_if_needed()
      except Exception:
        pass
      time.sleep(0.2)

  threading.Thread(target=_round_watcher, daemon=True).start()

  # --------- routes ----------

  @app.get("/")
  def root() -> Response:
    return redirect(url_for("join"))

  @app.get("/s")
  def join() -> Response:
    return Response(render_template("join.html"))

  @app.get("/s/")
  def join_slash() -> Response:
    return redirect(url_for("join"))

  @app.get("/teacher")
  def teacher() -> Response:
    # teacher key is kept server-side; we set it into a cookie for convenience on this machine
    resp = Response(render_template("teacher.html"))
    resp.set_cookie("teacher_key", state.teacher_key, httponly=False, samesite="Lax")
    return resp

  @app.get("/s/<team>")
  def student(team: str) -> Response:
    if team not in ("A", "B"):
      abort(404)
    return Response(render_template("student.html", team=team))

  @app.get("/api/state")
  def api_state() -> Response:
    close_round_if_needed()
    return jsonify(public_snapshot())

  @app.get("/api/teacher/state")
  def api_teacher_state() -> Response:
    require_teacher()
    close_round_if_needed()
    return jsonify(teacher_snapshot())

  @app.post("/api/teacher/reset")
  def api_teacher_reset() -> Response:
    require_teacher()
    with lock:
      state.team_score = {"A": 0, "B": 0}
      state.team_correct = {"A": 0, "B": 0}
      state.team_total = {"A": 0, "B": 0}
      state.active_round = None
      state.roster = {"A": {}, "B": {}}
    emit("reset", public_snapshot())
    return jsonify({"ok": True})

  @app.post("/api/join")
  def api_join() -> Response:
    body = request.get_json(silent=True) or {}
    team = str(body.get("team") or "").upper()
    token = str(body.get("token") or "")
    nickname = str(body.get("nickname") or "").strip()
    if team not in ("A", "B"):
      abort(400, "bad team")
    if not token or len(token) > 64:
      abort(400, "bad token")
    if not nickname:
      abort(400, "bad nickname")
    if len(nickname) > 20:
      nickname = nickname[:20]

    t = now_ms()
    with lock:
      state.roster.setdefault("A", {})
      state.roster.setdefault("B", {})
      # allow switching teams: remove from opposite team if exists
      other = "B" if team == "A" else "A"
      if token in state.roster.get(other, {}):
        del state.roster[other][token]
      existing = state.roster[team].get(token)
      joined_at = existing.get("joined_at_ms") if isinstance(existing, dict) else None
      state.roster[team][token] = {
        "nickname": nickname,
        "joined_at_ms": joined_at or t,
        "last_seen_ms": t,
      }

    emit("roster_updated", public_snapshot())
    return jsonify({"ok": True})

  @app.post("/api/teacher/start_round")
  def api_teacher_start_round() -> Response:
    require_teacher()
    body = request.get_json(silent=True) or {}
    duration_s = int(body.get("duration_s") or 15)
    duration_s = max(5, min(60, duration_s))
    with lock:
      if not state.qa:
        abort(400, "No questions")
      qa_item = secrets.choice(state.qa)
      options, correct_index = build_options(qa_item["a"], 4)
      r = RoundState(
        round_id=secrets.token_urlsafe(8),
        q=qa_item["q"],
        options=options,
        correct_index=correct_index,
        started_at_ms=now_ms(),
        duration_s=duration_s,
      )
      state.active_round = r
    emit("round_started", public_snapshot())
    return jsonify({"ok": True})

  @app.post("/api/answer")
  def api_answer() -> Response:
    close_round_if_needed()
    body = request.get_json(silent=True) or {}
    team = str(body.get("team") or "").upper()
    token = str(body.get("token") or "")
    choice = body.get("choice")
    if team not in ("A", "B"):
      abort(400, "bad team")
    if not token or len(token) > 64:
      abort(400, "bad token")
    if not isinstance(choice, int):
      abort(400, "bad choice")

    with lock:
      r = state.active_round
      if not r or r.ended_at_ms is not None:
        return jsonify({"ok": False, "reason": "no_active_round"})
      # bump last_seen if joined
      if token in state.roster.get(team, {}):
        state.roster[team][token]["last_seen_ms"] = now_ms()
      # time window
      if now_ms() > r.started_at_ms + r.duration_s * 1000:
        return jsonify({"ok": False, "reason": "round_ended"})
      # one answer per token per round
      if token in r.answers[team]:
        return jsonify({"ok": False, "reason": "already_answered"})
      if choice < 0 or choice >= len(r.options):
        abort(400, "choice range")
      r.answers[team][token] = (choice, now_ms())

    emit("answer_received", {"team": team})
    return jsonify({"ok": True})

  @app.get("/api/events")
  def api_events() -> Response:
    close_round_if_needed()
    q = bus.subscribe()

    def gen():
      try:
        # initial snapshot
        snap = public_snapshot()
        yield f"event: snapshot\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"
        while True:
          event = q.get()
          yield f"id: {event['id']}\n"
          yield f"event: {event['type']}\n"
          yield f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
      finally:
        bus.unsubscribe(q)

    return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})

  @app.get("/static/<path:filename>")
  def static_files(filename: str) -> Response:
    return send_from_directory(BASE_DIR / "static", filename)

  return app


app = create_app()


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

