"""Create, publish to, and serve a local Commute News library."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import formatdate
import fcntl
import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import speech_models


AUDIO_TYPES = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}
DEFAULT_PORT = 18781
LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_atomic(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def locked(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def default_host():
    try:
        local_name = subprocess.check_output(
            ["/usr/sbin/scutil", "--get", "LocalHostName"], text=True,
            stderr=subprocess.DEVNULL, timeout=3,
        ).strip()
        if local_name:
            return local_name + ".local"
    except (OSError, subprocess.SubprocessError):
        pass
    return socket.gethostname()


def library_settings(root):
    try:
        settings = read_json(root / "library.json")
        if "feed_id" not in settings:
            settings["feed_id"] = settings.pop("token")
        return settings
    except FileNotFoundError as error:
        raise ValueError("请先选择语音模型，然后运行 setup 初始化播客库。") from error


def language_tag(tag):
    if not isinstance(tag, str) or not LANGUAGE_TAG.fullmatch(tag):
        raise ValueError("请使用语言代码，例如 ja、en、zh-CN。")
    return tag


def feed_base(settings):
    return f'http://{settings["host"]}:{settings["port"]}/p/{settings["feed_id"]}'


def update_library(root, args):
    path = root / "library.json"
    with locked(root):
        settings = library_settings(root) if path.exists() else {
            "language": "ja", "title": "Commute News",
            "port": DEFAULT_PORT, "host": default_host(),
            "feed_id": uuid4().hex,
        }
        changes = {name: getattr(args, name) for name in ("language", "hosts", "title", "port", "host", "model")}
        settings.update({name: value for name, value in changes.items() if value is not None})
        if not path.exists() and "model" not in settings:
            raise ValueError("请选择语音模型。运行 models 查看列表，再给 setup 传入 --model。")
        language_tag(settings["language"])
        if not HOST.fullmatch(settings["host"]) or not 1 <= settings["port"] <= 65535:
            raise ValueError("请填写可由手机访问的电脑主机名或 IPv4 地址及有效端口。")
        if not settings["title"].strip():
            raise ValueError("节目名称不能为空。")
        (root / "episodes").mkdir(exist_ok=True)
        write_atomic(path, json.dumps(settings, ensure_ascii=False).encode())
        update_feed(root, settings)
    return library_status(root, settings)


def library_status(root, settings):
    model = settings.get("model", "fish")
    profile = settings.get("profile", {})
    episodes = sorted((read_json(path) for path in (root / "episodes").glob("*/episode.json")),
                      key=lambda episode: episode["published"], reverse=True)
    today, episode_id = daily_slot(profile)
    return {
        "library": str(root), "language": settings["language"], "title": settings["title"],
        "hosts": settings.get("hosts", 2),
        "rss": feed_base(settings) + "/feed.xml",
        "model": model, "model_name": speech_models.MODELS[model]["name"],
        "key_configured": bool(configured_key(root, model)),
        "profile": profile, "local_date": today,
        "daily_published": (root / "episodes" / episode_id / "episode.json").is_file(),
        "recent_titles": [episode["title"] for episode in episodes[:7]],
    }


def set_preference(root, name, value):
    with locked(root):
        settings = library_settings(root)
        settings[name] = value
        write_atomic(root / "library.json", json.dumps(settings, ensure_ascii=False).encode())
        update_feed(root, settings)
    return library_status(root, settings)


def set_profile(root, changes):
    if not isinstance(changes, dict) or changes.keys() - {"topics", "less", "timezone", "time"}:
        raise ValueError("偏好只接受 topics、less、timezone 和 time。")
    for name in ("topics", "less"):
        if name not in changes:
            continue
        labels = changes[name]
        if (not isinstance(labels, list) or len(labels) > 20
                or any(not isinstance(label, str) or not 1 <= len(label.strip()) <= 100 for label in labels)):
            raise ValueError(f"{name} 必须是最多 20 个简短主题的列表。")
        changes[name] = list(dict.fromkeys(label.strip() for label in labels))
    if "timezone" in changes:
        try:
            ZoneInfo(changes["timezone"])
        except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
            raise ValueError("请输入有效时区，例如 Asia/Tokyo。") from error
    if "time" in changes and (not isinstance(changes["time"], str)
                              or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", changes["time"])):
        raise ValueError("时间请用 HH:MM 格式，例如 06:30。")
    with locked(root):
        settings = library_settings(root)
        settings["profile"] = {**settings.get("profile", {}), **changes}
        write_atomic(root / "library.json", json.dumps(settings, ensure_ascii=False).encode())
    return library_status(root, settings)


def daily_slot(profile):
    zone = ZoneInfo(profile["timezone"]) if "timezone" in profile else None
    day = datetime.now(zone).date().isoformat()
    return day, hashlib.sha256(f"daily:{day}".encode()).hexdigest()[:32]


def update_feed(root, settings):
    base = feed_base(settings)
    rss = ET.Element("rss", {
        "version": "2.0", "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:dc": "http://purl.org/dc/elements/1.1/",
    })
    channel = ET.SubElement(rss, "channel")
    for name, value in (
        ("title", settings["title"]), ("link", base + "/feed.xml"),
        ("description", "Personal commute news"), ("language", settings["language"]),
        ("itunes:block", "yes"),
    ):
        ET.SubElement(channel, name).text = value
    episodes = [read_json(path) for path in (root / "episodes").glob("*/episode.json")]
    for episode in sorted(episodes, key=lambda ep: ep["published"], reverse=True):
        item = ET.SubElement(channel, "item")
        for name, value in (
            ("title", episode["title"]), ("description", episode["notes"]),
            ("pubDate", formatdate(episode["published"], usegmt=True)),
            ("dc:language", episode["language"]),
        ):
            ET.SubElement(item, name).text = value
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = episode["id"]
        extension = episode.get("audio_format", "mp3")
        ET.SubElement(item, "enclosure", {
            "url": f'{base}/{episode["id"]}.{extension}',
            "length": str(episode["bytes"]), "type": AUDIO_TYPES[extension],
        })
    write_atomic(root / "feed.xml", ET.tostring(rss, encoding="utf-8", xml_declaration=True))


def configured_key(root, model):
    key = os.environ.get(speech_models.MODELS[model]["key_env"], "").strip()
    if key:
        return key
    try:
        return (root / f".{model}-key").read_text().strip()
    except FileNotFoundError:
        return ""


def set_key(root, model):
    name = speech_models.MODELS[model]["name"]
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError("请在你自己的终端运行 key，粘贴密钥时输入会隐藏。")
    key = getpass.getpass(f"{name} API Key：").strip()
    if not key or not key.isascii() or any(char.isspace() for char in key):
        raise ValueError("API Key 不能为空或包含空白字符。")
    write_atomic(root / f".{model}-key", key.encode())
    return {"model": model, "key_configured": True}


def validate_draft(draft, settings):
    if not isinstance(draft, dict):
        raise ValueError("播客稿必须是 JSON 对象。")
    title = draft.get("title")
    notes = draft.get("notes", "")
    dialogue = draft.get("dialogue")
    hosts = draft.get("hosts", settings.get("hosts", 2))
    if type(hosts) is not int or hosts not in (1, 2):
        raise ValueError("请选择单人或双人节目（hosts 为 1 或 2）。")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise ValueError("标题必须包含 1–200 个字符。")
    if not isinstance(notes, str) or len(notes) > 6000:
        raise ValueError("节目简介必须是最多 6000 字符的文本。")
    if not isinstance(dialogue, list) or not hosts <= len(dialogue) <= 80:
        raise ValueError(f"请提供 {hosts}–80 段台词。")
    turns = []
    for turn in dialogue:
        if not isinstance(turn, dict) or type(turn.get("host")) is not int or turn["host"] not in (1, 2):
            raise ValueError("每轮对话的 host 必须是 1 或 2。")
        line = turn.get("text")
        if not isinstance(line, str) or not 1 <= len(line.strip()) <= 300 or "<|speaker:" in line:
            raise ValueError("每轮正文必须包含 1–300 个字符，且不带说话人标记。")
        turns.append({"host": turn["host"], "text": line.strip()})
    if {turn["host"] for turn in turns} != set(range(1, hosts + 1)):
        raise ValueError("台词里的主持人必须和节目选择的主持人数一致。")
    if sum(len(turn["text"]) for turn in turns) > 10000:
        raise ValueError("正文最多 10000 个字符。")
    return {
        "title": title.strip(), "notes": notes.strip(), "dialogue": turns,
        "language": language_tag(draft.get("language", settings["language"])), "hosts": hosts,
    }


def publish(root, draft, daily=False):
    with locked(root):
        settings = library_settings(root)
        episode = validate_draft(draft, settings)
        model = settings.get("model", "fish")
        day = None
        if daily:
            profile = settings.get("profile", {})
            if not profile.get("topics") or not profile.get("timezone"):
                raise ValueError("请先确认新闻方向和时区，再生成每日节目。")
            day, episode_id = daily_slot(profile)
        else:
            identity = [episode["title"], episode["language"], episode["dialogue"]]
            if model != "fish":
                identity.append(model)
            episode_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:32]
        destination = root / "episodes" / episode_id
        reused = destination.exists()
        if not reused:
            key = configured_key(root, model)
            if not key:
                name = speech_models.MODELS[model]["name"]
                raise ValueError(f"请先在终端运行 key 配置 {name}。")
            audio, extension = speech_models.render(model, episode["dialogue"], episode["language"], key, episode["hosts"])
            episode.update(id=episode_id, published=datetime.now(timezone.utc).timestamp(), bytes=len(audio),
                           model=model, audio_format=extension)
            if daily:
                episode["day"] = day
            with tempfile.TemporaryDirectory(prefix=".pending-", dir=destination.parent) as temp:
                stage = Path(temp) / "episode"
                stage.mkdir()
                (stage / f"episode.{extension}").write_bytes(audio)
                (stage / "episode.json").write_text(json.dumps(episode, ensure_ascii=False), encoding="utf-8")
                stage.rename(destination)
        else:
            episode = read_json(destination / "episode.json")
            extension = episode.get("audio_format", "mp3")
            model = episode.get("model", model)
        update_feed(root, settings)
    return {
        "title": episode["title"], "id": episode_id, "language": episode["language"], "reused": reused,
        "hosts": episode.get("hosts", 2), "day": day, "model": model, "audio": str(destination / f"episode.{extension}"),
        "rss": feed_base(settings) + "/feed.xml",
    }


class FeedHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        root = self.server.library
        settings = library_settings(root)
        prefix = f'/p/{settings["feed_id"]}/'
        if not path.startswith(prefix):
            self.send_error(404)
            return
        file_name = path[len(prefix):]
        if file_name == "feed.xml":
            file_path = root / "feed.xml"
            media = "application/rss+xml; charset=utf-8"
        elif re.fullmatch(r"[a-f0-9]{32}\.(mp3|m4a)", file_name):
            episode_id, extension = file_name.split(".")
            file_path = root / "episodes" / episode_id / f"episode.{extension}"
            media = AUDIO_TYPES[extension]
        else:
            self.send_error(404)
            return
        try:
            data = file_path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_bytes(data, media)

    do_HEAD = do_GET

    def send_bytes(self, data, media):
        size = len(data)
        start, end = 0, size - 1
        seek = media in AUDIO_TYPES.values()
        byte_range = self.headers.get("Range") if seek else None
        if byte_range:
            match = re.fullmatch(r"bytes=(\d{0,18})-(\d{0,18})", byte_range)
            if not match or not any(match.groups()):
                start = size
            else:
                first, last = match.groups()
                start = int(first) if first else max(0, size - int(last))
                end = min(end, int(last)) if first and last else end
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if byte_range else 200)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "private, max-age=86400" if seek else "private, no-cache")
        if seek:
            self.send_header("Accept-Ranges", "bytes")
        if byte_range:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data[start:end + 1])


def serve(root):
    settings = library_settings(root)
    with ThreadingHTTPServer(("", settings["port"]), FeedHandler) as server:
        server.library = root
        print(feed_base(settings) + "/feed.xml", flush=True)
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=Path.home() / "Documents" / "Commute News")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("init", "setup"):
        initialize = commands.add_parser(action)
        initialize.add_argument("--language")
        initialize.add_argument("--hosts", type=int, choices=(1, 2))
        initialize.add_argument("--model", choices=speech_models.MODELS)
        initialize.add_argument("--title")
        initialize.add_argument("--port", type=int)
        initialize.add_argument("--host")
    commands.add_parser("models").add_argument("--language", default="ja")
    commands.add_parser("model").add_argument("id", choices=speech_models.MODELS)
    commands.add_parser("status")
    commands.add_parser("profile", help="Update confirmed news preferences from a JSON object on standard input")
    commands.add_parser("language").add_argument("tag")
    commands.add_parser("hosts").add_argument("count", type=int, choices=(1, 2))
    commands.add_parser("key")
    publish_parser = commands.add_parser("publish", help="Read a dialogue JSON object from standard input")
    publish_parser.add_argument("--daily", action="store_true", help="Publish at most one daily episode per local date")
    commands.add_parser("serve")
    args = parser.parse_args()
    root = args.library.expanduser().resolve()
    try:
        if args.action in ("init", "setup"):
            result = update_library(root, args)
            if args.action == "setup" and not result["key_configured"]:
                set_key(root, result["model"])
                result["key_configured"] = True
        elif args.action == "models":
            result = speech_models.choices(language_tag(args.language))
        elif args.action == "model":
            result = set_preference(root, "model", args.id)
        elif args.action == "status":
            result = library_status(root, library_settings(root))
        elif args.action == "profile":
            result = set_profile(root, json.load(sys.stdin))
        elif args.action == "language":
            result = set_preference(root, "language", language_tag(args.tag))
        elif args.action == "hosts":
            result = set_preference(root, "hosts", args.count)
        elif args.action == "key":
            result = set_key(root, library_settings(root).get("model", "fish"))
        elif args.action == "publish":
            result = publish(root, json.load(sys.stdin), daily=args.daily)
        else:
            serve(root)
            return
        print(json.dumps(result, ensure_ascii=False))
    except KeyboardInterrupt:
        return
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
