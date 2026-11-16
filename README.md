# 逐句精听

一套为**手机精听、跟读、背诵**设计的网页学习工具：书架页 + 每篇课文一个学习页。打开网址就能用。

**手机现在就可以听：** [https://niclodian1.github.io/tingju/](https://niclodian1.github.io/tingju/)

iPhone 用 Safari 打开 → 点「每日口语（演示）」→ 点任意一句即可播放。可再点底部分享 →「添加到主屏幕」。

- 🎧 **逐句同步**：点击任意一句，跳到音频对应位置播放。
- 🎯 **时间轴校准**：音频和字幕来源不同时，可自动测量 + 手动微调。
- 📚 **多课文书架**：一篇课文一个文件夹，打包后自动出现在书架。
- 📱 **手机网页**：GitHub Pages 在线访问，或局域网 / 离线包。
- 🔒 **数据隔离**：每篇课文的收藏、校准、设置独立保存。

> ⚖️ **版权说明**：本仓库只包含学习工具和一篇原创演示课文。不提供、也不存储他人影视作品。音频与字幕版权归原权利人所有，请只使用你自己合法持有的拷贝。

---

## 用 GitHub Pages 做成手机能打开的网站

页面本身是静态 HTML，**可以用 GitHub Pages 免费上线**。手机 Safari 打开网址就能学，还能「添加到主屏幕」。

### 1. 先在本机生成站点

```bash
python3 tools/build_web.py
```

会把可公开的内容写到 `docs/`：书架、演示课文、约 30 秒的原创语音。

### 2. 推到 GitHub 并打开 Pages

```bash
git init
git add .
git commit -m "Publish sentence listener"
# 在 GitHub 新建一个公开仓库后：
git remote add origin https://github.com/你的用户名/仓库名.git
git branch -M main
git push -u origin main
```

然后打开仓库 **Settings → Pages**：

- Source 选 **Deploy from a branch**
- Branch 选 `main`，文件夹选 **`/docs`**
- 保存后等待 1–2 分钟

手机访问：

```
https://你的用户名.github.io/仓库名/
```

iPhone 用 Safari 打开 → 底部分享 →「添加到主屏幕」。

### GitHub 做不到的事

| 限制 | 影响 |
| --- | --- |
| 单文件不能超过 **100 MB** | 你本机那条 133 MB 音轨无法上传到 GitHub |
| 仓库建议小于 1 GB | 不适合放整部影视原声 |
| GitHub Pages **默认公开** | 任何人都能打开你的网址 |
| 服务条款禁止侵权内容 | 影视原声、整部对白、盗版字幕被投诉后仓库会被删除 |

所以公开网站只放 **工具 + 原创演示课文**。你自己的长音频请留在本机，用局域网服务器访问。

---

## 合规：改名字不够，内容本身不能上公网

把片名、文件夹名改掉，**不能**让受版权保护的原声和对白变成可以公开分发的材料。

公开仓库 / GitHub Pages **不要放**：

- 影视原声、整部对白、从影视作品抽出的字幕
- 片源站、字幕组、压制组的名字（例如片源网站域名、转载包）
- 用改名后的「课文一」包装整部电影

可以放：

- 本仓库的播放器、打包脚本、原创演示课文
- 你自己写的句子、你有权使用的有声书 / 播客 / 课程
- 公有领域材料（需自己确认授权）

本机继续精听你**已经合法持有**的音视频，用下面的局域网方式即可，不必传到 GitHub。

本仓库已做的处理：

- 演示课文换成原创 12 句 + 系统语音，约 190 KB
- 模板、文档、示例里的片源片名、片源站、压制组名称已去掉
- `素材/` 和 `学习包/` 已加入 `.gitignore`，不会被提交

---

## 项目结构

```
english_learn/
├── docs/                                ★ GitHub Pages 站点（python3 tools/build_web.py 生成）
│   ├── index.html                       #   书架首页
│   └── movies/demo/                     #   原创演示课文
├── samples/daily_english/               # 演示课文源文件（原创）
├── 学习包/                              # 本机私人学习包（不提交）
├── 素材/                                # 本机私人音视频 / 字幕（不提交）
├── tools/
│   ├── index.html                       # 学习页模板
│   ├── library_template.html            # 书架页模板
│   ├── build_web.py                     # 生成 GitHub Pages 站点
│   ├── build_offline_pack.py            # 字幕 → 学习页
│   ├── build_library.py                 # 扫描 meta.json 生成书架
│   ├── calibrate_timeline.py            # 时间轴自动校准
│   ├── serve_range.py                   # 局域网服务器（支持 Range）
│   └── extract_audio.sh                 # 从自有文件提取音轨
├── tests/
└── README.md
```

---

## 本机 / 局域网使用（私人材料）

电脑运行：

```bash
python3 tools/serve_range.py
```

手机与电脑连同一 Wi-Fi，Safari 打开打印出的地址。此方式需要电脑开着，适合你自己的长音频。

完全离线：把 `学习包/` 整个文件夹传到手机，用 Documents 等支持本地网页的 App 打开 `index.html`。

### 学习模式

| 模式 | 作用 |
| --- | --- |
| 🔁 单句循环 | 反复听当前句直到听懂 |
| ⏯ 句尾停顿 | 句末自动暂停供跟读 |
| 🀄 遮挡译文 | 隐藏中文 |
| 🔤 盲听遮罩 | 隐藏英文，点击揭示 |
| ⭐ 仅看收藏 | 只显示星标句 |
| 🎯 时间轴校准 | 声音与字幕有偏差时微调 |

声音比字幕晚出现 → 调大偏移；声音比字幕早出现 → 调小偏移。

---

## 新增一篇课文（三步）

请只对你合法持有的文件操作。

```bash
mkdir -p 学习包/movies/my_lesson
./tools/extract_audio.sh "素材/my_video.mkv" "学习包/movies/my_lesson/audio.m4a"

python3 tools/calibrate_timeline.py "素材/my_video.mkv" "素材/字幕/my_lesson.srt" --all

python3 tools/build_offline_pack.py "素材/字幕/my_lesson.srt" \
    --id my_lesson --title 我的课文 --offset 0.00
```

公开网站请改输出到 `docs/`，并且确认课文本身可以公开：

```bash
python3 tools/build_offline_pack.py "samples/daily_english/lesson.srt" \
    docs/movies/demo/learning.html \
    --id demo --title 每日口语（演示）
python3 tools/build_web.py
```

---

## 回归测试

```bash
python3 tools/build_web.py
node tests/test_parser.js
node tests/test_player.js
```

---

## 常见问题

| 问题 | 说明 |
| --- | --- |
| iPhone 点本地 HTML 没反应？ | iOS 限制。用 GitHub Pages、局域网，或 Documents App。 |
| 每次打开都要重新选音频？ | 离线文件选择器是这样；在线 / 局域网模式会自动载入同目录音频。 |
| 为什么不能把整部影视原声放到 GitHub？ | 单文件超 100 MB，而且公开分发影视原声和对白会侵权。 |
| 台词与声音对不上？ | 用 🎯 校准面板微调。 |
| 收藏/设置会串吗？ | 不会，按课文标识隔离。 |
