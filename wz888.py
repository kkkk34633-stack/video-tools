import json
import re
import time
import random
import requests
import base64
from bs4 import BeautifulSoup
from datetime import datetime
from pypinyin import lazy_pinyin

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import boto3
from botocore.config import Config
from supabase import create_client

# ==========================================
# ⚙️ 新增：Supabase 配置区域
# ==========================================
SUPABASE_URL = "https://etietwvnqxlcvghyasxw.supabase.co"
SUPABASE_KEY = "sb_publishable_l3yKmjHJ9IgpbcUgcakvkA_yvvY5NHu"

def get_supabase_client():  # 👈 ✨ 去掉了容易报错的 "-> Client" 类型提示
    """
    初始化并返回 Supabase 客户端
    """
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ 初始化 Supabase 客户端失败: {e}")
        return None

# 初始化客户端
supabase_db = get_supabase_client()


# ==========================================
# 1. ⚙️ 配置区域（置于脚本顶部，方便一眼看到并修改）
# ==========================================
# 建议：实际生产中，更好的做法是使用 os.environ.get("R2_ACCESS_KEY_ID") 从系统环境变量读取
R2_ACCOUNT_ID = "b257ddf9f8d76c000787b5bae86a07c2"
R2_ACCESS_KEY_ID = "54235d87b340dbdd438e828c4e1f30e5"
R2_SECRET_ACCESS_KEY = "85d0e16fd137cb69e34e21dc9c722f6ee9a9b43ff8fee82a88f35b2de855933d"
BUCKET_NAME = "my-video-bucket"

# ==========================================
# 2. 🔌 初始化云服务客户端
# ==========================================
def get_r2_client():
    """
    初始化并返回 R2 客户端，只在真正需要上传时调用
    """
    try:
        client = boto3.client(
            service_name="s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto"
        )
        return client
    except Exception as e:
        print(f"❌ 初始化 R2 客户端失败: {e}")
        return None



# ==================== 🕷️ 1. 网页爬虫部分（集成 Base64 解密） ====================

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def decrypt_base64_title(js_content):
    """
    专门用来提取并解密 d('...') 里的密文
    """
    try:
        # 正则匹配 d('xxxx') 或 d("xxxx") 里的内容
        match = re.search(r"d\(['\"](.*?)['\"]\)", js_content)
        if match:
            encrypted_str = match.group(1)
            # 进行 Base64 解码
            decoded_bytes = base64.b64decode(encrypted_str)
            # 转为 utf-8 字符串
            return decoded_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ 解密失败: {e}")
    return ""

def crawl_wz888():
    print("🕷️ [第一阶段] 开始温和爬取目标网站数据...")
    scraped_videos = []
    
    url = "https://wz888.net/list/52897129-1.html"
    print(f"🚀 正在建立请求连接: {url}")
    
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://wz888.net/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        
        if response.status_code == 200:
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 🎯 锁定大容器
            show_box = soup.find(id="ShowBox") or soup.find(class_="ShowBox")
            
            if show_box:
                print("🎯 成功定位到 #ShowBox 容器，开始解析视频列表...")
                dl_tags = show_box.find_all("dl")
                print(f"📊 容器内共发现 {len(dl_tags)} 个视频卡片（dl 标签）。")
                
                for index, dl in enumerate(dl_tags):
                    img_src = None
                    video_title = ""
                    video_url = None  # ✨ 新增：初始化视频链接变量
                    
                    # ---- 2. 图片定位：dl -> dt -> img ----
                    dt = dl.find("dt")
                    if dt:
                        img = dt.find("img")
                        a_link = dt.find("a")
                        if img:
                            img_src = img.get("data-original") or img.get("src")
                        if a_link:
                            video_url = "https://wz888.net" + a_link.get("href")
                    # ---- 3. 标题定位：直接提取 JS 里的密文并用 Python 解密 ----
                    dd = dl.find("dd")
                    if dd:
                        script_tag = dd.find("script")
                        if script_tag:
                            # 拿到 <script> 里的原始代码
                            js_code = script_tag.string or script_tag.get_text() or ""
                            # 调用解密函数
                            video_title = decrypt_base64_title(js_code)
                    
                    # 🔍 调试诊断
                    if not img_src or not video_title:
                        print(f"⚠️ 卡片 [{index + 1}] 提取失败 -> 图片: {img_src} | 标题: '{video_title}'")
                    
                    # ---- 4. 路径补全并压入结果 ----
                    if img_src and video_title:
                        if img_src.startswith("//"):
                            img_src = "https:" + img_src
                        elif img_src.startswith("/"):
                            img_src = "https://wz888.net" + img_src
                            
                        scraped_videos.append({
                            "title": video_title,
                            "image": img_src,
                            "url": video_url  # ✨ 新增：将链接放入返回结果中
                        })
            else:
                print("❌ 未在页面中找到 id 为 'ShowBox' 的元素。")

            print(f"✅ 解析结束！共成功提取到 {len(scraped_videos)} 条视频数据。")
            
        else:
            print(f"❌ 请求网页失败，状态码: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 爬取网页时发生异常: {e}")
        
    crawl_delay = random.uniform(1.0, 2.0)
    print(f"😴 网站防封锁保护：随机挂起等待 {crawl_delay:.2f} 秒...\n")
    time.sleep(crawl_delay)
    
    return scraped_videos


# ==================== 📝 2. 数据清洗与翻译部分 ====================

def clean_and_translate(title):
    if title is None: return ""
    title_str = str(title).strip()
    if not title_str: return ""
    
    title_str = re.sub(r'[\(（【\[][^\)）】\]]*$', '', title_str).strip()
    prefix_code = ""
    code_match = re.match(r'^(\[[A-Za-z0-9-]+\])\s*', title_str)
    if code_match:
        prefix_code = code_match.group(1)
        title_str = title_str[len(prefix_code):].strip()
    
    code_raw_match = re.match(r'^([A-Za-z0-9]+-\d+-[A-Za-z]|[A-Za-z0-9]+-\d+|^[A-Za-z]{3,4}\d{3,4})\s*', title_str)
    if code_raw_match and not prefix_code:
        prefix_code = f"[{code_raw_match.group(1)}]"
        title_str = title_str[len(code_raw_match.group(1)):].strip()

    if not title_str: return prefix_code
        
    try:
        if any('\u4e00' <= char <= '\u9fff' for char in title_str) and not any('\u3040' <= char <= '\u30ff' for char in title_str):
            return f"{prefix_code} {title_str}".strip()
            
        # ✨ 核心修改：使用 deep-translator 的同步调用
        translated_title = GoogleTranslator(source='auto', target='zh-CN').translate(title_str)
        if not translated_title:
            return f"{prefix_code} {title_str}".strip()
            
        translated_title = re.sub(r'\b[A-Za-z]+-\d+\b', '', translated_title)
        translated_title = re.sub(r'\b[A-Z]{2,4}\b', '', translated_title)
        return f"{prefix_code} {translated_title}".strip()
        
    except Exception as e:
        print(f"⚠️ 这一条翻译折了: {title_str[:10]}... 原因: {e}")
        return f"{prefix_code} {title_str}".strip()


# ==================== 抓取m3u8文件，存入r2,返回地址链接 ====================
def get_m3u8_from_scratch(detail_url, image_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wz888.net/"
    }
    try:
        # 1. 访问详情页
        print(f"🎯 访问详情页{detail_url}")
        res_detail = requests.get(detail_url, headers=headers, verify=False, timeout=10)
        if res_detail.status_code != 200:
            print("❌ 详情页请求失败")
            return None
        
        # 2. 从 HTML 或 script 中提取 play.php 链接
        # 这里使用更精准的正则匹配，匹配类似于 https://m.892539.xyz/play.php?site_id=15&source_id=216463 的链接
        play_php_match = re.search(r'(https?://[^\s"\'`]+\.xyz/play\.php\?[^\s"\'`]*)', res_detail.text)
        
        if not play_php_match:
            # 备用匹配方案：如果网页里写的是相对路径或者变量形式
            site_id_match = re.search(r'site_id\s*=\s*["\']?(\d+)["\']?', res_detail.text)
            source_id_match = re.search(r'source_id\s*=\s*["\']?(\d+)["\']?', res_detail.text)
            if site_id_match and source_id_match:
                play_php_url = f"https://m.892539.xyz/play.php?site_id={site_id_match.group(1)}&source_id={source_id_match.group(1)}"
            else:
                print("❌ 未能在详情页中找到 play.php 播放接口")
                return None
        else:
            play_php_url = play_php_match.group(1)
            
        print(f"🎯 成功提取到播放接口: {play_php_url}")
        
        # 3. 访问 play.php 链接，获取 M3U8 数据
        print(f"🔄 [第二步] 正在请求播放接口...")
        res_play = requests.get(play_php_url, headers=headers, timeout=10)
        
        if "#EXTM3U" in res_play.text:
            print("🎉 成功！已直接拿到 M3U8 文本数据！")
            m3u8_content = res_play.text
            
            # 4. 从 M3U8 文本中提取所有的 .ts 视频分片链接
            ts_urls = re.findall(r'(https?://[^\s]+\.ts)', m3u8_content)
            # return {
            #     "play_php_url": play_php_url,
            #     "ts_count": len(ts_urls),
            #     "ts_urls": ts_urls
            # }

            # 正则表达式解析：
            # https?:// 匹配 http:// 或 https://
            # ([a-zA-Z0-9]+) 第一捕获组：提取域名主体（如 wz888）
            # \.[a-z]+/ 匹配 .net/ 或 .com/
            # video/ 匹配路径
            # (\d+) 第二捕获组：提取纯数字 ID（如 1263852993）
            pattern = r"https?://([a-zA-Z0-9]+)\.[a-z]+/video/(\d+)\.html"
            
            match = re.search(pattern, detail_url)
            if match:
                # match.group(1) 对应第一个括号里的内容
                platform = match.group(1)
                # match.group(2) 对应第二个括号里的内容
                video_id = match.group(2)
                
                # 使用 f-string 组合成你需要的格式
                combined_id = f"{platform}_{video_id}"
            else:
                print("❌ URL 格式不匹配，无法提取")
            print(f"❌ combined_id是{combined_id}")
            r2_path, r2_img_path = upload_m3u8_and_ts_to_r2(m3u8_content, combined_id, ts_urls, image_url)
            #r2_path = "2026-07/wz888_1165103993/index.m3u8"
            #r2_img_path = "2026-07/wz888_1165103993/cover.jpg"
            return {
                "play_php_url": play_php_url,
                "ts_count": len(ts_urls),
                "ts_urls": ts_urls,
                "r2_path": r2_path,  # ✨ 将路径塞进结果字典中
                "r2_img_path": r2_img_path,
                "combined_id": combined_id  # ✨ 塞进字典中返回
            }

        else:
            print("❌ 请求 play.php 成功，但返回的不是标准的 M3U8 数据")
            return None
            
    except Exception as e:
        print(f"💥 运行过程中发生错误: {e}")
        return None


# ==================== 上传r2 ====================
def upload_m3u8_and_ts_to_r2(m3u8_content, combined_id, ts_urls, img_url):
    """
    1. 下载并上传所有的 .ts 分片到 R2
    2. 将 M3U8 中的绝对路径替换为相对路径
    3. 上传重写后的 M3U8 到 R2
    """
    r2_client = get_r2_client()
    if not r2_client:
        print("❌ 无法初始化 R2 客户端，取消上传")
        return False
    
    r2_m3u8_key = None
    r2_img_key = None

    try:
        current_date = datetime.now().strftime("%Y-%m")
        # 基础目录，例如: 2026-07/wz888_1263852993/
        base_dir = f"{current_date}/{combined_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://wz888.net/"
        }

        
        # ----------------- ✨ 新增：下载并上传封面图片 -----------------
        if img_url:
            # 🚀 统一强制规定 R2 内的文件名永远为 cover.jpg
            r2_img_key = f"{base_dir}/cover.jpg"
            print(f"📸 正在下载并上传封面图片到 R2: {r2_img_key} ...")

            try:
                img_res = requests.get(img_url, headers=headers, timeout=15)
                # 🚨 【拦截点 1】判断状态码，如果不成功则直接跳出整个方法
                if img_res.status_code == 200:
                    r2_client.put_object(
                        Bucket=BUCKET_NAME,
                        Key=r2_img_key,
                        Body=img_res.content,
                        ContentType="image/jpeg"
                    )
                    print("✅ 封面图片上传成功！")
                else:
                    print(f"⚠️ 封面图片下载失败，状态码: {img_res.status_code}")
                    return None
            except Exception as img_err:
                print(f"⚠️ 封面图片上传发生异常: {img_err}")
                r2_img_key = None


        # ----------------- 1. 循环下载并上传每个 .ts 文件 -----------------
        print(f"📦 开始处理该视频的 {len(ts_urls)} 个 .ts 分片...")
        # 1. 循环下载并上传每个 .ts 文件
        for idx, ts_url in enumerate(ts_urls):
            ts_name = ts_url.split('/')[-1].split('?')[0]
            r2_ts_key = f"{base_dir}/{ts_name}"
            
            print(f" └── [{idx+1}/{len(ts_urls)}] 正在下载并上传: {ts_name}")
            
            # 初始化控制变量
            success = False
            max_retries = 3  # 最大重试 3 次
            
            for attempt in range(max_retries):
                try:
                    # 下载 ts 分片
                    ts_res = requests.get(ts_url, headers=headers, timeout=15)
                    
                    if ts_res.status_code == 200:
                        # 成功拿到了数据，直接流式上传到 R2
                        r2_client.put_object(
                            Bucket=BUCKET_NAME,
                            Key=r2_ts_key,
                            Body=ts_res.content,
                            ContentType="video/mp2t"
                        )
                        success = True
                        break  # 成功后跳出重试循环
                    elif ts_res.status_code == 403:
                        print(f"  ⚠️ 触发 403 被拒！可能需要延长等待，尝试第 {attempt+1} 次重试...")
                        time.sleep(3)  # 触发安全拦截时，多睡一会
                    else:
                        print(f"  ⚠️ 分片 {ts_name} 状态码异常 ({ts_res.status_code})，尝试重试...")
                        
                except Exception as ts_err:
                    print(f"  ⚠️ 分片 {ts_name} 网络异常: {ts_err}，尝试第 {attempt+1} 次重试...")
                
                # 失败后，重试等待时间逐步加长（1.5s -> 3s -> 4.5s）
                time.sleep((attempt + 1) * 1.5)

            if not success:
                print(f"❌ 严重警告：分片 {ts_name} 彻底下载失败！已跳过。")
            
            # ✨ 核心防封：随机休眠（0.3 秒 到 0.8 秒之间）
            # 既减少了不必要的无意义等待时间，又打破了固定频率特征
            jitter_sleep = random.uniform(0.3, 0.8)
            time.sleep(jitter_sleep)

        # 2. 修改 M3U8 文件内容（将网络绝对路径替换为仅含文件名的相对路径）
        # 这样播放器请求 M3U8 时，会自动去同级目录下寻找 .ts 文件
        new_m3u8_content = m3u8_content
        for ts_url in ts_urls:
            ts_name = ts_url.split('/')[-1].split('?')[0]
            # 把原本长长的 "https://xxx.com/.../001.ts" 替换为 "001.ts"
            new_m3u8_content = new_m3u8_content.replace(ts_url, ts_name)

        # 3. 上传重写后的新 M3U8 文件
        r2_m3u8_key = f"{base_dir}/index.m3u8"
        print(f"📤 正在上传重写后的 M3U8 到 R2: {r2_m3u8_key} ...")
        
        r2_client.put_object(
            Bucket=BUCKET_NAME,
            Key=r2_m3u8_key,
            Body=new_m3u8_content.encode('utf-8'),
            ContentType="application/x-mpegURL"
        )
        print("✅ 视频及所有分片全部成功备份至 R2！")
        return r2_m3u8_key, r2_img_key
        
    except Exception as e:
        print(f"❌ 上传 R2 整体任务失败: {e}")
        return r2_m3u8_key, r2_img_key



# ==================== 处理链接 ====================
def to_seo_slug(title, mode="pinyin"):
    """
    将中文/英文标题转换为 SEO 友好的拼音或英文 Slug (限制长度)
    :param title: 原始标题
    :param mode: "pinyin" (拼音) 或 "english" (英文)
    """
    if not title:
        return ""
    
    # 1. 提取番号前缀 (如 ABP-123) 并转为小写
    prefix_code = ""
    code_match = re.search(r'\[([A-Za-z0-9-]+)\]', title)
    if code_match:
        prefix_code = code_match.group(1).lower()
        # 移除标题中的番号部分，避免重复转换
        title = title.replace(code_match.group(0), "").strip()

    # 2. 核心转换逻辑
    if mode == "english":
        try:
            # 将中文翻译为英文
            translated = GoogleTranslator(source='auto', target='en').translate(title)
            slug_core = translated.lower()
        except Exception as e:
            print(f"⚠️ 英文 Slug 翻译失败: {e}，降级使用拼音")
            slug_core = "-".join(lazy_pinyin(title))
    else:
        # 默认模式：pinyin (将 "漂亮的女孩" 转换为 "piao-liang-de-nv-hai")
        pinyin_list = lazy_pinyin(title)
        slug_core = "-".join(pinyin_list).lower()

    # 3. 拼接番号与转换后的核心内容
    if prefix_code:
        full_slug = f"{prefix_code}-{slug_core}"
    else:
        full_slug = slug_core

    # 4. 清理非字符（只保留小写字母、数字和连字符 '-'）
    full_slug = re.sub(r'[^a-z0-9-]', ' ', full_slug)
    full_slug = re.sub(r'[\s_]+', '-', full_slug)
    full_slug = re.sub(r'-+', '-', full_slug)
    full_slug = full_slug.strip('-')

    # 5. 💡 控制链接长度限制：只保留前 5 个单词/拼音
    # 这样可以极大防止 URL 长度爆炸，确保完美的 SEO 长度
    words = full_slug.split('-')
    if len(words) > 7:
        full_slug = "-".join(words[:7])  # 限制最长 7 个节点 (如: abp-123-piao-liang-de-nv-hai)

    return full_slug


# ==================== 🎬 3. 主程序串联运行 ====================

if __name__ == "__main__":
    
    videos = crawl_wz888()
    
    if videos:
        print(f"🌐 [第二阶段] 开始安全翻译处理 {len(videos)} 条视频标题...\n")

        for index, item in enumerate(videos):
            old_title = item.get("title", "")
            new_title = clean_and_translate(old_title)

            # 2. ✨ 基于中文 title，生成拼音(或英文)的 SEO Slug
            # 如果想用英文，把 mode 改为 "english"（会调用谷歌翻译，稍慢但效果极佳）
            slug_name = to_seo_slug(new_title, mode="pinyin")
            print(f"    slug_name: {slug_name}")
            
            print(f"[{index + 1}/{len(videos)}] 原文: {old_title}")
            print(f"    图片: {item.get('image')}")
            print(f"    译文: {new_title}")
            print(f"    链接: {item.get('url')}")  # ✨ 新增：在控制台打印链接，方便调试查看
            result = get_m3u8_from_scratch(item.get('url'), item.get('image'))
            if result:
                print("\n=== 解析结果展示 ===")
                print(f"提取出的播放器链接: {result['play_php_url']}")
                print(f"解析出的视频分片数量: {result['ts_count']} 个")
                print(f"R2 数据库存储路径: {result['r2_path']}")
                print(f"R2 数据库图片存储路径: {result.get('r2_img_path')}")
                print(f"R2 combined_id: {result.get('combined_id')}")
                print(f"new_title: {new_title}")
            
                # 2. ✨ 数据同步写入 Supabase 数据库
                if supabase_db:
                    db_data = {
                        "id": result.get('combined_id'),
                        "title": new_title,
                        "m3u8_url": result['r2_path'],
                        "cover_url": result.get('r2_img_path'),
                        "category_id": "1",
                        "slug" : slug_name
                    }

                    try:
                        print("💾 正在同步数据到 Supabase...")
                        # 使用 upsert 方法：如果 combined_id 冲突，它将自动更新已有行的字段值
                        response = supabase_db.table("videos").upsert(db_data).execute()
                        print("✅ Supabase 数据同步成功！")
                    except Exception as db_err:
                        print(f"❌ 写入 Supabase 失败: {db_err}")

            print("-" * 50)

            
            translate_delay = random.uniform(1.2, 2.5)
            time.sleep(translate_delay)

        with open("video_data_translated.json", "w", encoding="utf-8") as f:
            json.dump(videos, f, ensure_ascii=False, indent=2)

        print("\n🎉 [搞定！] 网页爬取、清洗与翻译全部温和执行完毕！已生成 video_data_translated.json")