# NGA爬虫字段说明

## 字段列表

| 序号 | 字段名                 | 类型       | 说明                   |
| -- | ------------------- | -------- | -------------------- |
| 1  | thread\_id          | string   | 帖子ID → raw\_id       |
| 2  | author              | string   | 作者                   |
| 3  | title               | string   | 标题                   |
| 4  | content             | string   | 内容                   |
| 5  | post\_time          | datetime | 发布时间                 |
| 6  | keyword             | string   | 关键词                  |
| 7  | replies             | int      | 回复数 → comment\_count |
| 8  | view\_count         | int      | 查看数                  |
| 9  | like\_count         | int      | 点赞数（若有）              |
| 10 | floor               | int      | 楼层（可选，用于热点判断）        |
| 11 | quote               | string   | 引用内容（可选）             |
| 12 | is\_hot\_reply      | boolean  | 热点回复标记               |
| 13 | author\_level       | int      | 用户等级（推荐）             |
| 14 | author\_post\_count | int      | 作者历史发帖数（可通过统计表补充）    |
| 15 | board\_name         | string   | 版块名称（可选）             |
| 16 | has\_image          | boolean  | 是否含图片                |
| 17 | has\_video          | boolean  | 是否含视频                |

<br />

# B站爬虫字段说明

## 字段列表

| 序号 | 字段名                    | 类型       | 说明                          |
| -- | ---------------------- | -------- | --------------------------- |
| 1  | bvid                   | string   | BV号 → raw\_id               |
| 2  | up\_name               | string   | UP主 → author                |
| 3  | title                  | string   | 标题                          |
| 4  | desc                   | string   | 描述                          |
| 5  | pubdate                | datetime | 发布时间                        |
| 6  | keyword                | string   | 关键词                         |
| 7  | video\_play\_count     | int      | 播放量 → view\_count           |
| 8  | liked\_count           | int      | 点赞数                         |
| 9  | video\_comment         | int      | 评论数                         |
| 10 | video\_coin\_count     | int      | 投币数                         |
| 11 | video\_favorite\_count | int      | 收藏数                         |
| 12 | video\_share\_count    | int      | 分享数                         |
| 13 | video\_danmaku         | int      | 弹幕数 → danmaku\_count        |
| 14 | up\_fans               | int      | 粉丝数 → author\_fans          |
| 15 | up\_total\_videos      | int      | 历史投稿数 → author\_post\_count |
| 16 | up\_level              | int      | UP主等级 → author\_level       |
| 17 | mid                    | string   | UP主数字ID（可选，用于关联）            |
| 18 | has\_image             | boolean  | 是否含图片（封面可视为有图）              |
| 19 | has\_video             | boolean  | 是否含视频（固定为1）                 |

<br />

# 作者统计表（author\_stats）

## 字段列表

| 列名           | 类型           | 说明             |
| ------------ | ------------ | -------------- |
| author       | varchar(128) | 作者名称           |
| platform     | tinyint      | 平台（0=NGA，1=B站） |
| avg\_hot     | float        | 历史平均热度         |
| avg\_like    | float        | 历史平均点赞         |
| avg\_comment | float        | 历史平均评论         |
| post\_count  | int          | 历史总发文数         |
| last\_update | datetime     | 最后更新时间         |

```
{
  "platform": "nga",           // "bilibili" 或 "nga"
  "type": "post",              // "post"/"reply" (NGA); "video"/"comment" (B站)
  "raw_id": "123456",          // NGA: thread_id; B站: bvid
  "author": "用户名",
  "title": "帖子标题或视频标题",
  "content": "正文内容",
  "publish_time": "2026-03-31 12:34:56",
  "keyword": "原神",
  "view_count": 100,           // NGA无则0
  "like_count": 10,
  "comment_count": 5,          // NGA: replies
  "coin_count": 0,             // B站有，NGA填0
  "favorite_count": 0,
  "share_count": 0,
  "danmaku_count": 0,
  "is_hot_reply": false,       // NGA可选
  "author_fans": 0,            // B站填up_fans，NGA填0
  "author_level": 0,           // B站填up_level
  "author_post_count": 0,      // B站填up_total_videos
  "has_image": false,
  "has_video": false,
  "board_name": ""             // NGA版块名
}
```

