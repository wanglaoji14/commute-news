"""Model choices and speech synthesis for the local podcast."""
import base64
import binascii
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
import wave

import fish_tts

MODELS = {
    "fish": {"name": "Fish Audio S2.1 Pro", "language": "ja", "key_env": "FISH_API_KEY",
             "key_url": "https://fish.audio/app/api-keys"},
    "doubao": {"name": "豆包语音合成 2.0", "language": "zh", "key_env": "DOUBAO_TTS_API_KEY",
               "key_url": "https://console.volcengine.com/speech/"},
    "elevenlabs": {"name": "ElevenLabs Eleven v4", "language": "en", "key_env": "ELEVENLABS_API_KEY",
                   "key_url": "https://elevenlabs.io/app/developers/api-keys"},
}
DOUBAO_VOICES = ("zh_male_cixingjieshuonan_uranus_bigtts", "zh_female_vv_uranus_bigtts")
ELEVEN_VOICES = ("6WwXjDDEMyNmFG95zycZ", "jSuBIjxMKhqIfb0wCK1F")
AFCONVERT = "/usr/bin/afconvert"


def choices(language):
    primary = language.lower().split("-")[0]
    return [{"id": model, **details, "recommended": details["language"] == primary}
            for model, details in MODELS.items()]


def json_request(url, payload, headers):
    return Request(url, json.dumps(payload, ensure_ascii=False).encode(),
                   {**headers, "Content-Type": "application/json"})


def doubao_events(response):
    lines = []
    for raw in response:
        line = raw.decode().rstrip("\r\n")
        if line.startswith("data:"):
            lines.append(line[5:].lstrip())
        if not line and lines:
            yield json.loads("\n".join(lines))
            lines.clear()
    if lines:
        yield json.loads("\n".join(lines))


def doubao_audio(text, host, language, key):
    code = language.lower().split("-")[0]
    localized = {"zh": "zh-cn", "es": "es-mx"}
    language_code = language.lower() if language.lower() in ("es-es", "pt-br") else localized.get(code, code)
    request = json_request("https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse", {
        "req_params": {
            "text": text, "speaker": DOUBAO_VOICES[host - 1],
            "audio_params": {"format": "mp3", "sample_rate": 24000},
            "additions": json.dumps({"explicit_language": language_code}),
        },
    }, {"X-Api-Key": key, "X-Api-Resource-Id": "seed-tts-2.0",
        "X-Api-Request-Id": str(uuid4()), "Accept": "text/event-stream"})
    audio = bytearray()
    with urlopen(request, timeout=90) as response:
        for event in doubao_events(response):
            code = event.get("code")
            if code not in (0, 20000000):
                raise RuntimeError(f"豆包 TTS 返回错误码 {code}，请核对语音合成 2.0 开通状态及音色权限。")
            if event.get("data"):
                audio.extend(base64.b64decode(event["data"], validate=True))
            if code == 20000000:
                return bytes(audio)
    raise RuntimeError("豆包 TTS 未返回完整音频。")


def eleven_audio(turns, language, key, hosts):
    base = "https://api.elevenlabs.io/v1"
    body = {"model_id": "eleven_v4", "language_code": language.lower().split("-")[0]}
    if hosts == 1:
        endpoint = f"/text-to-speech/{ELEVEN_VOICES[0]}"
        body["text"] = "\n\n".join(turn["text"] for turn in turns)
    else:
        endpoint = "/text-to-dialogue"
        body["inputs"] = [{"text": turn["text"], "voice_id": ELEVEN_VOICES[turn["host"] - 1]}
                          for turn in turns]
    request = json_request(f"{base}{endpoint}?output_format=mp3_44100_128", body,
                           {"xi-api-key": key, "Accept": "audio/mpeg"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def batches(dialogue, max_length, by_host=False):
    block = []
    length = 0
    for turn in dialogue:
        size = len(turn["text"]) + 2
        if block and (length + size > max_length or (by_host and block[0]["host"] != turn["host"])):
            yield block
            block, length = [], 0
        block.append(turn)
        length += size
    if block:
        yield block


def check_mp3(data):
    if not (data.startswith(b"ID3") or len(data) > 2 and data[0] == 0xff and data[1] & 0xe0 == 0xe0):
        raise RuntimeError("语音服务未返回有效 MP3。")
    return data


def convert(source, destination, *options):
    try:
        subprocess.run([AFCONVERT, *options, str(source), str(destination)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("macOS 无法转换播客音频。") from error


def join_mp3(parts):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        joined = root / "joined.wav"
        with wave.open(str(joined), "wb") as output:
            output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            for data in parts:
                source, decoded = root / "part.mp3", root / "part.wav"
                source.write_bytes(data)
                convert(source, decoded, "-f", "WAVE", "-d", "LEI16@24000", "-c", "1")
                with wave.open(str(decoded), "rb") as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
                        raise RuntimeError("解码后的播客片段格式不一致。")
                    output.writeframes(audio.readframes(audio.getnframes()))
                decoded.unlink()
        destination = root / "episode.m4a"
        convert(joined, destination, "-f", "m4af", "-d", "aac")
        return destination.read_bytes(), "m4a"


def render(model, dialogue, language, key, hosts):
    if model == "fish":
        return fish_tts.render(dialogue, language, key, hosts), "mp3"
    name = MODELS[model]["name"]
    try:
        if model == "doubao":
            blocks = list(batches(dialogue, 1800, by_host=True))
            parts = (doubao_audio("\n\n".join(turn["text"] for turn in block),
                                  block[0]["host"], language, key) for block in blocks)
        else:
            blocks = [dialogue] if hosts == 1 else list(batches(dialogue, 2000))
            parts = (eleven_audio(block, language, key, hosts) for block in blocks)
        if len(blocks) == 1:
            return check_mp3(next(parts)), "mp3"
        if not Path(AFCONVERT).is_file():
            raise RuntimeError("分段合成需要 macOS 自带的 afconvert。")
        return join_mp3(check_mp3(part) for part in parts)
    except HTTPError as error:
        raise RuntimeError(f"{name} 请求失败（HTTP {error.code}）。请核对 API Key、模型权限或账户额度。") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"{name} 网络请求失败或超时。") from error
    except (UnicodeError, json.JSONDecodeError, binascii.Error) as error:
        raise RuntimeError(f"{name} 返回了无法解析的音频响应。") from error
