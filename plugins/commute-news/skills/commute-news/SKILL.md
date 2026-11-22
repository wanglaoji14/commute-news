---
name: commute-news
description: Recommend personal news topics from the listener's interests and authorized Agent history, then publish a daily local podcast to a private RSS. Use for requests such as 初始化我的播客, 我想每天听点 AI 新闻, or 以后多推荐日本科技.
---

# Commute News

Use Python 3 and the bundled `scripts/podcast.py`. Resolve its absolute path relative to this file. The default library is `~/Documents/Commute News`. For a different library, pass the same `--library /absolute/path` before each subcommand. Keep credentials out of chat and prompts.

## Onboard the listener

1. Start by asking what the listener wants to hear. If they allow it, use relevant Agent history that the host actually makes available. Identify two or three plausible news directions with a short reason for each, and ask which they want. Give explicit interests more weight than incidental questions. If the host offers no relevant history, use the listener's answers. Use and save only confirmed news topics and feedback. Keep conversation excerpts and private details out of the local profile, episode, automation prompt, and speech API request.
2. Ask for language, one or two hosts, and the desired daily delivery time and time zone if unknown. Run `models --language <tag>` and show the three choices, marking only the language-matched one as recommended. Wait for a choice. Japanese recommends Fish Audio S2.1 Pro, Chinese recommends 豆包语音合成 2.0, and English recommends ElevenLabs Eleven v4.
3. For a new library, give the selected service's API Key page and the exact terminal command `python3 "/absolute/path/to/podcast.py" setup --language <tag> --hosts <1|2> --model <id>`. The listener enters their key in the local hidden prompt. For Doubao, tell them to enable 豆包语音合成 2.0 in the project that owns their key. Use `status` after setup to confirm the library and configured key.
4. Pipe the confirmed preferences as JSON to `profile`. Use `topics` for confirmed directions, `less` for topics the listener wants less of, and `time` and `timezone` for the confirmed local schedule, for example `{"topics":["AI 模型发布","日本科技"],"time":"06:30","timezone":"Asia/Tokyo"}`. Pass only fields the listener wants to change. For feedback, read the saved list first and add or remove the user's explicit topic without dropping their other choices.
5. Once the listener requests daily delivery and confirms the time, create or update one daily local automation through the host's supported scheduling action, if available. Give it the absolute library path and direct it to use this Skill's daily workflow and read the profile on every run. Keep credentials, raw history, and copies of the topic list out of the schedule. If scheduling is unavailable, tell the listener that the daily job still needs to be enabled in a host that supports local recurring runs. The RSS server only serves files.
6. Give the listener their private RSS from `status` during setup. If they want to listen on iPhone, give the exact `python3 "/absolute/path/to/podcast.py" serve` command, including their custom library argument if needed. Ask them to keep that terminal running with the Mac and iPhone on the same Wi-Fi. If the feed is empty, ask them to add it after the first edition appears. In Apple Podcasts, open Library → More (…) → Follow a Show by URL and paste the RSS address. They subscribe once and keep the same address for later episodes.

## Produce the daily episode

1. Run `status` on the configured library. If `daily_published` is true, finish without resubmitting. If the profile has no confirmed topics or the selected provider needs a key, report what setup is missing.
2. Recommend a current story based on the saved topics and feedback, using `recent_titles` to avoid repeating coverage without a material update. Use verifiable primary sources where available. If today's news is quiet, explain a relevant recent development with its real date. If there's no credible material, report that today's edition was skipped. Use the library's default language and host count.
3. Write about five minutes of radio-style material. Use one host for a monologue, or an explainer and a follow-up host for dialogue. Send JSON to `publish --daily` on stdin with `title`, `notes` containing source URLs, `language`, `hosts`, and `dialogue` with 1–80 entries. Each entry has `host` (1 or 2) and `text` (1–300 characters). Use host 1 for solo and both hosts for dialogue. The publisher uses the profile's local date and reuses an already published daily episode.
4. The episode appears on the same RSS. On errors, report the specific issue and avoid repeated billable retries. For a separately requested preview or extra edition, use `publish` without `--daily`.

## Update settings or listen

Use `language <tag>`, `hosts <1|2>`, or `model <id>` to change the corresponding default. For a missing key, give the selected service's API Key page and exact terminal command using the `key` subcommand. Apply one-episode requests as overrides.

Use `serve` in a dedicated terminal to make the private RSS and audio available to devices on the local network. Keep the terminal running during access and give the RSS only to the listener. If the phone cannot resolve the computer's `.local` hostname on the same Wi-Fi, use `init --host <computer-LAN-IPv4>` and give the new subscription address.
