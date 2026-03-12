#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AMD GetInfo - 使用curl提取Apple Music URL中的艺术家和专辑信息
"""

import subprocess
import re
import json
import sys
from urllib.parse import unquote

def convert_traditional_to_simplified(text: str) -> str:
    """将繁体中文转换为简体中文 - 通用方案"""
    try:
        # 尝试使用 opencc 库进行繁简转换（如果可用）
        try:
            import opencc
            converter = opencc.OpenCC('t2s')  # 繁体到简体
            converted = converter.convert(text)
            if converted != text:
                print(f"🔍 opencc转换: '{text}' -> '{converted}'")
            return converted
        except ImportError:
            print("⚠️ opencc库未安装，使用内置映射")
        
        # 内置的常用繁简映射（作为备选方案）
        traditional_to_simplified = {
            # 常用字符
            '絲': '丝', '路': '路', '專': '专', '輯': '辑', '藝': '艺', '術': '术',
            '樂': '乐', '蘋': '苹', '果': '果', '歌': '歌', '曲': '曲', '演': '演',
            '唱': '唱', '音': '音', '聲': '声', '響': '响', '節': '节', '奏': '奏',
            '調': '调', '和': '和', '諧': '谐', '旋': '旋', '律': '律', '韻': '韵',
            '詞': '词', '作': '作', '編': '编', '製': '制', '發': '发', '行': '行',
            '版': '版', '權': '权', '錄': '录', '音': '音', '頻': '频', '視': '视',
            '覺': '觉', '感': '感', '情': '情', '愛': '爱', '喜': '喜', '歡': '欢',
            '悲': '悲', '傷': '伤', '痛': '痛', '苦': '苦', '甜': '甜', '酸': '酸',
            '辣': '辣', '鹹': '咸', '淡': '淡', '濃': '浓', '香': '香', '臭': '臭',
            '美': '美', '醜': '丑', '好': '好', '壞': '坏', '新': '新', '舊': '旧',
            '大': '大', '小': '小', '高': '高', '低': '低', '長': '长', '短': '短',
            '寬': '宽', '窄': '窄', '厚': '厚', '薄': '薄', '深': '深', '淺': '浅',
            '遠': '远', '近': '近', '快': '快', '慢': '慢', '早': '早', '晚': '晚',
            '春': '春', '夏': '夏', '秋': '秋', '冬': '冬', '東': '东', '西': '西',
            '南': '南', '北': '北', '中': '中', '外': '外', '內': '内', '上': '上',
            '下': '下', '左': '左', '右': '右', '前': '前', '後': '后', '裡': '里',
            '邊': '边', '角': '角', '圓': '圆', '方': '方', '三': '三', '角': '角',
            '形': '形', '狀': '状', '色': '色', '彩': '彩', '光': '光', '影': '影',
            '風': '风', '雨': '雨', '雪': '雪', '雷': '雷', '電': '电', '雲': '云',
            '霧': '雾', '露': '露', '霜': '霜', '冰': '冰', '火': '火', '水': '水',
            '土': '土', '金': '金', '木': '木', '石': '石', '山': '山', '川': '川',
            '海': '海', '河': '河', '湖': '湖', '江': '江', '溪': '溪', '泉': '泉',
            '井': '井', '池': '池', '塘': '塘', '溝': '沟', '渠': '渠', '橋': '桥',
            '路': '路', '街': '街', '巷': '巷', '道': '道', '門': '门', '窗': '窗',
            '牆': '墙', '壁': '壁', '屋': '屋', '房': '房', '樓': '楼', '閣': '阁',
            '亭': '亭', '台': '台', '塔': '塔', '廟': '庙', '寺': '寺', '觀': '观',
            '宮': '宫', '殿': '殿', '廳': '厅', '堂': '堂', '室': '室', '廳': '厅',
            '廚': '厨', '廁': '厕', '臥': '卧', '客': '客', '書': '书', '畫': '画',
            '詩': '诗', '詞': '词', '文': '文', '章': '章', '字': '字', '句': '句',
            '段': '段', '篇': '篇', '頁': '页', '冊': '册', '本': '本', '卷': '卷',
            '集': '集', '叢': '丛', '叢': '丛', '叢': '丛', '叢': '丛', '叢': '丛',
        }
        
        # 应用映射
        converted = text
        for traditional, simplified in traditional_to_simplified.items():
            converted = converted.replace(traditional, simplified)
        
        if converted != text:
            print(f"🔍 内置映射转换: '{text}' -> '{converted}'")
        
        return converted
        
    except Exception as e:
        print(f"⚠️ 繁简转换失败: {e}")
        return text

def extract_artist_name(artist_text: str) -> str:
    """从艺术家文本中提取真实的艺术家名称"""
    try:
        # 处理"由XXX演唱"格式
        if artist_text.startswith('由') and artist_text.endswith('演唱'):
            # 提取"由"和"演唱"之间的内容
            artist_name = artist_text[1:-2].strip()
            return artist_name
        
        # 处理"XXX的专辑"格式
        # 例如："薛之谦的专辑" -> "薛之谦"
        if artist_text.endswith('的专辑'):
            artist_name = artist_text[:-3].strip()  # 移除"的专辑"
            return artist_name
        
        # 处理"XXX的歌曲"格式
        # 例如："薛之谦的歌曲" -> "薛之谦"
        if artist_text.endswith('的歌曲'):
            artist_name = artist_text[:-3].strip()  # 移除"的歌曲"
            return artist_name
        
        # 处理其他可能的格式
        # 例如："XXX - Apple Music" -> "XXX"
        if ' - Apple Music' in artist_text:
            artist_name = artist_text.replace(' - Apple Music', '').strip()
            return artist_name
        
        # 如果没有特殊格式，直接返回
        return artist_text.strip()
        
    except Exception as e:
        print(f"⚠️ 提取艺术家名称失败: {e}")
        return artist_text.strip()

def extract_album_name(album_text: str) -> str:
    """从专辑文本中提取真实的专辑名称"""
    try:
        # 处理"《XXX》- XXX的专辑"格式
        # 例如："《初学者》- 薛之谦的专辑" -> "初学者"
        if '《' in album_text and '》' in album_text:
            # 提取《》之间的内容
            start = album_text.find('《') + 1
            end = album_text.find('》')
            if start > 0 and end > start:
                album_name = album_text[start:end].strip()
                return album_name
        
        # 处理"《XXX》"格式
        if album_text.startswith('《') and album_text.endswith('》'):
            album_name = album_text[1:-1].strip()
            return album_name
        
        # 处理"XXX - XXX的专辑"格式
        if ' - ' in album_text and album_text.endswith('的专辑'):
            album_name = album_text.split(' - ')[0].strip()
            return album_name
        
        # 如果没有特殊格式，直接返回
        return album_text.strip()
        
    except Exception as e:
        print(f"⚠️ 提取专辑名称失败: {e}")
        return album_text.strip()

def get_apple_music_info(url):
    """使用curl获取Apple Music页面信息"""
    try:
        # 使用curl获取页面内容
        cmd = ['curl', '-s', '-L', '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36', url]
        
        print(f"🔍 执行命令: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ curl命令执行失败: {result.stderr}")
            return None
            
        html_content = result.stdout
        
        if not html_content:
            print("❌ 获取到的HTML内容为空")
            return None
            
        print(f"✅ 成功获取HTML内容，长度: {len(html_content)} 字符")
        
        # 解析HTML内容
        return parse_apple_music_html(html_content, url)
        
    except subprocess.TimeoutExpired:
        print("❌ curl命令超时")
        return None
    except Exception as e:
        print(f"❌ 执行curl命令时发生错误: {e}")
        return None

def parse_apple_music_html(html_content, url):
    """解析Apple Music HTML内容"""
    try:
        # 方法1: 从<title>标签提取
        title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            print(f"📄 页面标题: {title}")
            
            # 从标题中提取艺术家和专辑
            # 格式通常是: "专辑名 - 艺术家名 - Apple Music"
            title_parts = title.split(' - ')
            if len(title_parts) >= 2:
                album_name = title_parts[0].strip()
                artist_name = title_parts[1].strip()
                
                # 对于专辑，直接从URL中提取专辑名
                if '/album/' in url:
                    # 从URL中提取专辑名，格式: /album/专辑名/ID
                    import urllib.parse
                    url_parts = url.split('/album/')
                    if len(url_parts) >= 2:
                        album_id_part = url_parts[1].split('/')[0]  # 获取专辑名部分
                        real_album_name = urllib.parse.unquote(album_id_part)
                        print(f"🎵 从URL提取专辑名: {real_album_name}")
                    else:
                        real_album_name = extract_album_name(album_name)
                else:
                    real_album_name = extract_album_name(album_name)
                
                # 对于专辑，专辑名可能包含艺术家信息，需要进一步解析
                # 检查多种连字符类型
                has_dash = any(dash in album_name for dash in ['-', '–', '—', '−'])
                if '/album/' in url and has_dash:
                    # 专辑名格式可能是 "《XXX》- XXX的专辑"
                    # 尝试多种连字符类型进行分割
                    for dash in ['-', '–', '—', '−']:
                        if dash in album_name:
                            album_parts = album_name.split(dash)
                            if len(album_parts) >= 2:
                                artist_info = album_parts[1].strip()
                                # 从艺术家信息中提取真实艺术家名称
                                real_artist_name = extract_artist_name(artist_info)
                                break
                            else:
                                real_artist_name = extract_artist_name(artist_name)
                        else:
                            real_artist_name = extract_artist_name(artist_name)
                else:
                    # 移除"Apple Music"等后缀
                    if artist_name.endswith(' - Apple Music'):
                        artist_name = artist_name.replace(' - Apple Music', '')
                    
                    # 提取真实的艺术家名称
                    real_artist_name = extract_artist_name(artist_name)
                
                print(f"🎵 从标题提取: 专辑='{album_name}' -> 提取后='{real_album_name}', 艺术家='{artist_name}' -> 提取后='{real_artist_name}'")
                
                # 判断是否为单曲或专辑
                if '/song/' in url:
                    # 单曲：添加title字段
                    return {
                        'title': real_album_name,  # 对于单曲，album_name实际上是歌曲名
                        'album': real_album_name,
                        'artist': real_artist_name,
                        'type': 'song',
                        'source': 'title_tag'
                    }
                else:
                    # 专辑
                    return {
                        'album': real_album_name,
                        'artist': real_artist_name,
                        'type': 'album',
                        'source': 'title_tag'
                    }
        
        # 方法2: 从JSON-LD数据提取
        json_ld_match = re.search(r'<script id="schema:music-album" type="application/ld\+json">(.*?)</script>', html_content, re.DOTALL)
        if json_ld_match:
            try:
                json_data = json.loads(json_ld_match.group(1))
                print(f"📊 找到JSON-LD数据: {json_data}")
                
                if 'name' in json_data and 'byArtist' in json_data:
                    album_name = json_data['name']
                    artist_name = json_data['byArtist']['name'] if isinstance(json_data['byArtist'], dict) else json_data['byArtist']
                    
                    # 提取真实的艺术家名称和专辑名称
                    real_artist_name = extract_artist_name(artist_name)
                    real_album_name = extract_album_name(album_name)
                    print(f"🎵 从JSON-LD提取: 专辑='{album_name}' -> 提取后='{real_album_name}', 艺术家='{artist_name}' -> 提取后='{real_artist_name}'")
                    
                    # 判断是否为单曲或专辑
                    if '/song/' in url:
                        # 单曲：添加title字段
                        return {
                            'title': real_album_name,  # 对于单曲，album_name实际上是歌曲名
                            'album': real_album_name,
                            'artist': real_artist_name,
                            'type': 'song',
                            'source': 'json_ld'
                        }
                    else:
                        # 专辑
                        return {
                            'album': real_album_name,
                            'artist': real_artist_name,
                            'type': 'album',
                            'source': 'json_ld'
                        }
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON-LD解析失败: {e}")
        
        # 方法3: 从meta标签提取
        meta_artist_match = re.search(r'<meta property="music:musician" content="(.*?)"', html_content)
        meta_album_match = re.search(r'<meta property="og:title" content="(.*?)"', html_content)
        
        if meta_artist_match and meta_album_match:
            artist_name = meta_artist_match.group(1).strip()
            album_name = meta_album_match.group(1).strip()
            
            # 提取真实的艺术家名称和专辑名称
            real_artist_name = extract_artist_name(artist_name)
            real_album_name = extract_album_name(album_name)
            print(f"🎵 从meta标签提取: 专辑='{album_name}' -> 提取后='{real_album_name}', 艺术家='{artist_name}' -> 提取后='{real_artist_name}'")
            
            # 判断是否为单曲或专辑
            if '/song/' in url:
                # 单曲：添加title字段
                return {
                    'title': real_album_name,  # 对于单曲，album_name实际上是歌曲名
                    'album': real_album_name,
                    'artist': real_artist_name,
                    'type': 'song',
                    'source': 'meta_tags'
                }
            else:
                # 专辑
                return {
                    'album': real_album_name,
                    'artist': real_artist_name,
                    'type': 'album',
                    'source': 'meta_tags'
                }
        
        # 方法4: 从URL路径提取（备选方案）
        print("🔄 尝试从URL路径提取信息...")
        url_info = extract_from_url(url)
        if url_info:
            return url_info
        
        print("❌ 无法从HTML内容中提取艺术家和专辑信息")
        return None
        
    except Exception as e:
        print(f"❌ 解析HTML内容时发生错误: {e}")
        return None

def extract_from_url(url):
    """从URL路径中提取专辑信息"""
    try:
        # 匹配 /cn/album/专辑名/ID 格式
        album_match = re.search(r'/cn/album/([^/]+)/(\d+)', url)
        if album_match:
            album_slug = album_match.group(1)
            album_id = album_match.group(2)
            
            # URL解码专辑名
            try:
                decoded_album = unquote(album_slug)
                print(f"🔍 从URL提取: 专辑slug='{album_slug}', 解码后='{decoded_album}', ID={album_id}")
                
                # 转换专辑名称（使用顶部的通用函数）
                simplified_album = convert_traditional_to_simplified(decoded_album)
                print(f"🔍 专辑名称转换: '{decoded_album}' -> '{simplified_album}'")
                
                # 将slug转换为更友好的专辑名（移除.title()，对中文无效）
                album_name = simplified_album.replace('-', ' ').replace('_', ' ')
                
                return {
                    'album': album_name,
                    'artist': '未知艺术家',
                    'album_id': album_id,
                    'source': 'url_path'
                }
            except Exception as e:
                print(f"⚠️ URL解码失败: {e}")
                return None
        
        # 匹配 /cn/song/歌曲名/ID 格式
        song_match = re.search(r'/cn/song/([^/]+)/(\d+)', url)
        if song_match:
            song_slug = song_match.group(1)
            song_id = song_match.group(2)
            
            try:
                decoded_song = unquote(song_slug)
                print(f"🔍 从URL提取: 歌曲slug='{song_slug}', 解码后='{decoded_song}', ID={song_id}")
                
                # 转换歌曲名称（使用顶部的通用函数）
                simplified_song = convert_traditional_to_simplified(decoded_song)
                print(f"🔍 歌曲名称转换: '{decoded_song}' -> '{simplified_song}'")
                
                # 将slug转换为更友好的歌曲名（移除.title()，对中文无效）
                song_name = simplified_song.replace('-', ' ').replace('_', ' ')
                
                return {
                    'title': song_name,  # 添加title字段
                    'album': song_name,
                    'artist': '未知艺术家',
                    'song_id': song_id,
                    'type': 'song',
                    'source': 'url_path'
                }
            except Exception as e:
                print(f"⚠️ URL解码失败: {e}")
                return None
        
        return None
        
    except Exception as e:
        print(f"❌ 从URL提取信息时发生错误: {e}")
        return None

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("使用方法: python3 amd_getinfo.py <Apple_Music_URL>")
        print("示例: python3 amd_getinfo.py 'https://music.apple.com/cn/album/耳朵/1438734966'")
        sys.exit(1)
    
    url = sys.argv[1].strip()
    
    # 移除URL末尾的多余字符
    if url.endswith('%60%60%60'):
        url = url.replace('%60%60%60', '')
        print(f"⚠️ 检测到URL末尾有多余字符，已清理: {url}")
    
    print(f"🎵 开始提取Apple Music信息...")
    print(f"🔗 URL: {url}")
    print("-" * 60)
    
    # 获取信息
    info = get_apple_music_info(url)
    
    print("-" * 60)
    
    if info:
        print("✅ 成功提取音乐信息:")
        if 'title' in info:
            print(f"   🎵 歌曲名: {info.get('title', '未知')}")
        print(f"   🎵 专辑/歌曲: {info.get('album', '未知')}")
        print(f"   👤 艺术家: {info.get('artist', '未知')}")
        print(f"   📍 数据来源: {info.get('source', '未知')}")
        
        if 'album_id' in info:
            print(f"   🆔 专辑ID: {info['album_id']}")
        if 'song_id' in info:
            print(f"   🆔 歌曲ID: {info['song_id']}")
        if 'type' in info:
            print(f"   📝 类型: {info['type']}")
            
        # 输出为JSON格式（便于其他程序使用）
        print("\n📋 JSON格式输出:")
        print(json.dumps(info, ensure_ascii=False, indent=2))
        
    else:
        print("❌ 无法提取音乐信息")
        sys.exit(1)

if __name__ == "__main__":
    main()

