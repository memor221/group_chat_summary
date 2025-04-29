# encoding:utf-8

import os
import json
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from plugins import *
from config import conf
import sqlite3
from datetime import datetime, timedelta  # 增加 timedelta 导入
import uuid
import time
import asyncio
from playwright.async_api import async_playwright
import threading
import glob
import schedule
import io

class ImageStreamWrapper:
    """
    Wraps io.BytesIO to provide both file-like operations (seek, read)
    and a __len__ method returning the total size of the stream content.
    """
    def __init__(self, image_bytes: bytes):
        self._stream = io.BytesIO(image_bytes)
        # Store the length derived from the initial bytes
        self._length = len(image_bytes)
    def __len__(self):
        """Returns the total length of the underlying bytes."""
        return self._length
    def __getattr__(self, name):
        """Delegates any other attribute/method access to the underlying BytesIO stream."""
        # logger.debug(f"ImageStreamWrapper: Delegating '{name}'") # Optional: for debugging delegation
        return getattr(self._stream, name)
    # Optional: Explicit delegation for commonly used methods if __getattr__ proves problematic
    # or for slight potential performance gain (usually negligible).
    def read(self, *args, **kwargs):
         # logger.debug(f"ImageStreamWrapper: Calling read()") # Optional debug
         return self._stream.read(*args, **kwargs)
    def seek(self, *args, **kwargs):
         # logger.debug(f"ImageStreamWrapper: Calling seek()") # Optional debug
         return self._stream.seek(*args, **kwargs)
    def tell(self, *args, **kwargs):
         # logger.debug(f"ImageStreamWrapper: Calling tell()") # Optional debug
         return self._stream.tell(*args, **kwargs)
    def close(self, *args, **kwargs):
        # logger.debug(f"ImageStreamWrapper: Calling close()") # Optional debug
        # It's good practice to delegate close as well
        return self._stream.close(*args, **kwargs)
    # Add seekable if needed, though __getattr__ should cover hasattr checks too
    def seekable(self):
        # logger.debug(f"ImageStreamWrapper: Calling seekable()") # Optional debug
        return self._stream.seekable()
    
QL_PROMPT = '''
我给你一份json格式的群聊内容：群聊结构如下（注意：忽略所有机器人指令消息）：
user是发言者，content是发言内容,time是发言时间：
[{'user': '秋风', 'content': '总结',time:'2025-02-26 09:50:53'},{'user': '秋风', 'content': '你好',time:'2025-02-26 09:50:53'},{'user': '小王', 'content': '你好',time:'2025-02-26 09:50:53'}]
-------分割线-------
任务：根据提供的微信群聊天记录生成群消息总结，输出为风格固定、一致的HTML页面，适合截图分享

## 自动提取信息
系统将自动从您提供的聊天记录中提取以下信息：
- 群名称：{group_name}
- 日期范围：根据记录中的所有日期自动生成（格式：YYYY-MM-DD ~ YYYY-MM-DD）
- 时间范围：根据记录中的首条和末条消息时间确定

## 总结模式选择
- 总结模式：[完整版/简化版] (默认为完整版)
- 如果需要简化版，请在提交时注明"生成简化版总结"

## 简化版说明
如选择"简化版"，将只生成以下核心部分：
- 时段讨论热点（最多3个）
- 重要消息汇总
- 话唠榜（仅前3名）
- 简化版词云
总结内容更精简，适合快速浏览和分享。

## 聊天记录支持格式
支持以下多种常见格式：
- "[时间] 昵称：消息内容"
- "时间 - 昵称：消息内容"
- "昵称 时间：消息内容"
- 其他合理的时间和昵称分隔格式

如未能识别消息格式或未找到有效记录，将显示提示信息并尝试按最佳猜测处理。

## 输出要求
必须使用以下固定的HTML模板和CSS样式，仅更新内容部分，确保每次生成的页面风格完全一致。使用严格定义的深色科技风格。

## HTML结构模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{group_name}群聊总结 - [日期]</title>
    <style>
        /* 严格定义的CSS样式，确保风格一致性 */
        :root {
            --bg-primary: #0f0e17;
            --bg-secondary: #1a1925;
            --bg-tertiary: #252336;
            --text-primary: #fffffe;
            --text-secondary: #a7a9be;
            --accent-primary: #ff8906;
            --accent-secondary: #f25f4c;
            --accent-tertiary: #e53170;
            --accent-blue: #3da9fc;
            --accent-purple: #7209b7;
            --accent-cyan: #00b4d8;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'SF Pro Display', 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            font-size: 16px;
            width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            text-align: center;
            padding: 30px 0;
            background-color: var(--bg-secondary);
            margin-bottom: 30px;
        }
        
        h1 {
            font-size: 36px;
            font-weight: 700;
            color: var(--accent-primary);
            margin-bottom: 10px;
        }
        
        .date {
            font-size: 18px;
            color: var(--text-secondary);
            margin-bottom: 20px;
        }
        
        .meta-info {
            display: flex;
            justify-content: center;
            gap: 20px;
        }
        
        .meta-info span {
            background-color: var(--bg-tertiary);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
        }
        
        section {
            background-color: var(--bg-secondary);
            margin-bottom: 30px;
            padding: 25px;
        }
        
        h2 {
            font-size: 28px;
            font-weight: 600;
            color: var(--accent-blue);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--accent-blue);
        }
        
        h3 {
            font-size: 22px;
            font-weight: 600;
            color: var(--accent-primary);
            margin: 15px 0 10px 0;
        }
        
        h4 {
            font-size: 18px;
            font-weight: 600;
            color: var(--accent-secondary);
            margin: 12px 0 8px 0;
        }
        
        p {
            margin-bottom: 15px;
        }
        
        ul, ol {
            margin-left: 20px;
            margin-bottom: 15px;
        }
        
        li {
            margin-bottom: 5px;
        }
        
        a {
            color: var(--accent-blue);
            text-decoration: none;
        }
        
        a:hover {
            text-decoration: underline;
        }
        
        /* 卡片容器样式 */
        .topics-container, .tutorials-container, .messages-container, 
        .dialogues-container, .qa-container, .participants-container {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
        }
        
        /* 卡片样式 */
        .topic-card, .tutorial-card, .message-card, 
        .dialogue-card, .qa-card, .participant-item, .night-owl-item {
            background-color: var(--bg-tertiary);
            padding: 20px;
        }
        
        /* 话题卡片 */
        .topic-category {
            display: inline-block;
            background-color: var(--accent-blue);
            color: var(--text-primary);
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 14px;
            margin-bottom: 10px;
        }
        
        .topic-keywords {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 10px 0;
        }
        
        .keyword {
            background-color: rgba(61, 169, 252, 0.2);
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 14px;
        }
        
        .topic-mentions {
            color: var(--accent-cyan);
            font-weight: 600;
        }
        
        /* 教程卡片 */
        .tutorial-type {
            display: inline-block;
            background-color: var(--accent-secondary);
            color: var(--text-primary);
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 14px;
            margin-bottom: 10px;
        }
        
        .tutorial-meta {
            color: var(--text-secondary);
            margin-bottom: 10px;
            font-size: 14px;
        }
        
        .tutorial-category {
            margin-top: 10px;
            font-style: italic;
            color: var(--text-secondary);
        }
        
        /* 消息卡片 */
        .message-meta {
            margin-bottom: 10px;
        }
        
        .message-meta span {
            margin-right: 15px;
            font-size: 14px;
        }
        
        .message-type {
            background-color: var(--accent-tertiary);
            color: var(--text-primary);
            padding: 3px 10px;
            border-radius: 15px;
        }
        
        .priority {
            padding: 3px 10px;
            border-radius: 15px;
        }
        
        .priority-high {
            background-color: var(--accent-secondary);
        }
        
        .priority-medium {
            background-color: var(--accent-primary);
        }
        
        .priority-low {
            background-color: var(--accent-blue);
        }
        
        /* 对话卡片 */
        .dialogue-type {
            display: inline-block;
            background-color: var(--accent-purple);
            color: var(--text-primary);
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 14px;
            margin-bottom: 10px;
        }
        
        .dialogue-content {
            background-color: rgba(255, 255, 255, 0.05);
            padding: 15px;
            margin-bottom: 15px;
        }
        
        .dialogue-highlight {
            font-style: italic;
            color: var(--accent-primary);
            margin: 10px 0;
            font-weight: 600;
        }
        
        /* 问答卡片 */
        .question {
            margin-bottom: 15px;
        }
        
        .question-meta, .answer-meta {
            color: var(--text-secondary);
            margin-bottom: 5px;
            font-size: 14px;
        }
        
        .question-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        
        .tag {
            background-color: rgba(114, 9, 183, 0.2);
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 14px;
        }
        
        .answer {
            background-color: rgba(255, 255, 255, 0.05);
            padding: 15px;
            margin-top: 10px;
        }
        
        .accepted-badge {
            background-color: var(--accent-primary);
            color: var(--text-primary);
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 14px;
        }
        
        /* 热度图 */
        .heatmap-container {
            display: grid;
            grid-template-columns: 1fr;
            gap: 15px;
        }
        
        .heat-topic {
            font-weight: 600;
            margin-bottom: 5px;
        }
        
        .heat-bar {
            height: 20px;
            background-color: rgba(255, 255, 255, 0.1);
            margin: 5px 0;
            border-radius: 10px;
            overflow: hidden;
        }
        
        .heat-fill {
            height: 100%;
            border-radius: 10px;
        }
        
        /* 话唠榜 */
        .participant-rank {
            font-size: 28px;
            font-weight: 700;
            color: var(--accent-primary);
            margin-right: 15px;
            float: left;
        }
        
        .participant-name {
            font-weight: 600;
            font-size: 18px;
            margin-bottom: 5px;
        }
        
        .participant-count {
            color: var(--accent-cyan);
            margin-bottom: 10px;
        }
        
        .participant-characteristics, .participant-words {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        
        .characteristic {
            background-color: rgba(242, 95, 76, 0.2);
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 14px;
        }
        
        .word {
            background-color: rgba(229, 49, 112, 0.2);
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 14px;
        }
        
        /* 熬夜冠军 */
        .night-owl-item {
            background: linear-gradient(135deg, #0f0e17 0%, #192064 100%);
            padding: 20px;
            display: flex;
            align-items: center;
        }
        
        .owl-crown {
            font-size: 40px;
            margin-right: 20px;
        }
        
        .owl-name {
            font-weight: 600;
            font-size: 18px;
            margin-bottom: 5px;
        }
        
        .owl-title {
            color: var(--accent-primary);
            font-style: italic;
            margin-bottom: 10px;
        }
        
        .owl-time, .owl-messages {
            color: var(--text-secondary);
            margin-bottom: 5px;
        }
        
        .owl-note {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 10px;
            font-style: italic;
        }
        
        /* 词云 - 云朵样式 */
        .cloud-container {
            position: relative;
            margin: 0 auto;
            padding: 20px 0;
        }
        
        .cloud-wordcloud {
            position: relative;
            width: 600px;
            height: 400px;
            margin: 0 auto;
            background-color: var(--bg-tertiary);
            border-radius: 50%;
            box-shadow: 
                40px 40px 0 -5px var(--bg-tertiary),
                80px 10px 0 -10px var(--bg-tertiary),
                110px 35px 0 -5px var(--bg-tertiary),
                -40px 50px 0 -8px var(--bg-tertiary),
                -70px 20px 0 -10px var(--bg-tertiary);
            overflow: visible;
        }
        
        .cloud-word {
            position: absolute;
            transform-origin: center;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
        }
        
        .cloud-word:hover {
            transform: scale(1.1);
            z-index: 10;
        }
        
        .cloud-legend {
            margin-top: 60px;
            display: flex;
            justify-content: center;
            gap: 30px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 50%;
        }
        
        /* 底部 */
        footer {
            text-align: center;
            padding: 20px 0;
            margin-top: 50px;
            background-color: var(--bg-secondary);
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        footer p {
            margin: 5px 0;
        }
        
        .disclaimer {
            margin-top: 15px;
            font-style: italic;
        }
    </style>
</head>
<body>
    <header>
        <h1>[群名称]总结</h1>
        <p class="date">[日期范围]</p>
        <div class="meta-info">
            <span>总消息数：[数量]</span>
            <span>日均消息数：[数量]</span>
            <span>活跃用户：[数量]</span>
            <span>时间范围：[时间范围]</span>
        </div>
    </header>

    <!-- 1. 今日讨论热点 -->
    <section class="hot-topics">
        <h2>今日讨论热点</h2>
        <div class="topics-container">
            <!-- 在这里填充讨论热点内容，严格按照以下格式，保留3-5个话题 -->
            <div class="topic-card">
                <h3>[热点话题名称]</h3>
                <div class="topic-category">[话题分类]</div>
                <p class="topic-summary">[简要总结(50-100字)]</p>
                <div class="topic-keywords">
                    <span class="keyword">[关键词1]</span>
                    <span class="keyword">[关键词2]</span>
                    <!-- 添加更多关键词 -->
                </div>
                <div class="topic-mentions">提及次数：[次数]</div>
            </div>
            <!-- 复制上述卡片结构添加更多话题 -->
        </div>
    </section>

    <!-- 2. 实用教程与资源分享 -->
    <section class="tutorials">
        <h2>实用教程与资源分享</h2>
        <div class="tutorials-container">
            <!-- 在这里填充教程和资源内容，严格按照以下格式 -->
            <div class="tutorial-card">
                <div class="tutorial-type">[TUTORIAL | NEWS | RESOURCE]</div>
                <h3>[分享的教程或资源标题]</h3>
                <div class="tutorial-meta">
                    <span class="shared-by">分享者：[昵称]</span>
                    <span class="share-time">时间：[时间]</span>
                </div>
                <p class="tutorial-summary">[内容简介]</p>
                <div class="key-points">
                    <h4>要点：</h4>
                    <ul>
                        <li>[要点1]</li>
                        <li>[要点2]</li>
                        <!-- 添加更多要点 -->
                    </ul>
                </div>
                <div class="tutorial-link">
                    <a href="[URL]" class="link valid">查看原文: [域名]</a>
                </div>
                <div class="tutorial-category">分类：[分类]</div>
            </div>
            <!-- 复制上述卡片结构添加更多资源 -->
        </div>
    </section>

    <!-- 3. 重要消息汇总 -->
    <section class="important-messages">
        <h2>重要消息汇总</h2>
        <div class="messages-container">
            <!-- 在这里填充重要消息内容，严格按照以下格式 -->
            <div class="message-card">
                <div class="message-meta">
                    <span class="time">[消息时间]</span>
                    <span class="sender">[发送者昵称]</span>
                    <span class="message-type">[NOTICE | EVENT | ANNOUNCEMENT | OTHER]</span>
                    <span class="priority priority-high">优先级：[高|中|低]</span>
                </div>
                <p class="message-content">[消息内容]</p>
                <div class="message-full-content">
                    <p>[完整通知内容]</p>
                </div>
            </div>
            <!-- 复制上述卡片结构添加更多消息 -->
        </div>
    </section>

    <!-- 4. 有趣对话或金句 -->
    <section class="interesting-dialogues">
        <h2>有趣对话或金句</h2>
        <div class="dialogues-container">
            <!-- 在这里填充对话内容，严格按照以下格式 -->
            <div class="dialogue-card">
                <div class="dialogue-type">[DIALOGUE | QUOTE]</div>
                <div class="dialogue-content">
                    <div class="message">
                        <div class="message-meta">
                            <span class="speaker">[说话者昵称]</span>
                            <span class="time">[发言时间]</span>
                        </div>
                        <p class="message-content">[消息内容]</p>
                    </div>
                    <div class="message">
                        <div class="message-meta">
                            <span class="speaker">[说话者昵称]</span>
                            <span class="time">[发言时间]</span>
                        </div>
                        <p class="message-content">[消息内容]</p>
                    </div>
                    <!-- 添加更多对话消息 -->
                </div>
                <div class="dialogue-highlight">[对话中的金句或亮点]</div>
                <div class="dialogue-topic">相关话题：[某某话题]</div>
            </div>
            <!-- 复制上述卡片结构添加更多对话 -->
        </div>
    </section>

    <!-- 5. 问题与解答 -->
    <section class="questions-answers">
        <h2>问题与解答</h2>
        <div class="qa-container">
            <!-- 在这里填充问答内容，严格按照以下格式 -->
            <div class="qa-card">
                <div class="question">
                    <div class="question-meta">
                        <span class="asker">[提问者昵称]</span>
                        <span class="time">[提问时间]</span>
                    </div>
                    <p class="question-content">[问题内容]</p>
                    <div class="question-tags">
                        <span class="tag">[相关标签1]</span>
                        <span class="tag">[相关标签2]</span>
                        <!-- 添加更多标签 -->
                    </div>
                </div>
                <div class="answers">
                    <div class="answer">
                        <div class="answer-meta">
                            <span class="responder">[回答者昵称]</span>
                            <span class="time">[回答时间]</span>
                            <span class="accepted-badge">最佳回答</span>
                        </div>
                        <p class="answer-content">[回答内容]</p>
                    </div>
                    <!-- 添加更多回答 -->
                </div>
            </div>
            <!-- 复制上述卡片结构添加更多问答 -->
        </div>
    </section>

    <!-- 6. 群内数据可视化 -->
    <section class="analytics">
        <h2>群内数据可视化</h2>
        
        <!-- 话题热度 -->
        <h3>话题热度</h3>
        <div class="heatmap-container">
            <!-- 在这里填充话题热度数据，严格按照以下格式 -->
            <div class="heat-item">
                <div class="heat-topic">[话题名称]</div>
                <div class="heat-percentage">[百分比]%</div>
                <div class="heat-bar">
                    <div class="heat-fill" style="width: [百分比]%; background-color: #3da9fc;"></div>
                </div>
                <div class="heat-count">[数量]条消息</div>
            </div>
            <!-- 复制上述结构添加更多热度项，每项使用不同颜色 -->
            <div class="heat-item">
                <div class="heat-topic">[话题名称]</div>
                <div class="heat-percentage">[百分比]%</div>
                <div class="heat-bar">
                    <div class="heat-fill" style="width: [百分比]%; background-color: #f25f4c;"></div>
                </div>
                <div class="heat-count">[数量]条消息</div>
            </div>
            <!-- 可用的颜色: #3da9fc, #f25f4c, #7209b7, #e53170, #00b4d8, #4cc9f0 -->
        </div>
        
        <!-- 话唠榜 -->
        <h3>话唠榜</h3>
        <div class="participants-container">
            <!-- 在这里填充话唠榜数据，严格按照以下格式 -->
            <div class="participant-item">
                <div class="participant-rank">1</div>
                <div class="participant-info">
                    <div class="participant-name">[群友昵称]</div>
                    <div class="participant-count">[数量]条消息</div>
                    <div class="participant-characteristics">
                        <span class="characteristic">[特点1]</span>
                        <span class="characteristic">[特点2]</span>
                        <!-- 添加更多特点 -->
                    </div>
                    <div class="participant-words">
                        <span class="word">[常用词1]</span>
                        <span class="word">[常用词2]</span>
                        <!-- 添加更多常用词 -->
                    </div>
                </div>
            </div>
            <!-- 复制上述结构添加更多参与者 -->
        </div>
        
        <!-- 熬夜冠军 -->
        <h3>熬夜冠军</h3>
        <div class="night-owls-container">
            <!-- 在这里填充熬夜冠军数据，严格按照以下格式 -->
            <div class="night-owl-item">
                <div class="owl-crown" title="熬夜冠军">👑</div>
                <div class="owl-info">
                    <div class="owl-name">[熬夜冠军昵称]</div>
                    <div class="owl-title">[熬夜冠军称号]</div>
                    <div class="owl-time">最晚活跃时间：[时间]</div>
                    <div class="owl-messages">深夜消息数：[数量]</div>
                    <div class="owl-last-message">[最后一条深夜消息内容]</div>
                    <div class="owl-note">注：熬夜时段定义为23:00-06:00，已考虑不同时区</div>
                </div>
            </div>
        </div>
    </section>

    <!-- 7. 词云 -->
    <section class="word-cloud">
        <h2>热门词云</h2>
        <div class="cloud-container">
            <!-- 词云容器 - 现在是云朵样式 -->
            <div class="cloud-wordcloud" id="word-cloud">
                <!-- 为每个词创建一个span元素，使用绝对定位放置 -->
                <!-- 以下是一些示例，请根据实际内容生成40-60个词 -->
                <span class="cloud-word" style="left: 300px; top: 120px; font-size: 38px; color: #00b4d8; transform: rotate(-15deg); font-weight: bold;">[关键词1]</span>
                
                <span class="cloud-word" style="left: 180px; top: 150px; font-size: 32px; color: #4cc9f0; transform: rotate(5deg); font-weight: bold;">[关键词2]</span>
                
                <span class="cloud-word" style="left: 400px; top: 180px; font-size: 28px; color: #f25f4c; transform: rotate(-5deg);">[关键词3]</span>
                
                <span class="cloud-word" style="left: 250px; top: 220px; font-size: 24px; color: #ff8906; transform: rotate(10deg);">[关键词4]</span>
                
                <span class="cloud-word" style="left: 350px; top: 90px; font-size: 22px; color: #e53170; transform: rotate(-10deg);">[关键词5]</span>
                
                <!-- 继续添加更多词 -->
            </div>
            
            <div class="cloud-legend">
                <div class="legend-item">
                    <span class="legend-color" style="background-color: #00b4d8;"></span>
                    <span class="legend-label">[分类1] 相关词汇</span>
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background-color: #4361ee;"></span>
                    <span class="legend-label">[分类2] 相关词汇</span>
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background-color: #7209b7;"></span>
                    <span class="legend-label">[分类3] 相关词汇</span>
                </div>
            </div>
        </div>
    </section>

    <!-- 8. 页面底部 -->
    <footer>
        <p>数据来源：{group_name}群聊天记录</p>
        <p>生成时间：<span class="generation-time">[当前时间]</span></p>
        <p>统计周期：[日期] [时间范围]</p>
        <p class="disclaimer">免责声明：本报告内容基于群聊公开讨论，如有不当内容或侵权问题请联系管理员处理。</p>
    </footer>
</body>
</html>
'''
conent_list={}
@plugins.register(
    name="group_chat_summary",
    desire_priority=89,
    hidden=True,
    desc="总结聊天",
    version="0.2",
    author="memor221",
)


class GroupChatSummary(Plugin):

    api_configs = []  # 多套API配置
    current_config_index = 0  # 当前使用的配置索引
    max_record_quantity = 1000
    black_chat_name=[]
    curdir = os.path.dirname(__file__)
    db_path = os.path.join(curdir, "chat_records.db")
    # 存储活跃图片路径，避免定时任务删除正在使用的图片
    active_image_files = {}
    def __init__(self):
        
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
            
            # 加载多套API配置
            self.api_configs = self.config.get("api_configs", [])
            if not self.api_configs:
                # 兼容旧配置格式
                default_config = {
                    "open_ai_api_base": self.config.get("open_ai_api_base", ""),
                    "open_ai_api_key": self.config.get("open_ai_api_key", ""),
                    "open_ai_model": self.config.get("open_ai_model", "gpt-4-0613")
                }
                self.api_configs = [default_config]
                
            self.max_record_quantity = self.config.get("max_record_quantity", 1000)
            self.black_chat_name = self.config.get("black_chat_name", [])
            self.delete_after_send = self.config.get("delete_after_send", True)
            
            # 初始化数据库
            self.init_database()
            
            # 启动定时清理任务（每天03:03）
            if self.delete_after_send:
                self._start_daily_image_cleanup()
            
            logger.info("[group_chat_summary] inited")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            self.handlers[Event.ON_RECEIVE_MESSAGE] = self.on_receive_message
        except Exception as e:
            logger.error(f"[group_chat_summary]初始化异常：{e}")
            raise "[group_chat_summary] init failed, ignore "

    def init_database(self):
        """初始化数据库"""
       
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 创建聊天记录表，将 create_time 改为 TEXT 类型
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT,
                        user_nickname TEXT,
                        content TEXT,
                        create_time TEXT,
                        UNIQUE(group_id, user_nickname, content, create_time)
                    )
                ''')
                conn.commit()
                logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"[group_chat_summary]数据库初始化异常：{e}")

    # 新增按时间总结
    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [ContextType.TEXT]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        content = e_context["context"].content.strip()
        # 匹配两种命令格式：总结聊天 30 / 总结 3小时
        if content.startswith("总结聊天") or content.startswith("总结"):
            reply = Reply()
            # {{ - reply.type = ReplyType.TEXT # Moved type assignment later }}
            if msg.other_user_nickname in self.black_chat_name:
                reply.content = "我母鸡啊"
                # {{ + }}
                reply.type = ReplyType.TEXT
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            # 解析参数
            cmd_parts = content.split(maxsplit=2)  # 最多分割2次，确保自定义提示保持完整
            if len(cmd_parts) < 2:
                reply.content = "命令格式错误，示例：总结聊天 30 或 总结 3小时 或 总结聊天 30 自定义提示"
                # {{ + }}
                reply.type = ReplyType.TEXT
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            # 提取自定义提示（如果有）
            custom_prompt = None
            if len(cmd_parts) >= 3:
                custom_prompt = cmd_parts[2].strip()
            # 判断是按条数还是按小时
            param = cmd_parts[1]
            time_mode = "小时" in param
            try:
                if time_mode:
                    # 考虑用户可能输入"总结 3小时 自定义提示"格式
                    hours_part = param.split()[0] if " " in param else param
                    hours = int(hours_part.replace("小时", ""))
                    time_threshold = datetime.now() - timedelta(hours=hours)
                    time_str = time_threshold.strftime("%Y-%m-%d %H:%M:%S")
                    # 如果自定义提示为None但param中有空格（如"3小时 自定义提示"），则提取提示
                    if custom_prompt is None and " " in param:
                        custom_prompt = param.split(" ", 1)[1].strip()
                else:
                    # 考虑用户可能输入"总结聊天 30 自定义提示"格式
                    num_part = param.split()[0] if " " in param else param
                    number_int = int(num_part)
                    # 如果自定义提示为None但param中有空格（如"30 自定义提示"），则提取提示
                    if custom_prompt is None and " " in param:
                        custom_prompt = param.split(" ", 1)[1].strip()
            except ValueError:
                reply.content = "参数必须是数字，例如：总结 3小时 或 总结聊天 30 或 总结聊天 30 自定义提示"
                # {{ + }}
                reply.type = ReplyType.TEXT
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            generated_summary_content = "" # 用于存储生成的文本总结
            if e_context["context"]["isgroup"]:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        if time_mode:
                            # 按时间范围查询
                            cursor.execute('''
                                SELECT user_nickname, content, create_time
                                FROM chat_records
                                WHERE group_id = ? AND create_time >= ?
                                ORDER BY create_time DESC
                            ''', (msg.other_user_id, time_str))
                        else:
                            # 按条数查询（原逻辑）
                            cursor.execute('''
                                SELECT user_nickname, content, create_time
                                FROM chat_records
                                WHERE group_id = ?
                                ORDER BY create_time DESC
                                LIMIT ?
                            ''', (msg.other_user_id, number_int))
                        records = cursor.fetchall()
                        chat_list = [
                            {"user": record[0], "content": record[1], "time": record[2]}
                            for record in records
                        ]
                        chat_list.reverse()  # 保持时间正序
                        # 根据是否有自定义提示来组装请求内容
                        if custom_prompt:
                            # 分割QL_PROMPT，保留分割线前面的内容
                            prompt_parts = QL_PROMPT.split("-------分割线-------")
                            # 用户自定义提示替换默认提示
                            cont = prompt_parts[0] + "#注意：不需要列举聊天记录；请以清晰的层次结构和简洁的语言，通过分析和合理的猜测推断，回答问题，并将内容转换成HTML代码，要求:页面美观自然，柔和色彩，清晰一目了然，不同内容板块可以使用不同的颜色条作为区分，直接输出代码，不需要其他说明，问题：" + custom_prompt + "----聊天记录如下：" + json.dumps(chat_list, ensure_ascii=False)
                        else:
                            # 使用原有默认提示
                            cont = QL_PROMPT + "----聊天记录如下：" + json.dumps(chat_list, ensure_ascii=False)
                        group_name = e_context["context"].get("group_name") or "群聊"
                        # 替换群名称占位符
                        cont = cont.replace("{group_name}", group_name)
                        generated_summary_content = self.shyl(cont) # Store summary content
                except Exception as e:
                    logger.error(f"[group_chat_summary]获取聊天记录异常：{e}")
                    generated_summary_content = "获取聊天记录失败" # Store error message
            else:
                generated_summary_content = "只做群聊总结" # Store message
            # ====== HTML转图片逻辑 或 直接使用文本 ======
            is_html, html_raw = self._is_html_content(generated_summary_content)
            if is_html:
                html_block = self.extract_html_block(html_raw)
                if html_block:
                    # 生成图片路径
                    image_dir = os.path.join(os.path.dirname(__file__), '../html_to_image/temp')
                    os.makedirs(image_dir, exist_ok=True)
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    image_name = f"{timestamp}_{uuid.uuid4()}.png"
                    image_path = os.path.join(image_dir, image_name)
                    # 截图
                    try:
                        asyncio.run(self.html_to_image(html_block, image_path, 1200, 90, 0.5))
                        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                            try:
                                with open(image_path, 'rb') as f:
                                    image_content = f.read()
                                # {{ - reply.content = io.BytesIO(image_content) }}
                                # {{ + Use the wrapper class }}
                                reply.content = ImageStreamWrapper(image_content)
                                reply.type = ReplyType.IMAGE
                            except Exception as e:
                                logger.error(f"[group_chat_summary] 读取或包装图片文件失败: {e}")
                                reply.content = "读取或包装图片文件失败: " + str(e)
                                reply.type = ReplyType.TEXT # Fallback to text reply
                        else:
                            logger.warning(f"[group_chat_summary] HTML转图片成功，但文件无效或大小为0: {image_path}")
                            reply.content = "HTML转图片成功，但文件无效。"
                            reply.type = ReplyType.TEXT
                    except Exception as e:
                        logger.error(f"[group_chat_summary] HTML转图片异常: {e}")
                        reply.content = "HTML转图片失败: " + str(e)
                        reply.type = ReplyType.TEXT
                else:
                    logger.warning("[group_chat_summary] 内容判定为HTML，但无法提取HTML块。")
                    # Could not extract HTML block, send raw summary
                    reply.content = generated_summary_content
                    reply.type = ReplyType.TEXT
            else:
                 # Content is not HTML, send as text
                reply.content = generated_summary_content
                reply.type = ReplyType.TEXT
            # ====== END ======
            # Ensure reply type is set if not set above (e.g., if no image processing happened)
            if not reply.type:
                 reply.type = ReplyType.TEXT # Default to TEXT if type wasn't assigned
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def on_receive_message(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        self.add_conetent(msg)
    def add_conetent(self, message):
        """添加聊天记录到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 将时间戳转换为字符串格式
                time_str = datetime.fromtimestamp(message.create_time).strftime('%Y-%m-%d %H:%M:%S')
                # 插入数据
                cursor.execute('''
                    INSERT OR IGNORE INTO chat_records (group_id, user_nickname, content, create_time)
                    VALUES (?, ?, ?, ?)
                ''', (
                    message.other_user_id,
                    message.actual_user_nickname,
                    message.content,
                    time_str  # 使用格式化后的时间字符串
                ))
                conn.commit()
                
                # 删除超过最大记录数的旧记录
                cursor.execute('''
                    DELETE FROM chat_records 
                    WHERE group_id = ? AND id NOT IN (
                        SELECT id FROM chat_records 
                        WHERE group_id = ? 
                        ORDER BY create_time DESC 
                        LIMIT ?
                    )
                ''', (message.other_user_id, message.other_user_id, self.max_record_quantity))
                conn.commit()
        except Exception as e:
            logger.error(f"[group_chat_summary]添加聊天记录异常：{e}")
    def get_help_text(self, **kwargs):
        help_text = "总结聊天+数量 或 总结+N小时；例：总结聊天 30 或 总结 3小时\n"
        help_text += "支持自定义提示：总结聊天 30 自定义提示 或 总结 3小时 自定义提示"
        return help_text
    
    def get_current_config(self):
        """获取当前使用的API配置"""
        if not self.api_configs:
            return None
        return self.api_configs[self.current_config_index]
        
    def next_config(self):
        """切换到下一个API配置"""
        if not self.api_configs:
            return None
        self.current_config_index = (self.current_config_index + 1) % len(self.api_configs)
        return self.get_current_config()
    
    def shyl(self, content):
        """使用多套API配置轮流尝试请求"""
        import requests
        import json
        
        # 尝试所有可用的API配置
        for _ in range(len(self.api_configs)):
            config = self.get_current_config()
            
            # 检查配置是否有效
            if not config or not config.get("open_ai_api_base") or not config.get("open_ai_api_key"):
                logger.warning(f"[group_chat_summary]跳过无效配置: {self.current_config_index}")
                self.next_config()
                continue
                
            url = config.get("open_ai_api_base") + "/chat/completions"
            payload = json.dumps({
                "model": config.get("open_ai_model"),
                "messages": [{"role": "user", "content": content}],
                "stream": False
            })
            headers = {
                'Authorization': 'Bearer ' + config.get("open_ai_api_key"),
                'Content-Type': 'application/json'
            }
            
            try:
                logger.info(f"[group_chat_summary]尝试使用配置 {self.current_config_index}")
                response = requests.request("POST", url, headers=headers, data=payload)
                
                # 检查响应状态码
                if response.status_code == 200:
                    # 使用.json()方法将响应内容转换为JSON
                    response_json = response.json()
                    # 提取"content"字段
                    content = response_json['choices'][0]['message']['content']
                    return content
                else:
                    logger.warning(f"[group_chat_summary]请求失败，状态码：{response.status_code}，尝试下一个配置")
                    self.next_config()
            except Exception as e:
                logger.error(f"[group_chat_summary]请求异常：{e}，尝试下一个配置")
                self.next_config()
        
        # 所有配置都失败
        return '所有模型请求均失败，请检查API配置'
    
    def _load_config_template(self):
        logger.info("[group_chat_summary]use config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)

    # 工具函数：判断内容是否为 HTML 及提取 HTML 片段
    def _is_html_content(self, content):
        if not content or not isinstance(content, str):
            return False, None
        
        # 清理内容便于检查
        cleaned_content = content.strip()
        
        # 检查各种HTML内容格式
        if '<!DOCTYPE html' in content or '<html' in content:
            return True, content
            
        # 检查是否为markdown代码块中的HTML (```html ... ```)
        if cleaned_content.startswith('```html') and cleaned_content.endswith('```'):
            html_body = cleaned_content[7:-3].strip()
            return True, html_body
            
        # 检查是否为一般代码块，内容包含HTML标记 (``` ... ```)
        if cleaned_content.startswith('```') and cleaned_content.endswith('```'):
            code_body = cleaned_content[3:-3].strip()
            if '<html' in code_body or '<!DOCTYPE html' in code_body or code_body.count('<') > 5:
                return True, code_body
                
        # 检查是否包含足够的HTML标签特征
        if (content.count('<') > 5 and content.count('>') > 5 and 
            ('<html' in content or '<body' in content or '<div' in content or '<head' in content)):
            return True, content
            
        # 检查是否只包含HTML标签内容
        if content.count('<') > 10 and content.count('>') > 10:
            return True, content
            
        return False, None

    def extract_html_block(self, content):
        """提取HTML内容，适应多种格式（优先检测最后一个html代码块）"""
        # 逆向查找最后一个```html代码块
        last_html_block = None
        if '```html' in content:
            # 找到最后一个```html起始位置
            last_start = content.rfind('```html')
            if last_start != -1:
                # 从起始位置开始找结束标记
                end_pos = content.find('```', last_start + 7)
                if end_pos != -1:
                    last_html_block = content[last_start+7:end_pos].strip()
                else:
                    last_html_block = content[last_start+7:].strip()
            if last_html_block:
                return last_html_block

        # 逆向查找最后一个普通代码块
        if '```' in content:
            # 找最后一个```起始位置
            last_code_start = content.rfind('```')
            if last_code_start > 0:
                # 向前找前一个```作为起始
                prev_start = content.rfind('```', 0, last_code_start-1)
                if prev_start != -1 and content[prev_start+3:prev_start+10].strip() == 'html':
                    code_content = content[prev_start+7:last_code_start].strip()
                    if '<html' in code_content:
                        return code_content

        # 原有检测逻辑（作为fallback）
        if content.strip().startswith('<'):
            return content
            
        # 从```html...```代码块提取
        if '```html' in content:
            start = content.find('```html') + 7
            end = content.find('```', start)
            if end != -1:
                return content[start:end].strip()
            else:
                return content[start:].strip()
                
        # 从普通代码块提取
        if content.strip().startswith('```'):
            start = content.find('```') + 3
            # 跳过第一行，以防是语言标识符
            newline_pos = content.find('\n', start)
            if newline_pos != -1:
                start = newline_pos + 1
            end = content.rfind('```')
            if end != -1:
                return content[start:end].strip()
            else:
                return content[start:].strip()
                
        # 提取<!DOCTYPE html>到</html>的内容
        doctype_start = content.find('<!DOCTYPE html')
        if doctype_start != -1:
            html_end = content.find('</html>', doctype_start)
            return content[doctype_start:html_end+7] if html_end != -1 else content[doctype_start:]
        
        return None
                
        # 提取<html>到</html>的内容
        html_start = content.find('<html')
        if html_start != -1:
            html_end = content.find('</html>', html_start)
            if html_end != -1:
                return content[html_start:html_end+7]
            else:
                return content[html_start:]
                
        # 如果以上都没找到但确实包含HTML特征，返回完整内容
        if content.count('<') > 10 and content.count('>') > 10:
            return content
            
        return None

    async def html_to_image(self, html_content, image_path, image_width=800, image_quality=90, wait_time=0.5):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                # 先设置初始视口宽度
                await page.set_viewport_size({"width": image_width, "height": 600})
                # 包裹内容，确保最大宽度和样式一致
                html_with_style = f"""
                <html>
                <head>
                    <meta charset=\"UTF-8\">
                    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
                    <style>
                    body {{
                        font-family: 'Microsoft YaHei', 'Segoe UI', Tahoma, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        padding: 20px;
                        background-color: #f9f9f9;
                        max-width: {image_width}px;
                        margin: 0 auto;
                        box-sizing: border-box;
                    }}
                    h1, h2, h3, h4 {{
                        color: #2c3e50;
                    }}
                    .topic {{
                        background-color: white;
                        border-radius: 8px;
                        padding: 16px;
                        margin-bottom: 20px;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    }}
                    </style>
                </head>
                <body>
                    {html_content}
                </body>
                </html>
                """
                await page.set_content(html_with_style)
                await asyncio.sleep(wait_time)
                # 获取内容实际高度
                dimensions = await page.evaluate('''() => ({ width: document.documentElement.clientWidth, height: document.body.scrollHeight })''')
                max_height = min(dimensions["height"], 5000)
                # 再次设置视口，宽度固定，适应内容高度
                await page.set_viewport_size({"width": image_width, "height": max_height})
                await page.screenshot(path=image_path, full_page=True, type="png")
                await browser.close()
        except Exception as e:
            logger.error(f"[group_chat_summary] HTML转图片失败: {e}")
            raise e

    def _start_daily_image_cleanup(self):
        def cleanup():
            image_dir = os.path.join(os.path.dirname(__file__), '../html_to_image/temp')
            files = glob.glob(os.path.join(image_dir, '*.png'))
            for f in files:
                try:
                    # 避免删除活跃的图片文件
                    if f in self.active_image_files:
                        continue
                    os.remove(f)
                except Exception as e:
                    logger.warning(f"[group_chat_summary] 定时清理图片失败: {e}")
        def run_schedule():
            schedule.every().day.at("03:03").do(cleanup)
            while True:
                schedule.run_pending()
                time.sleep(60)
        t = threading.Thread(target=run_schedule, daemon=True)
        t.start()

    def on_send_reply(self, e_context: EventContext):
        """消息发送后的回调，用于关闭文件并释放引用"""
        try:
            # 获取当前回复
            reply = e_context.econtext.get("reply")
            if reply and reply.type == ReplyType.IMAGE and hasattr(reply.content, "close"):
                # 尝试关闭文件
                try:
                    reply.content.close()
                except Exception as e:
                    logger.warning(f"[group_chat_summary] 关闭图片文件失败: {e}")
                
                # 清理超过5分钟的文件引用
                current_time = time.time()
                expired_paths = []
                for path, info in self.active_image_files.items():
                    if current_time - info["time"] > 300:  # 5分钟
                        expired_paths.append(path)
                        if "file" in info and hasattr(info["file"], "close"):
                            try:
                                info["file"].close()
                            except Exception:
                                pass
                
                # 从活跃文件字典中移除过期项
                for path in expired_paths:
                    del self.active_image_files[path]
        except Exception as e:
            logger.error(f"[group_chat_summary] 消息发送回调异常: {e}")
            
        # 取消注册自身，避免影响其他消息
        if Event.ON_SEND_REPLY in self.handlers:
            del self.handlers[Event.ON_SEND_REPLY]


