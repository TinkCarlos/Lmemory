# Lmemory

[English](README.md) · [MIT 许可证](LICENSE)

Lmemory 给 AI 助手提供可以核对出处的本地记忆。把它指向一个 Markdown 文件夹，问以前定过什么，它会返回相关笔记、证据行和出处。

Lmemory 由 **Tink** 维护。它把笔记保存在纯 Markdown 文件中，用 SQLite 本地检索，并减少重建段落索引时的正则扫描。下文给出同一合成库的空缓存首问对照。

## 快速开始

需要 Python 3.9 或更新版本，以及 SQLite FTS5。

```sh
git clone https://github.com/TinkCarlos/Lmemory.git
cd Lmemory
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
lmemory demo --lang zh
```

演示会在临时目录建立样例库，展示查找原决定、查到更新后的决定，以及库里缺少答案时的回执。

Windows 和其他客户端的接入方式见[安装指南](docs/INSTALL.zh.md)。

### 查询自己的笔记

```sh
LMEMORY_NO_QUERY_LOG=1 lmemory --vault "/你的/笔记目录" ask "我们之前怎么定的发布流程？"
```

### 通过 MCP 接入 Codex

把下面这段加入 Codex 配置并替换路径，查询工具名是 `lmemory_ask`。

```toml
[mcp_servers.lmemory]
command = "/absolute/path/to/Lmemory/.venv/bin/lmemory"
args = ["--vault", "/笔记目录的绝对路径", "mcp"]

[mcp_servers.lmemory.env]
LMEMORY_NO_QUERY_LOG = "1"
```

检索在本机运行，返回来源路径、证据行，以及三种记忆状态之一。`direct` 有直接依据、`related` 只有相关记录、`none` 没有足够依据。检索使用 SQLite，无需 API 密钥。

## 相比 KRouter 改了什么

索引会给包含日期、时长或频率的段落打标签。Lmemory 先判断当前位置能否匹配英文规则的开头，再检查后续分支，减少逐字符的重复扫描。中文表达和 Unicode 数字延续原来的匹配方式，召回排序与缓存格式也保持兼容。

### 空缓存首问对比

三个版本在同一台 Apple M5、同一套 Python 3.12.13 上，使用相同的 **10,017 页 Markdown**（10,000 页生成内容加公开模板）。每次从空缓存发出第一道 stdio MCP 查询，共测六轮，交替反转执行顺序。

| 版本 | 首问耗时中位数 | 段落证据 |
| --- | ---: | --- |
| [KRouter v2.1.2](https://github.com/398894496-arch/KRouter/releases/tag/v2.1.2) | 6.681 秒 | 基准 |
| [上游 KRouter `673007d`](https://github.com/398894496-arch/KRouter/commit/673007d) | 7.482 秒 | 逐项一致 |
| **Lmemory** | **6.159 秒** | 逐项一致 |

在这批样本里，Lmemory 的首问中位数比衍生基线低 **17.7%**，比正式发布版低 **7.8%**。每轮比较首问和 36 道公开检索题，去除时间戳和安装路径的差异后，每组对比的 **222/222 份回执逐字一致**。和 v2.1.2 对照时有五轮更快，和固定上游提交对照时六轮都更快。这组数字衡量的是合成库检索，模型作答和其他资料库的表现可能不同。

### 复现对比

在 Lmemory 仓库目录执行以下命令。`lmemory-bench-20261119` 标签指向本次实测的版本。

```sh
git clone https://github.com/398894496-arch/KRouter.git ../krouter-upstream
git -C ../krouter-upstream worktree add --detach ../krouter-v2.1.2 v2.1.2
git -C ../krouter-upstream worktree add --detach ../krouter-673007d 673007d
git worktree add --detach ../lmemory-bench lmemory-bench-20261119
python3 ../lmemory-bench/bench/scale/cold_rebuild.py ../krouter-v2.1.2 ../krouter-673007d ../lmemory-bench --rounds 6
```

脚本自行生成笔记并使用隔离缓存，输出首问耗时、检索回执和段落证据是否一致。

## 项目文档

<a name="能接哪些应用"></a>

- Lmemory 支持本地 stdio MCP 客户端。Codex、Claude Code、Cursor 等接入方法见[安装指南](docs/INSTALL.zh.md)。

<a name="它不会做什么"></a>

- 检索机制和配置选项见[实现说明](docs/DETAILS.zh.md)。

<a name="用数字说话"></a>
<a name="自己复现"></a>

- 本次构建的实测结果和步骤见[空缓存首问对比](#空缓存首问对比)。

## 致谢与许可证

Lmemory 由 [Tink](https://github.com/TinkCarlos) 维护，基于 [KRouter](https://github.com/398894496-arch/KRouter) 改造，保留原版权声明与 [MIT 许可证](LICENSE)。
