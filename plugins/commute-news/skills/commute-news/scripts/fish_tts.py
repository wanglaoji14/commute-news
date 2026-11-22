"""Render a solo or two-host script as one Fish Audio request."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VOICES = (
    "d738c70d206149e69f8e3b6fc8af9d96",  # Jin, radio host
    "297a6fd278df47c3b9da9bfdf55ac89a",  # Satoru
)


def render(dialogue, language, key, hosts=2):
    if hosts == 1:
        text = "\n\n".join(turn["text"] for turn in dialogue)
        reference_id = VOICES[0]
    else:
        text = "".join(f'<|speaker:{turn["host"] - 1}|>{turn["text"]}' for turn in dialogue)
        reference_id = VOICES
    payload = {
        "text": text,
        "reference_id": reference_id,
        "format": "mp3",
        "language": language,
        "latency": "normal",
    }
    request = Request("https://api.fish.audio/v1/tts",
                      json.dumps(payload, ensure_ascii=False).encode("utf-8"), {
                          "Authorization": f"Bearer {key}",
                          "Content-Type": "application/json",
                          "model": "s2.1-pro",
                      })
    try:
        with urlopen(request, timeout=180) as response:
            audio = response.read()
    except HTTPError as exc:
        errors = {401: "请在本机终端重新设置 Fish Audio API Key", 402: "请检查 Fish Audio API 余额",
                  403: "请检查 API Key 和音色权限", 429: "达到 Fish Audio 并发限制"}
        detail = errors.get(exc.code, "请检查模型、音色或服务状态")
        raise RuntimeError(f"Fish Audio 请求失败（HTTP {exc.code}）。{detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Fish Audio 请求超时或网络连接失败") from exc
    if not (audio.startswith(b"ID3") or
            len(audio) > 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0):
        raise RuntimeError("Fish Audio 未返回有效 MP3")
    return audio
