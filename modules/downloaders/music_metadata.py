#!/usr/bin/env python3
"""
音乐元数据处理模块
为下载的音乐文件添加ID3标签和封面
"""
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional, Union
import requests
from urllib.parse import urlparse
import tempfile

# 配置日志
logger = logging.getLogger(__name__)

class MusicMetadataManager:
    """音乐元数据管理器"""
    
    def __init__(self):
        self.session = requests.Session()
        # 设置User-Agent避免被网站屏蔽
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 检查可用的音频标签库
        self.available_libraries = self._check_available_libraries()
        logger.info(f"🔧 可用的音频标签库: {', '.join(self.available_libraries) if self.available_libraries else '无'}")
    
    def _check_available_libraries(self) -> list:
        """检查可用的音频标签处理库"""
        available = []
        
        # 检查 mutagen (推荐)
        try:
            import mutagen
            available.append('mutagen')
            logger.info("✅ 检测到 mutagen 库")
        except ImportError:
            logger.warning("⚠️ 未安装 mutagen 库")
        
        # 检查 eyed3 (MP3专用)
        try:
            import eyed3
            available.append('eyed3')
            logger.info("✅ 检测到 eyed3 库")
        except ImportError:
            logger.warning("⚠️ 未安装 eyed3 库")
        
        # 检查 tinytag (只读)
        try:
            import tinytag
            available.append('tinytag')
            logger.info("✅ 检测到 tinytag 库（只读）")
        except ImportError:
            logger.warning("⚠️ 未安装 tinytag 库")
        
        return available
    
    def add_metadata_to_file(
        self, 
        file_path: Union[str, Path], 
        metadata: Dict[str, str],
        cover_url: Optional[str] = None
    ) -> bool:
        """
        为音乐文件添加元数据
        
        Args:
            file_path: 音乐文件路径
            metadata: 元数据字典 {title, artist, album, album_artist, date, track_number, genre}
            cover_url: 专辑封面URL
            
        Returns:
            bool: 是否成功添加元数据
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"❌ 文件不存在: {file_path}")
            return False
        
        # 根据文件扩展名和可用库选择处理方法
        file_ext = file_path.suffix.lower()
        
        if 'mutagen' in self.available_libraries:
            return self._add_metadata_with_mutagen(file_path, metadata, cover_url)
        elif 'eyed3' in self.available_libraries and file_ext == '.mp3':
            return self._add_metadata_with_eyed3(file_path, metadata, cover_url)
        else:
            logger.warning(f"⚠️ 无可用的音频标签库处理 {file_ext} 文件")
            logger.info("💡 建议安装: pip install mutagen")
            return False
    
    def _add_metadata_with_mutagen(
        self, 
        file_path: Path, 
        metadata: Dict[str, str],
        cover_url: Optional[str] = None
    ) -> bool:
        """使用mutagen库添加元数据"""
        try:
            from mutagen import File
            from mutagen.id3 import ID3NoHeaderError, ID3, TIT2, TPE1, TALB, TPE2, TDRC, TRCK, TCON, APIC
            from mutagen.flac import FLAC
            
            logger.info(f"🎵 使用mutagen为文件添加元数据: {file_path.name}")
            
            # 尝试加载音频文件
            audio_file = File(str(file_path))
            
            if audio_file is None:
                logger.error(f"❌ mutagen无法识别音频文件: {file_path}")
                return False
            
            file_ext = file_path.suffix.lower()
            
            if file_ext == '.mp3':
                return self._add_metadata_mp3_mutagen(file_path, metadata, cover_url)
            elif file_ext == '.flac':
                return self._add_metadata_flac_mutagen(file_path, metadata, cover_url)
            else:
                logger.warning(f"⚠️ mutagen暂不支持处理 {file_ext} 文件的元数据")
                return False
                
        except ImportError:
            logger.error("❌ mutagen库导入失败")
            return False
        except Exception as e:
            logger.error(f"❌ mutagen处理文件时出错: {e}")
            return False
    
    def _add_metadata_mp3_mutagen(
        self, 
        file_path: Path, 
        metadata: Dict[str, str],
        cover_url: Optional[str] = None
    ) -> bool:
        """使用mutagen为MP3文件添加ID3标签"""
        try:
            from mutagen.id3 import ID3NoHeaderError, ID3, TIT2, TPE1, TALB, TPE2, TDRC, TRCK, TCON, APIC
            
            # 尝试加载现有的ID3标签
            try:
                tags = ID3(str(file_path))
            except ID3NoHeaderError:
                # 如果没有ID3标签，创建新的
                tags = ID3()
            
            # 添加基本元数据
            if metadata.get('title'):
                tags[TIT2] = TIT2(encoding=3, text=metadata['title'])
                logger.debug(f"  添加标题: {metadata['title']}")
            
            if metadata.get('artist'):
                tags[TPE1] = TPE1(encoding=3, text=metadata['artist'])
                logger.debug(f"  添加艺术家: {metadata['artist']}")
            
            if metadata.get('album'):
                tags[TALB] = TALB(encoding=3, text=metadata['album'])
                logger.debug(f"  添加专辑: {metadata['album']}")
            
            if metadata.get('album_artist'):
                tags[TPE2] = TPE2(encoding=3, text=metadata['album_artist'])
                logger.debug(f"  添加专辑艺术家: {metadata['album_artist']}")
            
            # 处理时间字段：支持同时写入年份和完整日期
            if metadata.get('date'):
                # 写入年份
                try:
                    from mutagen.id3 import TYER
                    tags[TYER] = TYER(encoding=3, text=metadata['date'])
                    logger.debug(f"  添加年份(TYER): {metadata['date']}")
                except:
                    # 如果TYER不可用，使用TDRC写入年份
                    tags[TDRC] = TDRC(encoding=3, text=metadata['date'])
                    logger.debug(f"  添加年份(TDRC): {metadata['date']}")
            
            if metadata.get('releasetime'):
                # 写入完整发布时间 (录音时间)
                tags[TDRC] = TDRC(encoding=3, text=metadata['releasetime'])
                logger.debug(f"  添加录音时间(TDRC): {metadata['releasetime']}")
            
            if metadata.get('track_number'):
                tags[TRCK] = TRCK(encoding=3, text=str(metadata['track_number']))
                logger.debug(f"  添加曲目编号: {metadata['track_number']}")
            
            if metadata.get('genre'):
                tags[TCON] = TCON(encoding=3, text=metadata['genre'])
                logger.debug(f"  添加流派: {metadata['genre']}")
            
            # 添加光盘编号
            if metadata.get('disc_number'):
                try:
                    from mutagen.id3 import TPOS
                    disc_number = str(metadata['disc_number'])
                    tpos_value = f"{disc_number}/1"
                    tags[TPOS] = TPOS(encoding=3, text=tpos_value)
                    logger.debug(f"  添加光盘编号: {tpos_value}")
                except Exception as e:
                    logger.warning(f"⚠️ 添加光盘编号失败: {e}")
            
            # 添加封面
            if cover_url:
                cover_data = self._download_cover_image(cover_url)
                if cover_data:
                    tags[APIC] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,  # 封面图片
                        desc='Cover',
                        data=cover_data
                    )
                    logger.debug("  添加专辑封面")
            
            # 保存标签
            tags.save(str(file_path))
            logger.info(f"✅ 成功为MP3文件添加元数据: {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 为MP3文件添加元数据失败: {e}")
            return False
    
    def _add_metadata_flac_mutagen(
        self, 
        file_path: Path, 
        metadata: Dict[str, str],
        cover_url: Optional[str] = None
    ) -> bool:
        """使用mutagen为FLAC文件添加Vorbis Comment标签"""
        try:
            from mutagen.flac import FLAC, Picture
            
            audio_file = FLAC(str(file_path))
            
            # 添加基本元数据
            if metadata.get('title'):
                audio_file['TITLE'] = metadata['title']
                logger.debug(f"  添加标题: {metadata['title']}")
            
            if metadata.get('artist'):
                audio_file['ARTIST'] = metadata['artist']
                logger.debug(f"  添加艺术家: {metadata['artist']}")
            
            if metadata.get('album'):
                audio_file['ALBUM'] = metadata['album']
                logger.debug(f"  添加专辑: {metadata['album']}")
            
            if metadata.get('album_artist'):
                audio_file['ALBUMARTIST'] = metadata['album_artist']
                logger.debug(f"  添加专辑艺术家: {metadata['album_artist']}")
            
            # 处理时间字段：支持同时写入年份和完整日期
            if metadata.get('date'):
                # 写入年份
                audio_file['DATE'] = metadata['date']
                logger.debug(f"  添加年份(DATE): {metadata['date']}")
            
            if metadata.get('releasetime'):
                # 写入完整发布时间 (录音时间)
                audio_file['RELEASETIME'] = metadata['releasetime']
                # 兼容字段
                audio_file['RELEASEDATE'] = metadata['releasetime']
                logger.debug(f"  添加录音时间(RELEASETIME): {metadata['releasetime']}")
            
            if metadata.get('track_number'):
                audio_file['TRACKNUMBER'] = str(metadata['track_number'])
                logger.debug(f"  添加曲目编号: {metadata['track_number']}")
            
            if metadata.get('genre'):
                audio_file['GENRE'] = metadata['genre']
                logger.debug(f"  添加流派: {metadata['genre']}")
            
            # 添加光盘编号
            if metadata.get('disc_number'):
                disc_number = str(metadata['disc_number'])
                audio_file['DISCNUMBER'] = disc_number
                audio_file['DISCTOTAL'] = '1'
                audio_file['TOTALDISCS'] = '1'
                # 额外兼容字段
                audio_file['DISC'] = disc_number
                audio_file['PART'] = disc_number
                audio_file['PARTOFSET'] = f"{disc_number}/1"
                audio_file['PART_OF_SET'] = f"{disc_number}/1"
                logger.debug(f"  添加光盘编号: {disc_number}")
            
            # 添加封面
            if cover_url:
                cover_data = self._download_cover_image(cover_url)
                if cover_data:
                    picture = Picture()
                    picture.type = 3  # 封面图片
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Cover'
                    picture.data = cover_data
                    audio_file.clear_pictures()
                    audio_file.add_picture(picture)
                    logger.debug("  添加专辑封面")
            
            # 保存标签
            audio_file.save()
            logger.info(f"✅ 成功为FLAC文件添加元数据: {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 为FLAC文件添加元数据失败: {e}")
            return False
    
    def _add_metadata_with_eyed3(
        self, 
        file_path: Path, 
        metadata: Dict[str, str],
        cover_url: Optional[str] = None
    ) -> bool:
        """使用eyed3库为MP3文件添加元数据（备用方案）"""
        try:
            import eyed3
            
            logger.info(f"🎵 使用eyed3为MP3文件添加元数据: {file_path.name}")
            
            # 加载音频文件
            audiofile = eyed3.load(str(file_path))
            
            if audiofile is None or audiofile.tag is None:
                # 如果没有标签，初始化一个
                audiofile.initTag()
            
            # 添加基本元数据
            if metadata.get('title'):
                audiofile.tag.title = metadata['title']
                logger.debug(f"  添加标题: {metadata['title']}")
            
            if metadata.get('artist'):
                audiofile.tag.artist = metadata['artist']
                logger.debug(f"  添加艺术家: {metadata['artist']}")
            
            if metadata.get('album'):
                audiofile.tag.album = metadata['album']
                logger.debug(f"  添加专辑: {metadata['album']}")
            
            if metadata.get('album_artist'):
                audiofile.tag.album_artist = metadata['album_artist']
                logger.debug(f"  添加专辑艺术家: {metadata['album_artist']}")
            
            if metadata.get('date'):
                try:
                    year = int(metadata['date'][:4])
                    audiofile.tag.recording_date = year
                    logger.debug(f"  添加年份: {year}")
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ 无法解析年份: {metadata['date']}")
            
            if metadata.get('track_number'):
                try:
                    track_num = int(metadata['track_number'])
                    audiofile.tag.track_num = track_num
                    logger.debug(f"  添加曲目编号: {track_num}")
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ 无法解析曲目编号: {metadata['track_number']}")
            
            if metadata.get('genre'):
                audiofile.tag.genre = metadata['genre']
                logger.debug(f"  添加流派: {metadata['genre']}")
            
            # 添加封面
            if cover_url:
                cover_data = self._download_cover_image(cover_url)
                if cover_data:
                    audiofile.tag.images.set(3, cover_data, "image/jpeg", "Cover")
                    logger.debug("  添加专辑封面")
            
            # 保存标签
            audiofile.tag.save()
            logger.info(f"✅ 成功为MP3文件添加元数据: {file_path.name}")
            return True
            
        except ImportError:
            logger.error("❌ eyed3库导入失败")
            return False
        except Exception as e:
            logger.error(f"❌ eyed3处理文件时出错: {e}")
            return False
    
    def _download_cover_image(self, cover_url: str) -> Optional[bytes]:
        """下载专辑封面图片"""
        try:
            if not cover_url:
                return None
            
            logger.debug(f"🖼️ 下载专辑封面: {cover_url}")
            
            response = self.session.get(cover_url, timeout=30)
            response.raise_for_status()
            
            # 检查内容类型
            content_type = response.headers.get('content-type', '').lower()
            if not any(img_type in content_type for img_type in ['image/jpeg', 'image/jpg', 'image/png']):
                logger.warning(f"⚠️ 不支持的图片格式: {content_type}")
                return None
            
            image_data = response.content
            
            # 检查图片大小（限制为5MB）
            if len(image_data) > 5 * 1024 * 1024:
                logger.warning("⚠️ 专辑封面过大，跳过添加")
                return None
            
            logger.debug(f"✅ 成功下载专辑封面: {len(image_data)} 字节")
            return image_data
            
        except Exception as e:
            logger.warning(f"⚠️ 下载专辑封面失败: {e}")
            return None
    
    def get_file_metadata(self, file_path: Union[str, Path]) -> Optional[Dict[str, str]]:
        """读取音乐文件的现有元数据"""
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"❌ 文件不存在: {file_path}")
            return None
        
        try:
            if 'mutagen' in self.available_libraries:
                return self._get_metadata_with_mutagen(file_path)
            elif 'tinytag' in self.available_libraries:
                return self._get_metadata_with_tinytag(file_path)
            else:
                logger.warning("⚠️ 无可用的音频标签读取库")
                return None
                
        except Exception as e:
            logger.error(f"❌ 读取文件元数据失败: {e}")
            return None
    
    def _get_metadata_with_mutagen(self, file_path: Path) -> Optional[Dict[str, str]]:
        """使用mutagen读取元数据"""
        try:
            from mutagen import File
            
            audio_file = File(str(file_path))
            if audio_file is None:
                return None
            
            metadata = {}
            
            # 根据文件类型读取不同的标签
            if hasattr(audio_file, 'tags') and audio_file.tags:
                tags = audio_file.tags
                
                # 尝试读取常见的标签字段
                for key, mutagen_keys in [
                    ('title', ['TIT2', 'TITLE']),
                    ('artist', ['TPE1', 'ARTIST']),
                    ('album', ['TALB', 'ALBUM']),
                    ('album_artist', ['TPE2', 'ALBUMARTIST']),
                    ('date', ['TDRC', 'DATE']),
                    ('track_number', ['TRCK', 'TRACKNUMBER']),
                    ('genre', ['TCON', 'GENRE'])
                ]:
                    for mutagen_key in mutagen_keys:
                        if mutagen_key in tags:
                            value = tags[mutagen_key]
                            if hasattr(value, 'text'):
                                metadata[key] = str(value.text[0]) if value.text else ''
                            else:
                                metadata[key] = str(value[0]) if isinstance(value, list) else str(value)
                            break
            
            return metadata if metadata else None
            
        except Exception as e:
            logger.error(f"❌ mutagen读取元数据失败: {e}")
            return None
    
    def _get_metadata_with_tinytag(self, file_path: Path) -> Optional[Dict[str, str]]:
        """使用tinytag读取元数据"""
        try:
            from tinytag import TinyTag
            
            tag = TinyTag.get(str(file_path))
            
            metadata = {
                'title': tag.title or '',
                'artist': tag.artist or '',
                'album': tag.album or '',
                'album_artist': tag.albumartist or '',
                'date': str(tag.year) if tag.year else '',
                'track_number': str(tag.track) if tag.track else '',
                'genre': tag.genre or ''
            }
            
            return metadata if any(metadata.values()) else None
            
        except Exception as e:
            logger.error(f"❌ tinytag读取元数据失败: {e}")
            return None

def install_required_libraries():
    """安装音频元数据处理所需的库"""
    import subprocess
    
    print("🔧 安装音频元数据处理库...")
    
    libraries = ['mutagen', 'eyed3', 'tinytag']
    
    for lib in libraries:
        try:
            print(f"📦 安装 {lib}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', lib])
            print(f"✅ {lib} 安装成功")
        except subprocess.CalledProcessError as e:
            print(f"❌ {lib} 安装失败: {e}")
        except Exception as e:
            print(f"❌ 安装 {lib} 时出错: {e}")

if __name__ == "__main__":
    # 测试模块
    logging.basicConfig(level=logging.DEBUG)
    
    manager = MusicMetadataManager()
    
    # 示例元数据
    test_metadata = {
        'title': '测试歌曲',
        'artist': '测试艺术家',
        'album': '测试专辑',
        'album_artist': '测试专辑艺术家',
        'date': '2024',
        'track_number': '1',
        'genre': '流行'
    }
    
    print("🎵 音乐元数据管理器测试")
    print(f"可用库: {manager.available_libraries}")
    
    if not manager.available_libraries:
        print("⚠️ 没有可用的音频标签库")
        print("💡 运行以下命令安装:")
        print("pip install mutagen eyed3 tinytag")
    else:
        print("✅ 元数据管理器初始化成功")

