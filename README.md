# Commute News · Codex 本地播客

先告诉 Codex 你想听什么。你也可以授权它参考相关历史对话，帮你提出可能喜欢的新闻方向。确认后，定时任务按偏好每天制作一期，音频和私人 RSS 保存在自己的电脑上。

## 1. 安装

插件在 macOS 上运行，需要 Codex 和 Python 3.9 或更新版本。

```bash
codex plugin marketplace add wanglaoji14/commute-news --ref main
codex plugin add commute-news@commute-news
```

从本公开仓库安装过的用户，可以刷新来源并重新安装当前版本，然后在 Codex 打开新对话。

```bash
codex plugin marketplace upgrade commute-news
codex plugin add commute-news@commute-news
```

## 2. 告诉 Agent 你想听什么

在 Codex 选择 `commute-news` Skill，发送「我想每天早上听一点 AI 和科技新闻，你觉得我适合听哪些方向？」Agent 会先问你的兴趣，也可以在你同意后参考它能访问的相关历史。它会给出几个建议，请你确认想听的方向。插件只保存确认过的主题和反馈。

然后选语言、单人或双人、语音模型。Skill 按所选语言标出一个推荐。

| 推荐语言 | 语音模型 | 获取 API Key |
| --- | --- | --- |
| 日语 | **Fish Audio S2.1 Pro** | [Fish Audio API Keys](https://fish.audio/app/api-keys) |
| 中文 | **字节豆包语音合成 2.0** | [豆包语音控制台](https://console.volcengine.com/speech/)，在同一个项目开通语音合成 2.0 |
| 英语 | **ElevenLabs Eleven v4** | [ElevenLabs API Keys](https://elevenlabs.io/app/developers/api-keys) |

选择后，Skill 会给出所选服务的 API Key 页面和一条本机终端设置命令。按终端提示粘贴自己的 Key，输入时不显示。密钥保存在本机，文件只允许当前用户读写。节目库默认在 `~/Documents/Commute News`。合成费用由所选服务计入自己的账号。建好节目库后，Skill 会主动给你私人 RSS 地址，并引导你[在 iPhone 订阅](#4-用-iphone-订阅)。

## 3. 每天更新

设置好本地节目库后，告诉 Agent 希望几点听到节目和所在时区，例如「每天日本时间早上 6:30，优先推荐新 AI 模型发布和日本科技」。然后在支持本地定时运行的 Codex 环境中启用每日任务。每天到点，Agent 读取确认过的方向、找当天值得推荐的新闻、写稿并生成一期。定时任务要能访问本机节目库并在预定时间运行。

之后可以说「以后多讲日本科技」「这类融资消息少一点」。新偏好从下次生成时生效。每天使用同一条 RSS，同一天的定时任务重复触发时会复用已生成的一期。

Fish Audio 用 Jin 和 Satoru。豆包语音合成 2.0 每次请求指定一个音色，双人节目逐段合成并在本机拼接。Eleven v4 的双人模式使用 Text to Dialogue。 [Fish Audio 接口](https://docs.fish.audio/features/text-to-speech) · [豆包 HTTP SSE 接口](https://docs.volcengine.com/docs/doubao-voice/http-chunked-sse-unidirectional-streaming-v3?lang=zh) · [ElevenLabs 对话接口](https://elevenlabs.io/docs/overview/capabilities/text-to-dialogue)

## 4. 用 iPhone 订阅

请 Skill 给出 `serve` 命令，在一个单独的终端运行并保持开启。让 iPhone 和 Mac 连到同一个可互访的 Wi-Fi。在 Apple 播客进入「资料库」→「…」→「通过 URL 关注节目」，粘贴终端输出的 RSS。如果节目库还没有音频，等首集发布后再添加。以后用同一条 RSS 接收更新，订阅一次即可。

如果手机无法访问 Mac 的 `.local` 地址，用 Skill 的 `init --host <Mac 的局域网 IPv4>` 改用局域网 IP，再用新的 URL 订阅。可以先在 iPhone 的 Safari 打开 RSS 地址，确认两台设备可以互访。出门前可把节目下载到手机。局域网服务需要 Mac 保持清醒，播放器才能继续拉取节目。

## 许可证

本仓库的代码和文档采用 [MIT License](LICENSE)。语音 API 和供应商音色按各自服务条款使用。
