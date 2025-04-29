# Group Chat Summary Plugin

群聊总结插件 (group_chat_summary) 是一个用于自动记录和总结群聊内容的插件。它能够实时保存群聊记录，并根据需要生成结构化的群聊总结报告，并支持将 HTML 总结自动渲染为图片发送，适合截图分享。

总结插件自用修改版本，原插件地址 https://github.com/wclzq/group_chat_summary

## 效果

### 总结样式
![总结样式](https://i.ibb.co/ynV6k1Mt/image.jpg)

### 自定义总结样式（效果随机，没有固定）
![总结样式](https://i.ibb.co/jPSBSKrW/image.jpg)

## 安装

1. 使用管理员命令安装
```
#installp https://github.com/memor221/group_chat_summary.git
```
2. 扫描新插件
```
#scanp
```
3. 启用插件
```
#enablep group_chat_summary
```
## 功能特点

- 自动记录群聊消息
- 生成结构化的群聊总结报告图
- 支持自定义总结消息数量或时间范围
- 支持自定义总结提示
- 支持黑名单功能
- 自动清理过期消息
- 自动检测 HTML 总结并转为图片发送，图片宽度固定 800px，适合群分享
- 群名称自动动态注入，无需手动填写

## 使用方法

在群聊中，发送以下命令来获取群聊总结：

例如：
- `总结聊天 30` - 总结最近30条消息
- `总结聊天 3小时` - 总结最近3小时内的消息
- `总结聊天 30 自定义提示` - 总结最近30条消息并使用自定义提示



## 配置参数

在 `config.json` 中配置以下参数：

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| api_configs | array | 支持多套 OpenAI API 配置 | 必填 |
| max_record_quantity | number | 每个群保存的最大消息数量 | 1000 |
| black_chat_name | array | 黑名单群聊列表 | [] |
| delete_after_send | bool | 是否自动定时清理图片（每天03:03），true为开启，false为关闭 | true |

配置示例：

```json
{
  "api_configs": [
    {
      "open_ai_api_base": "https://api.openai.com/v1",
      "open_ai_api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxx",
      "open_ai_model": "gpt-3.5-turbo"
    }
  ],
  "max_record_quantity": 1000,
  "black_chat_name": ["群聊1", "群聊2"],
  "delete_after_send": true
}
```

## 依赖说明

请确保已安装以下依赖（requirements.txt）：
- playwright
- requests
- pillow
- aiofiles
- pyee

## 数据存储

插件使用SQLite数据库存储聊天记录，数据库文件名为 `chat_records.db`。数据会自动清理，只保留每个群的最新消息（数量由 max_record_quantity 配置）。

## 注意事项

1. 确保已正确配置 OpenAI API 相关参数
2. 插件仅支持群聊总结，私聊不可用
3. 被加入黑名单的群聊无法使用总结功能
4. 建议根据服务器性能适当调整 max_record_quantity 参数
5. 如需 HTML 总结转图片，需保证 playwright 及其依赖已正确安装
6. 图片自动清理功能可通过 delete_after_send 配置开关，开启时每天03:03自动清理图片目录
7. 如果生成结果不理想的话，更换代码处理能力好些的模型

## 错误处理

如果遇到"所有模型请求均失败，请检查API配置"等提示，请检查：
1. API配置是否正确
2. 网络连接是否正常
3. API密钥是否有效
4. playwright 是否已安装并可用

## 其他
本人不懂代码，插件完全由ai生成，勉强能用，分享给大家，如果有什么问题的话，还望见谅
![赞赏码](https://i.ibb.co/F4NM1Pg3/zsm.png)