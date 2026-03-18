# 苏轼·课堂问答游戏

本项目包含两套玩法：

- **静态小游戏**（`index.html`）：选择题 + 配对，适合离线/投屏
- **两组对战（Kahoot 风格）**（Flask，`server.py`）：A 组 vs B 组，比“快 + 准”

## 运行方式

### 方式一：两组对战（推荐课堂使用）

1) 建虚拟环境并安装依赖

```bash
cd /Users/garywit/work/chinese_class_game
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) 启动服务（默认端口 5000，如被占用可改成 5050）

```bash
python server.py
```

3) 打开页面

- 教师端：`http://127.0.0.1:5000/teacher`
- 学生端 A 组：`http://127.0.0.1:5000/s/A`
- 学生端 B 组：`http://127.0.0.1:5000/s/B`

课堂同学用手机连同一 Wi‑Fi 时，把 `127.0.0.1` 换成老师电脑的局域网 IP（例如 `192.168.1.23`）。

### 方式二：静态小游戏（不分组对战）

由于浏览器对本地 `fetch` 有限制，请用本地静态服务器打开：

```bash
cd /Users/garywit/work/chinese_class_game
python3 -m http.server 8000
```

然后在浏览器打开 `http://localhost:8000`。

## 题库格式

题库在 `data/qa.json`，是一个数组：

```json
[
  { "q": "问题…", "a": "正确答案…" }
]
```

你可以把 PDF/Excel 的内容整理成这个格式直接替换即可。

